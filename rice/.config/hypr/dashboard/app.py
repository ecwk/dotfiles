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
import re
import gi
# Layer shell must load before GTK initializes Wayland (launcher also uses LD_PRELOAD).
gi.require_version('Gtk4LayerShell','1.0')
from gi.repository import Gtk4LayerShell as Layer
gi.require_version('Gtk','4.0')
gi.require_version('Gdk','4.0')
gi.require_version('Vte','3.91')
gi.require_version('GLibUnix','2.0')
from gi.repository import Gtk,Gdk,Gio,GLib,GLibUnix,Pango,Vte
from core import ROOT,STATE,TITLES,Store,PRESETS,command,read_json,write_json
from gpu import gpu_name
from theme import read_appearance,MODES,THEME_FILE,read_palette,css,terminal_colors,btop_theme
from music_art import ArtworkBackdrop
from services import Jobs,Spectrum,media_snapshot,media_action,artwork_bytes

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
        self.content=box(); self.content.set_vexpand(True)
        self.root.append(self.content)
        self.set_child(self.root)
        self.connect('close-request',lambda *_:True)
    def place(self):
        r=self.app.layout[self.key]
        Layer.set_monitor(self,self.app.monitor)
        Layer.set_margin(self,Layer.Edge.LEFT,r['x'])
        Layer.set_margin(self,Layer.Edge.TOP,r['y'])
        self.set_default_size(r['w'],r['h'])
        if self.key=='music' and hasattr(self.app,'music'): self.app.music.resize(r['w'],r['h'])
        self.set_visible(r['visible'])

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
        columns,rows={'btop':(80,24)}[program]
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
        self.launched_theme=btop_theme(self.app.palette) if self.program=='btop' and self.app.btop_themed() else None
        self.terminal.reset(True,True)
        # Keep the terminal background transparent while restoring its normal ANSI palette.
        self.app.color_terminal(self.terminal,self.program)
        filename={'btop':'btop.conf'}[self.program]
        config=STATE/filename; config.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/'data'/filename,config)
        if self.program=='btop' and self.app.btop_themed():
            theme_path=STATE/'walltheme.theme'
            theme_path.write_text(btop_theme(self.app.palette))
            config.write_text(config.read_text().replace('color_theme = "Default"',f'color_theme = "{theme_path}"'))
        self.status.set_visible(False)
        argv={
            'btop':['/usr/bin/btop','--config',str(config),'--themes-dir',str(STATE)],
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
        elif self.program=='btop' and self.launched_theme!=(btop_theme(self.app.palette) if self.app.btop_themed() else None):
            self.restart()
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

class FastfetchWidget:
    """Render native Fastfetch output without a watch-mode PTY scrolling its logo."""
    def __init__(self,app,panel):
        self.app=app; self.panel=panel; self.output=b''
        self.terminal=Vte.Terminal()
        self.terminal.add_css_class('fastfetch')
        self.terminal.set_font(Pango.FontDescription('monospace 8'))
        self.terminal.set_clear_background(False)
        self.terminal.set_scrollback_lines(0)
        self.terminal.set_input_enabled(False)
        self.columns=52
        self.terminal.set_size(self.columns,9)
        self.terminal.set_hexpand(True); self.terminal.set_vexpand(True)
        self.terminal.set_halign(Gtk.Align.CENTER); self.terminal.set_valign(Gtk.Align.CENTER)
        panel.content.append(self.terminal)
        # Fit the character grid inside the fixed preset panel.
        self.fit()
        self.refresh(); repeat(30,self.refresh)
    def fit(self):
        # Presets own panel bounds; fit the text within them without moving edges.
        r=self.app.layout['system']
        size=min(8, 8*(r['w']-34)/(self.columns*6), 8*(r['h']-34)/(9*13))
        self.terminal.set_font(Pango.FontDescription(f'monospace {max(4,size):.2f}'))
    def refresh(self):
        config=read_json(ROOT/'data/fastfetch.jsonc',{})
        if self.app.theme_mode!='original' and self.app.palette:
            accent=self.app.palette['accent']
            config['logo']['color']={'1':accent,'2':accent}
            config['display']['color']['keys']=accent
        # Pass a snapshot as data so an in-flight refresh cannot race a config rewrite.
        def work():
            name=gpu_name()
            if name:
                config['modules']=[m for m in config['modules'] if not (m.get('type')=='custom' and m.get('key')=='gpu')]
                for i,m in enumerate(config['modules']):
                    if m.get('type')=='gpu': config['modules'][i]={'type':'custom','key':'gpu','format':name}
            columns=max(52,22+len(name or ''))
            config_json=json.dumps(config)
            result=subprocess.run(['/usr/bin/fastfetch','--config','-',
                                   '--detect-version','true','--pipe','false'],input=config_json.encode(),capture_output=True,timeout=8)
            if result.returncode: raise RuntimeError(result.stderr.decode(errors='replace').strip())
            return result.stdout,columns
        snapshot=(self.app.theme_mode,dict(self.app.palette or {}))
        def done(output,error):
            if snapshot!=(self.app.theme_mode,self.app.palette or {}):
                self.refresh(); return
            if not error:
                output,columns=output
                if columns!=self.columns:
                    self.columns=columns; self.terminal.set_size(columns,9); self.fit()
            self.render(output,error)
        self.app.jobs.run('fastfetch',work,done)
    def render(self,output,error):
        if error:
            self.terminal.set_tooltip_text('Fastfetch refresh failed · '+error)
            return
        # Drop only the final newline before Fastfetch's closing ANSI sequences.
        # Otherwise a nine-line output scrolls a nine-row terminal and loses the logo tip.
        output=re.sub(rb'\r?\n(?=(?:\x1b\[[0-?]*[ -/]*[@-~])*$)',b'',output)
        output=output.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
        self.output=output
        self.terminal.reset(True,True)
        self.app.color_terminal(self.terminal,'fastfetch')
        self.terminal.feed(b'\x1b[2J\x1b[H'+output+b'\x1b[?25l')
        self.terminal.set_tooltip_text(None)

class MusicWidget:
    def __init__(self,app,panel):
        self.app=app; self.panel=panel; self.player=None; self.players=[]; self.art_url=''; self.props={}
        self.position=0; self.position_at=time.monotonic()
        panel.root.add_css_class('music-card')
        self.backdrop=ArtworkBackdrop()
        overlay=Gtk.Overlay(); panel.set_child(None)
        overlay.set_child(self.backdrop); overlay.add_overlay(panel.root)
        panel.set_child(overlay)
        self.body=box(spacing=5); self.body.set_vexpand(True)
        self.row=box(False,14)
        self.art=Gtk.Picture(); self.art.set_can_shrink(True); self.art.set_content_fit(Gtk.ContentFit.COVER)
        self.art_frame=Gtk.Overlay(); self.art_frame.add_css_class('art')
        self.art_frame.set_overflow(Gtk.Overflow.HIDDEN)
        self.art_spacer=Gtk.Box(width_request=48,height_request=48)
        self.art_frame.set_child(self.art_spacer); self.art_frame.add_overlay(self.art)
        self.row.append(self.art_frame)
        info=box(spacing=2); info.set_hexpand(True); info.set_valign(Gtk.Align.CENTER)
        self.title=label('Nothing playing','track'); self.artist=label('Open your favourite music player','subtitle')
        info.append(self.title); info.append(self.artist); self.row.append(info)
        self.body.append(self.row)
        self.timeline=box(False,9)
        self.elapsed=label('','subtitle'); self.remaining=label('','subtitle')
        self.progress=Gtk.ProgressBar(); self.progress.set_hexpand(True); self.progress.set_valign(Gtk.Align.CENTER)
        self.timeline.append(self.elapsed); self.timeline.append(self.progress); self.timeline.append(self.remaining)
        self.body.append(self.timeline)
        controls=box(False,54); self.controls=controls; controls.set_halign(Gtk.Align.CENTER); controls.set_vexpand(True); controls.set_valign(Gtk.Align.CENTER)
        self.previous=button('',lambda:self.action('Previous'))
        self.previous.set_icon_name('media-seek-backward-symbolic'); self.previous.set_tooltip_text('Previous track')
        self.play=button('',lambda:self.action('Pause' if self.props.get('PlaybackStatus')=='Playing' else 'Play'))
        self.play.set_icon_name('media-playback-start-symbolic'); self.play.set_tooltip_text('Play / pause')
        self.next=button('',lambda:self.action('Next'))
        self.next.set_icon_name('media-seek-forward-symbolic'); self.next.set_tooltip_text('Next track')
        for b in (self.previous,self.play,self.next):
            controls.append(b); b.set_sensitive(False); b.add_css_class('transport')
        self.body.append(controls); panel.content.append(self.body)
        self.refresh(); repeat(1,self.refresh)
        self.progress_timer=GLib.timeout_add(100,self.update_progress)
    def resize(self,width,height):
        compact=width<360; large=height>=190
        self.controls.set_spacing(20 if compact else 54)
        self.body.reorder_child_after(self.timeline,self.controls if compact else self.row)
        self.art_frame.set_visible(not compact)
        size=64 if large else 40
        self.art_spacer.set_size_request(size,size)
        self.title.set_max_width_chars(40 if not compact else 18)
        for b in (self.previous,self.next): b.get_child().set_pixel_size(36 if large else 32)
        self.play.get_child().set_pixel_size(48 if large else 40)
        self.elapsed.set_visible(not compact); self.remaining.set_visible(not compact)
    def apply_art_mode(self):
        active=self.app.store.data.get('ios_album_art',True) and self.backdrop.texture is not None
        self.backdrop.darkness=self.app.store.data.get('music_darkness',65)
        self.backdrop.enabled=active; self.backdrop.queue_draw()
        if active: self.panel.root.add_css_class('art-colors')
        else: self.panel.root.remove_css_class('art-colors')
    def refresh(self):
        preferred=self.app.store.data.get('music_player','')
        self.app.jobs.run('music',lambda:media_snapshot(preferred),self.update)
    def update(self,result,error):
        if error:
            self.update(([],None,None),None)
            self.title.set_text('Player connection unavailable'); return
        players,self.player,props=result
        self.players=players
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
        self.position=max(0,props.get('Position',0)); self.position_at=time.monotonic()
        self.update_progress()
        url=meta.get('mpris:artUrl','') if meta.get('xesam:title') else ''
        if url!=self.art_url:
            self.art_url=url; self.art.set_paintable(None)
            self.backdrop.texture=None; self.apply_art_mode()
            if url:
                self.app.jobs.run('art-'+str(hash(url)),lambda:artwork_bytes(url),lambda data,err:self.set_art(url,data,err))
    def update_progress(self):
        length=max(0,self.props.get('Metadata',{}).get('mpris:length',0))
        pos=self.position
        if self.props.get('PlaybackStatus')=='Playing':
            pos+=max(0,time.monotonic()-self.position_at)*1_000_000*self.props.get('Rate',1.0)
        pos=max(0,min(pos,length)) if length else 0
        self.progress.set_fraction(pos/length if length else 0)
        self.elapsed.set_text(f'{int(pos/60_000_000)}:{int(pos/1_000_000)%60:02d}' if length else '')
        left=max(0,length-pos)
        self.remaining.set_text(f'-{int(left/60_000_000)}:{int(left/1_000_000)%60:02d}' if length else '')
        return True
    def set_art(self,url,data,error):
        if url!=self.art_url or error: return
        try:
            texture=Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
            self.art.set_paintable(texture); self.backdrop.texture=texture
            self.apply_art_mode()
        except GLib.Error: pass
    def action(self,method):
        if self.player:
            player=self.player
            self.app.jobs.run('music-action',lambda:media_action(player,method),lambda v,e:self.refresh())

class Dashboard(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='io.github.ecwk.GlassDashboard',flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.ready=False; self.panels={}; self.jobs=Jobs(); self.store=Store(); self.spectrum=Spectrum()
        self.connect('activate',self.activate)
        self.connect('command-line',self.command_line)
        self.connect('shutdown',self.shutdown)
    def command_line(self,app,cmd):
        args=cmd.get_arguments()[1:]
        if '--quit' in args: self.quit(); return 0
        self.activate(self)
        if '--control' in args:
            try:
                request=json.loads(args[args.index('--control')+1])
                self.control(request)
                cmd.print_literal(json.dumps(self.snapshot())+'\n')
                return 0
            except (ValueError,KeyError,IndexError,TypeError,OSError) as exc:
                cmd.printerr_literal(str(exc)+'\n'); return 1
        if '--reset-layout' in args: self.reset_layout()
        if '--restart-terminal' in args: self.terminal.restart()
        if '--smoke-test' in args:
            GLib.timeout_add_seconds(8,lambda:(self.quit(),False)[1])
        return 0
    def activate(self,*_):
        if self.ready: return
        if not Layer.is_supported():
            raise RuntimeError('Wayland layer-shell unavailable; use the included launcher in your Hyprland session')
        self.ready=True
        STATE.mkdir(parents=True,exist_ok=True)
        self.theme_mode=read_appearance(self.store.data.get('theme_mode','full'))
        if self.theme_mode not in MODES: self.theme_mode='full'
        self.palette=read_palette()
        self.theme_monitor=None; self.theme_reload_source=0
        provider=Gtk.CssProvider(); provider.load_from_path(str(ROOT/'style.css'))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.theme_provider=Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),self.theme_provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+1)
        self.theme_provider.load_from_string(css(self.theme_mode,self.palette))
        self.music_provider=Gtk.CssProvider(); self.music_provider.load_from_path(str(ROOT/'music.css'))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),self.music_provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+2)
        settings=Gtk.Settings.get_default(); settings.set_property('gtk-interface-color-scheme',Gtk.InterfaceColorScheme.DARK)
        self.monitors=Gdk.Display.get_default().get_monitors()
        self.monitors.connect('items-changed',lambda *_:self.monitor_changed())
        self.select_monitor()
        for key in TITLES: self.panels[key]=Panel(self,key)
        self.music=MusicWidget(self,self.panels['music'])
        self.build_spectrum()
        self.terminal=TerminalWidget(self,self.panels['btop'])
        self.system=FastfetchWidget(self,self.panels['system'])
        self.apply_theme()
        self.watch_theme()
        self.theme_retry=repeat(10,self.watch_theme)
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
        if hasattr(self,'system'): self.system.fit()
        for panel in self.panels.values(): panel.place()
    def save_layout(self):
        if not hasattr(self,'layout'): return
        self.store.data['layouts'][self.monitor_key]=self.layout
        self.store.save()
    def select_layout(self,name):
        if name not in PRESETS: raise ValueError('Unknown layout preset')
        selections=self.store.data.setdefault('layout_presets',{})
        selections[self.monitor_key]=name
        self.layout=self.store.layout(self.monitor_key,self.width,self.height)
        self.system.fit()
        for p in self.panels.values(): p.place()
        self.save_layout()
    def reset_layout(self):
        self.select_layout('balanced-center')
    def build_spectrum(self):
        panel=self.panels['visualiser']
        self.canvas=Gtk.DrawingArea(vexpand=True,hexpand=True)
        self.canvas.set_content_height(35)
        def draw(area,cr,w,h):
            values=self.spectrum.values; step=w/len(values)
            for i,v in enumerate(values):
                bar=max(2,v*h)
                shade=.65+.25*v
                if self.theme_mode!='original' and self.palette:
                    c=colour(self.palette['accent']); cr.set_source_rgba(c.red,c.green,c.blue,.40+.55*v)
                else: cr.set_source_rgba(shade,shade,shade,.40+.55*v)
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
    def btop_themed(self):
        return self.theme_mode=='full' and bool(self.palette) and bool(self.store.data.get('theme_btop',False))
    def color_terminal(self,terminal,program):
        fg,palette=terminal_colors(self.theme_mode,self.palette,program,self.btop_themed())
        terminal.set_colors(colour(fg),colour('rgba(0,0,0,0)'),[colour(c) for c in palette])
    def apply_theme(self):
        self.theme_provider.load_from_string(css(self.theme_mode,self.palette))
        light=self.theme_mode=='full' and read_json(THEME_FILE,{}).get('mode')=='light'
        Gtk.Settings.get_default().set_property('gtk-interface-color-scheme',Gtk.InterfaceColorScheme.LIGHT if light else Gtk.InterfaceColorScheme.DARK)
        self.music.backdrop.dark_mode=not light
        self.music.backdrop.queue_draw()
        self.color_terminal(self.terminal.terminal,'btop')
        root=self.panels['btop'].root
        if self.theme_mode=='full' and not self.store.data.get('theme_btop_background',self.store.data.get('theme_btop',False)): root.add_css_class('btop-original')
        else: root.remove_css_class('btop-original')
        signature=btop_theme(self.palette) if self.btop_themed() else None
        if hasattr(self,'btop_theme_signature') and signature!=self.btop_theme_signature:
            self.terminal.restart()
        self.btop_theme_signature=signature
        self.system.refresh(); self.canvas.queue_draw()
    def watch_theme(self):
        if self.theme_monitor is not None: return
        if not THEME_FILE.parent.is_dir(): return
        try:
            self.theme_monitor=Gio.File.new_for_path(str(THEME_FILE.parent)).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES,None)
            self.theme_monitor.connect('changed',self.theme_changed)
            self.reload_theme()
        except GLib.Error: self.theme_monitor=None
    def theme_changed(self,monitor,file,other,event):
        if not any(f and f.get_basename() in ('current.json','appearance.json') for f in (file,other)): return
        if self.theme_reload_source: GLib.source_remove(self.theme_reload_source)
        self.theme_reload_source=GLib.timeout_add(150,self.reload_theme)
    def reload_theme(self):
        self.theme_reload_source=0
        palette=read_palette()
        # Keep the last valid colors across transient invalid/incomplete publications.
        mode=read_appearance(self.theme_mode)
        light=mode=='full' and read_json(THEME_FILE,{}).get('mode')=='light'
        if mode!=self.theme_mode or (palette is not None and palette!=self.palette) or self.music.backdrop.dark_mode==light:
            self.theme_mode=mode
            if palette is not None: self.palette=palette
            self.apply_theme()
        return False
    def snapshot(self):
        return dict(layout=self.store.data.get('layout_presets',{}).get(self.monitor_key,'balanced-center'),
                    layouts=[dict(id=k,title=v['title']) for k,v in PRESETS.items()],theme=self.theme_mode,themeAvailable=bool(self.palette),
                    iosAlbumArt=bool(self.store.data.get('ios_album_art',True)),
                    musicDarkness=self.store.data.get('music_darkness',65),
                    styleTui=bool(self.store.data.get('theme_btop',False)),
                    styleBackground=bool(self.store.data.get('theme_btop_background',self.store.data.get('theme_btop',False))),
                    monitor=self.monitor_key,monitors=[self.monitors.get_item(i).get_connector() for i in range(self.monitors.get_n_items())],
                    player=self.store.data.get('music_player',''),players=self.music.players,
                    widgets=[dict(id=k,title=TITLES[k].title(),visible=v['visible']) for k,v in self.layout.items()])
    def control(self,request):
        action=request.get('action','status'); value=request.get('value')
        if action=='status': return
        if action=='layout': self.select_layout(value)
        elif action=='theme':
            if value not in MODES: raise ValueError('Unknown theme mode')
            command([str(Path.home()/'.local/bin/walltheme'),'settings','--style',value])
            self.reload_theme()
        elif action in ('styleTui','styleBackground'):
            if self.theme_mode!='full': raise ValueError('Btop styling requires Full theme')
            if not isinstance(value,bool): raise ValueError('Expected boolean')
            self.store.data['theme_btop' if action=='styleTui' else 'theme_btop_background']=value; self.apply_theme()
        elif action=='iosAlbumArt':
            if not isinstance(value,bool): raise ValueError('Expected boolean')
            self.store.data['ios_album_art']=value; self.music.apply_art_mode()
        elif action=='musicDarkness':
            if type(value) is not int or not 0<=value<=100: raise ValueError('Expected integer from 0 to 100')
            self.store.data['music_darkness']=value; self.music.apply_art_mode()
        elif action=='visibility':
            key=request['widget']
            if key not in self.panels or not isinstance(value,bool): raise ValueError('Invalid widget visibility')
            self.layout[key]['visible']=value; self.panels[key].place()
        elif action=='monitor':
            if value not in self.snapshot()['monitors']: raise ValueError('Display is not connected')
            self.store.data['monitor']=value; self.monitor_changed()
        elif action=='player':
            if value and value not in self.music.players: raise ValueError('Player is not available')
            self.store.data['music_player']=value; self.music.refresh()
        elif action=='reset': self.reset_layout()
        elif action=='restartTerminal': self.terminal.restart()
        else: raise ValueError('Unknown dashboard action')
        self.save_layout()
    def shutdown(self,*_):
        self.jobs.closed=True
        if getattr(self,'theme_monitor',None): self.theme_monitor.cancel()
        for source in ('theme_reload_source','theme_retry'):
            if getattr(self,source,0): GLib.source_remove(getattr(self,source))
        if self.ready:
            if hasattr(self,'music'): GLib.source_remove(self.music.progress_timer)
            self.save_layout()
            if hasattr(self,'terminal'): self.terminal.stop()
            self.spectrum.stop()

if __name__=='__main__':
    sys.exit(Dashboard().run(sys.argv))
