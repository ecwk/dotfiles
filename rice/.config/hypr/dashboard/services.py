"""Asynchronous integrations. GTK updates are always delivered on its main loop."""
import os
import threading
import subprocess
import time
import uuid
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

class Location:
    """Portal v1: city-level accuracy, persistent session, no private fallback service."""
    DEST='org.freedesktop.portal.Desktop'
    PATH='/org/freedesktop/portal/desktop'
    IFACE='org.freedesktop.portal.Location'
    def __init__(self,on_location,on_status):
        self.on_location=on_location
        self.on_status=on_status
        self.bus=None
        self.session=None
        self.subs=[]
        self.timeout=0
        self.generation=0
    def close(self):
        self.generation+=1
        if self.timeout: GLib.source_remove(self.timeout); self.timeout=0
        if self.bus:
            for sub in self.subs: self.bus.signal_unsubscribe(sub)
            if self.session:
                self.bus.call(self.DEST,self.session,'org.freedesktop.portal.Session','Close',None,None,Gio.DBusCallFlags.NONE,2000,None,None,None)
        self.subs=[]
        self.session=None
    def start(self):
        self.close()
        self.on_status('Requesting approximate location…')
        gen=self.generation
        def got_bus(obj,res,_):
            if gen!=self.generation: return
            try: self.bus=Gio.bus_get_finish(res)
            except GLib.Error as e: self.failed(str(e)); return
            self.subs.append(self.bus.signal_subscribe(self.DEST,self.IFACE,'LocationUpdated',self.PATH,None,Gio.DBusSignalFlags.NONE,self.updated,None))
            options={'session_handle_token':GLib.Variant('s','glass'+uuid.uuid4().hex),'accuracy':GLib.Variant('u',2),'distance-threshold':GLib.Variant('u',5000),'time-threshold':GLib.Variant('u',900)}
            self.bus.call(self.DEST,self.PATH,self.IFACE,'CreateSession',GLib.Variant('(a{sv})',(options,)),None,Gio.DBusCallFlags.NONE,5000,None,created,None)
        def created(bus,res,_):
            if gen!=self.generation: return
            try: self.session=bus.call_finish(res).unpack()[0]
            except GLib.Error as e: self.failed(str(e)); return
            token='glass'+uuid.uuid4().hex
            request='/org/freedesktop/portal/desktop/request/'+bus.get_unique_name()[1:].replace('.','_')+'/'+token
            self.subs.append(bus.signal_subscribe(self.DEST,'org.freedesktop.portal.Request','Response',request,None,Gio.DBusSignalFlags.NONE,response,None))
            bus.call(self.DEST,self.PATH,self.IFACE,'Start',GLib.Variant('(osa{sv})',(self.session,'',{'handle_token':GLib.Variant('s',token)})),None,Gio.DBusCallFlags.NONE,5000,None,started,None)
        def started(bus,res,_):
            if gen!=self.generation: return
            try: bus.call_finish(res)
            except GLib.Error as e: self.failed(str(e))
        def response(bus,sender,path,iface,signal,params,data):
            if params.unpack()[0]!=0: self.failed('Location permission was not granted')
        self.timeout=GLib.timeout_add_seconds(40,self.expired)
        Gio.bus_get(Gio.BusType.SESSION,None,got_bus,None)
    def expired(self):
        self.timeout=0
        self.failed('Location is unavailable. Choose a location or retry.')
        return False
    def failed(self,detail):
        self.close()
        self.on_status('Automatic location unavailable · Choose location',detail)
    def updated(self,bus,sender,path,iface,signal,params,data):
        session,loc=params.unpack()
        if session!=self.session or 'Latitude' not in loc or 'Longitude' not in loc: return
        if self.timeout: GLib.source_remove(self.timeout); self.timeout=0
        # City-level precision is sufficient for weather, and stored coordinates are coarse.
        self.on_location({'name':'Current location','latitude':round(loc['Latitude'],2),'longitude':round(loc['Longitude'],2)})
