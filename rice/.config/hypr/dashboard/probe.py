"""Short-lived, isolated terminal/layer-shell feasibility probe."""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
gi.require_version('Vte', '3.91')
from gi.repository import Gtk, Gtk4LayerShell as Layer, Vte, GLib, Pango

app = Gtk.Application(application_id='io.github.ecwk.GlassDashboard.Probe')
def activate(app):
    win = Gtk.ApplicationWindow(application=app, title='Dashboard feasibility probe')
    Layer.init_for_window(win)
    Layer.set_namespace(win, 'glass-dashboard-probe')
    Layer.set_layer(win, Layer.Layer.BOTTOM)
    Layer.set_keyboard_mode(win, Layer.KeyboardMode.ON_DEMAND)
    Layer.set_exclusive_zone(win, -1)
    Layer.set_anchor(win, Layer.Edge.LEFT, True)
    Layer.set_anchor(win, Layer.Edge.TOP, True)
    Layer.set_margin(win, Layer.Edge.LEFT, 360)
    Layer.set_margin(win, Layer.Edge.TOP, 280)
    win.set_default_size(720, 440)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    terminal = Vte.Terminal()
    terminal.set_font(Pango.FontDescription('monospace 9'))
    terminal.set_vexpand(True)
    def launch(*_):
        terminal.spawn_async(Vte.PtyFlags.DEFAULT, None, ['/usr/bin/btop'],
                             ['TERM=xterm-256color'], GLib.SpawnFlags.DEFAULT,
                             None, None, -1, None, lambda t,p,e,d: print('spawn',p,e,flush=True), None)
    restart = Gtk.Button(label='Terminal probe · Restart after quitting')
    restart.connect('clicked', launch)
    box.append(restart)
    box.append(terminal)
    win.set_child(box)
    win.present()
    launch()
    GLib.timeout_add_seconds(30, lambda: (app.quit(), False)[1])
app.connect('activate', activate)
app.run(None)
