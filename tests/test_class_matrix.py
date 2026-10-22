"""Small offline selector/guard checks. No database, sockets, Docker or credentials."""
import ast
from contextlib import redirect_stdout, contextmanager
from copy import deepcopy
import io
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

import verify_class_matrix as matrix
import verify_runtime as runtime
from bridge.catalog import Catalog, ProtocolError
from verify_runtime import MARKER


class FakeStore:
    """Validate the full manifest, with seed/character-scoped append-only history."""
    def __init__(self, catalog, guid):
        self.catalog, self.guid = catalog, guid
        self.history = []
        self.binding = None

    def bind(self, seed, raw):
        if self.binding is not None:
            raise RuntimeError('Never rebind or erase a failed fixture')
        parsed = self.catalog.parse(raw, seed, 1)
        self.binding = (self.guid, seed, parsed.checksum)
        return self.binding

    def receive(self, index, codes):
        if index < len(self.history):
            return self.history[index:index + len(codes)] == codes
        if index != len(self.history):
            return False
        self.history.extend(codes)
        return True


class MatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog()
        rows = {}
        for ability in cls.catalog.abilities:
            for rank in ability['prerequisites']:
                if rank['kind'] == 'rank_eligibility':
                    row = [0] * 40
                    row[39] = rank['min_level']
                    rows[rank['spell_id']] = row
        for _, _, spell in matrix.PROFILES:
            rows[spell] = [0] * 39 + [1]
        rows[168] = [0] * 39 + [1]
        cls.spells = SimpleNamespace(rows=rows)
        cls.plan = matrix.plan(cls.catalog, cls.spells)

    def test_exact_nine_legal_profiles_both_factions_no_dk(self):
        profiles = [c['profile'] for c in self.plan['cases']]
        self.assertEqual({p['class_id'] for p in profiles}, {1, 2, 3, 4, 5, 7, 8, 9, 11})
        self.assertEqual({p['faction'] for p in profiles}, {'alliance', 'horde'})
        self.assertTrue(all(p in self.catalog.profiles for p in profiles))
        self.assertEqual(next(p['race_id'] for p in profiles if p['class_id'] == 3), 2)

    def test_subset_uses_only_exact_catalog_profiles_and_two_slots(self):
        plan = matrix.plan(self.catalog, self.spells, classes=[9, 11])
        self.assertEqual([c['profile']['class_id'] for c in plan['cases']], [9, 11])
        self.assertEqual([c['profile']['race_id'] for c in plan['cases']], [1, 4])
        self.assertEqual([c['chain']['ranks'] for c in plan['cases']], [[5782, 6213], [2637, 18657]])
        self.assertEqual(plan['capacity']['planned_creates'], 2)
        self.assertEqual(plan['budget']['hard_stop_seconds'], 1800)
        self.assertEqual(len(matrix.capacity_budget(plan['cases'], self.snapshots())['assignments']), 2)

    def test_invalid_subsets_reject_before_plan_database_or_auth(self):
        for classes in ([6], [99], [9, 9], []):
            with self.subTest(classes=classes), self.assertRaises(RuntimeError):
                matrix.plan(self.catalog, self.spells, classes=classes)
        for values in (['6'], ['99'], ['9', '9']):
            with patch.object(matrix, 'plan', side_effect=AssertionError('plan')), \
                 patch.object(matrix, 'released_evidence', side_effect=AssertionError('runtime')), \
                 self.assertRaisesRegex(RuntimeError, 'legal matrix subset'):
                matrix.main(['--run', '--classes', *values])

    def test_final_two_release_exact_selection_and_limit_before_runtime(self):
        good = dict(owned_release=True, mail_lifetime_fixed=True, authorized_classes=[9, 11],
                    creation_limit=2, prior_partial_guid_preserved=39)
        matrix.authorize_selection(good, [9, 11])
        for change in ({'authorized_classes': [9]}, {'authorized_classes': [11, 9]},
                       {'authorized_classes': [9, 11, 1]}, {'creation_limit': 9},
                       {'prior_partial_guid_preserved': None}):
            with tempfile.TemporaryDirectory() as directory, patch.object(matrix, 'OUTPUT', Path(directory)), \
                 patch.object(matrix, 'released_evidence', side_effect=AssertionError('runtime')):
                (matrix.OUTPUT / 'release.json').write_text(json.dumps(good | change))
                with self.assertRaisesRegex(RuntimeError, 'exactly selected classes'):
                    matrix.main(['--run', '--classes', '9', '11'])
        with self.assertRaises(RuntimeError):
            matrix.authorize_selection(good, matrix.selected_classes())

    def test_main_passes_subset_to_offline_plan(self):
        with patch.object(matrix, 'plan', return_value=self.plan) as plan, redirect_stdout(io.StringIO()):
            matrix.main(['--classes', '9', '11'])
        plan.assert_called_once_with(classes=[9, 11])

    def test_live_main_passes_two_case_plan_and_fixed_budget(self):
        prepared = matrix.plan(self.catalog, self.spells, classes=[9, 11])
        release = dict(owned_release=True, mail_lifetime_fixed=True, authorized_classes=[9, 11],
                       creation_limit=2, prior_partial_guid_preserved=39)
        with tempfile.TemporaryDirectory() as directory, patch.object(matrix, 'OUTPUT', Path(directory)), \
             patch.object(matrix, 'released_evidence', return_value={}), \
             patch('verify_crash_runtime.no_other_runners'), \
             patch.object(matrix, 'plan', return_value=prepared) as plan, \
             patch.object(matrix, 'execute_matrix') as execute, \
             patch.object(matrix.time, 'monotonic', return_value=100), \
             patch('pymysql.connect') as connect, \
             patch.dict(matrix.os.environ, {'WOWPILAGO_TEST_ACCOUNT_PASSWORD': 'test-only',
                                            'WOWPILAGO_DB_PASSWORD': 'test-only'}):
            (matrix.OUTPUT / 'release.json').write_text(json.dumps(release))
            self.assertEqual(matrix.main(['--run', '--classes', '9', '11']), 0)
            plan.assert_called_once_with(classes=[9, 11])
            args = execute.call_args.args
            self.assertIs(args[0], connect.return_value.__enter__.return_value)
            self.assertIs(args[1], prepared)
            self.assertEqual(args[3], 1900)
            self.assertTrue((matrix.OUTPUT / 'attempt.json').is_file())

    def test_catalog_drift_fails(self):
        catalog = deepcopy(self.catalog)
        catalog.version = 'old'
        with self.assertRaisesRegex(RuntimeError, 'Catalog changed'):
            matrix.select_profiles(catalog)

    def test_full_manifests_scoped_and_immutable_in_fake_store(self):
        stores = []
        for guid, case in enumerate(self.plan['cases'], 100):
            raw = deepcopy(case['manifest'])
            original = deepcopy(raw)
            store = FakeStore(self.catalog, guid)
            store.bind(case['seed'], raw)
            self.assertTrue(store.receive(0, [case['chain']['ap_id']]))
            saved = deepcopy(store.history)
            self.assertTrue(store.receive(0, saved))
            self.assertFalse(store.receive(0, [919100001]))
            self.assertFalse(store.receive(3, [919100001]))
            self.assertEqual(store.history, saved)
            with self.assertRaises(RuntimeError):
                store.bind(case['seed'] + '-retry', raw)
            self.assertEqual(raw, original)
            self.assertEqual(raw['catalog_version'], matrix.SEMANTIC)
            self.assertEqual(len(raw['merchant']['stock']), 30)
            stores.append(store)
        self.assertEqual(len({s.binding for s in stores}), 9)
        self.assertEqual(len({s.binding[1] for s in stores}), 9)

    def test_cross_seed_and_cross_class_manifests_rejected(self):
        case = self.plan['cases'][0]
        with self.assertRaises(ProtocolError):
            FakeStore(self.catalog, 99).bind('wrong-seed', case['manifest'])
        raw = deepcopy(case['manifest'])
        raw['profile'] = self.plan['cases'][1]['profile']
        with self.assertRaises(ProtocolError):
            self.catalog.parse(raw, case['seed'], 1)

    def test_dk_profile_and_manifest_rejected(self):
        raw = deepcopy(self.plan['cases'][0]['manifest'])
        raw['profile']['class_id'] = 6
        with self.assertRaisesRegex(ProtocolError, 'Death Knights'):
            self.catalog.parse(raw, raw['seed_name'], 1)
        with self.assertRaises(RuntimeError):
            matrix.class_manifest(self.catalog, raw['profile'], raw['seed_name'])
        self.assertEqual(self.plan['dk']['normal_start_level'], 55)
        self.assertEqual(self.plan['dk']['live'], 'NOT EXECUTED')

    def test_rank_selection_is_class_specific_and_uses_normal_dbc_levels(self):
        for case in self.plan['cases']:
            chain = case['chain']
            self.assertEqual(chain['levels'], [self.spells.rows[s][39] for s in chain['ranks']])
            self.assertGreater(chain['levels'][0], 1)
            self.assertGreater(chain['levels'][1], chain['levels'][0])
            self.assertIn(str(chain['ap_id']), case['manifest']['rewards'])
            if case['profile']['class_id'] != 1:
                self.assertNotIn(100, chain['ranks'])
        self.assertEqual(len({c['chain']['base_spell'] for c in self.plan['cases']}), 9)

    def test_no_unearned_form_or_consumable_setup_in_selected_chain(self):
        for case in self.plan['cases']:
            for prerequisite in case['chain']['prerequisites']:
                if prerequisite['kind'] == 'baseline_spells':
                    self.assertEqual(case['profile']['class_id'], 1)
                    self.assertEqual(prerequisite['spell_ids'], [2457])
                if prerequisite['kind'] == 'rank_eligibility':
                    for key in ('required_spell', 'required_skill', 'required_skill_rank',
                                'totem_items', 'totem_categories', 'reagents'):
                        self.assertFalse(prerequisite[key])

    def test_dbc_catalog_level_mismatch_rejected(self):
        spells = deepcopy(self.spells)
        spells.rows[100][39] = 1
        with self.assertRaisesRegex(RuntimeError, 'normal levels disagree'):
            matrix.select_chain(self.catalog, 1, spells)

    def snapshots(self, count=8):
        return {a: (dict(id=i, username=a, email=MARKER, security=0, online=0), count)
                for i, a in enumerate(matrix.ACCOUNTS, 3)}

    def test_capacity_reserves_exactly_nine_without_test_creation(self):
        budget = matrix.capacity_budget(self.plan['cases'], self.snapshots())
        self.assertEqual(len(budget['assignments']), 9)
        self.assertEqual(sum(budget['remaining'].values()), 1)
        self.assertTrue(all(x['account'] in matrix.ACCOUNTS for x in budget['assignments']))

    def test_reviewed_namespace_preserves_previous_attempts(self):
        self.assertEqual(matrix.OUTPUT, matrix.ROOT / '.local/class-matrix-plan/final-two')
        self.assertEqual(matrix.BUDGET_SECONDS, 3600)

    def test_capacity_skips_full_b_and_reserves_nine_fresh_slots(self):
        snapshots = self.snapshots(0)
        row, _ = snapshots['APV2B']
        snapshots['APV2B'] = (row, 10)
        budget = matrix.capacity_budget(self.plan['cases'], snapshots)
        self.assertEqual(len(budget['assignments']), 9)
        self.assertEqual({a['account'] for a in budget['assignments']}, {'APV2C'})
        self.assertEqual(budget['remaining']['APV2B'], 0)

    def test_capacity_fails_closed_no_partial_allocation(self):
        snapshots = self.snapshots(10)
        before = deepcopy(snapshots)
        with self.assertRaisesRegex(RuntimeError, 'Insufficient capacity'):
            matrix.capacity_budget(self.plan['cases'], snapshots)
        self.assertEqual(snapshots, before)
        for changes in ({'security': 3}, {'online': 1}, {'email': ''}, {'username': 'APV2A'}):
            snapshots = self.snapshots()
            row, count = snapshots['APV2B']
            snapshots['APV2B'] = (row | changes, count)
            with self.assertRaises(RuntimeError):
                matrix.capacity_budget(self.plan['cases'], snapshots)

    def test_fresh_offline_actual_profile_before_login_and_bind(self):
        profile = self.plan['cases'][2]['profile']
        row = dict(guid=99, account=3, name='Apsfixture', race=2, **{'class': 3}, online=0, level=1)
        args = dict(account_id=3, name='Apsfixture', profile=profile, known={99}, bindings=[])
        matrix.fixture_guard(row, **args)
        for changes in ({'guid': 4}, {'race': 1}, {'class': 1}, {'online': 1}, {'level': 55}, {'account': 1}):
            with self.assertRaises(RuntimeError):
                matrix.fixture_guard(row | changes, **args)
        with self.assertRaises(RuntimeError):
            matrix.fixture_guard(row, **(args | dict(bindings=[{'id': 7}])))
        with self.assertRaises(RuntimeError):
            matrix.fixture_guard(row, **(args | dict(known=set())))

    def test_setup_allowlist_only_selected_spells_and_forward_caps(self):
        runner = object.__new__(matrix.MatrixRunner)
        runner.case = self.plan['cases'][0]
        self.assertEqual(runner.setup_command('Apsfixture', '.learn 100', 1, 10), '.learn 100')
        runner.setup_command('Apsfixture', '.levelup Apsfixture 2', 1, 10)
        for command in ('.learn 133', '.levelup Apsfixture -1', '.modify xp 100',
                        '.levelup Apsfixture 25', '.learn all', '.character deleted restore'):
            with self.assertRaises(RuntimeError):
                runner.setup_command('Apsfixture', command, 1, 10)

    def test_matrix_login_rejects_protected_accounts_reuse_and_gm_creation(self):
        runner = self.runner()
        for account, guid in (('APV2A', None), ('TEST', None), ('TEST', 14), ('APV2B', 13)):
            with self.subTest(account=account, guid=guid), self.assertRaises(RuntimeError), \
                 runner.login(account, guid=guid):
                self.fail('Unsafe login entered')

    def runner(self, case=None):
        with patch.object(matrix.Runner, 'query', return_value=[]):
            return matrix.MatrixRunner(Mock(), 'APV2B', case or self.plan['cases'][0])

    def test_default_and_run_never_probe_or_authenticate(self):
        with patch.object(matrix.artisan, 'docker', side_effect=AssertionError('docker')), \
             patch('verify_runtime.authenticate', side_effect=AssertionError('auth')), \
             patch.object(matrix, 'released_evidence', side_effect=AssertionError('release')), \
             patch.object(matrix, 'plan', return_value=self.plan), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(matrix.main([]), 0)
            self.assertEqual(json.loads(output.getvalue())['status'], 'PREPARED_NOT_EXECUTED')
            with tempfile.TemporaryDirectory() as directory, patch.object(matrix, 'OUTPUT', Path(directory)):
                with self.assertRaisesRegex(RuntimeError, 'Explicit matrix parent release'):
                    matrix.main(['--run'])

    def test_pending_build_stops_before_runtime(self):
        with patch.object(matrix.artisan.Path, 'read_text', return_value='{"status":"building"}'), \
             patch.object(matrix.artisan, 'runtime_evidence', side_effect=AssertionError('runtime')):
            with self.assertRaisesRegex(RuntimeError, 'not successful'):
                matrix.released_evidence()

    def test_apworld_has_no_dk_option(self):
        tree = ast.parse((matrix.ROOT / 'apworld/wowpilago/options.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'CharacterClass')
        values = [n.value.value for n in cls.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id.startswith('option_') for t in n.targets)]
        self.assertEqual(set(values), {1, 2, 3, 4, 5, 7, 8, 9, 11})

    def test_matrix_release_and_preserved_manifest_required(self):
        evidence = dict(manifest_sha256='m', world_sha256=matrix.WORLD)
        base = '0edea8dba721f996f00cf0b5c95e3576fff1ad4dd6e637fd8c0ad45b06f1285b'
        good = dict(owned_release=True, mail_lifetime_fixed=True, manifest_sha256='m',
                    world_sha256=matrix.WORLD, base_manifest_sha256=base,
                    patch_sha256='76342b88b9864f85525771ba51de7c2b78467343027075b83184bc76356aca6c')
        for change in ({}, {'mail_lifetime_fixed': False}, {'world_sha256': 'old'},
                       {'manifest_sha256': 'old'}, {'base_manifest_sha256': 'old'}, {'patch_sha256': 'old'}):
            with self.subTest(change=change), \
                 patch.object(matrix.artisan, 'build_evidence', return_value=evidence), \
                 patch.object(matrix.artisan, 'runtime_evidence', return_value={}), \
                 patch.object(matrix.Path, 'read_text', autospec=True, side_effect=lambda p: json.dumps(
                     {'src/server/game/Spells/Auras/' + n: base for n in ('SpellAuras.cpp', 'SpellAuraDefines.h')}
                     if p.name == 'source-files.sha256.json' else good | change)), \
                 patch.object(matrix.artisan, 'digest', return_value=base):
                if change:
                    with self.assertRaises(RuntimeError):
                        matrix.released_evidence()
                else:
                    self.assertEqual(matrix.released_evidence()['build'], evidence)

    def test_profile_mismatch_blocks_very_first_login_packet_all_nine_profiles(self):
        realm = SimpleNamespace(locked=False, flags=0)
        for case in self.plan['cases']:
            profile = case['profile']
            for field in ('race', 'class'):
                runner = self.runner(case)
                runner.account_row = Mock(return_value=dict(id=9, username='APV2B', email=MARKER, online=0, security=0))
                runner.query = Mock(side_effect=lambda sql, args=(): [{'n': 0}] if 'COUNT(*)' in sql else [])
                sock = Mock()
                wrong = dict(guid=99, account=9, name='', race=profile['race_id'],
                             **{'class': profile['class_id']}, level=1, online=0)
                wrong[field] = 99

                def connect(client, account, auth, selected_realm, name, **kwargs):
                    self.assertEqual(kwargs, dict(race=profile['race_id'], class_id=profile['class_id']))
                    wrong['name'] = name
                    client.events.append('CREATED ' + name)
                    client.send(0x3D, struct.pack('<Q', 99))
                    self.fail('First wrong-profile login passed')

                runner.character = Mock(side_effect=lambda guid: wrong)
                with self.subTest(profile=profile, field=field), \
                     patch.object(runtime, 'authenticate', return_value=SimpleNamespace(realms=[realm])), \
                     patch.object(runtime.socket, 'create_connection') as connection, \
                     patch.dict(runtime.os.environ, {'WOWPILAGO_TEST_ACCOUNT_PASSWORD': 'test-only'}), \
                     patch.object(matrix.MatrixClient, 'connect', connect):
                    connection.return_value.__enter__.return_value = sock
                    with self.assertRaisesRegex(RuntimeError, 'profile mismatch'), runner.login('APV2B'):
                        self.fail('Wrong profile entered')
                    sock.sendall.assert_not_called()

    def test_correct_native_creation_and_first_login_use_each_exact_profile(self):
        for case in self.plan['cases']:
            runner = self.runner(case)
            profile = case['profile']
            runner.pending_name = 'Apsfixture'
            runner.names[99] = runner.pending_name
            runner.known.add(99)
            row = dict(guid=99, account=9, name='Apsfixture', race=profile['race_id'],
                       **{'class': profile['class_id']}, level=1, online=0)
            runner.character = Mock(return_value=row)
            runner.account_row = Mock(return_value=dict(id=9))
            runner.query = Mock(return_value=[])
            authorize = lambda guid, events: runtime.guard_character(
                row, 9, 'Apsfixture', {99}, expected_profile=profile)
            sock = Mock()
            client = matrix.MatrixClient(sock, authorize, runner, False)
            creation = runtime.create_character('Apsfixture', race=profile['race_id'], class_id=profile['class_id'])
            with redirect_stdout(io.StringIO()):
                client.send(0x36, creation)
                client.send(0x3D, struct.pack('<Q', 99))
            self.assertEqual(sock.sendall.call_args_list[0].args[0][6:], creation)
            self.assertEqual(sock.sendall.call_args_list[1].args[0],
                             bytes.fromhex('000c3d0000006300000000000000'))

    def test_relogs_pass_exact_profile_and_test_control_keeps_default(self):
        runner = self.runner(self.plan['cases'][2])
        runner.guid = 99
        runner.known = {99, 13}
        runner.names = {99: 'Apsfixture', 13: 'Gmfixture'}
        @contextmanager
        def login(owner, account, **kwargs):
            calls.append((account, kwargs))
            yield Mock(), kwargs['guid']
        calls = []
        with patch.object(matrix.Runner, 'login', login), patch.object(runner, 'native_spells'):
            with runner.login('APV2B', guid=99):
                pass
            with runner.login('TEST', guid=13):
                pass
        self.assertEqual(calls, [('APV2B', dict(guid=99, expected_profile=runner.case['profile'])),
                                 ('TEST', dict(guid=13, expected_profile=None))])

    def test_exception_cleanup_waits_for_player_and_control_offline_after_logout(self):
        runner = self.runner()
        runner.guid, runner.known = 99, {99, 13}
        events = []
        @contextmanager
        def login(owner, account, **kwargs):
            try:
                yield Mock(), kwargs['guid']
            finally:
                events.append(('logout', kwargs['guid']))
        runner.offline = Mock(side_effect=lambda guid: events.append(('offline', guid)))
        with patch.object(matrix.Runner, 'login', login), patch.object(runner, 'native_spells'):
            with self.assertRaisesRegex(RuntimeError, 'deadline'):
                with runner.login('TEST', guid=13):
                    with runner.login('APV2B', guid=99):
                        raise RuntimeError('deadline')
        self.assertEqual(events, [('logout', 99), ('offline', 99), ('logout', 13), ('offline', 13)])

    def test_failed_fresh_packet_also_waits_for_offline(self):
        runner = self.runner()
        runner.guid, runner.known = 99, {99}
        @contextmanager
        def login(owner, account, **kwargs):
            yield Mock(), 99
        runner.offline = Mock()
        with patch.object(matrix.Runner, 'login', login), \
             patch.object(runner, 'native_spells', side_effect=RuntimeError('bad fresh packet')):
            with self.assertRaisesRegex(RuntimeError, 'bad fresh packet'), runner.login('APV2B', guid=99):
                self.fail('Bad fresh packet yielded to actions')
        runner.offline.assert_called_once_with(99)

    def test_deadline_and_single_attempt_stop_before_authentication(self):
        runner = self.runner()
        runner.deadline = 0
        with patch.object(runtime, 'authenticate') as auth:
            with self.assertRaisesRegex(RuntimeError, 'deadline'), runner.login('APV2B'):
                pass
            auth.assert_not_called()
        runner.deadline = float('inf')
        runner.created = True
        with self.assertRaisesRegex(RuntimeError, 'One creation'), runner.login('APV2B'):
            pass

    def test_native_aura_parser_literal_and_truncation(self):
        raw = b'\x01\x63' + struct.pack('<BIBBBii', 0, 168, 0x39, 1, 1, 1800000, 1800000)
        self.assertEqual(matrix.aura_spells(raw), (99, {168}))
        self.assertEqual(matrix.aura_spells(b'\x01\x63' + struct.pack('<BI', 0, 0)), (99, set()))
        for short in (b'', raw[:-1], raw[:7]):
            with self.assertRaises(RuntimeError):
                matrix.aura_spells(short)

    def test_matrix_native_opcode_allowlist_is_narrow(self):
        runner = self.runner(self.plan['cases'][6])
        runner.guid, runner.pending_name = 99, 'Apsfixture'
        client = matrix.MatrixClient(Mock(), Mock(), runner, False)
        for opcode, payload in ((0x36, runtime.create_character('Apsfixture')), (0x95, runtime.say_packet('.learn 133')),
                                (0x12E, struct.pack('<BIBI', 1, 133, 0, 0)), (0x136, b''), (0x251, b'')):
            with self.subTest(opcode=opcode), self.assertRaises(RuntimeError):
                client.send(opcode, payload)

    def test_executor_schedules_native_gate_phases_for_each_class(self):
        # Orchestration check only. Packet/guard tests above cover the actual native boundary.
        for case in self.plan['cases']:
            runner = self.runner(case)
            runner.output = None
            runner.reuse_control = Mock(return_value=13)
            runner.account_row = Mock(return_value=dict(id=9))
            fresh = dict(guid=99, account=9, name='Apsfixture', race=case['profile']['race_id'],
                         **{'class': case['profile']['class_id']}, online=0, level=1)
            runner.offline = Mock(return_value=fresh)
            runner.query = Mock(return_value=[])
            runner.immutable = Mock(return_value=[dict(id=7)])
            runner.state = Mock(return_value={k: [] for k in ('spells', 'receipts', 'progress', 'binding')})
            runner.command = Mock()
            runner.save = Mock()
            queued = []
            runner.queue = lambda player, gm, codes: (queued.extend(codes), runner.codes.extend(codes))
            spells = {case['baseline_spell'], 2457, 168}
            runner.baseline = set(spells)
            player = Mock(spells=spells, casts=[(99, 99, 1, 168)], failures=[], auras=[(99, {168})])
            # Supply responses after send so the executor really clears prior observations.
            player.send.side_effect = lambda *args: (player.casts.append((99, 99, 1, 168)),
                                                      player.auras.append((99, {168})))
            @contextmanager
            def login(account, *, guid=None):
                runner.guid = 99
                runner.known.add(99)
                runner.names[99] = 'Apsfixture'
                yield player, 99 if account != 'TEST' else 13
            runner.login = login
            store = Mock()
            store.bind.return_value = 7
            store.receive.return_value = True
            with patch('bridge.v2.Store', return_value=store) as factory:
                runner.execute()
            self.assertNotIn('password', factory.call_args.args[0])
            self.assertEqual(queued[0], case['chain']['ap_id'])
            self.assertTrue(all(c == 919100001 for c in queued[1:]))
            labels = [c.args[0] for c in runner.state.call_args_list]
            self.assertEqual(labels[:4], ['bound', 'locked', 'early-permission', 'cap-bypass-denied'])
            self.assertEqual(labels[-2:], ['relog', 'replay'])
            self.assertEqual(runner.level, case['chain']['levels'][1])
            store.receive.assert_called_once_with(0, matrix.items(runner.codes))
            store.close.assert_called_once()

    @staticmethod
    def spell_client(spells):
        raw = struct.pack('<BH', 0, len(spells))
        raw += b''.join(struct.pack('<IH', spell, 0) for spell in sorted(spells)) + b'\x00\x00'
        return SimpleNamespace(spells=set(spells), initial_spell_packet=raw)

    def test_zero_saved_rows_with_fresh_native_baseline_passes(self):
        runner = self.runner()
        runner.guid, runner.binding = 99, 7
        runner.known, runner.names = {99}, {99: 'Apsfixture'}
        runner.baseline = {78, 2457}
        runner.original_binding = [dict(id=7)]
        runner.immutable = Mock(return_value=runner.original_binding)
        runner.reward_rows = Mock(return_value=[])
        runner.offline = Mock(return_value=dict(level=1, race=1, **{'class': 1}))
        saved = []  # Core-derived starting spells need no character_spell rows.
        runner.query = Mock(side_effect=lambda sql, args=(): saved if 'character_spell' in sql else [dict(cap_items=0)])
        # Literal SMSG_INITIAL_SPELLS: 78 and 2457, no cooldowns.
        player = SimpleNamespace(spells={78, 2457}, initial_spell_packet=bytes.fromhex(
            '0002004e00000000009909000000000000'))
        @contextmanager
        def login(owner, account, **kwargs):
            yield player, 99
        with patch.object(matrix.Runner, 'login', login), redirect_stdout(io.StringIO()):
            state = runner.state('valid', permitted=False)
            self.assertEqual(state['spells'], [])
            self.assertEqual(state['lastFreshNativeSpellSet']['spells'], [78, 2457])
            self.assertEqual(state['lastFreshNativeSpellSet']['login_sequence'], 1)
            runner.state('fresh-again', permitted=False)
            self.assertEqual(runner.login_sequence, 2)
            saved.append(dict(spell=100))
            with self.assertRaisesRegex(RuntimeError, 'rank gate'):
                runner.state('premature-saved', permitted=False)
            saved.clear()
            player.spells = {78}
            player.initial_spell_packet = self.spell_client({78}).initial_spell_packet
            with self.assertRaisesRegex(RuntimeError, 'baseline spell lost'):
                runner.state('lost-baseline', permitted=False)
            player.spells = {78, 2457, 100}
            player.initial_spell_packet = self.spell_client(player.spells).initial_spell_packet
            with self.assertRaisesRegex(RuntimeError, 'Locked/ineligible'):
                runner.state('locked-packet', permitted=False)
            player.spells = {78, 2457}
            player.initial_spell_packet = None
            with self.assertRaisesRegex(RuntimeError, 'Missing fresh'):
                runner.state('no-fresh-packet', permitted=False)
            player.initial_spell_packet = self.spell_client(player.spells).initial_spell_packet
            runner.immutable.return_value = [dict(id=8)]
            with self.assertRaisesRegex(RuntimeError, 'Immutable binding'):
                runner.state('mutated-binding', permitted=False)

    def test_every_player_login_checks_fresh_packet_before_actions(self):
        runner = self.runner()
        runner.guid, runner.known = 99, {99}
        runner.baseline = {78, 2457}
        runner.offline = Mock()
        @contextmanager
        def login(owner, account, **kwargs):
            yield player, 99
        for player in (self.spell_client({78}), self.spell_client({78, 2457, 100}),
                       SimpleNamespace(spells={78, 2457}, initial_spell_packet=None)):
            with patch.object(matrix.Runner, 'login', login), self.assertRaises(RuntimeError), \
                 runner.login('APV2B', guid=99):
                self.fail('Player actions must not run after bad/missing fresh packet')

    def test_initial_selected_chain_absence_and_active_rank_packet_rules(self):
        runner = self.runner()
        with self.assertRaisesRegex(RuntimeError, 'already starting-known'):
            runner.native_spells(self.spell_client({78, 2457, 100}))
        runner.native_spells(self.spell_client({78, 2457}))
        runner.permitted, runner.level = True, 26
        # Superseded rank 100 need not be active in the native spellbook.
        runner.native_spells(self.spell_client({78, 2457, 6178}))
        with self.assertRaisesRegex(RuntimeError, 'Eligible active rank missing'):
            runner.native_spells(self.spell_client({78, 2457, 100}))

    def test_matrix_captures_raw_initial_spells_on_each_new_connection(self):
        runner = self.runner()
        raw = self.spell_client({78, 2457}).initial_spell_packet
        first = matrix.MatrixClient(Mock(), Mock(), runner, False)
        with redirect_stdout(io.StringIO()) as log:
            first.process(0x12A, raw)
        self.assertEqual(first.spells, {78, 2457})
        self.assertEqual(first.initial_spell_packet, raw)
        self.assertEqual(json.loads(log.getvalue())['raw'], raw.hex())
        second = matrix.MatrixClient(Mock(), Mock(), runner, False)
        self.assertIsNone(second.spells)
        self.assertIsNone(second.initial_spell_packet)

    def test_eligible_native_rank_does_not_replace_saved_rank_checks(self):
        runner = self.runner()
        runner.guid, runner.binding, runner.level = 99, 7, 26
        runner.known, runner.baseline = {99}, {78, 2457}
        runner.original_binding = [dict(id=7)]
        runner.immutable = Mock(return_value=runner.original_binding)
        runner.reward_rows = Mock(return_value=[])
        runner.offline = Mock(return_value=dict(level=26, race=1, **{'class': 1}))
        saved = [dict(spell=6178)]
        runner.query = Mock(side_effect=lambda sql, args=(): saved if 'character_spell' in sql else [dict(cap_items=0)])
        @contextmanager
        def login(owner, account, **kwargs):
            yield self.spell_client({78, 2457, 6178}), 99
        with patch.object(matrix.Runner, 'login', login), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'rank gate'):
                runner.state('missing-saved-base', permitted=True)
            saved.append(dict(spell=100))
            state = runner.state('both-saved-highest-active', permitted=True)
            self.assertEqual(state['spells'], saved)

    def test_existing_attempt_stops_before_any_runtime_inspection(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(matrix, 'OUTPUT', Path(directory)), \
             patch.object(matrix, 'released_evidence', side_effect=AssertionError('runtime')):
            (matrix.OUTPUT / 'release.json').write_text(json.dumps(dict(owned_release=True, mail_lifetime_fixed=True)))
            (matrix.OUTPUT / 'attempt.json').write_text('preserved')
            with self.assertRaisesRegex(RuntimeError, 'Existing matrix attempt'):
                matrix.main(['--run'])
            self.assertEqual((matrix.OUTPUT / 'attempt.json').read_text(), 'preserved')

    def test_partial_failure_saves_history_and_stops_without_next_creation(self):
        observer = Mock(before={1, 2, 3, 4, 13})
        snapshots = self.snapshots()
        observer.account_row.side_effect = lambda a: snapshots[a][0]
        def query(sql, args=()):
            self.assertTrue(sql.startswith('SELECT '))
            if '@@server_uuid' in sql:
                return [dict(uuid=matrix.UUID)]
            if 'COUNT(*)' in sql:
                return [dict(n=8)]
            if 'SELECT email,reg_mail' in sql:
                return [dict(email=MARKER, reg_mail=MARKER)]
            return []
        observer.query.side_effect = query
        failed = Mock(guid=99, known={13, 99})
        failed.execute.side_effect = RuntimeError('native connection lost')
        frozen = dict(history=[dict(item_index=0, applied=1)])
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(matrix, 'Runner', return_value=observer), \
             patch.object(matrix, 'MatrixRunner', return_value=failed) as factory, \
             patch.object(matrix, 'check_account'), \
             patch.object(matrix, 'protected_snapshot', return_value=deepcopy(frozen)):
            output = Path(directory)
            with self.assertRaisesRegex(RuntimeError, 'native connection lost'):
                matrix.execute_matrix(Mock(), self.plan, output, float('inf'))
            summary = json.loads((output / 'summary.json').read_text())
            self.assertTrue(summary['protected_unchanged'])
            self.assertEqual(summary['classes'][0]['known_attempt_guids'], [99])
            self.assertEqual(summary['classes'][0]['status'], 'FAIL')
            self.assertEqual(summary['classes'][0]['error'], 'native connection lost')
            self.assertEqual(json.loads((output / 'before.json').read_text()), frozen)
            self.assertEqual(json.loads((output / 'after.json').read_text()), frozen)
            factory.assert_called_once()

    def test_baseline_and_talent_claims_are_bounded(self):
        self.assertEqual(self.plan['baseline_cast']['spell'], 168)
        self.assertEqual(self.plan['talents']['level80_available'], 71)
        self.assertEqual(self.plan['talents']['matrix_spending'], 0)
        self.assertIn('native execution', self.plan['missing'])


if __name__ == '__main__':
    unittest.main()
