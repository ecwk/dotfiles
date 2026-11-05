"""GPU identity from configuration/cache, without waking the discrete GPU."""
from core import ROOT,STATE,read_json

def valid_name(value):
    return isinstance(value,str) and 0<len(value.strip())<=120 and all(c.isprintable() and c not in '{}' for c in value)

def gpu_name():
    # Identity is static: never query the NVIDIA driver during periodic refreshes.
    for path in (ROOT/'data/gpu.json',STATE/'gpu.json'):
        data=read_json(path,{})
        name=data.get('name') if isinstance(data,dict) else None
        if valid_name(name): return name.strip()
    return None
