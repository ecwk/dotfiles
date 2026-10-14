import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import walltheme as w

class AppearanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root/'state/walltheme'
        self.config = self.root/'config'
        self.bar = self.config/'waybar'; self.bar.mkdir(parents=True)
        (self.bar/'style.css').write_text('@import "theme.css";')
        for name, value in [('STATE', self.state)]:
            p = patch.object(w, name, value); p.start(); self.addCleanup(p.stop)
        p = patch.dict(w.os.environ, XDG_CONFIG_HOME=str(self.config)); p.start(); self.addCleanup(p.stop)
        self.dark = {role:'#112233' for role in w.ROLES}
        self.light = {role:'#EEDDCC' for role in w.ROLES}
        self.record = {'wallpaper':'unchanged.jpg', 'mode':'dark', 'colors':self.dark,
                       'palettes':{'dark':self.dark, 'light':self.light}}
        w.atomic(self.state/'current.json', self.record)

    def test_mode_switch_keeps_wallpaper_and_palettes(self):
        with patch.object(w, 'apply_all') as wallpaper:
            result = w.theme_settings(mode='light')
            wallpaper.assert_not_called()
        record = json.loads((self.state/'current.json').read_text())
        self.assertEqual(record['wallpaper'], self.record['wallpaper'])
        self.assertEqual(record['palettes'], self.record['palettes'])
        self.assertEqual(record['colors'], self.light)
        self.assertEqual(result['mode'], 'light')
        self.assertIn('#EEDDCC', (self.bar/'theme.css').read_text())

    def test_styles_and_unknown_settings(self):
        w.atomic(self.state/'appearance.json', {'futureFeature':{'enabled':True}})
        w.theme_settings(style='accents')
        css = (self.bar/'theme.css').read_text()
        self.assertIn('#workspaces button.active', css)
        self.assertNotIn('window#waybar', css)
        self.assertTrue(json.loads((self.state/'appearance.json').read_text())['futureFeature']['enabled'])
        w.theme_settings(style='original')
        self.assertNotIn('#112233', (self.bar/'theme.css').read_text())
        w.theme_settings(style='full')
        self.assertIn('window#waybar', (self.bar/'theme.css').read_text())

    def test_migrates_dashboard_style(self):
        w.atomic(self.state.parent/'glass-dashboard/settings.json', {'theme_mode':'accents'})
        self.assertEqual(w.theme_settings()['style'], 'accents')

    def test_publish_refreshes_adapter_but_extract_does_not(self):
        with patch.object(w, 'extract', return_value=dict(self.record)):
            w.publish('new.jpg', 'light')
        self.assertIn('#EEDDCC', (self.bar/'theme.css').read_text())

    def test_missing_palette_falls_back_and_rejects_mode_change(self):
        (self.state/'current.json').unlink()
        self.assertFalse(w.theme_settings(style='full')['available'])
        with self.assertRaises(RuntimeError): w.theme_settings(mode='light')

    def test_invalid_color_cannot_enter_css(self):
        with self.assertRaises(RuntimeError): w.waybar_css('full', {'accent':'red;}'})
