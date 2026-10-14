import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import *
from types import SimpleNamespace
from unittest.mock import patch
Gtk.init()
providers=[]
for priority,name in enumerate(('style.css','music.css')):
    p=Gtk.CssProvider(); p.load_from_path(str(ROOT/name)); providers.append(p)
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),p,600+priority*2)
win=Gtk.Window(); Layer.init_for_window(win); Layer.set_namespace(win,'music-preview'); Layer.set_layer(win,Layer.Layer.OVERLAY); win.root=box(); win.root.add_css_class('glass'); win.content=box();win.root.append(win.content);win.set_child(win.root)
fake=SimpleNamespace(store=SimpleNamespace(data={}),jobs=SimpleNamespace(run=lambda *args:None))
with patch('app.repeat'): music=MusicWidget(fake,win)
music.resize(500,146);win.set_default_size(500,146)
# Deterministic artwork and MPRIS metadata; no live player is controlled.
props={'Metadata':{'xesam:title':'In The Abyss Of Death’s Obscurity','xesam:artist':['Engulfed'],'mpris:length':248000000,'mpris:artUrl':'file:///test'},'Position':166000000,'PlaybackStatus':'Paused','CanControl':True,'CanPlay':True,'CanGoNext':True,'CanGoPrevious':True}
music.update((['test'],'test',props),None)
import cairo,io
surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,100,100); ctx=cairo.Context(surface)
g=cairo.LinearGradient(0,0,100,100);g.add_color_stop_rgb(0,.9,.1,.04);g.add_color_stop_rgb(1,.04,.02,.03);ctx.set_source(g);ctx.paint()
out=io.BytesIO();surface.write_to_png(out);data=out.getvalue()
music.set_art(music.art_url,data,None)
assert music.backdrop.enabled
# Higher-priority artwork CSS must win even after a wallpaper theme reload.
from theme import css
provider=Gtk.CssProvider()
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,601)
palette=dict(background='#ffffff',surface='#eeeeee',foreground='#111111',muted='#222222',border='#333333',accent='#00ff00',on_accent='#000000')
for mode in ('full','accents','original'):
    provider.load_from_string(css(mode,palette))
    assert music.title.get_color().red > .99
fake.store.data['ios_album_art']=False;music.apply_art_mode();assert not music.backdrop.enabled
fake.store.data['ios_album_art']=True;music.apply_art_mode();assert music.backdrop.enabled
music.set_art('stale',b'bad',None);assert music.backdrop.enabled
win.present()
loop=GLib.MainLoop(); failures=[]
def capture():
    try:
        paint=Gtk.WidgetPaintable.new(win.get_child()); snap=Gtk.Snapshot();paint.snapshot(snap,win.get_width(),win.get_height())
        node=snap.to_node();texture=win.get_renderer().render_texture(node,None);texture.save_to_png('/tmp/music-preview.png')
        assert (win.get_width(),win.get_height())==(500,146)
        assert music.elapsed.get_text()=='2:46' and music.remaining.get_text()=='-1:22'
        assert music.play.get_sensitive()
        print('RENDER',win.get_width(),win.get_height())
        music.update(([],None,None),None);assert not music.backdrop.enabled
        assert not music.play.get_sensitive()
        music.set_art('stale',data,None);assert not music.backdrop.enabled
        print('PASS mode toggle, stale artwork, empty player, render')
    except Exception:
        import traceback
        traceback.print_exc(); failures.append(True)
    finally: loop.quit();win.destroy()
    return False
GLib.timeout_add(500,capture);loop.run()
raise SystemExit(1 if failures else 0)
