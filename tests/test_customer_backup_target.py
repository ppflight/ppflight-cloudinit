import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('backup_target', Path(__file__).resolve().parents[1] / 'tools/customer-backup-target.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class CustomerBackupTargetTest(unittest.TestCase):
    def test_notes_preservation_and_idempotency(self):
        notes = 'Operator notes\nKeep this exactly\n'
        merged = m.merge(notes, 'pbs-backup')
        self.assertTrue(merged.startswith(notes))
        self.assertEqual(merged, m.merge(merged, 'pbs-backup'))
        self.assertEqual({'state':'unset', 'storage_id':None}, m.parse(m.merge(merged, '-')))

    def test_invalid_or_duplicate_markers(self):
        for notes in [m.MARKER+'../x', m.MARKER+'a\n'+m.MARKER+'b', None]:
            self.assertEqual('invalid', m.parse(notes)['state'])
            with self.assertRaises(ValueError):
                m.merge(notes, 'pbs')

    def test_save_checks_storage_preserves_notes_and_uses_digest(self):
        rows = [{'storage':'pbs', 'enabled':1, 'active':1, 'content':'backup'}]
        notes = 'Keep operator notes'
        digest = 'a'*40
        with patch.object(m, 'read', side_effect=[rows, {'description':notes,'digest':digest}, {'description':m.merge(notes,'pbs')}]), patch.object(m.subprocess, 'run') as run:
            self.assertEqual('configured', m.save('pve01','pbs')['state'])
            args = run.call_args.args[0]
            self.assertEqual(['pvesh','set','/nodes/pve01/config','--description',m.merge(notes,'pbs'),'--digest',digest], args)
            run.assert_called_once()

    def test_unusable_storage_never_writes(self):
        for overrides in [{'active':0}, {'active':'0'}, {'enabled':0}, {'content':'images'}, {'storage':'foreign'}]:
            row = {'storage':'pbs','active':1,'enabled':1,'content':'backup'} | overrides
            with patch.object(m,'read', return_value=[row]), patch.object(m.subprocess,'run') as run:
                with self.assertRaises(ValueError): m.save('pve01','pbs')
                run.assert_not_called()

    def test_concurrent_config_change_is_not_overwritten(self):
        with patch.object(m,'read', return_value={'description':'notes','digest':'a'*40}), patch.object(m.subprocess,'run', side_effect=subprocess.CalledProcessError(1,'pvesh')) as run:
            with self.assertRaises(subprocess.CalledProcessError): m.save('pve01','-')
            run.assert_called_once()

    def test_missing_digest_or_failed_readback(self):
        with patch.object(m,'read',return_value={'description':'existing notes'}), patch.object(m.subprocess,'run') as run:
            with self.assertRaises(ValueError): m.save('pve01','-')
            run.assert_not_called()
        with patch.object(m,'read',side_effect=[{'digest':'a'*40}, {'description':''}]), patch.object(m.subprocess,'run'):
            with self.assertRaises(ValueError): m.save('pve01','-')

    def test_empty_node_initialization_still_requires_matching_readback(self):
        with patch.object(m,'read',side_effect=[{}, {'description':m.MARKER+'-'}]), patch.object(m.subprocess,'run') as run:
            self.assertEqual('unset', m.save('pve01','-')['state'])
            self.assertEqual(['perl','-e',m.INITIALIZE_EMPTY_CONFIG,'pve01',m.MARKER+'-\n'],run.call_args.args[0])

    def test_native_initialization_lock_rechecks_before_write(self):
        import tempfile, os, json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'PVE').mkdir()
            (root/'PVE/NodeConfig.pm').write_text(r'''
package PVE::NodeConfig;
use JSON::PP;
our $locked = 0;
sub lock_config { my ($node,$code)=@_; local $locked=1; $code->(); }
sub load_config { die 'unlocked read' unless $locked; return decode_json($ENV{TEST_CONFIG}); }
sub verify_conf { die 'invalid' unless $_[0]->{description} eq "PPFLIGHT_CUSTOMER_BACKUP_V1=-\n"; }
sub write_config { die 'unlocked write' unless $locked; open my $f, '>', $ENV{TEST_OUTPUT} or die; print $f encode_json($_[1]); close $f; }
1;
''')
            for config in [{}, {'description':'Someone edited this concurrently'}]:
                output=root/'written.json'
                output.unlink(missing_ok=True)
                env=dict(os.environ, PERL5LIB=tmp, TEST_CONFIG=json.dumps(config), TEST_OUTPUT=str(output))
                result=subprocess.run(['perl','-e',m.INITIALIZE_EMPTY_CONFIG,'pve01',m.MARKER+'-\n'],env=env,capture_output=True)
                self.assertEqual(config == {}, result.returncode == 0)
                self.assertEqual(config == {}, output.exists())
                if not config: self.assertEqual({'description':m.MARKER+'-\n'}, json.loads(output.read_text()))
