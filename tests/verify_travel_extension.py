"""One-shot extension of the hash-pinned, already-owned travel fixture. No creation."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import struct
import sys
import time
from unittest.mock import patch

import verify_runtime as shared
import verify_travel_runtime as travel
from verify_runtime import require, guard_account, LABEL
from verify_class_systems import DBC_DIR, items
from bridge.catalog import Catalog
from bridge.v2 import Store
from tools.validate_checks import DBC

OUTPUT = travel.ROOT / '.local/travel-extension'
PRIOR = travel.OUTPUT
HASHES = {
    'creation.json': '026efa96e5e24a788aeb0aed63159ad722939e40b0c991efa0c6b4414f6fed75',
    'manifest.json': 'edfa6be958ab7b12c6ab486eeb1bcbcd8d855b4517eb10709b599e32e32521df',
    'run.jsonl': '34bbbb1ad830730aa3a8b792f6e57461ff6f99330d1b7cd7ecdea95daf755664',
    'summary.json': 'bcc4abac81065a1bb738c06a262066101e83c14a69da009a7a81a6ead0070b58',
}
NAME, SEED = 'Apsfjnnrfebe', 'fabricated-travel-26946f5d437ba3bfa7eb55bd'
ARTISAN, FAST = 919100013, 32242
PLAN = dict(label=LABEL, network_without_run=False, guid=24, account='APV2F', binding=14,
            checks=['online Darnassus map 1 native flight denial',
                    'Outland fast flight before and after ONE next-index Artisan receipt'],
            excluded=['creation', 'history reset', 'SQL character writes', 'airborne movement', 'real AP'])


def normalized(value):
    return json.loads(json.dumps(value, default=str))


def prior_evidence():
    files = {name: (PRIOR / name).read_bytes() for name in HASHES}
    require({name: hashlib.sha256(data).hexdigest() for name, data in files.items()} == HASHES,
            'Original travel evidence hash mismatch')
    creation = json.loads(files['creation.json'])
    require(creation == dict(guid=24, name=NAME, account='APV2F', label=LABEL), 'Creation identity mismatch')
    events = [json.loads(line) for line in files['run.jsonl'].splitlines() if line.strip()]
    require([e for e in events if e.get('event') == 'fixture_created'] ==
            [dict(event='fixture_created', **creation)], 'Nonunique original creation')
    require([e for e in events if e.get('event') == 'binding'] ==
            [dict(event='binding', binding=14, guid=24, label=LABEL, seed=SEED)], 'Original binding mismatch')
    require(json.loads(files['summary.json'])['result'] == {'event': 'PASS'}
            and events[-1]['event'] == 'protected_assertion' and events[-1]['unchanged'], 'Prior run not released')
    state = next(e['state'] for e in events if e.get('event') == 'durable_state'
                 and e.get('label') == 'Northrend Cold Weather at 77')
    return json.loads(files['manifest.json']), state


def immutable(binding):
    return {k: v for k, v in binding.items() if k not in ('heartbeat', 'status')}


def fast_dbc():
    dbc = DBC(DBC_DIR / 'Spell.dbc')
    row = dbc.rows[FAST]
    require(dbc.text(row[136]) == 'Swift Blue Gryphon' and row[71:74] == (6, 6, 6)
            and row[95:98] == (78, 207, 32) and row[80:83] == (0, 279, 99),
            'Fast mount ID/name/effects differ from actual DBC')
    return dict(spell=FAST, name=dbc.text(row[136]), row=row,
                sha256=hashlib.sha256(dbc.raw).hexdigest())


class ExtensionRunner(travel.TravelRunner):
    @contextmanager
    def login(self, account, *, guid=None):
        require(guid is not None, 'Extension never creates characters')
        with super().login(account, guid=guid) as result:
            yield result

    def binding_row(self):
        rows = self.query('SELECT * FROM acore_characters.mod_archipelago_binding WHERE character_guid=24')
        require(len(rows) == 1, 'Missing or duplicate owned binding')
        return rows[0]

    def skills(self):
        return self.query('SELECT * FROM acore_characters.character_skills WHERE guid=24 AND skill=762')

    def verify_owned(self, raw, prior):
        account = self.account_row('APV2F')
        guard_account(account, 'APV2F')
        require(account['id'] == 7, 'Fixture account ID changed')
        require(self.query('SELECT guid,name FROM acore_characters.characters WHERE account=7') ==
                [dict(guid=24, name=NAME)], 'Fixture account character set changed')
        row = self.character(24)
        require(row is not None and all(row[k] == v for k, v in dict(
            guid=24, name=NAME, account=7, race=1, **{'class': 1}, level=77, online=0).items()),
            'Owned fixture profile/level/offline mismatch')
        require(str(row['creation_date']) == prior['location']['creation_date'], 'Creation timestamp changed')
        binding = self.binding_row()
        catalog = Catalog()
        manifest = catalog.parse(raw, SEED, 1)
        require(all(binding[k] == v for k, v in dict(id=14, character_guid=24,
            character_name=NAME, character_account=7, seed_name=SEED, team=0, slot=1,
            class_id=1, race_id=1, faction='alliance', protocol_version=2,
            manifest_hash=manifest.checksum, status='disconnected').items())
            and json.loads(binding['manifest']) == raw, 'Immutable binding/manifest mismatch')
        progress = self.query('SELECT * FROM acore_characters.mod_archipelago_progress WHERE binding_id=14')
        rewards = self.query('SELECT * FROM acore_characters.mod_archipelago_reward WHERE binding_id=14 ORDER BY item_index')
        spells = self.query('SELECT spell,specMask FROM acore_characters.character_spell WHERE guid=24 ORDER BY spell')
        require(normalized(progress) == prior['progress'] and normalized(rewards) == prior['rewards']
                and spells == prior['spells'] and all(r['applied'] == 1 for r in rewards)
                and [r['item_index'] for r in rewards] == list(range(13)), 'Prior state/history changed')
        require(progress[0]['riding_flags'] == 23 and progress[0]['cap_items'] == 7
                and progress[0]['access_flags'] == 3 and set(travel.MOUNTS) <= {r['spell'] for r in spells}
                and 34091 not in {r['spell'] for r in spells}, 'Unexpected prior riding state')
        require(self.skills() == [dict(guid=24, skill=762, value=225, max=225)], 'Prior riding skill changed')
        # Seed the login allowlist only after every ownership and immutable-history check above.
        self.guid, self.binding, self.level = 24, 14, 77
        self.known.add(24)
        self.names[24] = NAME
        self.codes = [r['ap_item'] for r in rewards]
        self.original_rewards, self.original_binding = rewards, immutable(binding)
        travel.emit('verified_owned_fixture', guid=24, binding=14, evidence_sha256=HASHES,
                    binding_row=binding, progress=progress, skills=self.skills())
        return catalog

    def assert_history(self):
        rewards = self.query('SELECT * FROM acore_characters.mod_archipelago_reward WHERE binding_id=14 ORDER BY item_index')
        require(rewards[:13] == self.original_rewards and immutable(self.binding_row()) == self.original_binding,
                'Old receipts or immutable binding changed')
        return rewards

    def execute(self):
        raw, prior = prior_evidence()
        catalog = self.verify_owned(raw, prior)
        control = self.reuse_control()  # Original GM13 guard unchanged.
        self.state('verified prior state')
        self.store = Store(dict(host='127.0.0.1', port=13317, user='root', database='acore_characters'), 24, catalog)
        require(self.store.bind(SEED, 0, 1, raw) == 14, 'Existing Store binding changed')
        self.store.status('disconnected')
        self.assert_history()
        tele = self.query("SELECT * FROM acore_world.game_tele WHERE name='Darnassus'")
        require(len(tele) == 1 and tele[0] == dict(id=252, position_x=9949.56, position_y=2284.21,
                position_z=1341.4, orientation=1.59587, map=1, name='Darnassus'), 'Darnassus coordinates changed')
        path = travel.SOURCE / 'data/sql/base/db_world/game_tele.sql'
        data = path.read_bytes()
        require(b"(252,9949.56,2284.21,1341.4,1.59587,1,'Darnassus')" in data, 'Pinned destination missing')
        travel.emit('destination_evidence', row=tele[0], source=str(path), sha256=hashlib.sha256(data).hexdigest())
        with self.login('TEST', guid=control) as (gm, _):
            with self.login('APV2F', guid=24) as (player, _):
                player.send(0x136, struct.pack('<I', 32239))
                player.stay(.3)
                self.teleport(player, gm, 'Darnassus', 1)
                require(all(abs(a-b) < .1 for a, b in zip(player.world[1:4], (9949.56, 2284.21, 1341.4))),
                        'Native destination coordinates differ')
                self.cast(player, 32239, error=60)
            self.state('Kalimdor native flight denied')
            with self.login('APV2F', guid=24) as (player, _):
                self.teleport(player, gm, 'HellfirePeninsula', 530)
                self.setup(gm, '.learn ' + str(FAST))  # Ordinary mount only, never riding training.
                player.stay(.5)
                try:
                    self.cast(player, FAST, error=107)
                except RuntimeError:
                    # Preserve a native failed negative check, but still observe the authorized post-receipt case.
                    require((24, 24, self.count, FAST) in player.casts
                            and not [f for f in player.failures if f[:2] == (self.count, FAST)]
                            and any(g == 24 and abs(s - 26.6) < .02 for _, g, s in player.speeds),
                            'Unexpected fast mount negative-check response')
                    self.defects.append('Fast flight 32242 accepted at 26.6 before Artisan, riding flags 23 / skill 225')
                    travel.emit('native_defect', detail=self.defects[-1], cast_count=self.count)
            before = self.state('fast mount before Artisan')
            require(before['progress'][0]['riding_flags'] == 23 and 34091 not in {r['spell'] for r in before['spells']},
                    'Artisan unexpectedly trained before receipt')
            self.assert_history()
            with self.login('APV2F', guid=24) as (player, _):
                require(len(self.codes) == 13, 'Not exact next index 13')
                self.queue(player, gm, ARTISAN)
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if player.spells is not None and 34091 in player.spells:
                        break
                    player.stay(.2)
                # Durable native save below verifies both the training spell and riding skill.
            trained = self.state('native Artisan receipt and training')
            require(34091 in {r['spell'] for r in trained['spells']} and trained['progress'][0]['riding_flags'] == 31
                    and self.skills() == [dict(guid=24, skill=762, value=300, max=300)], 'Native Artisan training missing')
            travel.emit('native_riding_skill', rows=self.skills())
            with self.login('APV2F', guid=24) as (player, _):
                self.cast(player, FAST, speed=26.6)
            after = self.state('actual Outland Artisan fast flight')
            require(any(r['spell'] == FAST and r['amount1'] == 280 for r in after['auras']), 'Saved 280 flight aura missing')
            with self.login('APV2F', guid=24) as (player, _):
                player.send(0x136, struct.pack('<I', FAST))
                player.stay(.3)
                self.teleport(player, gm, 'BoreanTundra', 571)
                self.cast(player, FAST, speed=26.6)
            north = self.state('actual Northrend Artisan fast flight')
            require(any(r['spell'] == FAST and r['amount1'] == 280 for r in north['auras']), 'Saved Northrend fast aura missing')
        self.offline(control)
        rewards = self.assert_history()
        require(len(rewards) == 14 and rewards[-1]['item_index'] == 13 and rewards[-1]['ap_item'] == ARTISAN
                and rewards[-1]['applied'] == 1, 'Not exactly one new applied Artisan receipt')
        require(after['inventory'] == prior['inventory'] and after['items'] == prior['items']
                and after['character'] == prior['character'], 'Character economy changed')
        travel.emit('history_assertion', old_indices=list(range(13)), unchanged=True, appended_index=13,
                    binding_immutable=True, skill=self.skills(), offline_guids=[13, 24])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps(PLAN, indent=2))
        return 0
    require(os.environ.get('WOWPILAGO_TEST_ACCOUNT_PASSWORD') == 'test-only'
            and os.environ.get('WOWPILAGO_DB_PASSWORD') == 'test-only', 'Private credentials required')
    prior_evidence()
    travel.emit('source_evidence', **travel.source_evidence(), fast_mount=fast_dbc())
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / 'attempt.json').open('x') as handle:
        json.dump(PLAN, handle, indent=2)
    import pymysql
    with pymysql.connect(host='127.0.0.1', port=13317, user='root', password='test-only', autocommit=True,
                         cursorclass=pymysql.cursors.DictCursor, connect_timeout=5, read_timeout=15, write_timeout=15) as db:
        runner = ExtensionRunner(db)
        runner.defects = []
        before = runner.protected()
        (OUTPUT / 'before.json').write_text(json.dumps(before, default=str, indent=2))
        result = {'event': 'FAIL'}
        try:
            with patch.object(shared, 'SmokeClient', travel.TravelClient):
                runner.execute()
            result = dict(event='FAIL' if runner.defects else 'PASS', defects=runner.defects)
        except Exception as exc:
            result['error'] = str(exc)
        finally:
            if runner.store is not None:
                runner.store.close()
            after = runner.protected()
            (OUTPUT / 'after.json').write_text(json.dumps(after, default=str, indent=2))
            if before != after:
                result = dict(event='FAIL', error='Protected GUIDs 1..3 changed')
            summary = dict(result=result, guid=24, binding=14, checks=runner.checks, defects=runner.defects,
                           protected_unchanged=before == after, world_sha256=travel.WORLD_HASH,
                           actual_flight_movement='unproven: no airborne position test', label=LABEL)
            (OUTPUT / 'summary.json').write_text(json.dumps(summary, indent=2))
            travel.emit('extension_result', **summary)
    return 0 if result['event'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
