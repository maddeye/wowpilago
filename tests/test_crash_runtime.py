"""Offline behavior tests only. No Docker, database, authentication, or realm."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import verify_crash_runtime as crash


def release():
    return dict(world=crash.WORLD, image=crash.IMAGE, world_id='a' * 64, issued_at=100,
                all_agents_released=True, normal_ap_journey_offline=True,
                exclusive_maintenance=True, offline_guids=[1, 2, 3, 4, 13],
                frozen_pending_sha256=crash.frozen_pending_digest([]))


def state(batches=0):
    result = dict(binding=[dict(id=8)], character=[dict(level=1, xp=0, money=0)],
                  progress=[dict(binding_id=8, vouchers=0, cap_items=0)], rewards=[],
                  inventory=[], items=[], authorized=[], abilities=[], purchases=[], stock=[],
                  spells=[], checks=[], boss_credit=[], enabled_checks=[], allowed_rewards=[])
    for batch in range(batches):
        item = 100 + batch
        for offset in range(2):
            result['rewards'].append(dict(binding_id=8, item_index=batch * 2 + offset,
                ap_item=crash.CODES[offset], kind='vouchers' if offset else 'bag',
                value=5 if offset else 21841, sender=0, location_id=-1, flags=0,
                applied=1, applied_value=5 if offset else 1, applied_at='timestamp',
                item_guid=None if offset else item))
        result['progress'][0]['vouchers'] += 5
        result['items'].append(dict(guid=item, owner_guid=20, itemEntry=21841, count=1, flags=1))
        result['inventory'].append(dict(bag=0, slot=23 + batch, item=item))
        result['authorized'].append(dict(item_guid=item, binding_id=8, item_entry=21841))
    return result


def runtime():
    return dict(Name='/' + crash.WORLD, Id='a' * 64, Image=crash.IMAGE,
                Config=dict(Entrypoint=['/work/install/bin/worldserver'],
                            Cmd=['-c', '/work/install/etc/worldserver.conf']),
                HostConfig=dict(RestartPolicy=dict(Name='no', MaximumRetryCount=0)),
                Mounts=[dict(Destination='/work/install', Source=str(crash.BUILD / 'install'), RW=False)],
                State=dict(Running=True, ExitCode=0, StartedAt='original'))


CHALLENGE = bytes.fromhex('002aec01') + b'\x01\x00\x00\x00' + bytes(range(36))


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.runner = object.__new__(crash.CrashRunner)
        self.runner.initial = crash.runtime_identity(runtime())
        self.runner.companions = {'auth': runtime(), 'database': runtime()}
        self.runner.output, self.runner.crashes = Path('/unused'), 0
        for name, kwargs in [('inspect', dict(return_value=runtime())),
                             ('command', dict(return_value=crash.WORLD_HASH + ' /proc/1/exe')),
                             ('save', {})]:
            patcher = patch.object(crash, name, **kwargs)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

    @contextlib.contextmanager
    def connections(self, *packets):
        with contextlib.ExitStack() as stack:
            clients = []
            for packet in packets:
                client, server = crash.socket.socketpair()
                stack.enter_context(client)
                stack.enter_context(server)
                server.sendall(packet)
                server.shutdown(crash.socket.SHUT_WR)
                clients.append(client)
            with patch.object(crash.socket, 'create_connection', side_effect=clients) as connect, \
                 patch.object(crash.time, 'sleep'):
                yield connect

    def test_proxy_accept_eof_then_full_world_challenge(self):
        with self.connections(b'', CHALLENGE) as connect:
            self.runner.health()
        self.assertEqual(connect.call_count, 2)
        self.assertEqual(connect.call_args.kwargs['timeout'], 2)
        self.assertEqual(self.command.call_count, 1)
        self.assertEqual(self.inspect.call_count, 4)  # Two world probes plus auth/database.
        self.save.assert_called_once()

    def test_partial_header_requires_all_four_bytes(self):
        sock = Mock()
        sock.recv.side_effect = [CHALLENGE[:1], CHALLENGE[1:3], CHALLENGE[3:4], CHALLENGE[4:]]
        with patch.object(crash.socket, 'create_connection', return_value=contextlib.closing(sock)):
            self.assertEqual(crash.read_world_challenge(), CHALLENGE)
        self.assertEqual([c.args[0] for c in sock.recv.call_args_list], [4, 3, 1, 40])
        sock.sendall.assert_not_called()

    def test_partial_payload_requires_all_forty_bytes(self):
        sock = Mock()
        sock.recv.side_effect = [CHALLENGE[:4], CHALLENGE[4:5], CHALLENGE[5:20], CHALLENGE[20:]]
        with patch.object(crash.socket, 'create_connection', return_value=contextlib.closing(sock)):
            self.assertEqual(crash.read_world_challenge(), CHALLENGE)
        self.assertEqual([c.args[0] for c in sock.recv.call_args_list], [4, 40, 39, 24])

    def test_truncated_header_or_payload_retries_without_declaring_ready(self):
        for truncated in (CHALLENGE[:2], CHALLENGE[:4], CHALLENGE[:-1]):
            with self.subTest(length=len(truncated)), self.connections(truncated, CHALLENGE) as connect:
                self.runner.health()
                self.assertEqual(connect.call_count, 2)

    def test_wrong_opcode_or_size_fails_closed_without_retry(self):
        for header in ('002aed01', '0029ec01', '002bec01', '802aec01'):
            with self.subTest(header=header), self.connections(bytes.fromhex(header)) as connect:
                with self.assertRaises(crash.ProtocolError):
                    self.runner.health()
                connect.assert_called_once()
        self.command.assert_not_called()
        self.save.assert_not_called()

    def test_socket_timeout_retries_and_both_deadlines_are_bounded(self):
        with patch.object(crash, 'read_world_challenge',
                          side_effect=[crash.socket.timeout(), CHALLENGE]) as probe, \
             patch.object(crash.time, 'sleep'):
            self.runner.health()
            self.assertEqual(probe.call_count, 2)
        sock = Mock()
        sock.recv.return_value = b'\x00'
        with patch.object(crash.socket, 'create_connection', return_value=contextlib.closing(sock)), \
             patch.object(crash.time, 'monotonic', side_effect=[0, 0, 1, 2]):
            with self.assertRaises(crash.socket.timeout):
                crash.read_world_challenge()
        self.assertEqual(sock.recv.call_count, 2)  # Dripping bytes cannot reset the 2s deadline.
        self.assertEqual([c.args[0] for c in sock.settimeout.call_args_list], [2, 1])
        with patch.object(crash.time, 'monotonic', side_effect=[0, 119, 119.5, 120, 120]), \
             patch.object(crash.time, 'sleep') as sleep, \
             patch.object(crash, 'read_world_challenge', side_effect=crash.socket.timeout()) as probe:
            with self.assertRaisesRegex(RuntimeError, 'readiness timeout'):
                self.runner.health()
        probe.assert_called_once_with(timeout=.5)
        sleep.assert_called_once_with(0)


class CrashTests(unittest.TestCase):
    def test_empty_mysql_tuple_rows_are_canonical_snapshot_lists(self):
        runner = crash.CrashRunner.__new__(crash.CrashRunner)
        runner.guid, runner.binding = 99, 88
        runner.exclusive = lambda: None
        runner.snapshot = lambda *args: {'items': (), 'authorized': (), 'abilities': ()}
        runner.query = lambda *args: ()
        with tempfile.TemporaryDirectory() as root:
            runner.output = Path(root)
            state = runner.state('empty')
        for key in ('items', 'authorized', 'abilities', 'checks', 'boss_credit', 'enabled_checks', 'allowed_rewards'):
            self.assertEqual(state[key], [])

    def test_default_has_no_external_calls_or_artifact_creation(self):
        with patch.object(crash, 'command', side_effect=AssertionError('Docker')), \
             patch.object(crash, 'source_evidence', side_effect=AssertionError('source probe')), \
             patch.object(crash, 'CrashRunner', side_effect=AssertionError('DB')), \
             patch.object(Path, 'mkdir', side_effect=AssertionError('write')), \
             patch.object(crash.socket, 'create_connection', side_effect=AssertionError('network')), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(crash.main([]), 0)
        self.assertFalse(json.loads(output.getvalue())['network_without_run'])

    def test_run_requires_release_before_any_external_call(self):
        with patch.object(crash, 'command', side_effect=AssertionError('external')):
            with self.assertRaisesRegex(RuntimeError, '--release'):
                crash.main(['--run'])

    def test_release_refuses_stale_incomplete_and_wrong_runtime(self):
        crash.validate_release(release(), 110)
        for key, value in [('issued_at', -1000), ('issued_at', 111), ('all_agents_released', False),
                           ('normal_ap_journey_offline', False), ('exclusive_maintenance', False),
                           ('offline_guids', [1, 2, 3]), ('offline_guids', [1, 2, 3, 4, 4]),
                           ('world', 'wow-worldserver-1'), ('image', 'latest'), ('world_id', 'short')]:
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                crash.validate_release(dict(release(), **{key: value}), 110)

    def test_runtime_requires_pinned_image_command_mount_and_no_auto_restart(self):
        crash.runtime_identity(runtime())
        for change in ('image', 'policy', 'mount', 'command'):
            info = runtime()
            if change == 'image':
                info['Image'] = 'latest'
            elif change == 'policy':
                info['HostConfig']['RestartPolicy']['Name'] = 'always'
            elif change == 'mount':
                info['Mounts'][0]['RW'] = True
            else:
                info['Config']['Cmd'] = ['other.conf']
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                crash.runtime_identity(info)

    def test_exact_queue_no_early_effect(self):
        before, queued = state(), state(1)
        queued['inventory'], queued['items'], queued['authorized'] = [], [], []
        queued['progress'] = deepcopy(before['progress'])
        for row in queued['rewards']:
            row.update(applied=0, applied_value=0, item_guid=None, applied_at=None)
        crash.verify_queued(before, queued)
        queued['progress'][0]['vouchers'] = 5
        with self.assertRaises(RuntimeError):
            crash.verify_queued(before, queued)

    def test_one_and_two_batches_have_exact_effects(self):
        for batches in (1, 2):
            crash.verify_effects(state(), state(batches), batches, 20, 8)

    def test_effect_checker_rejects_extra_effects_and_bad_item_proofs(self):
        changes = [lambda s: s['items'][0].update(count=2),
                   lambda s: s['items'][0].update(flags=9),
                   lambda s: s['items'][0].update(owner_guid=4),
                   lambda s: s['inventory'][0].update(slot=19),
                   lambda s: s['inventory'].append(dict(s['inventory'][0])),
                   lambda s: s['authorized'][0].update(binding_id=9),
                   lambda s: s['progress'][0].update(vouchers=10),
                   lambda s: s['character'][0].update(money=1000),
                   lambda s: s['purchases'].append(dict(stock_index=0)),
                   lambda s: s['rewards'][0].update(ap_item=42),
                   lambda s: s['rewards'][1].update(item_guid=100),
                   lambda s: s['rewards'].append(dict(s['rewards'][0]))]
        for index, change in enumerate(changes):
            after = state(1)
            change(after)
            with self.subTest(index=index), self.assertRaises(RuntimeError):
                crash.verify_effects(state(), after, 1, 20, 8)

    def test_queue_uses_valid_networkitem_and_only_store_ingress(self):
        runner = object.__new__(crash.CrashRunner)
        runner.store = Mock()
        runner.exclusive = Mock()
        runner.store.receive.return_value = True
        runner.queue(2)
        start, records = runner.store.receive.call_args.args
        self.assertEqual(start, 2)
        self.assertEqual([r['item'] for r in records], list(crash.CODES))
        self.assertTrue(all(r['class'] == 'NetworkItem' and r['location'] == -1 for r in records))
        runner.store.receive.return_value = False
        with self.assertRaises(RuntimeError):
            runner.queue(2)

    def test_world_only_sigkill_and_start_preserve_policy(self):
        runner = object.__new__(crash.CrashRunner)
        runner.crashes, runner.guid = 0, 20
        runner.initial = crash.runtime_identity(runtime())
        runner.exclusive, runner.health, runner.offline = Mock(), Mock(), Mock()
        runner.character = Mock(return_value=dict(online=1))
        player = Mock()
        dead = runtime()
        dead['State'].update(Running=False, ExitCode=137)
        with tempfile.TemporaryDirectory() as directory:
            runner.output = Path(directory)
            with patch.object(crash, 'inspect', side_effect=[runtime(), dead]), \
                 patch.object(crash, 'command') as command:
                runner.crash(player)
            self.assertEqual(command.call_args_list[0].args,
                             ('docker', 'kill', '--signal=SIGKILL', crash.WORLD))
            self.assertEqual(command.call_args_list[1].args, ('docker', 'start', crash.WORLD))
            self.assertEqual(command.call_count, 2)
            player.sock.close.assert_called_once()
            player.logout()  # Replaced with no-op, no graceful logout packet.
            runner.health.assert_called_once()
            runner.offline.assert_called_once_with(20)
            self.assertTrue((runner.output / 'killed-1.json').exists())
        runner.crashes = 2
        with self.assertRaises(RuntimeError):
            runner.crash()

    def test_refuses_to_restart_without_confirmed_sigkill(self):
        runner = object.__new__(crash.CrashRunner)
        runner.crashes, runner.guid = 0, None
        runner.exclusive = Mock()
        runner.initial = crash.runtime_identity(runtime())
        with tempfile.TemporaryDirectory() as directory:
            runner.output = Path(directory)
            with patch.object(crash, 'inspect', side_effect=[runtime(), runtime()]), \
                 patch.object(crash, 'command') as command, self.assertRaises(RuntimeError):
                runner.crash()
            self.assertEqual(command.call_count, 1)

    def test_no_test_or_existing_guid_login(self):
        runner = object.__new__(crash.CrashRunner)
        runner.exclusive = Mock()
        runner.guid, runner.known = 20, {20}
        for account, guid in [('TEST', 13), ('APV2B', 4), ('APV2B', 21)]:
            with self.subTest(account=account, guid=guid), self.assertRaises(RuntimeError):
                with runner.login(account, guid=guid):
                    self.fail('unsafe login')

    def test_exclusive_guard_rejects_online_pending_nondisconnected_and_owned_fixtures(self):
        runner = object.__new__(crash.CrashRunner)
        runner.release, runner.guid, runner.binding = release(), None, None
        runner.account_row = Mock(return_value=dict(id=9))

        def rows(sql, args=()):
            if sql == 'SELECT guid FROM acore_characters.characters':
                return [dict(guid=g) for g in release()['offline_guids']]
            if sql.startswith('SELECT IS_USED_LOCK'):
                return [dict(owner=None)]
            return []

        with patch.object(crash, 'no_other_runners'), patch.object(crash.time, 'time', return_value=110):
            runner.query = Mock(side_effect=rows)
            runner.exclusive()
            for token, bad in [('WHERE online<>0', [dict(guid=4, id=9)]),
                               ("status<>'disconnected'", [dict(id=1)]),
                               ('WHERE applied=0', [dict(binding_id=99, applied=0)]),
                               ('IS_USED_LOCK', [dict(owner=123)])]:
                runner.query = Mock(side_effect=lambda sql, args=(), token=token, bad=bad:
                                    bad if token in sql else rows(sql, args))
                with self.subTest(token=token), self.assertRaises(RuntimeError):
                    runner.exclusive()

    def test_digest_is_exact_order_independent_and_has_literal_empty_encoding(self):
        self.assertEqual(crash.frozen_pending_digest([]),
                         '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945')
        rows = [dict(binding_id=3, item_index=0, applied=0, value=5),
                dict(binding_id=7, item_index=2, applied=0, value=21841)]
        self.assertEqual(crash.frozen_pending_digest(rows),
                         crash.frozen_pending_digest([dict(reversed(list(r.items()))) for r in reversed(rows)]))
        self.assertNotEqual(crash.frozen_pending_digest(rows), crash.frozen_pending_digest(rows + rows))

    def test_release_requires_explicit_digest_even_for_empty_history(self):
        for value in (None, '', '0' * 63, 'g' * 64, 'A' * 64, True):
            with self.subTest(value=value), self.assertRaisesRegex(RuntimeError, 'frozen_pending_sha256'):
                crash.validate_release(dict(release(), frozen_pending_sha256=value), 110)
        omitted = release()
        del omitted['frozen_pending_sha256']
        with self.assertRaisesRegex(RuntimeError, 'frozen_pending_sha256'):
            crash.validate_release(omitted, 110)

    def test_existing_frozen_queue_allowed_but_any_history_change_rejected(self):
        frozen = [dict(binding_id=3, item_index=i, applied=0, value=5,
                       applied_at=None, applied_value=0, item_guid=None) for i in range(7)]
        frozen += [dict(binding_id=b, item_index=0, applied=0, value=21841,
                        applied_at=None, applied_value=0, item_guid=None) for b in (7, 9)]
        runner = object.__new__(crash.CrashRunner)
        runner.release = dict(release(), frozen_pending_sha256=crash.frozen_pending_digest(frozen))
        runner.guid = runner.binding = None
        runner.account_row = Mock(return_value=dict(id=9))
        pending = deepcopy(frozen)

        def rows(sql, args=()):
            if sql == crash.FROZEN_PENDING_SQL:
                return [r for r in pending if r['applied'] == 0]
            if sql == 'SELECT guid FROM acore_characters.characters':
                return [dict(guid=g) for g in runner.release['offline_guids']] + (
                    [dict(guid=runner.guid)] if runner.guid not in (None, 13) else [])
            if sql.startswith('SELECT character_guid'):
                return [dict(character_guid=runner.guid)]
            if sql.startswith('SELECT IS_USED_LOCK'):
                return [dict(owner=None)]
            return []

        runner.query = Mock(side_effect=rows)
        with patch.object(crash, 'no_other_runners'), patch.object(crash.time, 'time', return_value=110):
            runner.exclusive()  # All nine old receipts remain pending, untouched.
            for token, bad in [('WHERE online<>0', [dict(guid=7, id=9)]),
                               ("status<>'disconnected'", [dict(id=3)]),
                               ('IS_USED_LOCK', [dict(owner=123)])]:
                runner.query = Mock(side_effect=lambda sql, args=(), token=token, bad=bad:
                                    bad if token in sql else rows(sql, args))
                with self.subTest(token=token), self.assertRaises(RuntimeError):
                    runner.exclusive()
            runner.query = Mock(side_effect=rows)
            for change in ('wrong digest', 'new', 'changed', 'applied', 'removed'):
                pending = deepcopy(frozen)
                runner.release['frozen_pending_sha256'] = crash.frozen_pending_digest(frozen)
                if change == 'wrong digest':
                    runner.release['frozen_pending_sha256'] = '0' * 64
                elif change == 'new':
                    pending.append(dict(binding_id=99, item_index=0, applied=0))
                elif change == 'changed':
                    pending[0]['value'] = 6
                elif change == 'applied':
                    pending[0]['applied'] = 1
                else:
                    pending.pop()
                with self.subTest(change=change), self.assertRaisesRegex(RuntimeError, 'Frozen pending'):
                    runner.exclusive()
            pending = deepcopy(frozen)
            runner.release['frozen_pending_sha256'] = crash.frozen_pending_digest(frozen)
            runner.guid, runner.binding = 20, 80
            pending.append(dict(binding_id=80, item_index=0, applied=0))
            runner.exclusive()  # Only this invocation's fresh queue is excluded.
            pending[-1]['applied'] = 1
            runner.exclusive()
            pending[0]['value'] = 6
            with self.assertRaisesRegex(RuntimeError, 'Frozen pending'):
                runner.exclusive()
            pending = deepcopy(frozen)
            runner.guid, runner.binding = 13, 3
            with self.assertRaisesRegex(RuntimeError, 'Frozen history'):
                runner.exclusive()
            runner.guid = 20
            runner.query = Mock(side_effect=lambda sql, args=():
                                [dict(character_guid=13)] if sql.startswith('SELECT character_guid')
                                else rows(sql, args))
            with self.assertRaisesRegex(RuntimeError, 'Owned binding'):
                runner.exclusive()

    def test_final_protection_checks_digest_and_full_preexisting_history(self):
        pending = dict(binding_id=3, item_index=0, applied=0, value=5)
        delivered = dict(binding_id=3, item_index=1, applied=1, value=5)
        before = dict(mod_archipelago_reward=[pending, delivered], characters=[dict(guid=7)])
        attested = dict(release(), frozen_pending_sha256=crash.frozen_pending_digest([pending]))
        crash.verify_protected(before, deepcopy(before), attested)
        for change in ('new', 'changed', 'applied', 'delivered history', 'character'):
            after = deepcopy(before)
            if change == 'new':
                after['mod_archipelago_reward'].append(dict(binding_id=9, item_index=0, applied=0))
            elif change == 'changed':
                after['mod_archipelago_reward'][0]['value'] = 6
            elif change == 'applied':
                after['mod_archipelago_reward'][0]['applied'] = 1
            elif change == 'delivered history':
                after['mod_archipelago_reward'][1]['value'] = 6
            else:
                after['characters'][0]['guid'] = 8
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                crash.verify_protected(before, after, attested)
        with self.assertRaisesRegex(RuntimeError, 'Frozen pending'):
            crash.verify_protected(before, before, release())

    def test_stage_boundaries_refuse_before_queue_snapshot_or_kill(self):
        runner = object.__new__(crash.CrashRunner)
        runner.exclusive = Mock(side_effect=RuntimeError('Frozen pending changed'))
        runner.store, runner.snapshot = Mock(), Mock()
        with patch.object(crash, 'command') as command:
            for operation in (lambda: runner.queue(0), lambda: runner.state('test'),
                              lambda: runner.applied(Mock(), 2), runner.crash):
                with self.assertRaisesRegex(RuntimeError, 'Frozen pending'):
                    operation()
            command.assert_not_called()
        runner.store.receive.assert_not_called()
        runner.snapshot.assert_not_called()

    def test_second_creation_is_refused_before_authentication(self):
        runner = object.__new__(crash.CrashRunner)
        runner.exclusive, runner.created = Mock(), True
        with self.assertRaisesRegex(RuntimeError, 'Only one creation'):
            with runner.login():
                self.fail('second fixture')

    def test_health_rejects_changed_identity_without_starting_anything(self):
        runner = object.__new__(crash.CrashRunner)
        runner.initial = crash.runtime_identity(runtime())
        changed = runtime()
        changed['Id'] = 'b' * 64
        with patch.object(crash, 'inspect', return_value=changed), \
             patch.object(crash.socket, 'create_connection') as connection, \
             patch.object(crash, 'command') as command, self.assertRaisesRegex(RuntimeError, 'identity'):
            connection.return_value.__enter__.return_value.recv.side_effect = [CHALLENGE[:4], CHALLENGE[4:]]
            runner.health()
        command.assert_not_called()
        connection.assert_called_once()

    def test_observer_rejects_sql_writes(self):
        runner = object.__new__(crash.CrashRunner)
        for sql in ('UPDATE characters SET online=0', 'CALL apply_reward()', 'SELECT 1; DELETE FROM characters'):
            with self.assertRaises(RuntimeError):
                runner.query(sql)


if __name__ == '__main__':
    unittest.main()
