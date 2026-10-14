"""Asynchronous integrations. GTK updates are always delivered on its main loop."""
import os
import threading
import subprocess
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse, unquote
from gi.repository import Gio, GLib
from core import ROOT, STATE, command

class Jobs:
    def __init__(self):
        self.running=set()
        self.closed=False
    def run(self,key,work,done):
        if self.closed or key in self.running: return False
        self.running.add(key)
        def finish(value,error):
            self.running.discard(key)
            if not self.closed: done(value,error)
            return False
        def worker():
            try: value,error=work(),None
            except Exception as exc: value,error=None,str(exc)
            GLib.idle_add(finish,value,error)
        threading.Thread(target=worker,daemon=True,name=key).start()
        return True

MPRIS='org.mpris.MediaPlayer2.'
PLAYER='org.mpris.MediaPlayer2.Player'
PATH='/org/mpris/MediaPlayer2'

def bus_call(bus,name,path,iface,method,args=None):
    return bus.call_sync(name,path,iface,method,args,None,Gio.DBusCallFlags.NONE,2000,None).unpack()

def media_snapshot(preferred=''):
    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    names=bus_call(bus,'org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','ListNames')[0]
    players=[]
    for name in sorted(n for n in names if n.startswith(MPRIS)):
        try:
            props=bus_call(bus,name,PATH,'org.freedesktop.DBus.Properties','GetAll',GLib.Variant('(s)',(PLAYER,)))[0]
            players.append((name,props))
        except GLib.Error: pass
    if not players: return [],None,None
    selected=next((x for x in players if x[0]==preferred),None)
    selected=selected or next((x for x in players if x[1].get('PlaybackStatus')=='Playing'),players[0])
    return [n for n,_ in players],selected[0],selected[1]

def media_action(name,method):
    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    return bus_call(bus,name,PATH,PLAYER,method)

def artwork_bytes(url):
    parsed=urlparse(url)
    if parsed.scheme=='file' and parsed.netloc in ('','localhost'):
        with open(unquote(parsed.path),'rb') as f: data=f.read(4_000_001)
    elif parsed.scheme in ('http','https'):
        with urlopen(Request(url,headers={'User-Agent':'GlassDashboard/1.0'}),timeout=8) as r: data=r.read(4_000_001)
    else: raise ValueError('Unsupported artwork URL')
    if len(data)>4_000_000: raise ValueError('Artwork exceeds 4 MB')
    return data

class Spectrum:
    def __init__(self):
        self.values=[0]*48
        self.error=None
        self.process=None
    def start(self):
        self.stop()
        self.error=None
        try:
            self.process=subprocess.Popen(['cava','-p',str(ROOT/'data/cava.conf')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,text=True)
        except OSError as exc:
            self.error=str(exc)
            return
        proc=self.process
        def read():
            for line in proc.stdout:
                try:
                    values=[min(1,max(0,int(n)/100)) for n in line.strip().split(';') if n]
                    if len(values)==48: self.values=values
                except ValueError: pass
            proc.wait()
            error=proc.stderr.read().strip()
            proc.stdout.close()
            proc.stderr.close()
            if self.process is proc:
                self.values=[0]*48
                self.error=error[:100] or 'Visualiser stopped'
        threading.Thread(target=read,daemon=True,name='cava').start()
    def stop(self):
        proc,self.process=self.process,None
        if proc and proc.poll() is None:
            proc.terminate()
            try: proc.wait(timeout=1)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait()
