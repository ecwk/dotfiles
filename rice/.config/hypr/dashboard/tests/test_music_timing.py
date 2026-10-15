"""Clock-based progress between authoritative MPRIS snapshots."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import MusicWidget

class ProgressTiming(unittest.TestCase):
    def render(self,seconds,status='Playing',rate=1.0,position=10_000_000,length=60_000_000):
        widget=SimpleNamespace(position=position,position_at=100,
            props={'PlaybackStatus':status,'Rate':rate,'Metadata':{'mpris:length':length}},
            progress=Mock(),elapsed=Mock(),remaining=Mock())
        with patch('app.time.monotonic',return_value=100+seconds):
            self.assertTrue(MusicWidget.update_progress(widget))
        return widget
    def test_progress_advances_between_polls(self):
        widget=self.render(.5)
        widget.progress.set_fraction.assert_called_with(10.5/60)
        self.render(1).elapsed.set_text.assert_called_with('0:11')
    def test_paused_and_stopped_do_not_advance(self):
        for status in ('Paused','Stopped'):
            self.render(5,status).elapsed.set_text.assert_called_with('0:10')
    def test_playback_rate_and_seek_anchor(self):
        self.render(2,rate=2,position=30_000_000).elapsed.set_text.assert_called_with('0:34')
    def test_end_and_unknown_duration(self):
        self.render(100).progress.set_fraction.assert_called_with(1)
        self.render(100).remaining.set_text.assert_called_with('-0:00')
        self.render(1,length=0).elapsed.set_text.assert_called_with('')

if __name__=='__main__': unittest.main()
