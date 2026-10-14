"""Pure data, persistence and subprocess helpers (no GUI dependency)."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
STATE = Path(os.environ.get('GLASS_DASHBOARD_STATE', str(Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'glass-dashboard')))
TITLES = {'music':'NOW PLAYING', 'visualiser':'SOUND', 'btop':'SYSTEM MONITOR', 'system':'FASTFETCH'}

def read_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2)+'\n')
    temp.chmod(0o600)
    temp.replace(path)

def command(args, timeout=8, env=None):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout or f'{args[0]} failed').strip()[:240])
    return p.stdout.strip()

def clamp_rect(rect, width, height, minimum=(220,120)):
    def number(key, fallback):
        value = rect.get(key, fallback)
        return int(value) if isinstance(value,(float,int)) and math.isfinite(value) else fallback
    w = min(width, max(minimum[0], number('w', minimum[0])))
    h = min(height, max(minimum[1], number('h', minimum[1])))
    return {'x':max(0,min(width-w,number('x',0))), 'y':max(0,min(height-h,number('y',0))), 'w':w,'h':h, 'visible':bool(rect.get('visible',True))}

def minimum_for(key):
    return {'btop':(620,360),'system':(1,1)}.get(key,(220,100))

PRESETS = read_json(ROOT/'data/layouts.json', {})

def preset_layout(name, width, height):
    preset = PRESETS.get(name, PRESETS['balanced-center'])
    rects = preset['widgets']
    extent_w = max(r['x']+r['w'] for r in rects.values())
    extent_h = max(r['y']+r['h'] for r in rects.values())
    scale = min(1, max(1,width-32)/extent_w, max(1,height-32)/extent_h)
    total_w, total_h = round(extent_w*scale), round(extent_h*scale)
    x = (width-total_w)//2
    y = height-total_h-32 if preset['anchor']=='bottom' else (height-total_h)//2
    # Round shared edges rather than widths independently to preserve alignment.
    return {key:dict(x=x+round(r['x']*scale), y=y+round(r['y']*scale),
                     w=round((r['x']+r['w'])*scale)-round(r['x']*scale),
                     h=round((r['y']+r['h'])*scale)-round(r['y']*scale), visible=True)
            for key,r in rects.items()}

def default_layout(width, height):
    return preset_layout('balanced-center', width, height)

class Store:
    def __init__(self, path=None):
        self.path = path or STATE/'settings.json'
        self.data = read_json(self.path,{})
        if not isinstance(self.data,dict): self.data={}
        if not isinstance(self.data.get('layouts'),dict): self.data['layouts']={}
        for layout in self.data['layouts'].values():
            if isinstance(layout,dict):
                for key in ('clock','calendar','bluetooth','weather','controls'): layout.pop(key,None)
    def save(self): write_json(self.path,self.data)
    def layout(self, monitor, width, height):
        selections = self.data.get('layout_presets', {})
        name = selections.get(monitor, 'balanced-center') if isinstance(selections,dict) else 'balanced-center'
        result = preset_layout(name,width,height)
        saved = self.data['layouts'].get(monitor,{})
        if isinstance(saved,dict):
            for key,rect in result.items():
                old=saved.get(key,{})
                if isinstance(old,dict): rect['visible']=bool(old.get('visible',True))
        return result
