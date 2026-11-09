import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class FixedComputeTest(unittest.TestCase):
    def test_template_creation_explicitly_uses_fixed_hardware(self):
        source = (ROOT / "tools/build-template-engine.sh").read_text()
        create = source.split('  qm create "$vmid"', 1)[1].split('  CURRENT_VMID=', 1)[0]
        for value in ['--cores "$CORES"', '--sockets 1', '--numa 0', '--hotplug network,disk,usb']:
            self.assertIn(value, create)
        self.assertNotIn('--vcpus', create)
        self.assertNotIn('usb,cpu', create)
