"""Pure data, persistence and subprocess helpers (no GUI dependency)."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import subprocess
from datetime import date
from urllib.request import Request, urlopen
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent
STATE = Path(os.environ.get('GLASS_DASHBOARD_STATE', str(Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'glass-dashboard')))
TITLES = {'clock':'TIME & TERM', 'calendar':'CALENDAR', 'music':'NOW PLAYING', 'visualiser':'SOUND', 'btop':'SYSTEM MONITOR', 'weather':'WEATHER', 'system':'FASTFETCH', 'bluetooth':'BLUETOOTH', 'controls':'DASHBOARD'}

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

def fetch(url, params=None):
    if params:
        url += '?' + urlencode(params)
    req = Request(url, headers={'User-Agent':'GlassDashboard/1.0 (personal desktop)'})
    with urlopen(req, timeout=12) as r:
        data = r.read(2_000_001)
    if len(data)>2_000_000:
        raise ValueError('Response is too large')
    return json.loads(data)

def search_places(name):
    if len(name.strip()) < 2:
        return []
    return fetch('https://geocoding-api.open-meteo.com/v1/search', {'name':name.strip(), 'count':6, 'language':'en', 'format':'json'}).get('results', [])

def weather_for(location):
    return fetch('https://api.open-meteo.com/v1/forecast', {
        'latitude':location['latitude'], 'longitude':location['longitude'],
        'current':'temperature_2m,relative_humidity_2m,weather_code',
        'daily':'weather_code,temperature_2m_max,temperature_2m_min',
        'forecast_days':4, 'timezone':'auto'})

def conditions(code):
    if code == 0: return '☀', 'Clear sky'
    if code in (1,2): return '☁', 'Partly cloudy'
    if code == 3: return '☁', 'Overcast'
    if code in (45,48): return '≋', 'Fog'
    if code in (51,53,55,56,57): return '☂', 'Drizzle'
    if code in (61,63,65,66,67,80,81,82): return '☂', 'Rain'
    if code in (71,73,75,77,85,86): return '❄', 'Snow'
    if code in (95,96,99): return 'ϟ', 'Thunderstorm'
    return '○', 'Weather unavailable'

def academic(day, data=None):
    data = data or read_json(ROOT/'data/academic.json', {})
    for phase in data.get('phases', []):
        start, end = date.fromisoformat(phase['start']), date.fromisoformat(phase['end'])
        if start <= day <= end:
            label = phase['phase']
            if 'week' in phase:
                label = f"Teaching week {phase['week']+(day-start).days//7}"
            return f"{phase['semester']} · {label}", data['year']
    return 'Academic dates unavailable', 'Add the next official calendar to data/academic.json'

def clamp_rect(rect, width, height, minimum=(220,120)):
    def number(key, fallback):
        value = rect.get(key, fallback)
        return int(value) if isinstance(value,(float,int)) and math.isfinite(value) else fallback
    w = min(width, max(minimum[0], number('w', minimum[0])))
    h = min(height, max(minimum[1], number('h', minimum[1])))
    return {'x':max(0,min(width-w,number('x',0))), 'y':max(0,min(height-h,number('y',0))), 'w':w,'h':h, 'visible':bool(rect.get('visible',True))}

def minimum_for(key):
    return {'btop':(620,360),'bluetooth':(280,320),'controls':(84,40),'system':(380,144)}.get(key,(220,100))

def default_layout(width, height):
    defaults = read_json(ROOT/'data/layout.json', {})
    sx, sy = width/1440, height/900
    result = {}
    for key, rect in defaults.items():
        result[key] = clamp_rect({k:(bool(v) if k=='visible' else round(v*(sx if k in ('x','w') else sy))) for k,v in rect.items()}, width,height, minimum_for(key))
    return result

class Store:
    def __init__(self, path=None):
        self.path = path or STATE/'settings.json'
        self.data = read_json(self.path,{})
        if not isinstance(self.data,dict): self.data={}
        if not isinstance(self.data.get('layouts'),dict): self.data['layouts']={}
    def save(self): write_json(self.path,self.data)
    def layout(self, monitor, width, height):
        defaults = default_layout(width,height)
        saved = self.data['layouts'].get(monitor,{})
        if not isinstance(saved,dict): saved={}
        if 'calculator' in saved:
            # Upgrade the initial dashboard layout to make room for the Bluetooth TUI.
            saved.pop('calculator',None)
            for key in ('system','visualiser','btop','bluetooth'): saved[key]=dict(defaults[key])
        if isinstance(saved.get('system'),dict) and saved['system'].get('w',0)<=336:
            saved['system']['w']=defaults['system']['w']
            if isinstance(saved.get('visualiser'),dict) and saved['visualiser'].get('x')==720:
                saved['visualiser']=dict(defaults['visualiser'])
        if isinstance(saved.get('controls'),dict) and (saved['controls'].get('w',0)>120 or saved['controls'].get('h',0)>80):
            saved['controls']=dict(defaults['controls'])
        return {k:clamp_rect(saved.get(k,v) if isinstance(saved.get(k,v),dict) else v,width,height,minimum_for(k)) for k,v in defaults.items()}
