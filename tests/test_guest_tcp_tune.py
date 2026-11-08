import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tcp_tune', ROOT/'tools/guest-tcp-tune.py')
tune = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tune)


class GuestTcpTests(unittest.TestCase):
    def test_actual_memory_parser_rejects_missing_or_invalid_values(self):
        self.assertEqual(786432 * 1024, tune.memory_bytes('MemTotal: 786432 kB\nMemFree: 1 kB'))
        for text in ('MemFree: 1 kB', 'MemTotal: 0 kB', 'MemTotal: 1024 MB', 'MemTotal: bad kB'):
            with self.assertRaises(ValueError):
                tune.memory_bytes(text)

    def test_low_memory_caps_are_never_overridden_by_reference_floor(self):
        for mib in (128, 256, 512, 768, 1024, 2048, 4096, 16384):
            with self.subTest(memory=mib):
                memory = mib * tune.MIB
                values = tune.calculate(memory)
                maximum = int(values['net.core.wmem_max'])
                self.assertLessEqual(maximum, memory * 4 // 100)
                self.assertLessEqual(maximum, 256 * tune.MIB)
                self.assertEqual(maximum, int(values['net.ipv4.tcp_rmem'].split()[-1]))
                self.assertEqual(values, tune.calculate(memory))
                self.assertNotIn('net.ipv4.tcp_mem', values)
                self.assertNotIn('net.ipv4.tcp_adv_win_scale', values)
                self.assertEqual('bbr', values['net.ipv4.tcp_congestion_control'])
        with self.assertRaises(ValueError):
            tune.calculate(0)

    def test_atomic_file_preserves_unrelated_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root/'sysctl.conf'
            original.write_text('net.ipv4.ip_forward=1\n')
            target = root/'sysctl.d/zz-ppflight-tcp.conf'
            text = tune.render(tune.calculate(768 * tune.MIB))
            tune.atomic_write(target, text)
            tune.atomic_write(target, text)
            self.assertEqual(text, target.read_text())
            self.assertEqual('net.ipv4.ip_forward=1\n', original.read_text())
            self.assertEqual(1, len(list(target.parent.iterdir())))
            self.assertEqual(0o644, target.stat().st_mode & 0o777)

    def test_unprivileged_invocation_has_no_effect(self):
        with patch.object(tune.os, 'geteuid', return_value=1000), patch.object(tune, 'atomic_write') as write:
            with self.assertRaises(RuntimeError):
                tune.apply()
            write.assert_not_called()

    def test_hook_runs_per_instance_not_inside_build_appliance(self):
        script = (ROOT/'tools/prepare-guest.sh').read_text()
        self.assertIn('/var/lib/cloud/scripts/per-instance/ppflight-tcp-tune', script)
        self.assertLess(script.index('cloud-init clean --logs --seed'), script.index('exec /usr/local/sbin/ppflight-tcp-tune'))
        self.assertNotIn('curl |', script)
        self.assertNotIn('swapon', (ROOT/'tools/guest-tcp-tune.py').read_text())


if __name__ == '__main__':
    unittest.main()
