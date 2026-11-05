import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gpu
class GpuTests(unittest.TestCase):
    def test_names_without_driver_access(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'data').mkdir(); state=root/'state'; state.mkdir()
            with patch.object(gpu,'ROOT',root),patch.object(gpu,'STATE',state),patch('subprocess.run',side_effect=AssertionError('GPU identity must not launch a process')):
                self.assertIsNone(gpu.gpu_name())
                (state/'gpu.json').write_text(json.dumps({'name':'NVIDIA GeForce RTX 4060 Laptop GPU'}))
                self.assertEqual(gpu.gpu_name(),'NVIDIA GeForce RTX 4060 Laptop GPU')
                (root/'data/gpu.json').write_text(json.dumps({'name':'NVIDIA GeForce RTX 4070 Laptop GPU'}))
                self.assertEqual(gpu.gpu_name(),'NVIDIA GeForce RTX 4070 Laptop GPU')
                (root/'data/gpu.json').write_text('invalid json')
                self.assertEqual(gpu.gpu_name(),'NVIDIA GeForce RTX 4060 Laptop GPU')
    def test_invalid_names(self):
        for name in (None,'','\x1b[31mGPU','{invalid}','line\nbreak'):
            self.assertFalse(gpu.valid_name(name))
