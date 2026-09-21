import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('repair', Path(__file__).resolve().parents[1] / 'tools/repair-uefi-boot.py')
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)

class RepairSafetyTests(unittest.TestCase):
    def setUp(self):
        self.config = {'template': 1, 'name': 'ubuntu-2404', 'tags': 'ppflight-cloudinit', 'bios': 'ovmf', 'boot': 'order=scsi0', 'ide2': 'vpspool:vm-9001-cloudinit,media=cdrom', 'digest': 'a' * 40}

    def test_only_known_template_boot_orders_are_allowed(self):
        for boot in ('order=scsi0', repair.BOOT):
            self.config['boot'] = boot
            repair.validate(self.config, {'status': 'stopped'}, 'ubuntu-2404')

    def test_rejects_ordinary_running_locked_foreign_and_custom_guests(self):
        for key, value in [('template', 0), ('name', 'other'), ('tags', 'foreign'), ('bios', 'seabios'), ('lock', 'clone'), ('boot', 'order=net0;scsi0'), ('ide2', 'local:iso/custom.iso,media=cdrom'), ('digest', '')]:
            with self.subTest(key=key):
                config = copy.deepcopy(self.config)
                config[key] = value
                with self.assertRaises(ValueError):
                    repair.validate(config, {'status': 'stopped'}, 'ubuntu-2404')
        with self.assertRaises(ValueError):
            repair.validate(self.config, {'status': 'running'}, 'ubuntu-2404')
