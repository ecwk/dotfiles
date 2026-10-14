"""NVIDIA identity with a saved/static fallback for powered-down discrete GPUs."""
import subprocess
from core import ROOT,STATE,read_json,write_json

def valid_name(value):
    return isinstance(value,str) and 0<len(value.strip())<=120 and all(c.isprintable() and c not in '{}' for c in value)

def gpu_name():
    try:
        result=subprocess.run(['/usr/bin/nvidia-smi','--query-gpu=name','--format=csv,noheader'],capture_output=True,text=True,timeout=3)
        names=[line.strip() for line in result.stdout.splitlines() if line.strip()]
        if result.returncode==0 and names and valid_name(names[0]):
            name=names[0]
            cached=read_json(STATE/'gpu.json',{})
            try:
                if not isinstance(cached,dict) or cached.get('name')!=name: write_json(STATE/'gpu.json',{'name':name})
            except OSError: pass
            return name
    except (OSError,subprocess.SubprocessError): pass
    for path in (ROOT/'data/gpu.json',STATE/'gpu.json'):
        data=read_json(path,{})
        name=data.get('name') if isinstance(data,dict) else None
        if valid_name(name): return name.strip()
    return None
