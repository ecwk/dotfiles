#!/usr/bin/python
"""Glass Dashboard: independent bottom-layer GTK4 surfaces for Hyprland."""
from __future__ import annotations
import os
import sys
import json
import signal
import shutil
import subprocess
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import gi
# Layer shell must load before GTK initializes Wayland (launcher also uses LD_PRELOAD).
gi.require_version('Gtk4LayerShell','1.0')
from gi.repository import Gtk4LayerShell as Layer
gi.require_version('Gtk','4.0')
gi.require_version('Gdk','4.0')
gi.require_version('Vte','3.91')
gi.require_version('GLibUnix','2.0')
from gi.repository import Gtk,Gdk,Gio,GLib,GLibUnix,Pango,Vte
from core import ROOT,STATE,TITLES,Store,academic,clamp_rect,default_layout,minimum_for,command,read_json,write_json,search_places,weather_for,conditions
from services import Jobs,Spectrum,Location,media_snapshot,media_action,artwork_bytes

def box(vertical=True,spacing=8): return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,spacing=spacing)
def label(text='',css=None,wrap=False):
    w=Gtk.Label(label=text,xalign=0,wrap=wrap)
    w.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    if not wrap: w.set_ellipsize(Pango.EllipsizeMode.END)
    if css: w.add_css_class(css)
    return w
def button(text,callback,css=None):
    w=Gtk.Button(label=text)
    w.connect('clicked',lambda *_:callback())
    if css: w.add_css_class(css)
    return w
def clear(container):
    while container.get_first_child(): container.remove(container.get_first_child())
def colour(text):
    c=Gdk.RGBA(); c.parse(text); return c

def repeat(seconds,fn):
    def tick(): fn(); return True
    return GLib.timeout_add_seconds(seconds,tick)

class Panel(Gtk.ApplicationWindow):
    def __init__(self,app,key):
        super().__init__(application=app,title='Glass · '+TITLES[key])
        self.app,self.key=app,key
        Layer.init_for_window(self)
        Layer.set_namespace(self,'glass-dashboard-'+key)
        Layer.set_layer(self,Layer.Layer.BOTTOM)
        Layer.set_exclusive_zone(self,-1)
        Layer.set_keyboard_mode(self,Layer.KeyboardMode.ON_DEMAND)
        Layer.set_anchor(self,Layer.Edge.LEFT,True)
        Layer.set_anchor(self,Layer.Edge.TOP,True)
        self.root=box(spacing=10); self.root.add_css_class('glass')
        self.root.set_overflow(Gtk.Overflow.HIDDEN)
        if key=='controls': self.root.add_css_class('dock')
        self.content=box(); self.content.set_vexpand(True)
        self.root.append(self.content)
        self.overlay=Gtk.Overlay(); self.overlay.set_child(self.root)
        self.move_handle=label('⠿','handle')
        self.move_handle.set_halign(Gtk.Align.CENTER); self.move_handle.set_valign(Gtk.Align.START)
        self.move_handle.set_size_request(42,18); self.move_handle.set_tooltip_text('Move widget')
        self.resize=label('◢','handle')
        self.resize.set_halign(Gtk.Align.END); self.resize.set_valign(Gtk.Align.END)
        self.resize.set_size_request(22,22); self.resize.set_tooltip_text('Resize widget')
        self.overlay.add_overlay(self.move_handle); self.overlay.add_overlay(self.resize)
        self.set_child(self.overlay)
        for widget,mode in [(self.move_handle,'move'),(self.resize,'resize')]:
            gesture=Gtk.GestureDrag()
            gesture.connect('drag-begin',self.begin,mode)
            gesture.connect('drag-update',self.drag,mode)
            gesture.connect('drag-end',self.drag_end,mode)
            widget.add_controller(gesture)
        self.connect('close-request',self.close_requested)
        self.edit(False)
    def close_requested(self,*_):
        # Compositor close must not destroy one panel silently.
        return True
    def begin(self,gesture,x,y,mode):
        self.origin=dict(self.app.layout[self.key])
        if not self.app.editing:
            gesture.set_state(Gtk.EventSequenceState.DENIED); return
        try: self.pointer_origin=json.loads(command(['hyprctl','cursorpos','-j'],timeout=1))
        except Exception: self.pointer_origin=None
    def drag(self,gesture,dx,dy,mode):
        if not self.app.editing: return
        r=dict(self.origin)
        # Surface-local gesture coordinates shift while the layer window moves.
        # Hyprland's global pointer coordinates keep dragging stable.
        if self.pointer_origin is not None:
            try:
                pointer=json.loads(command(['hyprctl','cursorpos','-j'],timeout=1))
                dx=pointer['x']-self.pointer_origin['x']; dy=pointer['y']-self.pointer_origin['y']
            except Exception: pass
        if mode=='move': r['x']+=int(dx); r['y']+=int(dy)
        else: r['w']+=int(dx); r['h']+=int(dy)
        self.app.layout[self.key]=clamp_rect(r,self.app.width,self.app.height,minimum_for(self.key))
        self.place()
    def drag_end(self,gesture,dx,dy,mode):
        self.drag(gesture,dx,dy,mode)
        self.app.save_layout()
    def edit(self,enabled):
        self.resize.set_visible(enabled)
        self.move_handle.set_visible(enabled)
        self.move_handle.set_cursor_from_name('move')
        self.resize.set_cursor_from_name('se-resize')
        if enabled: self.root.add_css_class('editing')
        else: self.root.remove_css_class('editing')
    def place(self):
        r=self.app.layout[self.key]
        Layer.set_monitor(self,self.app.monitor)
        Layer.set_margin(self,Layer.Edge.LEFT,r['x'])
        Layer.set_margin(self,Layer.Edge.TOP,r['y'])
        self.set_default_size(r['w'],r['h'])
        self.set_visible(r['visible'] or self.key=='controls')

class TerminalWidget:
    def __init__(self,app,panel,program='btop'):
        self.program=program
        self.app=app; self.panel=panel; self.pid=None; self.starting=False; self.pending=False; self.closed=False
        self.retry_source=0; self.failures=0; self.started_at=0
        self.status=label('','error',True); self.status.set_visible(False)
        panel.content.append(self.status)
        self.terminal=Vte.Terminal()
        self.terminal.set_font(Pango.FontDescription('monospace 8'))
        self.terminal.set_clear_background(False)
        self.terminal.set_scrollback_lines(200)
        self.terminal.set_vexpand(True); self.terminal.set_hexpand(True)
        columns,rows={'btop':(80,24),'bluetui':(32,20),'fastfetch':(52,9)}[program]
        self.terminal.set_size(columns,rows)
        self.terminal.connect('child-exited',self.exited)
        panel.content.append(self.terminal)
        self.restart()
    def cancel_retry(self):
        if self.retry_source:
            GLib.source_remove(self.retry_source); self.retry_source=0
    def schedule(self,delay):
        if self.closed or self.retry_source: return
        def retry():
            self.retry_source=0
            self.launch()
            return False
        self.retry_source=GLib.timeout_add(delay,retry)
    def restart(self):
        if self.closed or self.starting: return
        self.cancel_retry()
        self.failures=0
        if self.pid:
            self.pending=True
            try: os.kill(self.pid,signal.SIGTERM)
            except ProcessLookupError: self.pid=None; self.pending=False; self.launch()
            else: GLib.timeout_add(800,self.force_stop,self.pid)
        else: self.launch()
    def force_stop(self,pid):
        if self.pid==pid:
            try: os.kill(pid,signal.SIGKILL)
            except ProcessLookupError: pass
        return False
    def launch(self):
        if self.closed or self.starting or self.pid: return
        self.starting=True
        self.terminal.reset(True,True)
        # Keep the terminal background transparent while restoring its normal ANSI palette.
        self.terminal.set_colors(colour('#e8e8e8'),colour('rgba(0,0,0,0)'),[])
        filename={'btop':'btop.conf','bluetui':'bluetui.toml','fastfetch':'fastfetch.jsonc'}[self.program]
        config=STATE/filename; config.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/'data'/filename,config)
        self.status.set_visible(False)
        argv={
            'btop':['/usr/bin/btop','--config',str(config)],
            'bluetui':['/usr/bin/bluetui','-c',str(config)],
            'fastfetch':['/usr/bin/fastfetch','--config',str(config),'--detect-version','true','--watch','30'],
        }[self.program]
        env=[f'{k}={v}' for k,v in os.environ.items() if k not in ('TERM','LD_PRELOAD')]+['TERM=xterm-256color']
        self.terminal.spawn_async(Vte.PtyFlags.DEFAULT,str(STATE),argv,env,GLib.SpawnFlags(Vte.SPAWN_NO_SYSTEMD_SCOPE),None,None,-1,None,self.spawned,None)
    def spawned(self,terminal,pid,error,data):
        self.starting=False
        if error:
            if self.closed: return
            self.failures+=1
            self.status.set_text(self.program+' unavailable · retrying automatically')
            self.status.set_tooltip_text(str(error)); self.status.set_visible(True)
            self.schedule(min(30000,1000*2**min(self.failures-1,5)))
            return
        self.pid=pid; self.started_at=time.monotonic()
        if self.closed: self.stop()
    def exited(self,terminal,status):
        self.pid=None
        if self.closed: return
        if time.monotonic()-self.started_at>10: self.failures=0
        else: self.failures+=1
        delay=100 if self.pending else min(5000,350*2**min(max(0,self.failures-1),4))
        self.pending=False
        self.schedule(delay)
    def stop(self):
        self.closed=True
        self.cancel_retry()
        if self.pid:
            try: os.kill(self.pid,signal.SIGKILL)
            except ProcessLookupError: pass

class MusicWidget:
    def __init__(self,app,panel):
        self.app=app; self.player=None; self.players=[]; self.art_url=''; self.props={}
        self.selector=Gtk.DropDown.new_from_strings(['Automatic'])
        self.selector.set_size_request(110,-1)
        self.selector.connect('notify::selected',lambda *_:self.refresh())
        row=box(False,16)
        self.art=Gtk.Picture(); self.art.set_size_request(112,112); self.art.set_can_shrink(True); self.art.set_content_fit(Gtk.ContentFit.COVER); self.art.add_css_class('art')
        row.append(self.art)
        info=box(spacing=7); info.set_hexpand(True)
        self.title=label('Nothing playing','track'); self.artist=label('Open your favourite music player','subtitle')
        info.append(self.title); info.append(self.artist)
        controls=box(False,8)
        self.previous=button('',lambda:self.action('Previous'))
        self.previous.set_icon_name('media-skip-backward-symbolic'); self.previous.set_tooltip_text('Previous track')
        self.play=button('',lambda:self.action('Pause' if self.props.get('PlaybackStatus')=='Playing' else 'Play'),'primary')
        self.play.set_icon_name('media-playback-start-symbolic'); self.play.set_tooltip_text('Play / pause')
        self.next=button('',lambda:self.action('Next'))
        self.next.set_icon_name('media-skip-forward-symbolic'); self.next.set_tooltip_text('Next track')
        for b in (self.previous,self.play,self.next): controls.append(b); b.set_sensitive(False)
        self.elapsed=label('','subtitle'); controls.append(self.elapsed)
        info.append(controls)
        self.progress=Gtk.ProgressBar(); info.append(self.progress)
        row.append(info); panel.content.append(row)
        self.refresh(); repeat(2,self.refresh)
    def refresh(self):
        i=self.selector.get_selected()
        preferred=self.players[i-1] if 0<i<=len(self.players) else ''
        self.app.jobs.run('music',lambda:media_snapshot(preferred),self.update)
    def update(self,result,error):
        if error: self.title.set_text('Player connection unavailable'); return
        players,self.player,props=result
        if players!=self.players:
            old=self.players[self.selector.get_selected()-1] if 0<self.selector.get_selected()<=len(self.players) else ''
            self.players=players
            self.selector.set_model(Gtk.StringList.new(['Automatic']+[p.removeprefix('org.mpris.MediaPlayer2.') for p in players]))
            self.selector.set_selected(players.index(old)+1 if old in players else 0)
        props=props or {}; self.props=props
        meta=props.get('Metadata',{})
        self.title.set_text(meta.get('xesam:title','Nothing playing'))
        self.artist.set_text(' · '.join(meta.get('xesam:artist',[])) or ('Open your favourite music player' if not self.player else self.player.removeprefix('org.mpris.MediaPlayer2.')))
        playing=props.get('PlaybackStatus')=='Playing'
        self.play.set_icon_name('media-playback-pause-symbolic' if playing else 'media-playback-start-symbolic')
        control=props.get('CanControl',False)
        self.play.set_sensitive(control and props.get('CanPause' if playing else 'CanPlay',False))
        self.previous.set_sensitive(control and props.get('CanGoPrevious',False))
        self.next.set_sensitive(control and props.get('CanGoNext',False))
        length=max(0,meta.get('mpris:length',0)); pos=max(0,props.get('Position',0))
        self.progress.set_fraction(min(1,pos/length) if length else 0)
        self.elapsed.set_text(f'{int(pos/60_000_000)}:{int(pos/1_000_000)%60:02d} / {int(length/60_000_000)}:{int(length/1_000_000)%60:02d}' if length else '')
        url=meta.get('mpris:artUrl','') if meta.get('xesam:title') else ''
        if url!=self.art_url:
            self.art_url=url; self.art.set_paintable(None)
            if url:
                self.app.jobs.run('art-'+str(hash(url)),lambda:artwork_bytes(url),lambda data,err:self.set_art(url,data,err))
    def set_art(self,url,data,error):
        if url!=self.art_url or error: return
        try: self.art.set_paintable(Gdk.Texture.new_from_bytes(GLib.Bytes.new(data)))
        except GLib.Error: pass
    def action(self,method):
        if self.player:
            player=self.player
            self.app.jobs.run('music-action',lambda:media_action(player,method),lambda v,e:self.refresh())

class WeatherWidget:
    def __init__(self,app,panel):
        self.app=app; self.panel=panel; self.generation=0; self.picker=None
        self.location=app.store.data.get('location')
        if not isinstance(self.location,dict) or not all(k in self.location for k in ('name','latitude','longitude')): self.location=None
        self.portal=Location(self.located,self.location_status)
        self.name=label('Your local forecast','subtitle'); panel.content.append(self.name)
        self.current=label('—°','big'); panel.content.append(self.current)
        self.description=label('Choose a location to get started','subtitle'); panel.content.append(self.description)
        self.forecast=label('','subtitle',True); panel.content.append(self.forecast)
        self.status=label('','subtitle',True); panel.content.append(self.status)
        row=box(False,5)
        row.append(button('Choose location',self.choose))
        row.append(button('↻',self.retry)); panel.content.append(row)
        attribution=Gtk.LinkButton(uri='https://open-meteo.com/',label='Open-Meteo · GeoNames'); attribution.add_css_class('flat'); panel.content.append(attribution)
        self.cache=read_json(STATE/'weather.json',{})
        if not isinstance(self.cache,dict): self.cache={}
        if self.location and self.cache.get('location')==self.location: self.render(self.cache.get('data',{}),self.cache.get('fetched',0))
        self.refresh(); repeat(900,self.refresh)
        if app.store.data.get('automatic_location',True): GLib.idle_add(self.auto_start)
    def location_status(self,text,detail=''):
        if detail: print('Location portal:',detail,flush=True)
        if 'permission was not granted' in detail:
            self.app.store.data['automatic_location']=False
            self.app.store.save()
        self.status.set_text(text); self.status.set_tooltip_text(detail or text)
    def auto_start(self):
        self.app.store.data['automatic_location']=True; self.app.store.save()
        self.portal.start(); return False
    def located(self,location):
        self.set_location(location,True)
    def set_location(self,location,automatic=False):
        if not automatic: self.portal.close()
        self.generation+=1
        self.location=location
        self.app.store.data.update(location=location,automatic_location=automatic)
        self.app.store.save()
        self.current.set_text('—°'); self.description.set_text('Loading forecast…'); self.forecast.set_text('')
        if self.picker: self.picker.close(); self.picker=None
        self.refresh()
    def retry(self):
        self.refresh()
        if self.app.store.data.get('automatic_location',True): self.portal.start()
    def refresh(self):
        if not self.location: return
        location=dict(self.location); gen=self.generation
        self.name.set_text(location['name'])
        self.app.jobs.run('weather-'+str(gen),lambda:weather_for(location),lambda data,error:self.received(gen,location,data,error))
    def received(self,gen,location,data,error):
        if gen!=self.generation: return
        if error:
            age=self.cache.get('fetched',0) if self.cache.get('location')==location else 0
            self.status.set_text('Offline · '+self.updated_text(age) if age else 'Forecast unavailable · Retry')
            self.status.set_tooltip_text(error); return
        fetched=time.time()
        self.cache={'location':location,'data':data,'fetched':fetched}
        write_json(STATE/'weather.json',self.cache)
        self.render(data,fetched)
    def updated_text(self,stamp):
        if not stamp: return 'No cached forecast'
        return 'Updated '+datetime.fromtimestamp(stamp).astimezone().strftime('%d %b, %H:%M')
    def render(self,data,fetched):
        try:
            current=data['current']; daily=data['daily']
            icon,description=conditions(current['weather_code'])
            self.name.set_text(self.location['name'])
            self.current.set_text(f"{icon}  {current['temperature_2m']:.0f}°")
            self.description.set_text(f"{description} · Humidity {current['relative_humidity_2m']}%")
            self.forecast.set_text('   '.join(f"{datetime.fromisoformat(d).strftime('%a')} {hi:.0f}°/{lo:.0f}°" for d,hi,lo in zip(daily['time'][1:4],daily['temperature_2m_max'][1:4],daily['temperature_2m_min'][1:4])))
            self.status.set_text(self.updated_text(fetched))
        except (KeyError,TypeError,ValueError): self.status.set_text('Forecast data unavailable · Retry')
    def choose(self):
        if self.picker: self.picker.present(); return
        win=Gtk.Window(application=self.app,title='Choose weather location',default_width=420,default_height=370)
        self.picker=win
        win.connect('close-request',lambda *_:setattr(self,'picker',None) or False)
        root=box(spacing=12); root.add_css_class('glass'); win.set_child(root)
        root.append(label('Choose your weather location','track'))
        root.append(label('Search a city or area. Your selection stays on this device.','subtitle',True))
        entry=Gtk.SearchEntry(placeholder_text='Singapore, Kent Ridge, Tokyo…'); root.append(entry)
        message=label('Type a place and press Enter','subtitle',True); root.append(message)
        results=box(spacing=6); scroll=Gtk.ScrolledWindow(vexpand=True); scroll.set_child(results); root.append(scroll)
        search_id=[0]
        def search(*_):
            search_id[0]+=1; token=search_id[0]; clear(results); message.set_text('Searching…')
            def done(places,error):
                if token!=search_id[0] or self.picker is not win: return
                message.set_text('Search unavailable · Try again' if error else ('Select a matching place' if places else 'No matches · Try a nearby city'))
                for p in places or []:
                    name=', '.join(dict.fromkeys(x for x in (p['name'],p.get('admin1'),p.get('country')) if x))
                    loc={'name':p['name'],'latitude':p['latitude'],'longitude':p['longitude']}
                    b=button(name,lambda loc=loc:self.set_location(loc)); b.set_tooltip_text(name); results.append(b)
            query=entry.get_text()
            self.app.jobs.run('place-'+str(token),lambda:search_places(query),done)
        entry.connect('activate',search)
        actions=box(False,8); actions.append(button('Search',search)); actions.append(button('Use my location',lambda:(win.close(),self.auto_start())))
        root.append(actions)
        root.append(label('Automatic mode requests approximate location. Coordinates are sent to Open-Meteo for weather.','subtitle',True))
        win.present()

class Dashboard(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='io.github.ecwk.GlassDashboard',flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.ready=False; self.editing=False; self.panels={}; self.jobs=Jobs(); self.store=Store(); self.spectrum=Spectrum()
        self.connect('activate',self.activate)
        self.connect('command-line',self.command_line)
        self.connect('shutdown',self.shutdown)
    def command_line(self,app,cmd):
        args=cmd.get_arguments()[1:]
        if '--quit' in args: self.quit(); return 0
        self.activate(self)
        if '--edit' in args: self.toggle_edit()
        if '--reset-layout' in args: self.reset_layout()
        if '--restart-terminal' in args: self.terminal.restart()
        if '--restart-bluetooth' in args: self.bluetooth.restart()
        if '--export-layout' in args: self.export_layout()
        if '--smoke-test' in args:
            GLib.timeout_add_seconds(8,lambda:(self.quit(),False)[1])
        return 0
    def activate(self,*_):
        if self.ready: return
        if not Layer.is_supported():
            raise RuntimeError('Wayland layer-shell unavailable; use the included launcher in your Hyprland session')
        self.ready=True
        STATE.mkdir(parents=True,exist_ok=True)
        provider=Gtk.CssProvider(); provider.load_from_path(str(ROOT/'style.css'))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        settings=Gtk.Settings.get_default(); settings.set_property('gtk-interface-color-scheme',Gtk.InterfaceColorScheme.DARK)
        self.monitors=Gdk.Display.get_default().get_monitors()
        self.monitors.connect('items-changed',lambda *_:self.monitor_changed())
        self.select_monitor()
        for key in TITLES: self.panels[key]=Panel(self,key)
        self.build_clock(); self.build_calendar()
        self.music=MusicWidget(self,self.panels['music'])
        self.build_spectrum()
        self.terminal=TerminalWidget(self,self.panels['btop'])
        self.weather=WeatherWidget(self,self.panels['weather'])
        self.bluetooth=TerminalWidget(self,self.panels['bluetooth'],'bluetui')
        self.system=TerminalWidget(self,self.panels['system'],'fastfetch')
        self.build_controls()
        for panel in self.panels.values(): panel.place()
        GLibUnix.signal_add(GLib.PRIORITY_DEFAULT,signal.SIGTERM,lambda:(self.quit(),False)[1])
    def select_monitor(self):
        items=[self.monitors.get_item(i) for i in range(self.monitors.get_n_items())]
        if not items: return False
        desired=self.store.data.get('monitor','eDP-1')
        self.monitor=next((m for m in items if m.get_connector()==desired),items[0])
        g=self.monitor.get_geometry(); self.width,self.height=g.width,g.height
        self.monitor_key=self.monitor.get_connector() or self.monitor.get_model() or 'default'
        self.layout=self.store.layout(self.monitor_key,self.width,self.height)
        # Geometry can change without the monitor list changing (scale / mode switches).
        if hasattr(self,'geometry_monitor'):
            try: self.geometry_monitor.disconnect(self.geometry_handler)
            except (TypeError,RuntimeError): pass
        self.geometry_monitor=self.monitor
        self.geometry_handler=self.monitor.connect('notify::geometry',lambda *_:self.monitor_changed())
        return True
    def monitor_changed(self):
        self.save_layout()
        if not self.select_monitor():
            for p in self.panels.values(): p.set_visible(False)
            return
        for panel in self.panels.values(): panel.place()
        if hasattr(self,'monitor_choice'): self.update_monitor_choices()
        self.sync_visibility()
    def save_layout(self):
        if not hasattr(self,'layout'): return
        self.store.data['layouts'][self.monitor_key]=self.layout
        self.store.save()
    def toggle_edit(self):
        self.editing=not self.editing
        for p in self.panels.values(): p.edit(self.editing)
        self.edit_button.set_icon_name('object-select-symbolic' if self.editing else 'document-edit-symbolic')
        self.edit_button.set_tooltip_text('Finish editing' if self.editing else 'Edit layout (Super + Shift + D)')
        if not self.editing: self.save_layout()
    def reset_layout(self):
        self.layout=default_layout(self.width,self.height)
        for p in self.panels.values(): p.place()
        self.save_layout()
        self.sync_visibility()
    def export_layout(self):
        layout={key:{name:(bool(value) if name=='visible' else round(value*(1440/self.width if name in ('x','w') else 900/self.height))) for name,value in rect.items()} for key,rect in self.layout.items()}
        try:
            write_json(ROOT/'data/layout.json',layout)
            self.edit_button.set_tooltip_text('Saved arrangement to data/layout.json in your Hyprland repository')
        except OSError as exc:
            self.edit_button.set_tooltip_text('Could not save layout: '+str(exc))
    def sync_visibility(self):
        if not hasattr(self,'visibility_checks'): return
        self.updating_visibility=True
        for key,check in self.visibility_checks.items(): check.set_active(self.layout[key]['visible'])
        self.updating_visibility=False
    def build_clock(self):
        panel=self.panels['clock']
        self.clock=label('','clock'); self.date=label('','subtitle'); self.term=label('','accent',True); self.year=label('','subtitle')
        for w in (self.clock,self.date,self.term,self.year): panel.content.append(w)
        def tick():
            now=datetime.now(ZoneInfo('Asia/Singapore'))
            self.clock.set_text(now.strftime('%H:%M'))
            self.date.set_text(now.strftime('%A, %d %B')+' · SGT')
            phase,year=academic(now.date()); self.term.set_text(phase); self.year.set_text(year)
        tick(); repeat(10,tick)
    def build_calendar(self):
        panel=self.panels['calendar']
        cal=Gtk.Calendar(); cal.set_hexpand(True); cal.set_vexpand(True)
        panel.content.append(cal)
        self.calendar_status=label('','subtitle',True); panel.content.append(self.calendar_status)
        def selected(*_):
            dt=cal.get_date()
            d=datetime(dt.get_year(),dt.get_month(),dt.get_day_of_month()).date()
            self.calendar_status.set_text(academic(d)[0])
        cal.connect('day-selected',selected)
        selected()
    def build_spectrum(self):
        panel=self.panels['visualiser']
        self.canvas=Gtk.DrawingArea(vexpand=True,hexpand=True)
        self.canvas.set_content_height(35)
        def draw(area,cr,w,h):
            values=self.spectrum.values; step=w/len(values)
            for i,v in enumerate(values):
                bar=max(2,v*h)
                shade=.65+.25*v
                cr.set_source_rgba(shade,shade,shade,.40+.55*v)
                cr.rectangle(i*step,h-bar,max(2,step-4),bar); cr.fill()
        self.canvas.set_draw_func(draw)
        panel.content.append(self.canvas)
        self.spectrum.start()
        self.last_spectrum=None
        self.next_spectrum_retry=0
        def tick():
            values=tuple(self.spectrum.values)
            if values!=self.last_spectrum:
                self.canvas.queue_draw(); self.last_spectrum=values
            if self.spectrum.error:
                self.canvas.set_tooltip_text(self.spectrum.error+' · retrying automatically')
                if time.monotonic()>=self.next_spectrum_retry:
                    self.next_spectrum_retry=time.monotonic()+30
                    self.spectrum.start()
            else: self.canvas.set_tooltip_text(None)
            return True
        GLib.timeout_add(50,tick)
    def build_controls(self):
        panel=self.panels['controls']
        row=box(False,8)
        self.edit_button=Gtk.Button(icon_name='document-edit-symbolic')
        self.edit_button.add_css_class('flat')
        self.edit_button.set_tooltip_text('Edit layout (Super + Shift + D)')
        self.edit_button.connect('clicked',lambda *_:self.toggle_edit())
        row.append(self.edit_button)
        menu=Gtk.MenuButton(icon_name='emblem-system-symbolic')
        menu.add_css_class('flat'); menu.set_tooltip_text('Dashboard settings'); row.append(menu)
        panel.content.append(row)
        popover=Gtk.Popover(); menu.set_popover(popover); contents=box(spacing=10); popover.set_child(contents)
        contents.append(label('Music player','heading'))
        contents.append(self.music.selector)
        contents.append(label('Display','heading'))
        self.monitor_choice=Gtk.DropDown(); self.update_monitor_choices()
        self.monitor_choice.connect('notify::selected',self.chosen_monitor); contents.append(self.monitor_choice)
        contents.append(label('Visible widgets','heading'))
        self.visibility_checks={}
        self.updating_visibility=False
        for key in TITLES:
            if key=='controls': continue
            cb=Gtk.CheckButton(label=TITLES[key].title(),active=self.layout[key]['visible'])
            self.visibility_checks[key]=cb
            def toggle(check,key=key):
                if self.updating_visibility: return
                self.layout[key]['visible']=check.get_active(); self.panels[key].place(); self.save_layout()
            cb.connect('toggled',toggle); contents.append(cb)
        contents.append(button('Save layout to repo',self.export_layout))
        contents.append(button('Reset layout',self.reset_layout))
        contents.append(button('Restart dashboard',lambda:subprocess.Popen(['systemctl','--user','restart','glass-dashboard.service'])))
    def update_monitor_choices(self):
        self.updating_monitors=True
        self.monitor_names=[self.monitors.get_item(i).get_connector() or 'Display' for i in range(self.monitors.get_n_items())]
        self.monitor_choice.set_model(Gtk.StringList.new(self.monitor_names))
        self.monitor_choice.set_selected(self.monitor_names.index(self.monitor_key) if self.monitor_key in self.monitor_names else 0)
        self.updating_monitors=False
    def chosen_monitor(self,*_):
        if self.updating_monitors: return
        i=self.monitor_choice.get_selected()
        if i>=len(self.monitor_names): return
        self.store.data['monitor']=self.monitor_names[i]; self.monitor_changed()
    def shutdown(self,*_):
        self.jobs.closed=True
        if self.ready:
            self.save_layout()
            if hasattr(self,'terminal'): self.terminal.stop()
            if hasattr(self,'bluetooth'): self.bluetooth.stop()
            if hasattr(self,'system'): self.system.stop()
            if hasattr(self,'weather'): self.weather.portal.close()
            self.spectrum.stop()

if __name__=='__main__':
    sys.exit(Dashboard().run(sys.argv))
