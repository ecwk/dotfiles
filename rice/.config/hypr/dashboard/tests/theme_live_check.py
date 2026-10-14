"""Opt-in live theme check: use an isolated GLASS_DASHBOARD_STATE, with the service stopped."""
import sys,json,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as module
from theme import read_palette
from app import Dashboard,GLib,Vte
from core import STATE
if not os.environ.get('GLASS_DASHBOARD_STATE') or STATE.resolve()==(Path.home()/'.local/state/glass-dashboard').resolve():
    raise SystemExit('Set GLASS_DASHBOARD_STATE to a disposable test directory.')
palette=read_palette()
if not palette: raise SystemExit('Apply a walltheme palette before running this opt-in live check.')
path=STATE/'walltheme/current.json'; path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps({'colors':palette}))
module.THEME_FILE=path
module.read_palette=lambda:read_palette(path)
app=Dashboard(); app.store.data.update(theme_mode='full',theme_btop=False,theme_btop_background=False); failures=[]; saved={}
def run(fn,next_fn=None):
    try: fn(); print('PASS',fn.__name__,flush=True)
    except Exception as e: failures.append(str(e)); print('FAIL',fn.__name__,repr(e),flush=True)
    if next_fn: GLib.timeout_add_seconds(2,next_fn)
    else: app.quit()
    return False
def initial():
    assert app.theme_mode=='full' and not app.btop_themed()
    assert app.system.output and app.system.terminal.get_row_count()==9
    assert app.theme_monitor
    saved['bt']=app.terminal.pid
    app.control({'action':'styleBackground','value':True})
    assert not app.panels['btop'].root.has_css_class('btop-original')
    assert app.terminal.pid==saved['bt'] and not app.btop_themed()
    app.control({'action':'styleBackground','value':False})
    assert app.panels['btop'].root.has_css_class('btop-original')
    app.control({'action':'styleTui','value':True})
def themed():
    assert app.terminal.pid and app.terminal.pid!=saved['bt']
    assert 'walltheme.theme' in (STATE/'btop.conf').read_text()
    app.control({'action':'theme','value':'accents'})
def accents():
    assert app.snapshot()['theme']=='accents'
    assert 'color_theme = "Default"' in (STATE/'btop.conf').read_text()
    assert app.theme_mode=='accents'
    app.control({'action':'theme','value':'original'})
def original():
    assert app.theme_mode=='original'
    assert b'137;180;250' in app.system.output
    app.control({'action':'theme','value':'full'})
    c=dict(palette,accent='#88ccaa',background='#eeeeee',surface='#dddddd',foreground='#111111')
    temp=path.with_suffix('.tmp'); temp.write_text(json.dumps({'colors':c})); temp.replace(path)
def reloaded():
    assert app.palette['accent']=='#88ccaa'
    assert b'136;204;170' in app.system.output
    assert '#88ccaa' in (STATE/'walltheme.theme').read_text()
    assert app.btop_themed() and app.terminal.pid
    path.write_text('{invalid')
def invalid():
    assert app.palette['accent']=='#88ccaa'
    assert app.store.data['theme_mode']=='full' and app.store.data['theme_btop']
    assert len([line for line in app.system.terminal.get_text_format(Vte.Format.TEXT).splitlines() if line.strip()])==9
steps=[initial,themed,accents,original,reloaded,invalid]
def step():
    fn=steps.pop(0)
    return run(fn,step if steps else None)
GLib.timeout_add_seconds(4,step)
app.run(['theme-live-test'])
sys.exit(bool(failures))
