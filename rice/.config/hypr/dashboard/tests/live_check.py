"""Run in an isolated GLASS_DASHBOARD_STATE from a real Wayland session."""
import sys,json,os,signal
from unittest.mock import patch
import copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import Dashboard,GLib,Layer,Gtk
from core import command,STATE

app=Dashboard()
failures=[]
results=[]

def check(name,fn):
    try:
        fn(); results.append(name); print('PASS',name,flush=True)
    except Exception as e:
        failures.append((name,str(e))); print('FAIL',name,e,flush=True)

def require(value,message):
    if not value: raise AssertionError(message)

first_pid=None
bluetooth_pid=None
fastfetch_pid=None

def stage1():
    global first_pid,bluetooth_pid,fastfetch_pid
    def surfaces():
        layers=json.loads(command(['hyprctl','layers','-j']))
        panels=[(level,x) for m in layers.values() for level,items in m['levels'].items() for x in items if x['namespace'].startswith('glass-dashboard-')]
        require(len(panels)==9,f'Expected nine panels, got {len(panels)}')
        require(all(level=='1' for level,x in panels),'Panel above bottom layer')
        for level,p in panels:
            require(p['x']+p['w']<=app.width and p['y']+p['h']<=app.height,'Panel exceeds output bounds')
    check('all nine panels are bottom-layer and on-screen',surfaces)
    def edit():
        app.toggle_edit(); require(all(p.resize.get_visible() and p.move_handle.get_visible() for p in app.panels.values()),'Missing edit handles')
        app.toggle_edit(); require(not any(p.resize.get_visible() or p.move_handle.get_visible() for p in app.panels.values()),'Edit handles remain')
    check('edit controls toggle independently of widget content',edit)
    def minimal_chrome():
        require(all(not hasattr(p,'header') for p in app.panels.values()),'Widget heading remains')
        require(not app.terminal.status.get_visible() and not app.bluetooth.status.get_visible(),'Persistent terminal hint remains')
        require(app.layout['controls']['w']<=120 and app.layout['controls']['h']<=80,'Controls are not compact')
        require(app.edit_button.get_label() is None,'Edit control has a text label')
    check('minimal chrome and tucked-away icon controls',minimal_chrome)
    def layout_gestures():
        panel=app.panels['clock']; old=copy.deepcopy(app.layout['clock']); app.toggle_edit()
        with patch('app.command',side_effect=['{"x":80,"y":70}','{"x":180,"y":110}']):
            panel.begin(None,0,0,'move'); panel.drag(None,100,40,'move')
        require(app.layout['clock']['x']==old['x']+100 and app.layout['clock']['y']==old['y']+40,'Drag geometry incorrect')
        with patch('app.command',side_effect=['{"x":400,"y":200}','{"x":440,"y":220}']):
            panel.begin(None,0,0,'resize'); panel.drag(None,40,20,'resize')
        require(app.layout['clock']['w']==old['w']+40,'Resize geometry incorrect')
        app.layout['clock']=old; panel.place(); app.toggle_edit()
    check('drag and resize handlers update layer geometry',layout_gestures)
    def media_empty():
        app.music.update(([],None,None),None)
        require(not app.music.play.get_sensitive() and not app.music.next.get_sensitive(),'No-player controls enabled')
    check('missing music players disable playback controls',media_empty)
    fastfetch_pid=app.system.pid
    require(bool(fastfetch_pid),'Fastfetch did not start')
    os.kill(fastfetch_pid,signal.SIGTERM)
    bluetooth_pid=app.bluetooth.pid
    require(bool(bluetooth_pid),'bluetui did not start')
    app.bluetooth.terminal.feed_child(b'q')
    def restart():
        global first_pid,bluetooth_pid,fastfetch_pid
        first_pid=app.terminal.pid; require(bool(first_pid),'btop did not start')
        app.terminal.terminal.feed_child(b'q')
    check('real btop accepts terminal input',restart)
    app.weather.set_location({'name':'Singapore','latitude':1.29,'longitude':103.85},False)
    GLib.timeout_add_seconds(2,stage2)
    return False

def stage2():
    def relaunched():
        require(app.terminal.pid and app.terminal.pid!=first_pid,'btop did not relaunch after q')
        require(not app.terminal.status.get_visible(),'Terminal hint remains visible')
    check('btop automatically relaunches after quitting',relaunched)
    def bluetooth_relaunched():
        require(app.bluetooth.pid and app.bluetooth.pid!=bluetooth_pid,'bluetui did not relaunch after q')
        require(not app.bluetooth.status.get_visible(),'Bluetooth hint remains visible')
    check('Bluetooth automatically relaunches after quitting',bluetooth_relaunched)
    check('native Fastfetch automatically relaunches after exit',lambda:require(app.system.pid and app.system.pid!=fastfetch_pid,'Fastfetch did not relaunch'))
    GLib.timeout_add_seconds(3,stage3)
    return False

def stage3():
    def restarted(): require(app.terminal.pid and app.terminal.pid!=first_pid,'No new terminal process')
    check('automatic btop recovery remains running',restarted)
    check('automatic Bluetooth recovery remains running',lambda:require(app.bluetooth.pid and app.bluetooth.pid!=bluetooth_pid,'No new Bluetooth process'))
    def malformed():
        app.weather.render({},0)
        require('unavailable' in app.weather.status.get_text(),'Bad forecast not handled')
    check('malformed weather response is handled',malformed)
    def stale():
        loc=app.weather.location
        app.weather.received(app.weather.generation-1,loc,{},None)
        app.weather.received(app.weather.generation,loc,None,'offline')
        require('Offline' in app.weather.status.get_text() or 'unavailable' in app.weather.status.get_text(),'Offline status missing')
    check('stale replies ignored and offline failure displayed',stale)
    check('settings can be persisted',app.save_layout)
    GLib.timeout_add_seconds(2,finish)
    return False

def finish():
    print(json.dumps({'passed':results,'failed':failures}),flush=True)
    app.quit()
    return False

app.connect('startup',lambda *_:GLib.timeout_add_seconds(3,stage1))
app.run(['live-check'])
sys.exit(1 if failures else 0)
