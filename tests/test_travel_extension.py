"""Offline guards for the one-shot travel extension."""
import contextlib
import copy
import io
import struct
import unittest
from unittest.mock import patch

import verify_travel_extension as extension
import verify_travel_runtime as travel
from integration_inputs import require_inputs


class ExtensionTests(unittest.TestCase):
    def test_offline_plan(self):
        with contextlib.redirect_stdout(io.StringIO()), patch.object(extension, 'prior_evidence', side_effect=AssertionError('network')):
            self.assertEqual(extension.main([]), 0)

    def test_no_creation(self):
        runner = object.__new__(extension.ExtensionRunner)
        with self.assertRaisesRegex(RuntimeError, 'never creates'), runner.login('APV2F'):
            self.fail('creation allowed')

    def test_fast_cast_packet(self):
        self.assertEqual(travel.cast_packet(32242, 1), struct.pack('<BIBI', 1, 32242, 0, 0))
        with self.assertRaises(RuntimeError):
            travel.cast_packet(32243, 1)

    def test_pinned_evidence_and_dbc(self):
        require_inputs(*(extension.PRIOR / name for name in extension.HASHES),
                       extension.DBC_DIR / 'Spell.dbc')
        raw, prior = extension.prior_evidence()
        self.assertEqual(raw['seed_name'], extension.SEED)
        self.assertEqual(prior['progress'][0]['riding_flags'], 23)
        self.assertEqual(extension.fast_dbc()['name'], 'Swift Blue Gryphon')

    def test_tampered_creation_hash_refused(self):
        require_inputs(*(extension.PRIOR / name for name in extension.HASHES))
        hashes = dict(extension.HASHES, **{'creation.json': '0' * 64})
        with patch.object(extension, 'HASHES', hashes), self.assertRaisesRegex(RuntimeError, 'hash mismatch'):
            extension.prior_evidence()

    def test_binding_only_excludes_mutable_heartbeat_and_status(self):
        row = dict(id=14, manifest_hash='abc', heartbeat='old', status='disconnected')
        changed = dict(row, heartbeat='new', status='connected')
        self.assertEqual(extension.immutable(row), extension.immutable(changed))
        changed['manifest_hash'] = 'wrong'
        self.assertNotEqual(extension.immutable(row), extension.immutable(changed))

    def test_ownership_guards_run_before_allowlist_seeding(self):
        require_inputs(*(extension.PRIOR / name for name in extension.HASHES))
        raw, prior = extension.prior_evidence()
        for field, value in (('name', 'Wrongname'), ('account', 8), ('race', 2),
                             ('class', 2), ('level', 76), ('online', 1)):
            with self.subTest(field=field):
                runner = object.__new__(extension.ExtensionRunner)
                runner.known, runner.names = set(), {}
                runner.account_row = lambda _: dict(id=7, username='APV2F',
                    email=extension.shared.MARKER, security=0, online=0)
                row = dict(prior['location'], **{field: value})
                runner.character = lambda _: row
                runner.query = lambda *_: [dict(guid=24, name=extension.NAME)]
                with self.assertRaises(RuntimeError):
                    runner.verify_owned(raw, prior)
                self.assertEqual(runner.known, set())
                self.assertEqual(runner.names, {})

    def test_old_receipt_changes_refused(self):
        runner = object.__new__(extension.ExtensionRunner)
        runner.original_rewards = [dict(item_index=i, applied=1) for i in range(13)]
        runner.original_binding = {'id': 14}
        runner.binding_row = lambda: {'id': 14}
        rows = copy.deepcopy(runner.original_rewards)
        rows[0]['applied'] = 0
        runner.query = lambda *_: rows
        with self.assertRaisesRegex(RuntimeError, 'Old receipts'):
            runner.assert_history()


if __name__ == '__main__':
    unittest.main()
