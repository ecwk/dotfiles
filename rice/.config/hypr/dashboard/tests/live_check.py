"""Run in an isolated GLASS_DASHBOARD_STATE from a real Wayland session."""
import sys,json,os,signal
from unittest.mock import patch
import copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import Dashboard,GLib,Layer,Gtk,Vte
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

def stage1():
    global first_pid
    def surfaces():
        layers=json.loads(command(['hyprctl','layers','-j']))
        panels=[(level,x) for m in layers.values() for level,items in m['levels'].items() for x in items if x['namespace'].startswith('glass-dashboard-')]
        require(len(panels)==4,f'Expected four panels, got {len(panels)}')
        require(all(level=='1' for level,x in panels),'Panel above bottom layer')
        for level,p in panels:
            require(p['x']+p['w']<=app.width and p['y']+p['h']<=app.height,'Panel exceeds output bounds')
    check('all four panels are bottom-layer and on-screen',surfaces)
    check('no editing or drag handles',lambda:require(not hasattr(app,'toggle_edit') and all(not hasattr(p,'move_handle') for p in app.panels.values()),'Editing remains'))
    def minimal_chrome():
        require('controls' not in app.panels,'Floating control dock remains')
        require(all(not hasattr(p,'header') for p in app.panels.values()),'Widget heading remains')
        require(not app.terminal.status.get_visible(),'Persistent terminal hint remains')
    check('minimal chrome with no floating control dock',minimal_chrome)
    def media_empty():
        app.music.update(([],None,None),None)
        require(not app.music.play.get_sensitive() and not app.music.next.get_sensitive(),'No-player controls enabled')
    check('missing music players disable playback controls',media_empty)
    def fastfetch_content():
        require(app.system.terminal.get_row_count()==9 and app.system.terminal.get_column_count()>=52,'Unexpected terminal grid: '+str((app.system.terminal.get_row_count(),app.system.terminal.get_column_count())))
        text=app.system.terminal.get_text_format(Vte.Format.TEXT)
        lines=[line for line in text.splitlines() if line.strip()]
        require(len(lines)==9,'Fastfetch did not fit in nine rows: '+repr(text))
        require('/\\' in lines[0],'Arch logo tip is clipped')
        require(not app.system.terminal.get_input_enabled(),'Fastfetch accepts stray keyboard input')
        for key in ('os','wm','up','cpu','gpu','ram','swap','disk','bat'):
            require(any(key in line for line in lines),'Missing Fastfetch field '+key)
        app.system.render(app.system.output,None)
    check('Fastfetch fits nine rows and keeps its logo tip after refresh',fastfetch_content)
    def restart():
        global first_pid
        first_pid=app.terminal.pid; require(bool(first_pid),'btop did not start')
        app.terminal.terminal.feed_child(b'q')
    check('real btop accepts terminal input',restart)
    GLib.timeout_add_seconds(2,stage2)
    return False

def stage2():
    def relaunched():
        require(app.terminal.pid and app.terminal.pid!=first_pid,'btop did not relaunch after q')
        require(not app.terminal.status.get_visible(),'Terminal hint remains visible')
    check('btop automatically relaunches after quitting',relaunched)
    GLib.timeout_add_seconds(3,stage3)
    return False

def stage3():
    def restarted(): require(app.terminal.pid and app.terminal.pid!=first_pid,'No new terminal process')
    check('automatic btop recovery remains running',restarted)
    def fastfetch_after_refresh():
        text=app.system.terminal.get_text_format(Vte.Format.TEXT)
        lines=[line for line in text.splitlines() if line.strip()]
        require(len(lines)==9 and '/\\' in lines[0] and 'os' in lines[0],'Refresh corrupted the logo or first row: '+repr(text))
        disk=next(line for line in lines if 'disk' in line)
        require('%)' in disk,'Disk percentage was clipped: '+disk)
    check('Fastfetch stays intact after repeated refreshes',fastfetch_after_refresh)
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
