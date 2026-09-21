import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

existing = load('template-existing')
prepare = load('prepare-image')
qga = load('configure-qga')


class QgaPolicyTests(unittest.TestCase):
    def test_distribution_allowlist_is_extended_without_enabling_file_access(self):
        before='FILTER_RPC_ARGS="--allow-rpcs=guest-ping,guest-info"\n'
        after=qga.environment(before)
        self.assertIn('guest-exec,guest-exec-status',after)
        self.assertNotIn('guest-file-open',after)
        self.assertIn('guest-ping,guest-info',after)
        self.assertEqual(after,qga.environment(after))

    def test_old_blacklist_keeps_unrelated_restrictions(self):
        self.assertEqual('BLACKLIST_RPC="guest-file-open"\n',qga.environment('BLACKLIST_RPC="guest-file-open,guest-exec,guest-exec-status"\n'))
        self.assertEqual('# BLACKLIST_RPC="guest-exec"\n',qga.environment('# BLACKLIST_RPC="guest-exec"\n'))
        self.assertIn('block-rpcs = guest-file-open',qga.configuration('[general]\nblock-rpcs = guest-exec,guest-file-open\n'))

    def test_unknown_filter_cannot_be_silently_overridden(self):
        with self.assertRaises(ValueError):
            qga.environment('FILTER_RPC_ARGS="--unknown=all"\n')


class ReplacementTests(unittest.TestCase):
    def test_vmids_are_cluster_scoped_and_fail_closed(self):
        template = {'vmid': 9000, 'node': 'pve01', 'type': 'qemu', 'template': 1}
        self.assertEqual('missing', existing.locate([], 9000, 'pve01'))
        self.assertEqual('present', existing.locate([template], 9000, 'pve01'))
        for changes in ({'node': 'pve02'}, {'type': 'lxc'}, {'template': 0}):
            with self.assertRaises(ValueError):
                existing.locate([dict(template, **changes)], 9000, 'pve01')
        for rows in ([template, template], {}, [{}]):
            with self.assertRaises(ValueError):
                existing.locate(rows, 9000, 'pve01')

    def test_ownership_lock_and_config_changes_block_replacement(self):
        config = {'template': 1, 'name': 'ubuntu-2404', 'tags': 'ppflight-cloudinit', 'digest': 'a'*40}
        self.assertEqual('a'*40, existing.managed(config, 'ubuntu-2404'))
        for changes in ({'lock': 'clone'}, {'name': 'foreign'}, {'template': 0}, {'tags': 'ppflight-cloudinit-build'}, {'digest': ''}):
            with self.assertRaises(ValueError):
                existing.managed(dict(config, **changes), 'ubuntu-2404')
        with self.assertRaises(ValueError):
            existing.managed(config, 'ubuntu-2404', 'b'*40)

    def test_linked_clones_and_unknown_state_are_rejected(self):
        existing.validate_clones('pool/base-9000-disk-0@__base__\t-')
        existing.validate_clones('')
        for output in ('pool/base@__base__\tpool/vm-100-disk-0', 'unknown', 'pool/base@snap\t'):
            with self.assertRaises(ValueError):
                existing.validate_clones(output)

    def test_zfs_dependencies_are_checked_for_all_template_volumes(self):
        commands = []
        def read(args):
            commands.append(args)
            if args[0] == 'pvesh':
                if args[2].endswith('/config'):
                    return json.dumps({'template':1, 'name':'test', 'tags':'ppflight-cloudinit','digest':'a'*40,'scsi0':'vpspool:base-9000-disk-0,size=16G','ide2':'vpspool:vm-9000-cloudinit,media=cdrom'})
                if args[2].endswith('/current'):
                    return '{"status":"stopped"}'
                return '{"type":"zfspool","pool":"vpspool"}'
            if 'name,clones' in args:
                return args[-1]+'@__base__\t-'
            return 'volume'
        with patch.object(existing, 'read', side_effect=read), patch('pathlib.Path.glob', return_value=[]):
            self.assertEqual('a'*40, existing.replace_check(9000, 'test', 'pve01'))
        self.assertEqual(2, len([c for c in commands if 'name,clones' in c]))


class PreparationTests(unittest.TestCase):
    def test_only_supported_unambiguous_root_partitions_expand(self):
        self.assertEqual('/dev/sda4', prepare.root_partition('/dev/sda2: /boot\n/dev/sda4: /'))
        for output in ('/dev/mapper/root: /', '/dev/sda1: /boot', '/dev/sda2: /\n/dev/sda3: /'):
            with self.assertRaises(ValueError):
                prepare.root_partition(output)

    def test_preparation_failure_keeps_official_source_and_removes_partial_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'official.img'; target = root/'prepared.img'; profile = root/'profile.sh'
            source.write_bytes(b'official'); profile.write_text('exit 1')
            def run(args, capture=False, timeout=7200):
                if args[:2] == ['qemu-img', 'info']:
                    return '{"format":"qcow2","virtual-size":1024}'
                if 'vfs-uuid' in args:
                    return '12345678-1234-1234-1234-123456789abc'
                if args[0] == 'guestfish':
                    return '/dev/sda1: /'
                if args[:2] == ['qemu-img', 'create']:
                    target.write_bytes(b'partial')
                    return ''
                raise subprocess.CalledProcessError(1, args)
            with patch.object(prepare, 'run', side_effect=run), patch.object(prepare.shutil, 'disk_usage') as usage:
                usage.return_value.free = 30*1024**3
                with self.assertRaises(subprocess.CalledProcessError):
                    prepare.prepare(source, target, '16G', profile)
            self.assertEqual(b'official', source.read_bytes())
            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix('.json').exists())

    def test_success_records_actual_prepared_hash_and_guest_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source=root/'official.img'; target=root/'prepared.img'; profile=root/'profile.sh'
            source.write_bytes(b'official'); profile.write_text('exit 0')
            commands=[]
            def run(args, capture=False, timeout=7200):
                commands.append(args)
                if args[:2] == ['qemu-img','info']:
                    return '{"format":"qcow2","virtual-size":1024}'
                if 'vfs-uuid' in args:
                    return '12345678-1234-1234-1234-123456789abc'
                if 'mountpoints' in args:
                    return '/dev/sda1: /'
                if args[:2] == ['qemu-img','create']:
                    target.write_bytes(b'prepared')
                if args[-1] == '/var/lib/ppflight-template/packages.tsv':
                    return 'qemu-guest-agent\t1.0\ncloud-init\t1.0'
                if 'cat' in args:
                    return 'updated_at_utc=2026-09-21T00:00:00Z\nautomatic_upgrades=disabled'
                return ''
            with patch.object(prepare,'run',side_effect=run), patch.object(prepare.shutil,'disk_usage') as usage:
                usage.return_value.free=30*1024**3
                prepare.prepare(source,target,'16G',profile)
            self.assertEqual(b'official',source.read_bytes())
            self.assertEqual(prepare.file_hash(target),json.loads(target.with_suffix('.json').read_text())['preparedSha256'])
            customize=next(c for c in commands if c[0]=='virt-customize')
            self.assertIn('--run-command',customize)
            self.assertIn('bash /var/tmp/ppflight-prepare-guest.sh',customize)
            self.assertNotIn('--firstboot',customize)

    def test_no_preparation_can_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'image'; path.write_bytes(b'keep')
            with self.assertRaises(ValueError):
                prepare.prepare(path,path,'16G',path)
            self.assertEqual(b'keep',path.read_bytes())


class FirmwareTests(unittest.TestCase):
    def test_uefi_requires_an_esp_before_creating_any_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'source'; target=root/'target'; profile=root/'profile'
            source.write_bytes(b'original'); profile.write_text('')
            def run(args, capture=False, timeout=7200):
                if args[:2] == ['qemu-img', 'info']:
                    return '{"format":"qcow2","virtual-size":1024}'
                if args[-1] == 'mountpoints': return '/dev/sda1: /'
                raise AssertionError('No write is permitted without an ESP')
            with patch.object(prepare, 'run', side_effect=run), patch.object(prepare.shutil,'disk_usage') as usage:
                usage.return_value.free=30*1024**3
                with self.assertRaisesRegex(ValueError, 'EFI System Partition'):
                    prepare.prepare(source,target,'16G',profile,'ovmf')
            self.assertFalse(target.exists())
            self.assertEqual(b'original',source.read_bytes())

    def test_validation_uses_fresh_unsigned_efi_variables_and_leaves_vendor_firmware_unchanged(self):
        boot=load('verify-guest-boot')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); vendor=root/'vendor'; vendor.mkdir(); work=root/'work'; work.mkdir()
            (vendor/'OVMF_CODE_4M.fd').write_bytes(b'code')
            (vendor/'OVMF_VARS_4M.fd').write_bytes(b'unsigned-vars')
            args=boot.firmware_arguments('ovmf',work,vendor)
            self.assertIn('readonly=on',args[1])
            self.assertIn(str(work/'efi-vars.fd'),args[3])
            (work/'efi-vars.fd').write_bytes(b'changed-by-guest')
            self.assertEqual(b'unsigned-vars',(vendor/'OVMF_VARS_4M.fd').read_bytes())
            self.assertEqual([],boot.firmware_arguments('seabios',work,vendor))
            with self.assertRaises(ValueError): boot.firmware_arguments('unknown',work,vendor)
            (vendor/'OVMF_CODE_4M.fd').unlink()
            with self.assertRaises(ValueError): boot.firmware_arguments('ovmf',work,vendor)

    def test_catalog_has_ten_uefi_and_two_distinct_legacy_templates(self):
        d=json.loads((ROOT/'catalog/template-catalog.v1.json').read_text())
        actual={i['target']['vmid']:i['target']['firmware'] for i in d['items']}
        self.assertEqual({**dict.fromkeys(range(9000,9010),'ovmf'),9010:'seabios',9011:'seabios'},actual)
        self.assertEqual(['ubuntu-2404-legacy','debian-12-legacy'],[i['templateRef'] for i in d['items'][-2:]])

if __name__ == '__main__':
    unittest.main()
