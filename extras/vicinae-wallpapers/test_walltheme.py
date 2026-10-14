import asyncio
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import walltheme as w

class SessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.old = self.root / 'original.jpg'; self.old.touch()
        self.other = self.root / 'second monitor.jpg'; self.other.touch()
        self.new = self.root / 'new $wall paper.jpg'; self.new.touch()
        self.config = self.root / 'waypaper.ini'
        self.config.write_text('[Settings]\nuse_xdg_state=False\nwallpaper=original\n')
        self.state = self.root / 'state'; self.state.mkdir()
        self.theme = self.state / 'current.json'
        self.theme.write_text('{"old":true}')
        self.displays = {'A': str(self.old), 'B': str(self.other)}
        self.original = dict(self.displays)
        def set_wallpaper(image, monitor): self.displays[monitor] = str(image)
        def apply(image):
            for name in self.displays: self.displays[name] = str(image)
        def run(args, *a, **kw):
            if '--wallpaper' in args: self.config.write_text('[Settings]\nuse_xdg_state=False\nwallpaper=changed\n')
            return ''
        def publish(image, mode):
            value = {'wallpaper': image, 'mode': mode}
            w.atomic(self.theme, value)
            return value
        for name, value in [('CONFIG',self.config),('STATE',self.state)]:
            p=patch.object(w,name,value); p.start(); self.addCleanup(p.stop)
        for name, value in [('active',lambda:dict(self.displays)), ('monitors',lambda:[{'name':m} for m in self.displays]), ('set_wallpaper',set_wallpaper), ('apply_all',apply), ('run',run), ('extract',lambda p:{}), ('publish',publish)]:
            p=patch.object(w,name,side_effect=value);p.start();self.addCleanup(p.stop)
        p=patch.object(w.subprocess,'run',return_value=subprocess.CompletedProcess([],0));p.start();self.addCleanup(p.stop)
        self.session=w.Session('token',self.state/'recovery.json')
        self.config_before=self.config.read_bytes();self.theme_before=self.theme.read_bytes()
    async def request(self,op,**fields):
        return await self.session.request({'token':'token','op':op,**fields})
    async def test_preview_cancel_preserves_saved_state_and_each_monitor(self):
        await self.request('preview',image=str(self.new))
        self.assertEqual(set(self.displays.values()),{str(self.new)})
        self.assertEqual(self.config.read_bytes(),self.config_before)
        self.assertEqual(self.theme.read_bytes(),self.theme_before)
        await self.request('cancel')
        self.assertEqual(self.displays,self.original)
        self.assertFalse(self.session.journal.exists())
    async def test_commit_then_cancel_later_preview_restores_commit(self):
        await self.request('commit',image=str(self.new),mode='light')
        self.assertEqual(json.loads(self.theme.read_text())['mode'],'light')
        await self.request('preview',image=str(self.old))
        await self.request('cancel')
        self.assertEqual(set(self.displays.values()),{str(self.new)})
        self.assertEqual(json.loads(self.theme.read_text())['wallpaper'],str(self.new))
    async def test_failed_commit_rolls_back_wallpaper_and_files(self):
        with patch.object(w,'publish',side_effect=OSError('disk full')):
            with self.assertRaises(OSError): await self.request('commit',image=str(self.new))
        self.assertEqual(self.displays,self.original)
        self.assertEqual(self.config.read_bytes(),self.config_before)
        self.assertEqual(self.theme.read_bytes(),self.theme_before)
    async def test_queued_preview_latest_wins(self):
        async with self.session.mutex:
            first=asyncio.create_task(self.request('preview',image=str(self.old)))
            last=asyncio.create_task(self.request('preview',image=str(self.new)))
            await asyncio.sleep(0)
        a,b=await asyncio.gather(first,last)
        self.assertTrue(a['skipped'])
        self.assertEqual(set(self.displays.values()),{str(self.new)})
        await self.request('cancel')
    async def test_crash_recovery_restores_interrupted_commit(self):
        self.session.snapshot['committing']=True
        w.atomic(self.session.journal,self.session.snapshot)
        self.config.write_text('partial commit'); self.theme.write_text('{}')
        self.displays['A']=str(self.new)
        w.recover(self.session.journal)
        self.assertEqual(self.displays,self.original)
        self.assertEqual(self.config.read_bytes(),self.config_before)
        self.assertEqual(self.theme.read_bytes(),self.theme_before)
    async def test_lost_heartbeat_reverts(self):
        await self.request('preview',image=str(self.new))
        self.session.last_beat-=10
        await asyncio.wait_for(self.session.watch(),2)
        self.assertEqual(self.displays,self.original)
    async def test_window_close_reverts_even_with_heartbeat(self):
        await self.request('preview',image=str(self.new))
        with patch.object(w.subprocess,'run',return_value=subprocess.CompletedProcess([],1)):
            await asyncio.wait_for(self.session.watch(),2)
        self.assertEqual(self.displays,self.original)
    async def test_failed_rollback_retains_journal(self):
        await self.request('preview',image=str(self.new))
        with patch.object(w,'restore_snapshot',side_effect=OSError('backend unavailable')):
            with self.assertRaises(OSError): await self.request('cancel')
        self.assertTrue(self.session.journal.exists())
    async def test_foreign_session_cannot_mutate(self):
        with self.assertRaises(RuntimeError):
            await self.session.request({'token':'wrong','op':'preview','image':str(self.new)})
        self.assertEqual(self.displays,self.original)

if __name__=='__main__':unittest.main()
