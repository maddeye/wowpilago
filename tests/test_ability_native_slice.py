"""Offline native adapter and orchestration checks. No real connections."""
from contextlib import redirect_stdout, contextmanager
import copy
import importlib.util
import io
import json
from pathlib import Path
import socket
import struct
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

from integration_inputs import require_inputs

PATH = Path(__file__).resolve().parents[1] / '.local/goal-ecbd80/ability-native-runtime/executor.py'
require_inputs(PATH)
spec = importlib.util.spec_from_file_location('private_ability_native', PATH)
slice = importlib.util.module_from_spec(spec)
spec.loader.exec_module(slice)


def release():
    now = time.time()
    return {'purpose': 'ability-native-38-13-old3b9-v1', 'parent_release': True,
            'mage': {'guid': 38, 'account_id': 4, 'account': 'APV2C', 'binding_id': 28},
            'control': {'guid': 13, 'account_id': 1, 'account': 'TEST'},
            'receipt_indexes': [2, 3], 'commands': slice.COMMANDS.copy(), 'build': slice.BUILD,
            'world_sha256': slice.WORLD, 'manifest_sha256': slice.MANIFEST,
            'source_inventory_sha256': '348e9f2932a988f7f2a894e3aa7b31423ca82ba8eee595707a3daa0d8a6e47b8',
            'executor_sha256': slice.file_hash(PATH),
            'runtime_sha256': slice.file_hash(PATH.parent / 'runtime.py'), 'contract_sha256': slice.CONTRACT_HASH,
            'attempt': 'offline-test-0001', 'issued_at': now - 1, 'expires_at': now + 60,
            'max_seconds': 900}


def spellbook(*spells):
    return b'\0' + struct.pack('<H', len(spells)) + b''.join(
        struct.pack('<IH', s, 0) for s in spells) + b'\0\0'


def observer(armed=False):
    connection, raw = object(), []
    obj = slice.AbilityObserver(connection, raw.append)
    obj.seed(20)
    obj.packet(connection, 0x12A, spellbook(12824, 133, 168))
    if armed:
        for phase in ['permission', 'cap', 'plus9']:
            obj.checkpoint(phase)
        obj.packet(connection, 0x1D4, level_packet(29))
        obj.checkpoint('plus1')
        obj.packet(connection, 0x1D4, level_packet(30))
    return obj, connection, raw


def level_packet(level):
    return struct.pack('<I13i', level, *range(13))


class PolicyTests(unittest.TestCase):
    def setUp(self):
        # Any accidental connection, including one hidden behind pymysql, fails this suite.
        self.network = patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.create = patch.object(socket, 'create_connection', side_effect=AssertionError('Network forbidden'))
        self.create.start()
        self.addCleanup(self.create.stop)

    def test_default_does_not_read_release_or_import_runtime(self):
        with patch.object(slice.Path, 'read_text', side_effect=AssertionError('Default read')), \
                patch.dict('sys.modules', {'pymysql': None, 'bridge.v2': None}), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(slice.main([]), 0)
        self.assertFalse(json.loads(out.getvalue())['network'])

    def test_missing_malformed_expired_wrong_release_before_reservation(self):
        with patch.object(slice, 'reserve_attempt', side_effect=AssertionError('Reserved too early')):
            with self.assertRaises(RuntimeError):
                slice.main(['--run'])
            for value in [None, {}, [], release() | {'expires_at': 0},
                          release() | {'max_seconds': 901}, release() | {'issued_at': float('nan')},
                          release() | {'receipt_indexes': [2, 3, 4]},
                          release() | {'commands': ['.learn 45438']},
                          release() | {'mage': {'guid': 4}},
                          release() | {'build': 'old-release'},
                          release() | {'executor_sha256': '0' * 64},
                          release() | {'runtime_sha256': '0' * 64},
                          release() | {'attempt': '../overwrite'},
                          release() | {'parent_release': 1}]:
                with self.subTest(value=value), self.assertRaises(RuntimeError):
                    slice.validate_release(value)
            with tempfile.TemporaryDirectory() as tmp:
                bad = Path(tmp) / 'bad.json'
                bad.write_text('{')
                with self.assertRaises(ValueError):
                    slice.main(['--run', '--release', str(bad)])

    def test_valid_release_dispatches_runtime_only_after_exclusive_reservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = release()
            path = Path(tmp) / 'release.json'
            path.write_text(json.dumps(r))
            original = slice.reserve_attempt
            runtime = SimpleNamespace(run=Mock(return_value=0))
            with patch.object(slice, 'reserve_attempt', side_effect=lambda value: original(value, Path(tmp) / 'attempts')), \
                    patch.object(slice, 'runtime_module', return_value=runtime):
                self.assertEqual(slice.main(['--run', '--release', str(path)]), 0)
            runtime.run.assert_called_once()
            self.assertEqual(runtime.run.call_args.args[0], r)
            attempt = Path(tmp) / 'attempts' / r['attempt']
            self.assertEqual(json.loads((attempt / 'release.json').read_text()), r)
            self.assertFalse((attempt / 'blocked.json').exists())
            self.assertEqual((attempt / 'release.json').stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                original(r, Path(tmp) / 'attempts')
            self.assertEqual(json.loads((attempt / 'release.json').read_text()), r)

    def test_historical_contract_and_real_current_source_drift_rejection(self):
        historical = slice.ROOT / '.local/goal-88bb/delete-archive-fix/APProgression.before.cpp.txt'
        require_inputs(historical)
        with self.assertRaisesRegex(RuntimeError, 'Unexpected current module change: APProgression.cpp'):
            slice.verify_local_contract()
        # Model the historical source only in this positive offline test; real admission still refuses.
        original = slice.file_hash
        current = slice.ROOT / 'src/APProgression.cpp'
        with patch.object(slice, 'file_hash', side_effect=lambda path: original(historical if Path(path) == current else path)):
            proof = slice.verify_local_contract()
        self.assertEqual(proof['world'], slice.WORLD)
        self.assertFalse(proof['running_attestation'])
        self.assertFalse(proof['current_area_deployed'])

    def test_exact_full_saved_baseline_and_manifest(self):
        saved = slice.baseline()
        self.assertEqual(slice.validate_baseline(saved)['manifest_hash'], slice.MANIFEST)
        for table, mutate in [
                ('characters', lambda rows: rows[0].update(money=999)),
                ('mod_archipelago_reward', lambda rows: next(r for r in rows if r['binding_id'] == 28).update(received_at='changed')),
                ('mod_archipelago_binding', lambda rows: next(r for r in rows if r['id'] == 28).update(manifest='{}')),
                ('item_instance', lambda rows: next(r for r in rows if r['guid'] == 591).update(count=9))]:
            actual = copy.deepcopy(saved)
            mutate(actual['acore_characters'][table])
            with self.subTest(table=table), self.assertRaises(RuntimeError):
                slice.validate_baseline(actual)
        actual = copy.deepcopy(saved)
        del actual['acore_auth']['account_access']
        with self.assertRaises(RuntimeError):
            slice.validate_baseline(actual)

    def test_receipts_are_append_once_not_replay(self):
        prefix = [r for r in slice.baseline()['acore_characters']['mod_archipelago_reward'] if r['binding_id'] == 28]
        receipt2 = dict(binding_id=28, item_index=2, ap_item=919146438, kind='ability', value=45438,
                        applied=1, applied_value=45438, location_id=-1, sender=0, flags=0, item_guid=None)
        self.assertEqual(slice.guard_receipt(3, 919100001, prefix + [receipt2], prefix)[0]['item'], 919100001)
        for index, code, rows in [(4, 919101122, prefix), (2, 919100001, prefix),
                                  (2, 919146438, prefix + [receipt2]), (3, 919100001, prefix),
                                  (3, 919100001, prefix + [receipt2 | {'applied': 0}])]:
            with self.subTest(index=index, code=code), self.assertRaises(RuntimeError):
                slice.guard_receipt(index, code, rows, prefix)
        changed = copy.deepcopy(prefix)
        changed[0]['received_at'] = 'changed'
        with self.assertRaises(RuntimeError):
            slice.guard_receipt(2, 919146438, changed, prefix)
        store = SimpleNamespace(guid=38, binding=28, manifest=SimpleNamespace(checksum=slice.MANIFEST),
                                receive=Mock(return_value=True))
        with tempfile.TemporaryDirectory() as tmp:
            attempt = Path(tmp)
            slice.append_receipt(store, 2, 919146438, prefix, prefix, attempt)
            with self.assertRaises(FileExistsError):
                slice.append_receipt(store, 2, 919146438, prefix, prefix, attempt)
            store.receive.assert_called_once()
        store.receive = Mock(side_effect=RuntimeError('Ambiguous commit'))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, 'Ambiguous'):
                slice.append_receipt(store, 2, 919146438, prefix, prefix, Path(tmp))
            with self.assertRaises(FileExistsError):
                slice.append_receipt(store, 2, 919146438, prefix, prefix, Path(tmp))
            store.receive.assert_called_once()

    def test_exact_online_command_and_actors_only(self):
        connection = object()
        kwargs = dict(control=13, target=38, online=True, connection=connection,
                      expected_connection=connection, step=0)
        slice.guard_command(slice.COMMANDS[0], **kwargs)
        for command, changes in [('.learn 45438', {}), (slice.COMMANDS[1], {}),
                                 (slice.COMMANDS[0], {'target': 4}),
                                 (slice.COMMANDS[0], {'control': 14}),
                                 (slice.COMMANDS[0], {'online': False}),
                                 (slice.COMMANDS[0], {'connection': object()})]:
            with self.subTest(command=command, changes=changes), self.assertRaises(RuntimeError):
                slice.guard_command(command, **(kwargs | changes))

    def test_partial_failure_cleanup_attempts_both_and_raw_after(self):
        mage = SimpleNamespace(login=True, logout=Mock(side_effect=RuntimeError('socket failed')))
        gm = SimpleNamespace(login=True, logout=Mock())
        offline = Mock(side_effect=[RuntimeError('still online'), None])
        capture = Mock()
        errors = slice.cleanup([(13, gm), (38, mage)], offline, capture)
        mage.logout.assert_called_once()
        gm.logout.assert_called_once()
        self.assertEqual(offline.call_count, 2)
        capture.assert_called_once()
        self.assertEqual(len(errors), 2)


class ObserverTests(unittest.TestCase):
    def test_same_connection_exact_new_six_bytes_after_plus1(self):
        obj, connection, raw = observer(True)
        packet = struct.pack('<IH', 45438, 0)
        obj.packet(connection, 0x12B, packet)
        obj.seal()
        self.assertEqual(obj.learned, 1)
        self.assertEqual(raw[-1]['payload_hex'], packet.hex())
        self.assertTrue(obj.initial <= obj.known)

    def test_truncated_wrong_suffix_spell_and_trailing_payloads(self):
        for payload in [b'', struct.pack('<I', 45438), struct.pack('<IH', 45438, 1),
                        struct.pack('<IH', 45439, 0), struct.pack('<IH', 45438, 0) + b'\0']:
            obj, connection, raw = observer(True)
            with self.subTest(payload=payload), self.assertRaises(RuntimeError):
                obj.packet(connection, 0x12B, payload)
            self.assertEqual(obj.phase, 'failed')
            self.assertEqual(raw[-1]['payload_hex'], payload.hex())

    def test_early_duplicate_wrong_connection_and_relog_hidden(self):
        packet = struct.pack('<IH', 45438, 0)
        for phase in ['level20', 'permission', 'cap', 'plus9', 'below']:
            obj, connection, _ = observer()
            obj.phase = phase
            with self.subTest(phase=phase), self.assertRaises(RuntimeError):
                obj.packet(connection, 0x12B, packet)
        obj, connection, _ = observer(True)
        with self.assertRaises(RuntimeError):
            obj.packet(object(), 0x12B, packet)
        obj, connection, _ = observer(True)
        obj.packet(connection, 0x12B, packet)
        with self.assertRaises(RuntimeError):
            obj.packet(connection, 0x12B, packet)
        obj, connection, _ = observer(True)
        with self.assertRaises(RuntimeError):
            obj.packet(connection, 0x12A, spellbook(12824, 45438))
        obj, connection, _ = observer(True)
        with self.assertRaises(RuntimeError):
            obj.seal()  # First seen in a later login is never acquisition proof.

    def test_initial_absence_and_29_checkpoint_mandatory(self):
        obj = slice.AbilityObserver(object(), lambda event: None)
        obj.seed(20)
        with self.assertRaises(RuntimeError):
            obj.packet(obj.connection, 0x12A, spellbook(12824, 45438))
        obj, _, _ = observer()
        with self.assertRaises(RuntimeError):
            obj.checkpoint('plus1')
        obj, _, _ = observer()
        obj.checkpoint('permission')
        obj.checkpoint('cap')
        obj.checkpoint('plus9')
        with self.assertRaises(RuntimeError):
            obj.packet(obj.connection, 0x1D4, level_packet(30))


class NativeBoundaryTests(unittest.TestCase):
    setUp = PolicyTests.setUp
    # Reuse the suite-wide network prohibition, not another live fixture.
    def test_level_length_phase_and_initial_seed_are_native(self):
        for payload in [b'', level_packet(29)[:-1], level_packet(29) + b'0', level_packet(30)]:
            obj, sock, _ = observer()
            obj.checkpoint('permission')
            obj.checkpoint('cap')
            obj.checkpoint('plus9')
            with self.subTest(payload=payload), self.assertRaises(RuntimeError):
                obj.packet(sock, 0x1D4, payload)
        obj, sock, _ = observer()
        with self.assertRaises(RuntimeError):
            obj.packet(sock, 0x1D4, level_packet(29))
        obj = slice.AbilityObserver(object(), lambda _: None)
        with self.assertRaises(RuntimeError):
            obj.packet(obj.connection, 0x12A, spellbook(12824))
        obj = slice.AbilityObserver(object(), lambda _: None)
        with self.assertRaises(RuntimeError):
            obj.seed(30)
        obj, sock, _ = observer()
        for phase in ('permission', 'cap', 'plus9'):
            obj.checkpoint(phase)
        obj.packet(sock, 0x1D4, level_packet(29))
        with self.assertRaises(RuntimeError):
            obj.packet(sock, 0x1D4, level_packet(30))  # +1 not sent yet.

    def test_creation_blocked_before_emit_and_exact_guid_enumeration(self):
        rt = slice.runtime_module()
        owner = SimpleNamespace(p=slice, clients=[], names={38: 'Apsmetxdtfsp'},
                                record=Mock(), check=Mock(), command_pending=None)
        sock = Mock()
        client = rt.NativeClient(sock, Mock(), owner, 38)
        # Force RealmClient's actual absent-name branch, bypassing only the server response.
        with patch.object(client, 'wait_for', side_effect=[b'0' * 40, b'\x0c', b'\0']):
            with self.assertRaisesRegex(RuntimeError, 'character creation'):
                client.connect('APV2C', SimpleNamespace(session_key=b'1' * 40),
                               SimpleNamespace(realm_id=1), 'Apsmetxdtfsp', class_id=8)
        self.assertEqual(sock.sendall.call_count, 2)  # Auth and enumeration, never creation.
        payload = (b'\x01' + struct.pack('<Q', 38) + b'Apsmetxdtfsp\0' +
                   bytes([1, 8, 0, 0, 0, 0, 0, 0, 20]) + bytes(20 + 12 + 1 + 12 + 23 * 9))
        client.enumeration(payload)
        self.assertEqual(client.observer.level, 20)
        client.process(0x12A, spellbook(12824, 133))
        self.assertEqual(client.observer.phase, 'level20')
        for phase in ('permission', 'cap', 'plus9'):
            client.observer.checkpoint(phase)
        client.process(0x1D4, level_packet(29))
        self.assertNotIn(45438, client.spells)
        client.observer.checkpoint('plus1')
        client.process(0x1D4, level_packet(30))
        client.process(0x12B, struct.pack('<IH', 45438, 0))
        client.observer.seal()
        self.assertIn(45438, client.spells)
        for opcode in (0x36, 0x95, 0x13D, 0x12E):
            with self.subTest(opcode=opcode), self.assertRaises(RuntimeError):
                client.send(opcode)
        client2 = rt.NativeClient(Mock(), Mock(), owner, 38)
        with self.assertRaises(RuntimeError):
            client2.enumeration(payload.replace(struct.pack('<Q', 38), struct.pack('<Q', 39), 1))

    def test_admission_precedes_root_login_and_connect(self):
        rt = slice.runtime_module()
        backend = object.__new__(rt.Backend)
        with patch.object(rt.Runner, 'login', side_effect=AssertionError('Root login reached')):
            for account, guid in [('APV2C', None), ('APV2C', 4), ('TEST', 14), ('APV2A', 38)]:
                with self.subTest(account=account, guid=guid), self.assertRaises(RuntimeError):
                    with backend.login(account, guid=guid):
                        pass

    def test_baseline_ambient_kept_raw_unknown_and_protected_rejected(self):
        old = slice.baseline()
        actual = copy.deepcopy(old)
        from verify_talent_switch_runtime import AUTOMATIC_WORLDSTATE_KEYS
        row = next(r for r in actual['acore_characters']['worldstates']
                   if r['entry'] in AUTOMATIC_WORLDSTATE_KEYS)
        row['value'] += 1
        latest = max(actual['acore_auth']['uptime'], key=lambda r: r['starttime'])
        latest['uptime'] += 10
        slice.validate_baseline(actual)
        self.assertNotEqual(actual, old)
        row = next(r for r in actual['acore_characters']['worldstates']
                   if r['entry'] not in AUTOMATIC_WORLDSTATE_KEYS)
        row['value'] += 1
        with self.assertRaises(RuntimeError):
            slice.validate_baseline(actual)

    def test_frozen_pending_receipts_are_preserved_not_a_preflight_blocker(self):
        rt = slice.runtime_module()
        saved = slice.baseline()
        binding = next(r for r in saved['acore_characters']['mod_archipelago_binding'] if r['id'] == 28)
        from provision_realm import UUID
        p = SimpleNamespace(**vars(slice))
        p.validate_baseline = Mock(return_value=binding)
        p.file_hash = Mock(return_value=p.ROOM_HASH)
        p.private_json = Mock()
        b = object.__new__(rt.Backend)
        b.p, b.attempt, b.known, b.names = p, Path('/not-written'), set(), {}
        b.query = Mock(return_value=[dict(uuid=UUID)])
        self.assertEqual(sum(not r['applied'] for r in saved['acore_characters']['mod_archipelago_reward']), 11)
        with patch.object(rt.Path, 'glob', return_value=[]), patch.object(rt.MerchantRunner, 'reuse_control'):
            self.assertEqual(b.preflight(saved), binding)
            extra = copy.deepcopy(saved)
            extra['acore_characters']['mod_archipelago_reward'].append(dict(binding_id=28, applied=0))
            with self.assertRaisesRegex(RuntimeError, 'Frozen pending'):
                b.preflight(extra)

    def test_readonly_time_fence_is_single_use_and_native(self):
        rt = slice.runtime_module()
        owner = SimpleNamespace(p=slice, clients=[], names={38:'Apsmetxdtfsp'}, record=Mock(), check=Mock())
        client = rt.NativeClient(Mock(), Mock(), owner, 38)
        client.observer.seed(20)
        client.process(0x12A, spellbook(12824,133))
        with self.assertRaisesRegex(RuntimeError, 'time fence'):
            client.send(0x1CE)
        for phase in ('permission','cap','plus9'):
            client.observer.checkpoint(phase)
        client.process(0x1D4, level_packet(29))
        with self.assertRaisesRegex(RuntimeError, 'time-fence response'):
            client.process(0x1CF, bytes(8))
        client.send(0x1CE)
        self.assertTrue(client.time_query_sent)
        with self.assertRaisesRegex(RuntimeError, 'time fence'):
            client.send(0x1CE)
        with self.assertRaisesRegex(RuntimeError, 'time-fence response'):
            client.process(0x1CF, bytes(7))
        payload=struct.pack('<II',100,200)
        client.process(0x1CF,payload)
        self.assertEqual(client.time_response,payload.hex())
        with self.assertRaisesRegex(RuntimeError, 'time-fence response'):
            client.process(0x1CF,payload)

    def test_late_level29_acquisition_cannot_be_credited_to_plus1(self):
        rt = slice.runtime_module()
        obs, conn, raw = observer()
        obs.checkpoint('permission'); obs.checkpoint('cap')
        gm = SimpleNamespace(guid=13,messages=[])
        mage = SimpleNamespace(guid=38,login=True,sock=conn,time_response=None)
        with tempfile.TemporaryDirectory() as tmp:
            b=object.__new__(rt.Backend)
            b.p,b.attempt,b.names=slice,Path(tmp),{38:'Apsmetxdtfsp'}
            def send_command(opcode,payload):
                obs.packet(conn,0x1D4,level_packet(29))
                gm.messages.append('You changed level of Apsmetxdtfsp to 29.')
            gm.send=send_command
            def fence(opcode):
                self.assertEqual(opcode,0x1CE)
                obs.packet(conn,0x12B,struct.pack('<IH',45438,0))
            mage.send=fence
            def wait(predicate,seconds):
                self.assertTrue(predicate())
            b.wait=wait
            with self.assertRaisesRegex(RuntimeError,'Wrong/early'):
                b.command(gm,mage,obs,0)
        self.assertEqual(obs.phase,'failed')

    def test_auth_played_time_must_match_only_the_owned_actor(self):
        rt=slice.runtime_module()
        old=slice.baseline(); new=copy.deepcopy(old)
        for account,guid,seconds in ((1,13,3),(4,38,7)):
            next(r for r in new['acore_auth']['account'] if r['id']==account)['totaltime']+=seconds
            next(r for r in new['acore_characters']['characters'] if r['guid']==guid)['totaltime']+=seconds
        with tempfile.TemporaryDirectory() as tmp:
            b=object.__new__(rt.Backend);b.p,b.attempt=slice,Path(tmp)
            b.audit_protected(old,new)
        next(r for r in new['acore_auth']['account'] if r['id']==4)['totaltime']+=1
        with tempfile.TemporaryDirectory() as tmp:
            b.attempt=Path(tmp)
            with self.assertRaisesRegex(RuntimeError,'Auth played time'):
                b.audit_protected(old,new)

    def test_saved_battle_end_is_bounded_without_relaxing_shared_guard(self):
        source=PATH.parent/'parent-prelease/snapshot.json'
        actual=json.loads(source.read_text())
        captured_at=source.stat().st_mtime
        self.assertEqual(slice.validate_baseline(actual,at_time=captured_at)['id'],28)
        from verify_talent_switch_runtime import compare_ambient
        with self.assertRaisesRegex(RuntimeError,'Protected worldstate'):
            compare_ambient('worldstates',slice.baseline()['acore_characters']['worldstates'],
                            actual['acore_characters']['worldstates'])
        for entry,delta in ((4024,1),(3781,120000),(3802,-1),(20003,1)):
            wrong=copy.deepcopy(actual)
            next(r for r in wrong['acore_characters']['worldstates'] if r['entry']==entry)['value']+=delta
            with self.subTest(entry=entry),self.assertRaises(RuntimeError):
                slice.validate_baseline(wrong,at_time=captured_at)
        with self.assertRaisesRegex(RuntimeError,'clock/save bounds'):
            slice.validate_baseline(actual,at_time=captured_at+120)

    def test_uptime_cannot_admit_a_new_boot_or_unowned_players(self):
        old=slice.baseline()['acore_auth']['uptime']
        actual=copy.deepcopy(old)
        latest=max(actual,key=lambda r:r['starttime'])
        latest['uptime']+=10
        latest['maxplayers']=2
        slice.validate_uptime(old,actual)
        latest['maxplayers']=3
        with self.assertRaises(RuntimeError):
            slice.validate_uptime(old,actual)
        actual=copy.deepcopy(old)
        actual.append(dict(max(actual,key=lambda r:r['starttime']),starttime=int(time.time()),uptime=0))
        with self.assertRaisesRegex(RuntimeError,'boot inventory'):
            slice.validate_uptime(old,actual)

    def test_capture_samples_both_clocks_before_serializing(self):
        rt=slice.runtime_module()
        b=object.__new__(rt.Backend)
        b.db=MagicMock();b.check=Mock();b.attempt=Path('/not-written')
        cursor=b.db.cursor.return_value.__enter__.return_value
        cursor.fetchall.side_effect=[[],[]]
        clock=[100];writes=[]
        def serialize(path,value):
            writes.append((path,value));clock[0]+=100
        b.p=SimpleNamespace(canonical=slice.canonical,private_json=serialize)
        with patch.object(rt.time,'time',return_value=10),patch.object(rt.time,'monotonic_ns',side_effect=lambda:clock[0]):
            b.capture('before')
        self.assertEqual(writes[1][1]['captured_at'],10)
        self.assertEqual(writes[1][1]['time_ns'],100)
        self.assertEqual(clock[0],300)

    def test_actual_readonly_capture_retains_partial_rows_and_private_permissions(self):
        rt = slice.runtime_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = MagicMock()
            cursor = db.cursor.return_value.__enter__.return_value = Mock()
            cursor.fetchall.side_effect = [[{'name': 'characters', 'engine': 'InnoDB'}],
                                          [{'guid': 38, 'online': 1}],
                                          RuntimeError('Capture interrupted')]
            b = rt.Backend(db, slice, release() | {'expires_at': time.time()+300}, Path(tmp))
            with self.assertRaisesRegex(RuntimeError, 'Capture interrupted'):
                b.capture('after')
            partial = json.loads((Path(tmp) / 'after.json').read_text())
            self.assertEqual(partial['acore_characters']['characters'], [{'guid': 38, 'online': 1}])
            self.assertFalse(json.loads((Path(tmp) / 'after-capture.json').read_text())['complete'])
            self.assertEqual((Path(tmp) / 'after.json').stat().st_mode & 0o777, 0o600)
            db.rollback.assert_called_once()
            statements = [c.args[0] for c in cursor.execute.call_args_list]
            self.assertIn('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY', statements)
            self.assertFalse(any(s.startswith(('UPDATE', 'INSERT', 'DELETE')) for s in statements))

    def test_actual_audit_records_native_changes_and_rejects_money_or_item_changes(self):
        rt = slice.runtime_module()
        old = slice.baseline()
        for table, mutate, rejected in [
                ('characters', lambda rows: next(r for r in rows if r['guid'] == 38).update(level=30), False),
                ('characters', lambda rows: next(r for r in rows if r['guid'] == 38).update(money=1), True),
                ('character_skills', lambda rows: next(r for r in rows if r['guid'] == 38).update(max=150), False),
                ('item_instance', lambda rows: next(r for r in rows if r['guid'] == 591).update(count=2), True)]:
            with self.subTest(table=table, rejected=rejected), tempfile.TemporaryDirectory() as tmp:
                b = object.__new__(rt.Backend)
                b.p, b.attempt = slice, Path(tmp)
                new = copy.deepcopy(old)
                mutate(new['acore_characters'][table])
                if rejected:
                    with self.assertRaises(RuntimeError):
                        b.audit_protected(old, new)
                else:
                    b.audit_protected(old, new)
                deltas = json.loads((Path(tmp) / 'all-deltas.json').read_text())
                self.assertIn('acore_characters.' + table, deltas)

    def test_runtime_attestation_uses_readonly_live_proc_image_mount_and_config(self):
        rt = slice.runtime_module()
        info = dict(Id='offline-container', Image=rt.IMAGE,
                    State=dict(Running=True, StartedAt='2026-10-20T00:00:00Z'),
                    Config=dict(Labels={'com.docker.compose.project': 'wow-test',
                                        'com.docker.compose.service': 'worldserver'},
                                Entrypoint=['/work/install/bin/worldserver'],
                                Cmd=['-c', '/work/install/etc/worldserver.conf'], Env=[]),
                    Mounts=[dict(Destination='/work/install', RW=False,
                                 Source=str(slice.ROOT / slice.BUILD / 'install')),
                            dict(Destination='/work/install/etc', RW=False,
                                 Source=str(slice.ROOT / '.local/v2-realm/config'))])
        def read_only_docker(*args):
            if args == ('inspect', rt.CONTAINER):
                return json.dumps([info])
            self.assertEqual(args[:2], ('exec', rt.CONTAINER))
            if args[2:] == ('cat', '/proc/1/cmdline'):
                return '/work/install/bin/worldserver\0-c\0/work/install/etc/worldserver.conf\0'
            if args[2:] == ('cat', '/proc/1/stat'):
                return '1 (worldserver) S ' + '0 ' * 18 + '123 0'
            self.assertEqual(args[2], 'sha256sum')
            hashes = {'/proc/1/exe': slice.WORLD, '/work/install/bin/worldserver': slice.WORLD,
                      '/work/install/etc/worldserver.conf': rt.CONFIG,
                      '/work/install/etc/modules/playerbots.conf': rt.BOTS_CONFIG}
            return hashes[args[3]] + '  ' + args[3]
        with patch.object(rt, 'docker', side_effect=read_only_docker):
            proof = rt.attest(slice)
            self.assertEqual(proof['world'], slice.WORLD)
            self.assertFalse(proof['current_area_deployed'])
            info['Image'] = 'wrong'
            with self.assertRaisesRegex(RuntimeError, 'container/image'):
                rt.attest(slice)
            info['Image'] = rt.IMAGE
            info['Mounts'][0]['RW'] = True
            with self.assertRaisesRegex(RuntimeError, 'read-only mount'):
                rt.attest(slice)

    def test_stores_close_even_when_one_close_fails(self):
        rt = slice.runtime_module()
        b = object.__new__(rt.Backend)
        b.stores = [SimpleNamespace(close=Mock(side_effect=RuntimeError('close failed'))),
                    SimpleNamespace(close=Mock())]
        self.assertEqual(len(b.close_stores()), 1)
        for store in b.stores:
            store.close.assert_called_once()

    def test_real_sequence_once_and_partial_failure_finalization(self):
        rt = slice.runtime_module()
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as tmp:
                events = []
                saved = slice.baseline()
                p = SimpleNamespace(**vars(slice))
                p.verify_local_contract = Mock()
                p.file_hash = Mock(return_value=p.ROOM_HASH)
                binding = next(r for r in saved['acore_characters']['mod_archipelago_binding'] if r['id'] == 28)

                class FakeBackend:
                    def __init__(self, db, policy, grant, attempt):
                        self.p, self.attempt = policy, attempt
                        self.rows = sorted([r for r in saved['acore_characters']['mod_archipelago_reward']
                                            if r['binding_id'] == 28], key=lambda r: r['item_index'])
                        self.store = SimpleNamespace(guid=38, binding=28,
                            manifest=SimpleNamespace(checksum=p.MANIFEST), receive=self.receive)
                        self.sealed = False
                        self.command_pending = None
                        self.names = {38:'Apsmetxdtfsp'}
                        self.stop = time.time() + 300
                    def capture(self, label):
                        events.append(label)
                        state = copy.deepcopy(saved)
                        if label == 'after' and self.sealed:
                            tables = state['acore_characters']
                            tables['character_spell'].append({'guid': 38, 'spell': 45438, 'specMask': 255})
                            next(r for r in tables['characters'] if r['guid'] == 38)['level'] = 30
                            next(r for r in tables['mod_archipelago_progress'] if r['binding_id'] == 28).update(
                                cap_items=2, last_level=30)
                            for check in (919600025, 919600030):
                                tables['mod_archipelago_check'].append(dict(binding_id=28,
                                    location_id=check, completed_at='offline fake', acknowledged=0))
                        p.private_json(self.attempt / (label + '.json'), state)
                        return state
                    def preflight(self, before):
                        events.append('preflight')
                        return binding
                    def attach(self, b):
                        events.append('attach')
                        return self.store
                    def receive(self, index, items):
                        events.append(('receive', index))
                        if fail:
                            raise RuntimeError('Ambiguous receipt commit')
                        _, code, kind, value = p.RECEIPTS[index-2]
                        self.rows.append(dict(binding_id=28, item_index=index, ap_item=code, kind=kind,
                            value=value, applied=1, applied_value=value, location_id=-1,
                            sender=0, flags=0, item_guid=None))
                        return True
                    def rewards(self):
                        return self.rows
                    def delivered(self, index):
                        events.append(('applied', index))
                        return True
                    def check(self):
                        pass
                    def wait(self, predicate, seconds):
                        self.pump()
                        require_value = predicate()
                        if not require_value:
                            raise AssertionError('Fake native condition unmet')
                    def pump(self, exclude=None):
                        events.append('pump-both')
                    def record(self, event):
                        events.append(event['event'])
                    def assert_opcode(self,actual,expected):
                        assert actual==expected
                    def command(self, gm, mage, obs, step):
                        events.append(('command', step))
                        rt.Backend.command(self, gm, mage, obs, step)
                    @contextmanager
                    def login(self, account, *, guid=None):
                        events.append(('login', guid))
                        if guid == 38 and not self.sealed:
                            obs, sock, _ = observer()
                            self.mage = SimpleNamespace(guid=38, login=True, sock=sock, observer=obs, time_response=None)
                            def fence(opcode):
                                self.assert_opcode(opcode,0x1CE)
                                self.mage.time_response='0000000000000000'
                                events.append('level29-fence')
                            self.mage.send=fence
                            client = self.mage
                        elif guid == 13:
                            def send(opcode, payload):
                                step = p.COMMANDS.index(self.command_pending)
                                self.command_pending = None
                                self.mage.observer.packet(self.mage.sock, 0x1D4,
                                                          level_packet(29 if step == 0 else 30))
                                if step == 1:
                                    self.mage.observer.packet(self.mage.sock, 0x12B, struct.pack('<IH', 45438, 0))
                                client.messages.append('You changed level of Apsmetxdtfsp to '+str(29 if step==0 else 30)+'.')
                            client = SimpleNamespace(guid=13, send=send, messages=[])
                        else:
                            client = SimpleNamespace(spells={12824, 133, 168, 45438})
                        try:
                            yield client
                        finally:
                            events.append(('normal-logout', guid))
                    def close_stores(self):
                        events.append('store-close')
                        return []
                    def audit_protected(self, before, after):
                        events.append('audit')
                    def all_offline(self, after):
                        events.append('all-offline')
                db = Mock()
                grant = release() | {'expires_at': time.time() + 300}
                with patch.object(rt, 'attest', return_value={'fake_offline': True}), \
                        patch('pymysql.connect', return_value=db):
                    rc = rt.run(grant, Path(tmp), p, FakeBackend)
                self.assertEqual(rc, int(fail))
                self.assertLess(events.index('preflight'), events.index(('login', 38)))
                self.assertEqual(events.count(('receive', 2)), 1)
                self.assertTrue((Path(tmp) / 'after.json').exists())
                self.assertIn('store-close', events)
                self.assertIn(('normal-logout', 38), events)
                self.assertIn(('normal-logout', 13), events)
                self.assertLess(events.index(('normal-logout', 38)), events.index('after'))
                db.close.assert_called_once()
                result = json.loads((Path(tmp) / 'result.json').read_text())
                self.assertFalse(result['todo97_complete'])
                if fail:
                    self.assertNotIn(('receive', 3), events)
                    self.assertNotIn(('command', 0), events)
                else:
                    self.assertLess(events.index(('applied', 2)), events.index(('receive', 3)))
                    self.assertLess(events.index(('applied', 3)), events.index(('command', 0)))
                    self.assertLess(events.index('level29-fence'),events.index(('command',1)))
                    self.assertLess(events.index(('command', 1)), events.index('same_socket_sealed'))
                    self.assertEqual(events.count(('login', 38)), 2)
                    self.assertEqual(events.count(('command', 0)), 1)
                    self.assertEqual(events.count(('command', 1)), 1)


if __name__ == '__main__':
    unittest.main()
