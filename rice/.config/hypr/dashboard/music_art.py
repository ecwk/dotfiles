"""Artwork-local rendering: blur the image itself, never the desktop wallpaper."""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gsk', '4.0')
gi.require_version('Graphene', '1.0')
from gi.repository import Gtk, Gdk, Gsk, Graphene

class ArtworkBackdrop(Gtk.Widget):
    def __init__(self):
        super().__init__()
        self.texture=None
        self.enabled=False
        self.dark_mode=True
        self.darkness=65
        self.set_hexpand(True); self.set_vexpand(True)
        self.set_can_target(False)

    def do_snapshot(self, snapshot):
        if not self.enabled or self.texture is None: return
        w,h=self.get_width(),self.get_height()
        if not w or not h: return
        rect=Graphene.Rect().init(0,0,w,h)
        clip=Gsk.RoundedRect(); clip.init_from_rect(rect,22)
        snapshot.push_rounded_clip(clip)
        base=Gdk.RGBA(); base.parse('#242124'); snapshot.append_color(base,rect)
        # Overscan keeps transparent blur edges outside the rounded card.
        radius=min(w,h)*.22
        tw,th=self.texture.get_width(),self.texture.get_height()
        scale=max((w+radius*6)/tw,(h+radius*6)/th)
        iw,ih=tw*scale,th*scale
        snapshot.push_blur(radius)
        snapshot.append_texture(self.texture,Graphene.Rect().init((w-iw)/2,(h-ih)/2,iw,ih))
        snapshot.pop()
        # Neutral veil mutes saturation and bounds brightness for white controls.
        veil=Gdk.RGBA(); veil.parse(f'rgba(24,22,26,{self.darkness/100 if self.dark_mode else 0.58})')
        snapshot.append_color(veil,rect)
        snapshot.pop()
