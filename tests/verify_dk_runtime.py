"""Unbound DK exclusion/start probe. Default prints a plan; never grants execution."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import struct
import time

import verify_artisan_runtime as artisan
from verify_runtime import Runner, SmokeClient, require, guard_account, guard_character, manifest_fixture
from realm_client import create_character
from bridge.catalog import Catalog, ProtocolError
from provision_realm import UUID, check_account
from verify_crash_runtime import CrashRunner, no_other_runners
from verify_class_matrix import aura_spells
from verify_travel_runtime import spell_go
from verify_class_systems import DBC_DIR
from tools.validate_checks import DBC

OUTPUT = artisan.ROOT / '.local/dk-runtime-plan/native-reviewed'
PROFILE = dict(race_id=1, class_id=6)
WORLD = '3b9b2bf9f946a1eeef5908e440ed917132c0559c4bc483ba14be199060641809'
MANIFEST = '6ac13239c2b11940904ece49ea6064c72980e433d6ef06aff587f36babc51553'
PATCH = '76342b88b9864f85525771ba51de7c2b78467343027075b83184bc76356aca6c'
PLAN = dict(status='PREP ONLY; NOT live proof', account='APV2F / id7 / role0',
            profile=PROFILE, level=55, logins=2, creation_limit=1,
            default_auth_calls=0, default_db_calls=0, ap='DK EXCLUDED; no Store ingress',
            requires='Ordinary Human DK55 intro start; fresh parent release and native proof still required',
            release='Separate parent-release.json, all matrix work released, maximum 30 minutes')


def save(name, value):
    (OUTPUT / (name + '.json')).write_text(json.dumps(value, indent=2, default=str))


def release(now=None):
    row = json.loads((OUTPUT / 'parent-release.json').read_text())
    now = time.time() if now is None else now
    require(row.get('native_matrix_released') is True and row.get('owned_release') is True
            and row.get('world_sha256') == WORLD and row.get('manifest_sha256') == MANIFEST
            and row.get('account') == 'APV2F' and row.get('creation_limit') == 1,
            'No explicit matching DK/matrix release')
    start, end = row.get('issued_at'), row.get('expires_at')
    require(type(start) in (int, float) and type(end) in (int, float)
            and start <= now < end and 0 < end - start <= 1800, 'Release expired or exceeds 30 minutes')
    return row


def eligibility(account, rows):
    guard_account(account, 'APV2F')
    require(account['id'] == 7 and account.get('reg_mail') == account['email'], 'Wrong account/reg_mail')
    require(isinstance(rows, list) and rows and len(rows) < 10
            and all(type(r.get('level')) is int and type(r.get('class')) is int for r in rows)
            and max(r['level'] for r in rows) >= 55 and not any(r['class'] == 6 for r in rows),
            'Unknown eligibility, full account, missing level55 or existing DK; no fallback')


def excluded():
    catalog = Catalog()
    require(not any(p['class_id'] == 6 for p in catalog.profiles), 'DK unexpectedly supported')
    raw = manifest_fixture(catalog, 'dk-exclusion-only')
    raw['profile'] = dict(raw['profile'], **PROFILE)
    raw['options'].update(character_race=1, character_class=6)
    try:
        catalog.parse(raw, 'dk-exclusion-only', 1)
    except ProtocolError as exc:
        require('Death Knights are excluded' in str(exc), 'Wrong API rejection')
        return str(exc)
    raise RuntimeError('Catalog accepted DK')


def source_evidence():
    config = artisan.ROOT / '.local/v2-realm/config/worldserver.conf'
    text = config.read_text()
    require(re.search(r'^StartHeroicPlayerLevel\s*=\s*55\s*$', text, re.M), 'Not ordinary heroic55')
    require(re.search(r'^PlayerStart.CustomSpells\s*=\s*0\s*$', text, re.M), 'Custom spells changed')
    inventory = json.loads((artisan.BUILD / 'source-files.sha256.json').read_text())
    contracts = {
        'World/WorldConfig.cpp': ('CONFIG_START_HEROIC_PLAYER_LEVEL, "StartHeroicPlayerLevel", 55',
                                  'CONFIG_START_CUSTOM_SPELLS, "PlayerStart.CustomSpells", false'),
        'Handlers/CharacterHandler.cpp': ('newChar->Create(sObjectMgr->GetGenerator<HighGuid::Player>().Generate(), createInfo.get())',
                                           'sScriptMgr->OnPlayerCreate(newChar.get());'),
        'Globals/ObjectMgr.cpp': ('SELECT race, class, map, zone, position_x, position_y, position_z, orientation FROM playercreateinfo',
                                  'info->mapId = mapId;', 'info->areaId = areaId;',
                                  '_playerInfo[current_race][current_class] = info;'),
        'Entities/Player/Player.cpp': ('sObjectMgr->GetPlayerInfo(createInfo->Race, createInfo->Class)',
                                       'Relocate(info->positionX, info->positionY, info->positionZ, info->orientation);',
                                       'SetMap(sMapMgr->CreateMap(info->mapId, this));',
                                       'uint32 start_level = !IsClass(CLASS_DEATH_KNIGHT, CLASS_CONTEXT_INIT)\n'
                                       '                         ? sWorld->getIntConfig(CONFIG_START_PLAYER_LEVEL)\n'
                                       '                         : sWorld->getIntConfig(CONFIG_START_HEROIC_PLAYER_LEVEL);',
                                       'SetUInt32Value(UNIT_FIELD_LEVEL, start_level);',
                                       'GetMapId() != MAP_EBON_HOLD',
                                       'talentPointsForLevel = GetLevel() < 56 ? 0 : GetLevel() - 55;',
                                       'talentPointsForLevel += m_questRewardTalentCount;',
                                       'sScriptMgr->OnPlayerCalculateTalentsPoints(this, talentPointsForLevel);'),
        'Maps/AreaDefines.h': ('MAP_EBON_HOLD                            = 609,',),
        'Entities/Player/PlayerStorage.cpp': (),
        'Spells/Auras/SpellAuras.cpp': (), 'Spells/Auras/SpellAuraDefines.h': (),
    }
    files = {'src/server/game/' + name: snippets for name, snippets in contracts.items()}
    files['data/sql/base/db_world/playercreateinfo.sql'] = (
        '(1,6,609,4298,2355.84,-5664.77,426.028,3.65997)',)
    files['data/sql/base/db_world/playercreateinfo_skills.sql'] = ()
    hashes = {}
    for path, snippets in files.items():
        source = artisan.SOURCE / path
        hashes[path] = artisan.digest(source)
        require(hashes[path] == inventory[path], 'DK source helper changed: ' + path)
        body = source.read_text()
        require(all(snippet in body for snippet in snippets),
                'Ordinary DK source contract changed: ' + path)
    # Script hooks can change live outcomes; both native logins must still prove the start facts.
    abilities = DBC(DBC_DIR / 'SkillLineAbility.dbc')
    providers = {s: [list(r) for r in abilities.rows.values() if r[2] == s
                    and r[1] in (183, 770, 772) and r[9] == 2 and r[7] == 1
                    and (not r[3] or r[3] & 1) and (not r[4] or r[4] & 32)]
                 for s in (6603, 48266, 47541)}
    require(all(providers.values()), 'Starting spell DBC providers changed')
    return dict(config_sha256=artisan.digest(config), source_files_sha256=hashes,
                dbc_sha256=artisan.digest(DBC_DIR / 'SkillLineAbility.dbc'), providers=providers,
                expected_start=dict(race=1, class_id=6, level=55, map=609, zone=4298,
                                    talent_points=0, starting_spells=[6603, 48266, 47541]),
                config=dict(StartHeroicPlayerLevel=55, **{'PlayerStart.CustomSpells': 0}),
                scope='Read-only source/data expectations, not live plugin or native proof')


class DKClient(SmokeClient):
    def __init__(self, sock, authorize, owner):
        self.owner, self.raw, self.casts, self.auras = owner, {}, [], []

        def checked(guid, events):
            row = owner.character(guid)
            if owner.guid is None:
                require(owner.create_sent and guid not in owner.before and guid > 4
                        and 'CREATED ' + owner.pending_name in events, 'Missing original creation proof')
                guard_character(row, 7, owner.pending_name, {guid}, expected_profile=PROFILE)
                require(row['online'] == 0 and row['level'] == 55, 'Not fresh offline55')
            else:
                require(guid == owner.guid, 'Not owned DK')
            owner.no_ap(guid)
            owner.observed.add(guid)
            save('first-login-guard' if owner.guid is None else 'relogin-guard', row)
            authorize(guid, events)
        super().__init__(sock, checked)

    def connect(self, account, auth, realm, name, **kwargs):
        require(account == 'APV2F' and kwargs == dict(race=1, class_id=6), 'Wrong profile/account')
        self.owner.pending_name = name
        return super().connect(account, auth, realm, name, **kwargs)

    def send(self, opcode, payload=b''):
        require(opcode in (0x1ED, 0x37, 0x36, 0x3D, 0x4B, 0x1DC, 0x391, 0x12E),
                'DK opcode blocked: no GM/chat/equip/Store/teleport/progression')
        if opcode == 0x36:
            require(self.owner.guid is None and not self.owner.create_sent
                    and payload == create_character(self.owner.pending_name, race=1, class_id=6),
                    'Only one exact fresh DK creation')
            self.owner.create_sent = True
            save('creation-intent-sent', dict(name=self.owner.pending_name))
        if opcode == 0x12E:
            require(self.owner.selfcast and not self.owner.cast_sent and self.spells is not None
                    and 48266 in self.spells and payload == struct.pack('<BIBI', 1, 48266, 0, 0),
                    'Only one source-confirmed starting Blood Presence SELF cast')
            self.owner.cast_sent = True
        super().send(opcode, payload)

    def process(self, opcode, payload):
        if opcode in (0x12A, 0x4C0, 0x132, 0x495, 0x496):
            self.raw.setdefault(hex(opcode), []).append(payload.hex())
        if opcode == 0x132:
            self.casts.append(spell_go(payload))
        if opcode in (0x495, 0x496):
            self.auras.append(aura_spells(payload))
        super().process(opcode, payload)


class DKRunner(Runner):
    def __init__(self, db, *, selfcast=False):
        super().__init__(db, 'APV2F')
        self.guid = self.binding = None
        self.observed = set()
        self.create_sent = self.reserved = self.cast_sent = False
        self.selfcast = selfcast
        self.client_type = lambda sock, authorize: DKClient(sock, authorize, self)

    def no_ap(self, guid):
        require(not self.query('SELECT * FROM acore_characters.mod_archipelago_binding WHERE character_guid=%s',
                               (guid,)), 'DK has AP binding; preserve and stop')

    def all_offline(self):
        require(not self.query('SELECT guid FROM acore_characters.characters WHERE online<>0')
                and not self.query('SELECT id FROM acore_auth.account WHERE online<>0'), 'Actors/accounts online')

    def preflight(self):
        self.all_offline()
        require(self.query('SELECT id FROM acore_auth.realmlist') == [dict(id=1)],
                'Single private realm1 required; no other-realm eligibility assumptions')
        start = self.query('SELECT map,zone FROM acore_world.playercreateinfo WHERE race=1 AND class=6')
        require(start == [dict(map=609, zone=4298)], 'Live Human DK start source differs')
        skills = self.query('SELECT skill FROM acore_world.playercreateinfo_skills '
                            'WHERE (raceMask=0 OR raceMask & 1) AND (classMask=0 OR classMask & 32)')
        require({183, 770, 772} <= {r['skill'] for r in skills}, 'Live default skill providers differ')
        row = self.account_row('APV2F')
        private = self.query('SELECT email,reg_mail,salt,verifier FROM acore_auth.account WHERE id=%s', (7,))
        require(len(private) == 1, 'Missing exact account7')
        check_account(private[0], 'APV2F', 'test-only')
        rows = self.query('SELECT guid,level,class FROM acore_characters.characters WHERE account=%s', (7,))
        eligibility(dict(row, reg_mail=private[0]['reg_mail']), rows)
        save('eligibility', dict(account=row, reg_mail=private[0]['reg_mail'], characters=rows))

    @contextmanager
    def login(self, account, *, guid=None):
        require(account == 'APV2F', 'TEST/protected account blocked')
        release()  # Immediately before each shared authenticate path, including relog.
        self.all_offline()
        if guid is None:
            require(not self.reserved, 'No second creation or retry')
            self.preflight()
            self.reserved = True
            with (OUTPUT / 'creation-intent.json').open('x') as stream:
                json.dump(dict(account=account, profile=PROFILE, level=55), stream)
        else:
            require(guid == self.guid and guid in self.known, 'Unknown relog')
        try:
            release()
            with Runner.login(self, account, guid=guid, expected_profile=PROFILE) as result:
                self.guid = result[1]
                yield result
        finally:
            # Also covers connect/validation/body failures before the context yields.
            rows = self.query('SELECT guid FROM acore_characters.characters WHERE account=%s', (7,))
            self.observed.update(r['guid'] for r in rows if r['guid'] not in self.before)
            for owned in sorted(self.observed):
                self.offline(owned)

    def saved(self):
        row = self.offline(self.guid)
        guard_character(row, 7, self.names[self.guid], self.known, expected_profile=PROFILE)
        require(row['guid'] > 4 and row['level'] == 55 and row['map'] == 609 and row['zone'] == 4298,
                'Saved DK start differs')
        self.no_ap(self.guid)
        return dict(character=row, spells=self.query(
            'SELECT spell,specMask FROM acore_characters.character_spell WHERE guid=%s ORDER BY spell', (self.guid,)))

    def protected(self):
        # All preexisting character child tables/stats and ALL AP tables/queues, not only bindings.
        result = CrashRunner.protected(self)
        for table, rows in result.items():
            if table.startswith('mod_archipelago_'):
                continue
            column = {'item_instance': 'owner_guid', 'character_pet': 'owner',
                      'character_pet_declinedname': 'owner'}.get(table, 'guid')
            result[table] = [r for r in rows if r[column] in self.before]
        result['account_access'] = self.query('SELECT * FROM acore_auth.account_access ORDER BY id,RealmID')
        return result

    def execute(self):
        before = self.protected()
        realm_counts = self.query('SELECT * FROM acore_auth.realmcharacters ORDER BY realmid,acctid')
        save('before', dict(tables=before, realm_counts=realm_counts))
        baseline = saved_spells = None
        completed = False
        try:
            for phase in range(2):
                with self.login('APV2F', guid=self.guid) as (client, guid):
                    save('native-' + str(phase), dict(guid=guid, raw=client.raw,
                         spells=sorted(client.spells or []), talent_points=client.talent_points))
                    require(client.spells is not None and {6603, 47541, 48266} <= client.spells
                            and client.talent_points == 0 and '0x4c0' in client.raw, 'Missing native start/talent0')
                    if baseline is None:
                        baseline = set(client.spells)
                    require(client.spells == baseline, 'Starting native baseline changed')
                    if self.selfcast and phase == 0:
                        cast_start, aura_start = len(client.casts), len(client.auras)
                        client.send(0x12E, struct.pack('<BIBI', 1, 48266, 0, 0))
                        client.stay(2)
                        save('selfcast', dict(raw=client.raw, casts=client.casts, auras=client.auras))
                        require(any(c[3] == 48266 and c[0] == c[1] == guid for c in client.casts[cast_start:])
                                and any(g == guid and 48266 in spells for g, spells in client.auras[aura_start:]),
                                'Missing actual Blood Presence SPELL_GO/aura')
                saved = self.saved()
                save('saved-' + str(phase), saved)
                if saved_spells is None:
                    saved_spells = saved['spells']
                require(saved['spells'] == saved_spells, 'Saved learned spell rows changed on relog')
            completed = True
        finally:
            after = self.protected()
            save('after', after)
            save('result', dict(guid=self.guid, observed_guids=sorted(self.observed),
                               sequence_completed=completed, protected_unchanged=before == after,
                               scope='headless start exception only; NOT GUI/full intro/AP support'))
            self.all_offline()
            require(before == after, 'Protected history changed; no repair/reset')
            counts_after = self.query('SELECT * FROM acore_auth.realmcharacters ORDER BY realmid,acctid')
            save('realm-counts-after', counts_after)
            created = self.query('SELECT guid FROM acore_characters.characters WHERE account=%s', (7,))
            added = len([r for r in created if r['guid'] not in self.before])
            expected = [dict(r, numchars=r['numchars'] + added) if r['acctid'] == 7 and r['realmid'] == 1 else r
                        for r in realm_counts]
            require(counts_after == expected, 'Unexpected realm character-count change')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--selfcast', action='store_true')
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps(PLAN, indent=2))
        return
    release()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / 'attempt.json').open('x') as stream:
        json.dump(dict(status='reserved; preserve on any failure', at=time.time()), stream)
    no_other_runners()
    require(os.environ.get('WOWPILAGO_TEST_ACCOUNT_PASSWORD') == 'test-only'
            and os.environ.get('WOWPILAGO_DB_PASSWORD') == 'test-only', 'Private credentials required')
    evidence = artisan.build_evidence()
    require(evidence['world_sha256'] == WORLD and evidence['manifest_sha256'] == MANIFEST
            and json.loads((artisan.BUILD / 'manifest.json').read_text())['patch_sha256'] == PATCH,
            'Fixed candidate drift')
    save('build', evidence)
    save('source', source_evidence())
    save('catalog-rejection', excluded())
    save('runtime', artisan.runtime_evidence(evidence))
    info = json.loads(artisan.docker('inspect', 'wow-test-worldserver-1'))[0]
    config = artisan.ROOT / '.local/v2-realm/config'
    require(any(m['Destination'] == '/work/install/etc' and not m['RW']
                and Path(m['Source']).resolve() == config.resolve() for m in info['Mounts'])
            and info['Config']['Cmd'] == ['-c', '/work/install/etc/worldserver.conf'],
            'Actual config mount/command differs')
    require(artisan.docker('exec', 'wow-test-worldserver-1', 'sha256sum',
                           '/work/install/etc/worldserver.conf').split()[0]
            == artisan.digest(config / 'worldserver.conf'), 'Runtime config differs')
    import pymysql
    with pymysql.connect(host='127.0.0.1', port=13317, user='root', password='test-only',
                         autocommit=True, cursorclass=pymysql.cursors.DictCursor,
                         connect_timeout=5, read_timeout=15, write_timeout=15) as db:
        runner = DKRunner(db, selfcast=args.selfcast)
        require(runner.query('SELECT @@server_uuid AS uuid') == [dict(uuid=UUID)], 'Wrong DB')
        runner.execute()


if __name__ == '__main__':
    main()
