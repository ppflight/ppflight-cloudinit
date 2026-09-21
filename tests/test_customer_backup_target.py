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
        with patch.object(m,'read',return_value={}), patch.object(m.subprocess,'run') as run:
            with self.assertRaises(ValueError): m.save('pve01','-')
            run.assert_not_called()
        with patch.object(m,'read',side_effect=[{'digest':'a'*40}, {'description':''}]), patch.object(m.subprocess,'run'):
            with self.assertRaises(ValueError): m.save('pve01','-')
