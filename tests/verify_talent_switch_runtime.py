"""Owned talent-switch executor. Default and source evidence are offline only."""
import argparse
from copy import deepcopy
from dataclasses import dataclass
from functools import cache
import json
from pathlib import Path
import struct
import os
import re
import select
import sys
import time
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / '.local/talent-switch-plan'
BIRTH = ROOT / '.local/class-matrix-plan/third-reviewed-run/attempt-ec4bda0bfebd4870253b7396/class-4'
TRAINER_SPAWN = 79788
TRAINER_ENTRY = 918
UNLOCK = 919100020
PRIOR_FUNDING_HASHES = {'.local/talent-switch-plan/schema-review/parent-funded-state.json': 'e97c5e44a80c688d205c41b9c84c7a9f647a6e4419128d53ebe2e087faf78987',
 '.local/talent-switch-plan/schema-review/parent-pre-retry-audit.json': '90ee3e63791a7adad75c524159fb13363762a52bc29a3d5dd9344545d47969a1',
 '.local/talent-switch-plan/schema-reviewed-execution/attempt.json': 'a029a85e6ae042560aeef5c358ebe1c6ffe2b65965a75235a9b0b4cada475fcd',
 '.local/talent-switch-plan/schema-reviewed-execution/failure.json': '673cb0fcc408194885ad4b136f9cc0d09aca9de6bfcb759f178f0a2a0f7cf359',
 '.local/talent-switch-plan/schema-reviewed-execution/money-burned.json': 'ee5576ca1466e1fdfdd97a2b3c44d9edfe9e9525897383887d2c774d7d9c1770',
 '.local/talent-switch-plan/schema-reviewed-execution/packets-13-1792454023406358863.jsonl': 'd17af592007051c42e22747b239fe65ce4c034a9f9db2a3fe782d5243468e4f5',
 '.local/talent-switch-plan/schema-reviewed-execution/packets-35-1792454026925129736.jsonl': 'd46686051415a0ee56da4cd656811600b054255d58d12d490af05ae8bee6f537',
 '.local/talent-switch-plan/schema-reviewed-execution/runtime.json': 'e43e2bd562a7b78bd3a5f32b11209ef9a84bcc5239311727d889c34ed8738bb7',
 '.local/talent-switch-plan/schema-reviewed-execution/setup-complete-1.json': 'faff42639c218dac346e0b694d9c3323289477aedbc40ea5b0bdd92fac681218',
 '.local/talent-switch-plan/schema-reviewed-execution/setup-complete-2.json': 'cce02012d1b6bd252bbe55af59f37461ec08dd37ad7dc22514d6e3f4760f2de0',
 '.local/talent-switch-plan/schema-reviewed-execution/setup-complete-3.json': 'd9d4118a0e0925baffdd3776bbf30b78a028f9a921034bba9d8a55b03d3ea9fd',
 '.local/talent-switch-plan/schema-reviewed-execution/setup-complete-4.json': 'b05c35d096ae2f08f41371a1e4c7f81f327001a24639cc2b917de292a3344cbf',
 '.local/talent-switch-plan/schema-reviewed-execution/setup-unresolved-5.json': '319e2cb28e1656e29e1879bbf1498df0920ddc1fd09d7487bfce661aa5074828',
 '.local/talent-switch-plan/schema-reviewed-execution/state-1-pre-money-original.json': '62e0068c8e2f8caf7726240c3d542bb1f4601ae799c4ee87dea17750fd905ffc',
 '.local/talent-switch-plan/schema-reviewed-execution/state-2-final-preserved.json': 'df993ee3d7a69e9b01793ea78dca04ca5115cc60e8ce67eda70411e00b7be770',
 '.local/talent-switch-plan/schema-reviewed-execution/trainer-observation.json': '2da06a0a8772b8bc61831734443c7d74ef87fa3940f856ca501d786572d90c45',
 '.local/talent-switch-plan/schema-reviewed-execution/world-conditions.json': '57319155b84b4b90e56d76a19eb6346fecb205205bd0449bfb21a0be79f40703',
 '.local/talent-switch-plan/schema-reviewed-execution/world-creature-default-trainer.json': '4aa59ac5277ffbb970114742c23bd234660de79fa1904615456d4b4b060e91d3',
 '.local/talent-switch-plan/schema-reviewed-execution/world-creature-template.json': '7dbcf8d60600d25d40a862ccfcd4c36d430e9fda8259ee09ad554f7355ac8495',
 '.local/talent-switch-plan/schema-reviewed-execution/world-creature.json': 'e9e1888af2c2bb50e6f67f25b5bc510bfd6fe137e83f3a522df72c2d931cf0be',
 '.local/talent-switch-plan/schema-reviewed-execution/world-gossip-menu-option.json': '2f96e5bba111af8318ee1729257b1b5364d908a344d25f490dc60ea24bbdaf08',
 '.local/talent-switch-plan/schema-reviewed-execution/world-gossip-menu.json': '3127be2340e8d20c55f4f0c0e59a368018c87ecd18a9cc8794412dd8eca544d2',
 '.local/talent-switch-plan/schema-reviewed-execution/world-trainer.json': '5847e6901db12c7d16e86606a83747904d92e16686fab52a1920fe3ceedf8efc'}
FUNDED_JOURNAL = OUTPUT / 'funded-continuation'
MONEY = 10010000  # 1000g dual spec plus the source-confirmed first 1g reset.
PLAN = dict(status='PREP_ONLY', live_executor=True, funded_continuation=True, creates=0, actor=35, control=13,
            account='APV2C', profile=dict(class_id=4, race_id=1), level=50,
            earned_before=33, earned_after=34, money_setup_copper=0, prior_funded_copper=MONEY,
            original_run_consumed=True,
            authorization='fresh parent 30-minute release from ALL current owners; none created here',
            sequence=['spec0 spend three: 30 free', 'NPC dual spec: spec1 empty 33 free',
                      'spec1 spend three: 30 free; one fabricated AP unlock: 31 free',
                      'spec0 three spent: 31 free; NPC respec: 34 free',
                      'relog/switch: spec0 34, spec1 31; exact ingress replay unchanged'],
            main_task='Recalculate available/spent points after levelups respecs relogs dualspecswitches: OPEN',
            excluded=['authentication', 'SQL execution', 'runtime/native/GUI/world/config changes'])


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def verify_prior_hashes():
    import hashlib
    for name, digest in PRIOR_FUNDING_HASHES.items():
        require(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest,
                'Preserved funding artifact changed: ' + name)
    return dict(PRIOR_FUNDING_HASHES)


def pristine_funded(data):
    """Full saved baseline, not just the cash field; no staged progression."""
    require(len(data) == 122 and {r['guid'] for r in data['characters']} == set(range(1, 43))
            and all(r['online'] == 0 for r in data['characters']), 'Expected 122 tables/42 offline actors')
    for guid, expected in ((35, (50, 0, MONEY)), (13, (1, 55, 0))):
        row = next(r for r in data['characters'] if r['guid'] == guid)
        require((row['level'], row['xp'], row['money']) == expected
                and (row['talentGroupsCount'], row['activeTalentGroup'], row['resettalents_cost']) == (1, 0, 0)
                and at_trainer((row['map'], row['position_x'], row['position_y'], row['position_z']))
                and row['instance_id'] == 0,
                'Pristine funded profile/funds/spec/position required: ' + str(guid))
        require(not any(r['guid'] == guid for r in data['character_talent']), 'Staged talents forbidden')
    original = json.loads((BIRTH / 'replay.json').read_text())
    manifest = json.loads((BIRTH / 'manifest.json').read_text())
    bindings = [r for r in data['mod_archipelago_binding'] if r['character_guid'] == 35]
    require(len(bindings) == 1, 'Original binding missing/duplicated')
    binding_guard(bindings[0], original['binding'][0], manifest)
    receipt_guard(sorted([r for r in data['mod_archipelago_reward'] if r['binding_id'] == 25],
                         key=lambda r: r['item_index']), original['receipts'], applied=False)
    require(sum(r['applied'] == 0 for r in data['mod_archipelago_reward']) == 11,
            'Frozen pending inventory changed')
    require([r for r in data['mod_archipelago_progress'] if r['binding_id'] == 25]
            == original['progress'], 'Nonpristine AP baseline')
    require(sorted((r['spell'], r['specMask']) for r in data['character_spell'] if r['guid'] == 35)
            == [(5277, 255), (26669, 255)], 'Nonpristine spellbook')
    require([r['base_spell'] for r in data['mod_archipelago_ability'] if r['binding_id'] == 25] == [5277],
            'Nonpristine ability permissions')


def funded_continuity(before, after, *, login_bookkeeping=False):
    """No talent/receipt/money allowance until the shared sequence actually begins."""
    before, after = archived_value(before), archived_value(after)
    require(before.keys() == after.keys(), 'Funded table inventory changed')
    audit = {}
    for table in before:
        if table in ('worldstates', 'creature_respawn'):
            audit[table] = compare_ambient(table, before[table], after[table])
        elif table == 'characters' and login_bookkeeping:
            # Only the two read-only logins may advance ordinary save bookkeeping.
            old = {r['guid']: r for r in before[table]}
            require(old.keys() == {r['guid'] for r in after[table]}, 'Funded roster changed')
            for row in after[table]:
                prior = old[row['guid']]
                allow = BOOKKEEPING if row['guid'] in (13, 35) else set()
                if allow and row['restState'] != prior['restState']:
                    require(prior['restState'] == 2 and row['restState'] == 1 and row['rest_bonus'] > 10,
                            'Funded login changed rest state outside source SetRestBonus transition')
                    allow = allow | {'restState'}
                require({k: v for k, v in row.items() if k not in allow}
                        == {k: v for k, v in prior.items() if k not in allow}, 'Funded read-only character changed')
                if allow:
                    require(row['totaltime'] >= prior['totaltime'] and row['leveltime'] >= prior['leveltime'],
                            'Funded played time moved backwards')
        else:
            require(before[table] == after[table], 'Funded protected baseline changed: ' + table)
    return dict(protected_comparison_passed=True, ambient_world_audit=audit)


def prior_funding():
    """Validate the immutable failed attempt as funding evidence, never as native PASS."""
    verify_prior_hashes()
    directory = OUTPUT / 'schema-reviewed-execution'
    read = lambda name: json.loads((directory / (name + '.json')).read_text())
    before, saved = read('state-1-pre-money-original'), read('state-2-final-preserved')
    require(read('money-burned') == dict(copper=MONEY, guid=35, once=True), 'Prior one-time funding missing')
    require(read('setup-complete-4') == dict(command=MONEY_COMMAND, messages=[MONEY_SUCCESS]),
            'Prior money target/delta differs')
    failure = dict(error='Native setup timeout: ' + MONEY_INFO, preserved=True)
    require(read('failure') == failure and read('setup-unresolved-5')['command'] == MONEY_INFO
            and money_readback(read('setup-unresolved-5')['messages']), 'Wrong prior failure/readback')
    trainer = read('trainer-observation')
    require(observe_trainer(trainer['messages'], trainer['gm_world'], trainer['player_world']).guid
            == trainer['guid'], 'Historical trainer evidence differs')
    events = {}
    for guid in (13, 35):
        packets = list(directory.glob('packets-' + str(guid) + '-*.jsonl'))
        require(len(packets) == 1, 'Ambiguous historical packet journal')
        events[guid] = [struct.unpack('<II', bytes.fromhex(r['raw']))
                        for r in map(json.loads, packets[0].read_text().splitlines())
                        if r['direction'] == 'SMSG' and r['opcode'] == '0x1f8']
    source_tp(before, saved, events[35], events[13])
    pristine_funded(saved)
    require(next(r for r in before['characters'] if r['guid'] == 35)['money'] == 0,
            'Historical pre-money balance differs')
    # Two exact source-backed historical deltas were caused by the original login/TP.
    # They are NOT added to the live snapshot allowlist.
    projected = deepcopy(saved)
    actor = next(r for r in projected['characters'] if r['guid'] == 35)
    prior = next(r for r in before['characters'] if r['guid'] == 35)
    require((prior['restState'], actor['restState']) == (2, 1)
            and prior['rest_bonus'] <= 1 and actor['rest_bonus'] > 10, 'Historical rested-state transition differs')
    actor['restState'] = prior['restState']
    check = dict(binding_id=25, location_id=919701519, acknowledged=0, completed_at='2026-10-19 23:53:55')
    require([r for r in saved['mod_archipelago_check'] if r not in before['mod_archipelago_check']] == [check]
            and all(r in saved['mod_archipelago_check'] for r in before['mod_archipelago_check'])
            and any(r['binding_id'] == 25 and r['location_id'] == 919701519
                    for r in before['mod_archipelago_enabled_check']), 'Historical Stormwind check differs')
    projected['mod_archipelago_check'].remove(check)
    comparison = compare_snapshots(before, projected, setup=True,
                                   at_time=max(r['logout_time'] for r in saved['characters']))
    return saved, dict(hashes=dict(PRIOR_FUNDING_HASHES), comparison=comparison,
                       player_exploration=events[35], gm_exploration=events[13],
                       historical_only=dict(restState=[2, 1], zone_check=check),
                       old_trainer_guid_is_not_current_authority=True)


def earned(unlocks):
    from verify_class_systems import expected_points
    return expected_points(50, unlocks)


def free_points(unlocks, active, talents, ranks):
    require(type(active) is int and active in (0, 1), 'Invalid active spec')
    require(all(type(r['specMask']) is int and r['specMask'] in (1, 2, 3)
                and r['spell'] in ranks for r in talents), 'Invalid talent mask/rank')
    spent = sum(ranks[r['spell']] + 1 for r in talents if r['specMask'] & (1 << active))
    require(spent <= earned(unlocks), 'Overspent active spec')
    return earned(unlocks) - spent


def owned_identity(character, account, birth, authorized):
    from verify_runtime import guard_account
    guard_account(account, 'APV2C')
    require(type(account['id']) is int and account['id'] == 4, 'Wrong account ID')
    require(birth['guid'] == authorized['guid'] == 35 and birth['account'] == 'APV2C'
            and birth['name'] == 'Apsckmrzjjql'
            and birth['profile'] == authorized['profile']
            and birth['profile']['class_id'] == 4 and birth['profile']['race_id'] == 1,
            'Original typed birth/profile proof required')
    expected = dict(guid=35, account=4, name=birth['name'], race=1, level=50, online=0)
    expected['class'] = 4
    require(all(type(character[k]) is type(v) and character[k] == v for k, v in expected.items()),
            'FIRST PLAYER LOGIN identity/ownership guard failed')
    return deepcopy(birth['profile'])


def archived_value(value):
    return json.loads(json.dumps(value, default=str))


def binding_guard(current, original, manifest):
    require(original.get('id') == 25 and original.get('character_guid') == 35
            and original.get('character_account') == 4 and original.get('class_id') == 4
            and original.get('race_id') == 1 and original.get('character_name') == 'Apsckmrzjjql'
            and original.get('seed_name') == 'fabricated-class-matrix-dc792199e5793d75b748ebb7e20be853',
            'Not the original owned binding')
    mutable = {'status', 'heartbeat'}
    require(archived_value({k: v for k, v in current.items() if k not in mutable})
            == archived_value({k: v for k, v in original.items() if k not in mutable}), 'Binding changed')
    raw = json.loads(current['manifest']) if isinstance(current['manifest'], str) else current['manifest']
    require(raw == manifest and raw['profile']['class_id'] == 4 and raw['profile']['race_id'] == 1
            and str(UNLOCK) in raw['rewards'], 'Wrong/incomplete original manifest')


def receipt_guard(rows, prefix, *, applied):
    require(archived_value(rows[:len(prefix)]) == archived_value(prefix), 'Old receipt prefix changed')
    require(len(rows) == len(prefix) + int(applied), 'Replay created an extra receipt')
    require([r['item_index'] for r in rows] == list(range(len(rows)))
            and all(r['applied'] == 1 for r in rows), 'Noncontiguous/unapplied receipts')
    if applied:
        tail = rows[-1]
        require(tail['binding_id'] == 25 and tail['ap_item'] == UNLOCK
                and tail['kind'] == 'talent' and tail['applied_value'] == 1,
                'Wrong unlock receipt')


def native_packet(operation, value=0):
    """Only source-resolved player bodies; no raw-opcode escape hatch."""
    if operation == 'learn':
        from verify_class_systems import talent_packet
        require(type(value) is int and value in (0, 1, 2), 'Only talent203 ranks0..2')
        return 0x251, talent_packet(203, value)
    if operation == 'tier-denial':
        require(type(value) is int and value == 0, 'Only row1 talent1827 rank0 denial')
        return 0x251, struct.pack('<II', 1827, 0)
    if operation == 'switch':
        require(type(value) is int and value in (0, 1), 'Only primary/secondary')
        return 0x12E, struct.pack('<BIBI', 0, (63645, 63644)[value], 0, 0)
    if operation == 'wipe':
        require(trainer_header(value), 'Only typed Rogue trainer GUID')
        return 0x2AA, struct.pack('<Q', value)
    raise RuntimeError('Unapproved player operation')


def release_guard(release, *, now, expected_hashes, current_owners, funded=False):
    require(type(release.get('creation_limit')) is int and type(release.get('money_setup_copper')) is int,
            'Grant scope must use exact integer fields')
    require(release.get('parent_authorized') is True and release.get('purpose') == ('talent-switch-funded' if funded else 'talent-switch')
            and release.get('guids') == [13, 35] and release.get('creation_limit') == 0
            and release.get('money_setup_copper') == (0 if funded else MONEY)
            and release.get('hashes') == expected_hashes
            and (release.get('readonly_commands') == [TRAINER_INFO, MONEY_INFO] if funded
                 else release.get('setup_readback') == MONEY_INFO), 'Missing/mismatched parent grant')
    if funded:
        require(release.get('prior_funding_sha256') == PRIOR_FUNDING_HASHES
                and release.get('prior_funding_attested') is True, 'Prior funding attestation required')
    require(type(now) is int and type(release.get('issued_at')) is int
            and type(release.get('expires_at')) is int
            and release['issued_at'] <= now < release['expires_at']
            <= release['issued_at'] + 1800, 'Expired/future/overlong grant')
    require(current_owners and set(release.get('released_owners', [])) == set(current_owners),
            'Every current owner must release afresh')


@dataclass
class SetupReservation:
    """Pure policy check, NOT a durable cross-process reservation or authorization."""
    reserved: bool = False
    money_used: bool = False

    def reserve(self):
        require(not self.reserved, 'One-shot attempt already reserved')
        self.reserved = True

    def money_command(self, selected_guid):
        require(self.reserved and not self.money_used and type(selected_guid) is int
                and selected_guid == 35, 'Money setup requires reserved exact owned target35')
        self.money_used = True  # Burn before send, including ambiguous failures.
        return '.modify money ' + str(MONEY)


def source_evidence():
    """Explicit offline observations, never called by the default CLI."""
    import verify_artisan_runtime as artisan
    from tools.validate_checks import DBC
    from verify_class_systems import DBC_DIR
    evidence = artisan.build_evidence()
    manifest = json.loads((artisan.BUILD / 'manifest.json').read_text())
    require(evidence['world_sha256'] == '3b9b2bf9f946a1eeef5908e440ed917132c0559c4bc483ba14be199060641809'
            and evidence['manifest_sha256'] == '6ac13239c2b11940904ece49ea6064c72980e433d6ef06aff587f36babc51553'
            and manifest['base_manifest_sha256'] == '0edea8dba721f996f00cf0b5c95e3576fff1ad4dd6e637fd8c0ad45b06f1285b'
            and manifest['patch_sha256'] == '76342b88b9864f85525771ba51de7c2b78467343027075b83184bc76356aca6c',
            'Wrong pinned build')
    inventory = json.loads((artisan.BUILD / 'source-files.sha256.json').read_text())
    paths = ['src/server/game/' + p for p in (
        'Handlers/SkillHandler.cpp', 'Handlers/MiscHandler.cpp', 'Handlers/SpellHandler.cpp',
        'Handlers/QueryHandler.cpp', 'Globals/ObjectMgr.cpp', 'Globals/ObjectMgr.h',
        'Chat/Chat.cpp', 'Chat/Chat.h', 'Entities/Object/ObjectGuid.cpp',
        'Miscellaneous/Language.h', 'Server/Protocol/Opcodes.cpp', 'Server/WorldSession.cpp',
        'Entities/Player/Player.cpp', 'Entities/Player/PlayerStorage.cpp', 'Entities/Player/Player.h', 'Entities/Player/PlayerGossip.cpp',
        'Spells/SpellEffects.cpp', 'Server/Protocol/Opcodes.h', 'World/WorldConfig.cpp')]
    paths += ['src/server/scripts/Commands/' + n for n in ('cs_modify.cpp', 'cs_go.cpp', 'cs_misc.cpp', 'cs_npc.cpp')]
    paths += ['apps/docker/Dockerfile', 'src/common/Configuration/Config.cpp',
              'src/common/Common.h', 'src/server/shared/SharedDefines.h']
    paths += ['src/server/game/Entities/Creature/GossipDef.cpp',
              'src/server/game/Achievements/AchievementMgr.cpp',
              'src/server/shared/DataStores/DBCEnums.h', 'src/server/shared/DataStores/DBCStructure.h']
    paths += ['src/server/' + p for p in (
        'game/Battlefield/Battlefield.cpp', 'game/Battlefield/Battlefield.h', 'game/Battlefield/BattlefieldMgr.cpp',
        'game/Battlefield/Zones/BattlefieldWG.cpp', 'game/Battlefield/Zones/BattlefieldWG.h',
        'game/World/World.cpp', 'game/World/WorldState.cpp', 'game/World/WorldStateDefines.h',
        'game/Maps/Map.cpp', 'game/Entities/Creature/Creature.cpp',
        'database/Database/Implementation/CharacterDatabase.cpp')]
    paths += ['modules/mod-archipelago/src/' + n for n in ('APProgression.cpp', 'APCatalog.h')]
    hashes = {}
    for path in paths:
        hashes[path] = artisan.digest(artisan.SOURCE / path)
        require(hashes[path] == inventory[path], 'Pinned source changed: ' + path)
    strings_path = artisan.SOURCE / 'data/sql/base/db_world/acore_string.sql'
    hashes[str(strings_path.relative_to(artisan.SOURCE))] = artisan.digest(strings_path)
    strings = strings_path.read_text()
    for row in ("(157,'You give {} copper to {}.'", "(116,'No character selected.'",
                "(35400,'¦ Player {} {} (guid: {})'", "(847,'¦ Money: {}g{}s{}c'",
                "(35410,'¦ Online for: {}'", "(5062,'SpellSchoolImmuneMask: {}'"):
        require(row in strings, 'Native completion string changed: ' + row)
    modify = (artisan.SOURCE / 'src/server/scripts/Commands/cs_modify.cpp').read_text()
    handler = modify[modify.index('static bool HandleModifyMoneyCommand'):modify.index('//Edit Unit field')]
    require(handler.index('PSendSysMessage(LANG_YOU_GIVE_MONEY')
            < handler.index('target->ModifyMoney(moneyToAdd)'), 'Money completion source order changed')
    talents, tabs, spells = [DBC(DBC_DIR / (n + '.dbc')) for n in ('Talent', 'TalentTab', 'Spell')]
    talent = talents.rows[203]
    require(talents.rows[1827][1:3] == (181, 1) and talents.rows[1827][13] == 0,
            'Row1 early-tier denial probe changed')
    require(talent[1:3] == (181, 0) and talent[4:9] == (13741, 13793, 13792, 0, 0)
            and talent[13] == 0 and tabs.rows[181][20] == 8, 'Talent203 must be Rogue row0 three ranks')
    birth, first, replay, raw = [json.loads((BIRTH / (n + '.json')).read_text())
                                 for n in ('creation', 'first-login-authorized', 'replay', 'manifest')]
    require(birth['profile'] == first['profile'] == raw['profile']
            and replay['character']['guid'] == birth['guid'] == first['guid'] == 35,
            'Birth identity mismatch')
    require(replay['character']['talentGroupsCount'] == 1
            and replay['character']['activeTalentGroup'] == 0
            and replay['progress'][0]['talent_unlocks'] == 0, 'Historical baseline changed')
    binding_guard(replay['binding'][0], replay['binding'][0], raw)
    reviewed = json.loads((ROOT / '.local/class-matrix-plan/parent-reviewed-seven.json').read_text())
    public = json.loads((ROOT / 'docs/verification/native-class-matrix.json').read_text())
    require(dict(class_id=4, guid=35, phases_checked=10) in reviewed['classes']
            and public['status'] == 'PASS_COMBINED_NINE_NATIVE_GATES'
            and public['world_sha256'] == evidence['world_sha256'], 'Parent/public proof mismatch')
    for name, needle in (
        ('creature.sql', '(79788,918,0,0,0,0,0,1,1,1,-8752.3,377.572,101.139,1.29154,'),
        ('creature_template.sql', "(918,0,0,0,0,0,'Osborne the Night Man','Rogue Trainer',NULL,4502,"),
        ('creature_default_trainer.sql', '(918,9)'),
        ('trainer.sql', "(9,0,4,'Hello, rogue!  Ready for some training?',0)")):
        path = artisan.SOURCE / 'data/sql/base/db_world' / name
        require(needle in path.read_text(), 'Trainer source row changed: ' + name)
        hashes[str(path.relative_to(artisan.SOURCE))] = artisan.digest(path)
    gossip_projection = gossip_source_projection(artisan.SOURCE / 'data/sql/base/db_world')
    hashes.update({'data/sql/base/db_world/' + name: digest
                   for name, digest in GOSSIP_SQL_HASHES.items()})
    criteria = DBC(DBC_DIR / 'Achievement_Criteria.dbc')
    for key, expected in {1149: (776, 43, 121), 9619: (2716, 69, 63624),
                          4224: (334, 86, 0), 3359: (1149, 61, 0),
                          3360: (1150, 60, 0), 12698: (4496, 115, 0)}.items():
        require(criteria.rows[key][1:4] == expected, 'Normal bookkeeping criterion changed')
    require(DBC(DBC_DIR / 'Achievement.dbc').rows[2716][39] == 10
            and DBC(DBC_DIR / 'WorldMapOverlay.dbc').rows[121][2:6] == (1519, 0, 0, 0),
            'Dual achievement/exploration bookkeeping changed')
    update = artisan.SOURCE / 'data/sql/updates/db_world/2026_07_21_00.sql'
    hashes[str(update.relative_to(artisan.SOURCE))] = artisan.digest(update)
    dbc = {}
    maps = DBC(DBC_DIR / 'Map.dbc')
    require(all(maps.rows[n][2] == 0 for n in AMBIENT_WORLD_MAPS), 'Ambient map is instanced')
    for name in ('Talent', 'TalentTab', 'Spell', 'AreaTable', 'Achievement_Criteria', 'Achievement', 'WorldMapOverlay', 'Map'):
        dbc[name] = artisan.digest(DBC_DIR / (name + '.dbc'))
    require(artisan.digest(artisan.BUILD / 'base-manifest.json') == manifest['base_manifest_sha256']
            and artisan.digest(ROOT / 'patches/azerothcore-v2.patch') == manifest['patch_sha256'],
            'Base/patch provenance changed')
    config_path = ROOT / '.local/v2-realm/config/worldserver.conf'
    config = config_path.read_text()
    require(re.findall(r'^DataDir\s*=\s*"([^"]+)"\s*$', config, re.M)
            == ['/azerothcore/env/dist/data'], 'Actual DBC directory differs')
    for name, value in (('MinDualSpecLevel', '40'), ('NoResetTalentsCost', '0')):
        require(re.findall(r'^\s*' + name + r'\s*=\s*(\d+)\s*$', config, re.M) == [value],
                'Installed config differs: ' + name)
    helper_paths = [Path(__file__), ROOT / 'tests/test_talent_switch_runtime.py',
                    ROOT / 'docs/TALENT_SWITCH_RUNTIME.md', ROOT / 'bridge/v2.py', ROOT / 'bridge/catalog.py']
    from verify_merchant_runtime import CONTROL_EVIDENCE
    helper_paths += [CONTROL_EVIDENCE / n for n in ('summary.json', 'before.json', 'run.jsonl')]
    helper_paths += [ROOT / 'tests' / n for n in ('verify_runtime.py', 'realm_client.py',
                     'verify_artisan_runtime.py', 'verify_merchant_runtime.py', 'verify_class_systems.py',
                     'verify_travel_runtime.py')]
    helpers = {str(p.relative_to(ROOT)): artisan.digest(p) for p in helper_paths}
    return dict(status='PREP_ONLY_SOURCE_OBSERVATIONS', build=evidence, source_hashes=hashes, helpers=helpers,
                config_sha256=artisan.digest(config_path), dbc_sha256=dbc, talent203=talent,
                spell_rows={str(n): spells.rows[n] for n in (63680, 63624, 63706, 63645, 63644)},
                birth_sha256={n: artisan.digest(BIRTH / (n + '.json')) for n in
                              ('creation', 'first-login-authorized', 'manifest', 'replay')},
                prior_funding_sha256=verify_prior_hashes(), gossip_option_projection=gossip_projection,
                fresh_native_verification=False)


def parse_talents(payload):
    from realm_client import Reader
    r = Reader(payload)
    player, free, count, active = r.unpack('BIBB')
    require(player == 0 and count in (1, 2) and active < count and free <= 34,
            'Invalid player talent header')
    specs = []
    for _ in range(count):
        n, = r.unpack('B')
        talents = {}
        for _ in range(n):
            talent, rank = r.unpack('IB')
            require(talent == 203 and rank <= 2 and talent not in talents,
                    'Unexpected/duplicate talent or rank')
            talents[talent] = rank
        glyph_count, = r.unpack('B')
        require(glyph_count == 6, 'Wrong glyph count')
        glyphs = list(r.unpack('6H'))
        require(not any(glyphs), 'Unexpected glyph')
        specs.append(dict(talents=talents, glyphs=glyphs))
    r.finish()
    return dict(free=free, count=count, active=active, specs=specs)


def trainer_header(guid):
    return (type(guid) is int and 0 < guid < 1 << 64 and guid >> 48 == 0xF130
            and (guid >> 24) & 0xFFFFFF == TRAINER_ENTRY and guid & 0xFFFFFF != 0)


def at_trainer(world):
    return (world is not None and len(world) >= 4 and world[0] == 0
            and sum((a-b)**2 for a, b in zip(world[1:4], (-8752.3, 377.572, 101.139))) < 25)


@dataclass(frozen=True)
class TrainerObservation:
    guid: int


def observe_trainer(messages, gm_world, player_world):
    """Validate the loaded cs_npc reply, never the fallback DB-derived GUID."""
    text = '\n'.join(messages)
    require(at_trainer(gm_world) and at_trainer(player_world), 'Trainer map/proximity not proved')
    require(not re.search(r'not\s*in\s*world', text, re.I), 'Trainer not loaded')
    rows = re.findall(r'^DB GUID: (\d+), current GUID: GUID Full: 0x([0-9a-fA-F]{16}) '
                      r'Type: Creature Entry: (\d+)  Low: (\d+)\.$', text, re.M)
    require(len(rows) == 1 and text.count('GUID Full:') == 1, 'No unique loaded trainer')
    spawn, raw, entry, low = rows[0]
    guid = int(raw, 16)
    require(int(spawn) == TRAINER_SPAWN and int(entry) == TRAINER_ENTRY
            and trainer_header(guid) and int(low) == guid & 0xFFFFFF, 'Trainer spawn/entry/GUID mismatch')
    require(re.findall(r'^Current Entry: (.+)$', text, re.M) == ['918 of (918, 0, 0).']
            and re.findall(r'^Phasemask: (.+)$', text, re.M) == ['1']
            and re.findall(r'^InstanceID: (.+)$', text, re.M) == ['0'], 'Trainer entry/phase/world mismatch')
    positions = re.findall(r'^Position: (-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)\.$', text, re.M)
    require(len(positions) == 1 and at_trainer((0, *map(float, positions[0]))),
            'Trainer source position mismatch')
    npc = tuple(map(float, positions[0]))
    require(all(sum((a-b)**2 for a, b in zip(world[1:4], npc)) < 25
                for world in (gm_world, player_world)), 'Actors farther than five yards from loaded trainer')
    return TrainerObservation(guid)


def parse_gossip(payload):
    from realm_client import Reader
    r = Reader(payload)
    guid, menu, title, count = r.unpack('QIII')
    require(trainer_header(guid) and menu in (4502, 10371, 10373) and count <= 16,
            'Unapproved trainer/menu')
    options = []
    for _ in range(count):
        wire, icon, coded, price = r.unpack('IBBI')
        text, box = r.cstring(), r.cstring()
        require(not coded and wire not in [o['wire'] for o in options]
                and '\ufffd' not in text + box, 'Coded/duplicate/malformed gossip')
        options.append(dict(wire=wire, icon=icon, price=price, text=text, box=box))
    quests, = r.unpack('I')
    require(quests <= 32, 'Invalid quest count')
    for _ in range(quests):
        r.unpack('IIiIB')
        r.cstring()
    r.finish()
    return dict(guid=guid, menu=menu, title=title, options=options)


GOSSIP = {
    'dual': (4502, 'How do I learn Dual Specialization?', 0),
    'purchase': (10371, 'I wish to learn Dual Specialization.', 10000000),
    'respec': (4502, 'I wish to unlearn my Talents.', 0),
}
GOSSIP_BOX = {
    'dual': '', 'respec': '',
    'purchase': 'Are you sure you wish to purchase a Dual Talent Specialization?',
}
# Exact selected references from the pinned gossip/body rows; these are never wire authority.
GOSSIP_BROADCAST_IDS = (7491, 8260, 8716, 8717, 33761, 33762, 33765, 60961, 62295)
GOSSIP_SQL_HASHES = {
    'gossip_menu.sql': 'ab852e42b041a672250f3a8c30a54b238bd8ae387fe4218d92b2e73bf5795332',
    'gossip_menu_option.sql': '1310ab8ae38bafd52e30b1cfa027e45714f9e340c172d1be286a3ba37c7766b5',
    'broadcast_text.sql': '6f227246c33732ee9e9ee5bd8e1fa6b641aef2b9f4784c69088b898470423734',
    'gossip_menu_option_locale.sql': '2deaaa90408b474fe20ca06a229b4da67e03cb70789fa9652c59bb0e1333e393',
    'broadcast_text_locale.sql': 'cf7c7f9fab812fd11047665b682992447c306fc630d9dfbd3a86d2ed06799290',
}


def resolve_gossip(gossip, trainer, purpose):
    """Resolve only a unique exact choice in the current parsed native menu."""
    require(purpose in GOSSIP, 'Unknown gossip operation')
    menu, text, price = GOSSIP[purpose]
    require(isinstance(trainer, TrainerObservation) and trainer_header(trainer.guid)
            and gossip is not None and gossip['guid'] == trainer.guid
            and gossip['menu'] == menu, 'Wrong current menu')
    matches = [o for o in gossip['options']
               if (o['text'], o['price'], o['icon'], o['box'])
               == (text, price, 0, GOSSIP_BOX[purpose])]
    require(len(matches) == 1, 'No unique source-confirmed wire option')
    return matches[0]['wire']


def gossip_source_projection(source):
    """Pinned enUS option projection; NPC query body text is not selection authority."""
    import hashlib
    for name, digest in GOSSIP_SQL_HASHES.items():
        require(hashlib.sha256((source / name).read_bytes()).hexdigest() == digest,
                'Pinned gossip SQL changed: ' + name)
    options = verify_dump_rows(source / 'gossip_menu_option.sql', None)
    broadcasts = verify_dump_rows(source / 'broadcast_text.sql', None)
    require(sorted(int(r['ID']) for r in broadcasts) == list(GOSSIP_BROADCAST_IDS),
            'Missing/duplicate selected broadcast')
    broadcasts = {int(r['ID']): r for r in broadcasts}
    projection = {}
    for purpose, menu, option, broadcast, kind, flag, target in (
            ('dual', 4502, 2, 33762, 20, 1, 10371),
            ('respec', 4502, 1, 62295, 16, 16, 4461),
            ('purchase', 10371, 0, 33765, 18, 16, 10373)):
        selected = [r for r in options if (r['MenuID'], r['OptionID']) == (menu, option)]
        require(len(selected) == 1, 'Missing/duplicate source option')
        row = selected[0]
        require(tuple(row[k] for k in ('OptionBroadcastTextID', 'OptionType', 'OptionNpcFlag',
                                      'ActionMenuID', 'OptionIcon', 'BoxCoded', 'BoxBroadcastTextID'))
                == (broadcast, kind, flag, target, 0, 0, 0), 'Source option contract changed')
        # ObjectMgr loads enUS at slot0; PlayerGossip uses the player's gender with
        # GetLocaleString, NOT BroadcastText::GetText (the separate NPC-body path).
        male, female = (broadcasts[broadcast][k] for k in ('MaleText', 'FemaleText'))
        require(male and male == female and male != row['OptionText'],
                'Expected nonempty gender-equal broadcast override')
        require(GOSSIP[purpose] == (menu, male, row['BoxMoney'])
                and GOSSIP_BOX[purpose] == row['BoxText'], 'Gossip broadcast projection differs')
        projection[purpose] = dict(menu=menu, broadcast=broadcast, text=male, icon=0,
                                   price=int(row['BoxMoney']), box=row['BoxText'],
                                   coded=0, operation=kind, npc_flag=flag, action_menu=target)
    return projection


WORLD_POSITION = (-8752.3, 377.572, 101.139)
GO = '.go xyz -8752.3 377.572 101.139 0 1.29154'
SUMMON = '.summon Apsckmrzjjql'
TRAINER_INFO = '.npc info 79788'
MONEY_COMMAND = '.modify money 10010000'
MONEY_INFO = '.pinfo Apsckmrzjjql'
PLAYER_LINK = '|cffffffff|Hplayer:Apsckmrzjjql|h[Apsckmrzjjql]|h|r'
MONEY_SUCCESS = 'You give 10010000 copper to ' + PLAYER_LINK + '.'
PINFO_HEADER = ('¦ Player  ' + PLAYER_LINK
                + ' (guid: GUID Full: 0x0000000000000023 Type: Player Low: 35)')


def money_confirmation(messages):
    require(not messages or messages == [MONEY_SUCCESS],
            'Wrong native money confirmation: ' + repr(messages))
    return messages == [MONEY_SUCCESS]


def money_readback(messages):
    # Installed English strings differ only in the leading field separator.
    messages = ['¦ ' + m[2:] if m.startswith('| ') else m for m in messages]
    headers = [m for m in messages if m.startswith('¦ Player ')]
    require(not headers or headers == [PINFO_HEADER], 'Wrong/offline money readback target')
    balances = [m for m in messages if m.startswith('¦ Money: ')]
    require(not balances or balances == ['¦ Money: 1001g0s0c'], 'Wrong money readback balance')
    return (headers == [PINFO_HEADER] and bool(balances)
            and any(re.fullmatch(r'¦ Online for: .+', m) for m in messages))


class Journal:
    """Exclusive durable intent. A partial attempt is never reusable."""
    def __init__(self, directory, *, funded=False):
        self.directory = directory
        self.funded = funded

    def record(self, name, value):
        require(re.fullmatch(r'[a-z0-9-]+', name) is not None, 'Invalid journal name')
        require(not self.funded or name != 'money-burned', 'Funded journal cannot reserve money')
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / (name + '.json')).open('x') as handle:
            json.dump(value, handle, sort_keys=True, default=str, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def external_grant(grant_path, owners_path, hashes=None, *, funded=False, inspect_processes=True):
    grant = json.loads(grant_path.read_text())
    owners = json.loads(owners_path.read_text())
    require(owners.get('purpose') == 'current-native-owners' and owners.get('owners')
            and owners.get('all_released') is True and owners.get('no_other_runners') is True,
            'Current owner inventory/release required')
    release_guard(grant, now=int(time.time()), expected_hashes=grant.get('hashes') if hashes is None else hashes,
                  current_owners=owners['owners'], funded=funded)
    import hashlib
    require(grant.get('owners_sha256') == hashlib.sha256(owners_path.read_bytes()).hexdigest()
            and grant.get('release_id')
            and (grant.get('prior_funding_attested') is True if funded else grant.get('money_once') is True)
            and isinstance(grant.get('hashes'), dict) and bool(grant['hashes']),
            'Parent must attest exact owner inventory and one-time money')
    require(type(owners.get('observed_at')) is int
            and grant['issued_at'] <= owners['observed_at'] <= int(time.time()), 'Stale owner inventory')
    if not inspect_processes:
        return grant
    # Inspect local processes only after authorization, never in the default path.
    import subprocess
    processes = subprocess.check_output(['ps', '-eo', 'pid,ppid,args'], text=True, timeout=5)
    rows = [line.strip().split(None, 2) for line in processes.splitlines()[1:]]
    parents = {int(pid): int(parent) for pid, parent, _ in rows}
    ancestors, pid = set(), os.getpid()
    while pid and pid not in ancestors:
        ancestors.add(pid)
        pid = parents.get(pid, 0)
    for pid, _, command in rows:
        require(int(pid) in ancestors or not re.search(
            r'(?:python\S* .*?(?:verify_|realm_client)|wowpilago.*(?:--run|session))', command),
            'Another potential native runner is present: ' + pid)
    return grant


def runtime_guard(evidence):
    import verify_artisan_runtime as a
    info = json.loads(a.docker('inspect', 'wow-test-worldserver-1'))[0]
    require(info['State']['Running'] and info['Image'] == a.IMAGE
            and info['Config']['Labels'].get('com.docker.compose.project') == 'wow-test'
            and info['Config']['Labels'].get('com.docker.compose.service') == 'worldserver',
            'Wrong runtime container/image')
    require(isinstance(info['State'].get('StartedAt'), str)
            and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z', info['State']['StartedAt']),
            'Fresh container StartedAt required')
    identity = world_process_identity(a.docker)
    require(any(m['Destination'] == '/work/install' and not m['RW']
                and Path(m['Source']).resolve() == (a.BUILD / 'install').resolve()
                for m in info['Mounts']), 'Wrong installed runtime mount')
    for path in ('/proc/1/exe', '/work/install/bin/worldserver'):
        require(a.docker('exec', 'wow-test-worldserver-1', 'sha256sum', path).split()[0]
                == evidence['build']['world_sha256'], 'Running binary differs')
    # Pinned Dockerfile worldserver defaults, not arbitrary config overrides.
    native_env = {v for v in info['Config'].get('Env', []) if v.startswith('AC_')}
    require(info['Config']['Cmd'] == ['-c', '/work/install/etc/worldserver.conf']
            and native_env <= {'AC_FORCE_CREATE_DB=1', 'AC_UPDATES_ENABLE_DATABASES=0',
                               'AC_DISABLE_INTERACTIVE=1', 'AC_CLOSE_IDLE_CONNECTIONS=0'},
            'Unexpected runtime config arguments/environment')
    config = a.docker('exec', 'wow-test-worldserver-1', 'cat', '/work/install/etc/worldserver.conf')
    require(__import__('hashlib').sha256(config.encode()).hexdigest() == evidence['config_sha256'],
            'Runtime configuration fingerprint differs')
    for name, checksum in evidence['dbc_sha256'].items():
        require(a.docker('exec', 'wow-test-worldserver-1', 'sha256sum',
                         '/azerothcore/env/dist/data/dbc/' + name + '.dbc').split()[0] == checksum,
                'Runtime DBC differs: ' + name)
    for name, value in (('MinDualSpecLevel', '40'), ('NoResetTalentsCost', '0')):
        require(re.findall(r'^\s*' + name + r'\s*=\s*(\d+)\s*$', config, re.M) == [value],
                'Installed configuration differs: ' + name)
    end = json.loads(a.docker('inspect', 'wow-test-worldserver-1'))[0]
    require(end['Id'] == info['Id'] and end['State']['Running']
            and end['State']['StartedAt'] == info['State']['StartedAt']
            and world_process_identity(a.docker) == identity, 'Runtime changed during fresh inspection')
    return dict(container=info['Id'], StartedAt=info['State']['StartedAt'], world_process_identity=identity,
                config_sha256=__import__('hashlib').sha256(config.encode()).hexdigest())


def world_process_identity(docker):
    stat = docker('exec', 'wow-test-worldserver-1', 'cat', '/proc/1/stat').strip()
    match = re.fullmatch(r'1 \(worldserver\) (.+)', stat)
    require(match is not None, 'PID1 is not worldserver')
    fields = match[1].split()
    require(len(fields) >= 20 and fields[19].isdigit() and int(fields[19]) > 0,
            'Missing world process start ticks')
    boot = docker('exec', 'wow-test-worldserver-1', 'cat', '/proc/sys/kernel/random/boot_id').strip()
    require(re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot) is not None,
            'Missing world process boot identity')
    return dict(pid=1, comm='worldserver', start_ticks=int(fields[19]), boot_id=boot)


# Imports define classes only. Neither constructor runs on the default path.
from verify_runtime import Runner, SmokeClient, say_packet


class TalentClient(SmokeClient):
    def __init__(self, sock, authorize, guid, journal, grant_check, trainer=None, *, funded=False):
        self.guid, self.journal, self.grant_check = guid, journal, grant_check
        self.funded = funded
        require(trainer is None or isinstance(trainer, TrainerObservation), 'Validated trainer observation required')
        self.trainer = trainer
        self.hello_pending, self.trainer_contact = False, False
        self.pending_respec = False
        self.talents, self.gossip, self.wipe = None, None, None
        self.talent_serial = self.gossip_serial = 0
        self.world, self.teleport_ack = None, None
        self.teleport_serial = 0
        self.selected_guid = None
        self.casts, self.exploration = [], []
        self.allowed_gossip = None
        self.used_commands = set()
        self.packet_log = (journal.directory / ('packets-' + str(guid) + '-' + str(time.time_ns()) + '.jsonl')).open('x', buffering=1)
        super().__init__(sock, authorize)

    def send(self, opcode, payload=b''):
        if opcode in (0x251, 0x12E, 0x2AA):
            allowed = {native_packet('learn', n) for n in range(3)} | {
                native_packet('tier-denial'), native_packet('switch', 0), native_packet('switch', 1)}
            if self.trainer is not None and self.wipe == (self.trainer.guid, 10000):
                allowed.add(native_packet('wipe', self.trainer.guid))
            require(self.guid == 35 and (opcode, payload) in allowed, 'Forbidden talent operation')
            if self.funded and (opcode, payload) in {native_packet('learn', n) for n in range(3)}:
                require(self.trainer_contact, 'Fresh trainer gossip required before funded talent spending')
        elif opcode in (0x17B, 0x17C):
            require(self.guid == 35 and self.trainer is not None, 'No validated runtime trainer')
            require(payload == struct.pack('<Q', self.trainer.guid) if opcode == 0x17B
                    else self.gossip is not None and self.gossip['guid'] == self.trainer.guid
                    and payload == self.allowed_gossip and self.allowed_gossip is not None
                    and payload[:12] == struct.pack('<QI', self.trainer.guid, self.gossip['menu']),
                    'Unobserved gossip selection')
            self.allowed_gossip = None
        elif opcode == 0x95:
            commands = (TRAINER_INFO, MONEY_INFO) if self.funded else (GO, SUMMON, MONEY_COMMAND, TRAINER_INFO, MONEY_INFO)
            allowed = {say_packet(c) for c in commands}
            if self.funded:
                require(payload in allowed and at_trainer(self.world), 'Funded mode permits only exact read-only commands near trainer')
                if payload == say_packet(MONEY_INFO):
                    require(say_packet(TRAINER_INFO) in self.used_commands and self.trainer is not None,
                            'Fresh trainer proof required before funded pinfo')
            else:
                if payload == say_packet(MONEY_COMMAND):
                    require(self.selected_guid == 35, 'Money requires native selection35')
                if payload == say_packet(MONEY_INFO):
                    require(say_packet(MONEY_COMMAND) in self.used_commands, 'Readback requires money invocation')
                if payload == say_packet(TRAINER_INFO):
                    require({say_packet(GO), say_packet(SUMMON)} <= self.used_commands
                            and at_trainer(self.world), 'Trainer info requires completed native setup')
            require(self.guid == 13 and payload in allowed and payload not in self.used_commands,
                    'Forbidden/repeated GM command')
            self.used_commands.add(payload)
        elif opcode == 0x13D:
            require(not self.funded and self.guid == 13 and payload == struct.pack('<Q', 35), 'Only setup GM selection35')
        elif opcode == 0xC7:
            require(not self.funded and self.teleport_ack is not None and payload == self.teleport_ack, 'Unsolicited teleport ack')
            self.teleport_ack = None
        elif opcode == 0xDC:
            require(not self.funded and payload == b'' and self.world is not None, 'Unsolicited/funded worldport ack')
        else:
            require(opcode in (0x1ED, 0x37, 0x3D, 0x1DC, 0x391, 0x4B), 'Forbidden opcode, including creation')
            if opcode == 0x3D:
                require(payload == struct.pack('<Q', self.guid), 'Wrong FIRST PLAYER LOGIN GUID')
            if opcode in (0x37, 0x4B):
                require(payload == b'', 'Unexpected lifecycle payload')
            if opcode in (0x1DC, 0x391):
                require(len(payload) == 8, 'Malformed lifecycle packet')
        if opcode in (0x1ED, 0x3D, 0x251, 0x12E, 0x2AA, 0x17B, 0x17C, 0x95, 0x13D):
            self.grant_check()
        if opcode == 0x2AA:
            self.wipe = None  # Burn confirmation before transport, including ambiguous failures.
        self.log('CMSG', opcode, payload)
        super().send(opcode, payload)
        if opcode == 0x13D:
            self.selected_guid = 35
        if opcode == 0x17B:
            self.hello_pending = True

    def log(self, direction, opcode, payload):
        self.packet_log.write(json.dumps(dict(direction=direction, opcode=hex(opcode), raw=payload.hex())) + '\n')

    def receive(self):
        opcode, payload = super().receive()
        self.log('SMSG', opcode, payload)
        return opcode, payload

    def process(self, opcode, payload):
        self.grant_check()
        from verify_travel_runtime import packed_guid, spell_go
        require(not self.funded or opcode not in (0x3E, 0xC7), 'Unexpected teleport in funded mode')
        if opcode in (0x236, 0x3E):
            require(len(payload) == 20, 'Malformed world position')
            self.world = struct.unpack('<Iffff', payload)
            if opcode == 0x3E:
                self.send(0xDC)
                self.teleport_serial += 1
        elif opcode == 0xC7:
            guid, offset = packed_guid(payload)
            require(guid == self.guid and len(payload) >= offset + 30 and self.world is not None,
                    'Malformed near teleport')
            sequence, = struct.unpack_from('<I', payload, offset)
            self.world = (self.world[0], *struct.unpack_from('<ffff', payload, offset + 14))
            self.teleport_ack = payload[:offset] + struct.pack('<II', sequence, 0)
            self.send(0xC7, self.teleport_ack)
            self.teleport_serial += 1
        elif opcode == 0x4C0:
            self.talents = parse_talents(payload)
            self.talent_serial += 1
        elif opcode == 0x17D:
            gossip = parse_gossip(payload)
            require(self.trainer is not None and gossip['guid'] == self.trainer.guid,
                    'Unobserved runtime gossip NPC')
            if self.hello_pending:
                require(gossip['menu'] == 4502, 'Fresh trainer hello must return root menu')
                self.hello_pending, self.trainer_contact = False, True
            self.gossip = gossip
            self.gossip_serial += 1
        elif opcode == 0x2AA:
            require(self.trainer is not None and self.pending_respec
                    and payload == struct.pack('<QI', self.trainer.guid, 10000),
                    'Unexpected NPC reset confirmation/price')
            self.wipe = (self.trainer.guid, 10000)
            self.pending_respec = False
        elif opcode == 0x132:
            self.casts.append(spell_go(payload))
        elif opcode == 0x12B:
            require(len(payload) == 6 and self.spells is not None, 'Malformed learned spell')
            self.spells.add(struct.unpack_from('<I', payload)[0])
        elif opcode == 0x203:
            require(len(payload) == 4 and self.spells is not None, 'Malformed removed spell')
            self.spells.discard(struct.unpack('<I', payload)[0])
        elif opcode == 0x1F8:
            require(len(payload) == 8, 'Malformed exploration event')
            area, xp = struct.unpack('<II', payload)
            require(xp == 0, 'Unexpected exploration XP, never ignore XP')
            self.exploration.append((area, xp))
        super().process(opcode, payload)

    def wait(self, predicate, label, seconds=15):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if predicate():
                return
            self.stay(.1)
        raise RuntimeError('Native timeout: ' + label)

    def action(self, operation, value=0):
        self.send(*native_packet(operation, value))

    def state(self, active, free, ranks):
        serial = self.talent_serial
        self.action('tier-denial')
        self.wait(lambda: self.talent_serial > serial, 'full talents response')
        expected = dict(free=free, count=len(ranks), active=active,
                        specs=[dict(talents={} if rank is None else {203: rank}, glyphs=[0]*6) for rank in ranks])
        require(self.talents == expected, 'Native full talent state differs: ' + repr(self.talents))
        require(self.spells is not None and 26669 in self.spells, 'Native Evasion rank missing')

    def switch(self, active, free, ranks):
        start = len(self.casts)
        self.action('switch', active)
        spell = (63645, 63644)[active]
        self.wait(lambda: any(c[1] == 35 and c[3] == spell for c in self.casts[start:]), 'activation SPELL_GO')
        self.state(active, free, ranks)

    def menu(self):
        serial = self.gossip_serial
        require(self.trainer is not None, 'No validated runtime trainer')
        self.send(0x17B, struct.pack('<Q', self.trainer.guid))
        self.gossip = None
        self.wait(lambda: self.gossip_serial > serial, 'trainer hello')
        require(self.gossip['menu'] == 4502, 'Wrong trainer root menu')

    def choose(self, purpose):
        wire = resolve_gossip(self.gossip, self.trainer, purpose)
        self.allowed_gossip = struct.pack('<QII', self.trainer.guid, self.gossip['menu'], wire)
        self.send(0x17C, self.allowed_gossip)
        # The send guard needs the last validated menu until transport accepts selection.
        self.gossip, self.wipe = None, None
        self.pending_respec = purpose == 'respec'


class TalentRunner(Runner):
    from verify_merchant_runtime import MerchantRunner
    reuse_control = MerchantRunner.reuse_control

    def __init__(self, db, journal, authorize, *, funded=False):
        self.funded, self.funded_gm_used = funded, False
        super().__init__(db, 'APV2C')
        self.journal, self.authorize = journal, authorize
        self.store = None
        self.trainer = None
        self.clients = []
        self.checkpoint = 0
        self.birth, self.first, self.raw, self.original = [json.loads((BIRTH / (n + '.json')).read_text())
            for n in ('creation', 'first-login-authorized', 'manifest', 'replay')]
        self.profile = owned_identity(self.character(35), self.account_row('APV2C'), self.birth, self.first)
        self.known.add(35)
        self.names[35] = self.birth['name']
        self.reuse_control()

    def client_type(self, sock, authorize):
        client = TalentClient(sock, authorize, self.login_guid, self.journal, self.authorize, self.trainer, funded=self.funded)
        self.clients.append(client)
        return client

    @contextmanager
    def login(self, account, *, guid=None):
        self.authorize()
        require((account, guid) in (('APV2C', 35), ('TEST', 13)), 'No creation or other login')
        if self.funded and guid == 13:
            require(not self.funded_gm_used, 'Funded control session already consumed')
            self.funded_gm_used = True
        if guid == 35:
            owned_identity(self.character(35), self.account_row(account), self.birth, self.first)
        self.login_guid = guid
        client_index = len(self.clients)
        # Root Runner closes its socket before its outer-finally bounded offline wait.
        try:
            with Runner.login(self, account, guid=guid,
                              expected_profile=self.profile if guid == 35 else None) as result:
                yield result
        finally:
            try:
                if len(self.clients) > client_index:
                    self.clients[client_index].packet_log.close()
            finally:
                self.offline(guid)  # Also covers auth/realm failures before Root enters its socket try.

    def all_offline(self):
        require(not self.query('SELECT guid FROM acore_characters.characters WHERE online<>0')
                and not self.query('SELECT id FROM acore_auth.account WHERE online<>0'), 'All actors/accounts must be offline')

    def snapshot_all(self):
        tables = self.query("SELECT TABLE_NAME AS name FROM information_schema.TABLES WHERE TABLE_SCHEMA='acore_characters' AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME")
        result = {}
        for row in tables:
            name = row['name']
            require(re.fullmatch('[a-zA-Z0-9_]+', name) is not None, 'Unsafe table identifier')
            rows = self.query('SELECT * FROM acore_characters.`' + name + '`')
            result[name] = sorted(rows, key=lambda r: json.dumps(r, sort_keys=True, default=str))
        return result

    def save(self, label):
        self.all_offline()
        data = self.snapshot_all()
        self.checkpoint += 1
        self.journal.record('state-' + str(self.checkpoint) + '-' + label, data)
        return data

    def preflight(self):
        from bridge.catalog import Catalog
        from provision_realm import UUID, check_account
        require(self.query('SELECT @@server_uuid AS uuid') == [dict(uuid=UUID)], 'Wrong private DB')
        self.all_offline()
        require(self.before == set(range(1, 43)), 'Expected exact existing 42 actors')
        account = self.account_row('APV2C')
        private = self.query('SELECT email,reg_mail,salt,verifier FROM acore_auth.account WHERE id=4')
        require(len(private) == 1, 'Missing private account')
        check_account(private[0], 'APV2C', os.environ['WOWPILAGO_TEST_ACCOUNT_PASSWORD'])
        require(len(self.query('SELECT guid FROM acore_characters.characters WHERE account=4')) == 10,
                'APV2C roster changed')
        current = self.query('SELECT * FROM acore_characters.mod_archipelago_binding WHERE character_guid=35')
        require(len(current) == 1, 'Original binding missing')
        binding_guard(current[0], self.original['binding'][0], self.raw)
        manifest = Catalog().parse(self.raw, self.raw['seed_name'], 1)
        require(manifest.checksum == current[0]['manifest_hash'], 'Immutable full manifest checksum differs')
        self.manifest = manifest
        self.prefix = self.query('SELECT * FROM acore_characters.mod_archipelago_reward WHERE binding_id=25 ORDER BY item_index')
        receipt_guard(self.prefix, self.original['receipts'], applied=False)
        progress = self.query('SELECT * FROM acore_characters.mod_archipelago_progress WHERE binding_id=25')
        require(len(progress) == 1 and progress[0]['talent_unlocks'] == 0 and progress[0]['cap_items'] == 4,
                'Wrong initial AP progress')
        row = self.character(35)
        require(row['money'] == (MONEY if self.funded else 0)
                and row['resettalents_cost'] == row['activeTalentGroup'] == 0
                and row['talentGroupsCount'] == 1
                and not self.query('SELECT * FROM acore_characters.character_talent WHERE guid=35'),
                'Pristine money/reset/spec/talent baseline required')
        require(self.query('SELECT base_spell FROM acore_characters.mod_archipelago_ability WHERE binding_id=25 ORDER BY base_spell')
                == [dict(base_spell=5277)], 'Evasion permission differs')
        spells = self.query('SELECT spell,specMask FROM acore_characters.character_spell WHERE guid=35 ORDER BY spell')
        require(spells == [dict(spell=5277, specMask=255), dict(spell=26669, specMask=255)],
                'Original Evasion spell masks changed')
        self.trainer_guard()

    def trainer_guard(self):
        source = __import__('verify_artisan_runtime').SOURCE / 'data/sql/base/db_world'
        # Compare live SELECT rows to the pinned full INSERT tuples, not guessed flags/conditions.
        for table, where in (
            ('creature', 'guid=79788'), ('creature_template', 'entry=918'),
            ('creature_default_trainer', 'CreatureId=918'), ('trainer', 'Id=9'),
            ('gossip_menu', 'MenuID IN (4502,10371,10373,4461)'),
            ('gossip_menu_option', 'MenuID IN (4502,10371,10373,4461)'),
            ('broadcast_text', 'ID IN (' + ','.join(map(str, GOSSIP_BROADCAST_IDS)) + ')'),
            ('conditions', '(SourceTypeOrReferenceId=15 AND SourceGroup IN (4502,10371,10373,4461)) OR (SourceTypeOrReferenceId=14 AND SourceGroup IN (4502,10371,10373,4461))')):
            rows = self.query('SELECT * FROM acore_world.' + table + ' WHERE ' + where)
            require(rows or table == 'conditions', 'Missing trainer/menu rows: ' + table)
            self.journal.record('world-' + table.replace('_', '-'), rows)
            verify_dump_rows(source / (table + '.sql'), rows)

    def ingress(self, replay=False):
        from verify_class_systems import items
        require(self.store is not None, 'No locked Store')
        self.authorize()
        if not replay:
            self.journal.record('ingress-intent', dict(binding=25, index=len(self.prefix), item=UNLOCK))
        require(self.store.receive(len(self.prefix), items([UNLOCK])), 'Exact ingress/replay rejected')

    def receipts(self, player):
        player.wait(lambda: self.query('SELECT applied FROM acore_characters.mod_archipelago_reward WHERE binding_id=25 ORDER BY item_index')
                    == [dict(applied=1)] * (len(self.prefix) + 1), 'one AP receipt applied', 45)
        rows = self.query('SELECT * FROM acore_characters.mod_archipelago_reward WHERE binding_id=25 ORDER BY item_index')
        receipt_guard(rows, self.prefix, applied=True)

    def setup_command(self, gm, player, command, complete):
        """One send, bounded paired pumping; never log out with an unrecorded ambiguity."""
        start = len(gm.messages)
        deadline = time.monotonic() + 15
        try:
            gm.send(0x95, say_packet(command))
            while time.monotonic() < deadline:
                for client in (gm, player):
                    client.grant_check()
                messages = gm.messages[start:]
                require(not any(m in ('No character selected.', 'Player not found!',
                                      'You have low security level for this.', 'Creature not found!')
                                or m == 'You are summoning ' + PLAYER_LINK + ' (offline).'
                                or m == PLAYER_LINK + ' is already being teleported.'
                                for m in messages), 'Native setup command refused: ' + repr(messages))
                if complete(messages):
                    self.journal.record('setup-complete-' + str(len(gm.used_commands)),
                                        dict(command=command, messages=messages))
                    return messages
                for client in (gm, player):
                    client.grant_check()
                    if time.monotonic() >= client.next_ping:
                        client.send(0x1DC, struct.pack('<II', client.ping_sequence, 0))
                        client.ping_sequence += 1
                        client.next_ping = time.monotonic() + 30
                ready, _, _ = select.select([gm.sock, player.sock], [], [],
                                            max(0, min(.1, deadline - time.monotonic())))
                for client in (gm, player):
                    if client.sock in ready:
                        client.grant_check()
                        client.process(*client.receive())
            raise RuntimeError('Native setup timeout: ' + command)
        except BaseException as exc:
            self.journal.record('setup-unresolved-' + str(len(gm.used_commands)),
                                dict(command=command, messages=gm.messages[start:], error=str(exc)))
            raise

    def attach_store(self):
        from bridge.v2 import Store
        from bridge.catalog import Catalog
        self.store = Store(dict(host='127.0.0.1', port=13317, user='root', database='acore_characters'), 35, Catalog())
        # Constructor owns the advisory lock. Do not call bind/status, which write SQL.
        binding_guard(self.query('SELECT * FROM acore_characters.mod_archipelago_binding WHERE id=25')[0],
                      self.original['binding'][0], self.raw)
        self.store.binding, self.store.manifest = 25, self.manifest

    def continue_funded(self):
        require(self.funded, 'Funded client policy required')
        saved, attestation = prior_funding()
        self.journal.record('prior-funding-attestation', attestation)
        self.preflight()
        before = self.save('funded-fresh-baseline')
        pristine_funded(before)
        self.journal.record('comparison-funded-baseline', funded_continuity(saved, before))
        self.before_setup = before
        self.attach_store()
        with self.login('TEST', guid=13) as (gm, _):
            with self.login('APV2C', guid=35) as (player, _):
                require(at_trainer(gm.world) and at_trainer(player.world), 'Funded actors must already be near trainer')
                require(self.trainer is None, 'Fresh trainer observation already consumed')
                messages = self.setup_command(gm, player, TRAINER_INFO, lambda messages:
                    any(re.fullmatch(r'SpellSchoolImmuneMask: \d+', m) for m in messages))
                self.trainer = observe_trainer(messages, gm.world, player.world)
                gm.trainer = player.trainer = self.trainer
                self.journal.record('trainer-observation', dict(guid=self.trainer.guid, spawn=TRAINER_SPAWN,
                                    entry=TRAINER_ENTRY, messages=messages, gm_world=gm.world,
                                    player_world=player.world, fresh=True))
                self.setup_command(gm, player, MONEY_INFO, money_readback)
                player.menu()
                self.journal.record('funded-readonly-proof', dict(guid=35, money=MONEY,
                                    trainer=self.trainer.guid, gossip=player.gossip))
        # Both normal logouts precede the pristine saved-state comparison. No further GM login.
        setup = self.save('funded-readonly-saved')
        pristine_funded(setup)
        self.journal.record('comparison-funded-readonly', funded_continuity(before, setup, login_bookkeeping=True))
        self.setup_baseline = setup
        self.execute_funded(setup)

    def execute(self):
        require(not self.funded, 'Funded context cannot execute setup')
        self.preflight()
        before = self.save('pre-money-original')
        require(sum(r['applied'] == 0 for r in before['mod_archipelago_reward']) == 11,
                'Frozen eleven pending receipt inventory changed')
        self.before_setup = before
        self.attach_store()
        with self.login('TEST', guid=13) as (gm, _):
            with self.login('APV2C', guid=35) as (player, _):
                player.state(0, 33, [None])
                serial = gm.teleport_serial
                self.setup_command(gm, player, GO, lambda messages:
                    gm.teleport_serial > serial and gm.world is not None and gm.world[0] == 0
                    and all(abs(a-b) < .1 for a, b in zip(gm.world[1:4], WORLD_POSITION)))
                serial = player.teleport_serial
                self.setup_command(gm, player, SUMMON, lambda messages:
                    messages == ['You are summoning ' + PLAYER_LINK + '.']
                    and player.teleport_serial > serial and at_trainer(player.world))
                require(self.trainer is None, 'Trainer observation already consumed')
                messages = self.setup_command(gm, player, TRAINER_INFO, lambda messages:
                    any(re.fullmatch(r'SpellSchoolImmuneMask: \d+', m) for m in messages))
                self.trainer = observe_trainer(messages, gm.world, player.world)
                self.journal.record('trainer-observation', dict(guid=self.trainer.guid, spawn=TRAINER_SPAWN,
                                    entry=TRAINER_ENTRY, messages=messages, gm_world=gm.world,
                                    player_world=player.world))
                gm.send(0x13D, struct.pack('<Q', 35))
                require(self.character(35)['money'] == 0 and self.names[35] == 'Apsckmrzjjql', 'Pre-money target/baseline changed')
                self.journal.record('money-burned', dict(guid=35, copper=MONEY, once=True))
                self.setup_command(gm, player, MONEY_COMMAND, money_confirmation)
                # LANG_YOU_GIVE_MONEY precedes ModifyMoney; connected pinfo reads GetMoney afterwards.
                self.setup_command(gm, player, MONEY_INFO, money_readback)
        setup = self.save('post-setup-baseline')
        self.setup_baseline = setup
        source_tp(before, setup, player.exploration, gm.exploration)
        self.journal.record('source-tp', dict(player_events=player.exploration, gm_events=gm.exploration,
                                            player_xp_delta=0, level=50))
        require(next(r for r in setup['characters'] if r['guid'] == 35)['money'] == MONEY,
                'Exact one-time money setup failed, never top up again')
        self.journal.record('comparison-setup', compare_snapshots(before, setup, setup=True))
        self.execute_funded(setup)

    def execute_funded(self, setup):
        with self.login('APV2C', guid=35) as (p, _):
            p.menu()  # Fresh exact loaded-NPC interaction before any talent spending.
            resolve_gossip(p.gossip, p.trainer, 'dual')
            resolve_gossip(p.gossip, p.trainer, 'respec')
            p.state(0, 33, [None])
            for rank in range(3):
                p.action('learn', rank)
                p.state(0, 32-rank, [rank])
            p.state(0, 30, [2])
            p.menu()
            serial = p.gossip_serial
            p.choose('dual')
            p.wait(lambda: p.gossip_serial > serial and p.gossip['menu'] == 10371, 'dual purchase menu')
            p.choose('purchase')
            p.wait(lambda: p.talents is not None and p.talents['count'] == 2, 'normal dual purchase')
            p.switch(1, 33, [2, None])
            for rank in range(3):
                p.action('learn', rank)
                p.state(1, 32-rank, [2, rank])
            self.ingress()
            self.receipts(p)
            p.state(1, 31, [2, 2])
        dual = self.save('secondary-unlock')
        assert_saved(dual, active=1, ranks=[2, 2], money=10000)
        self.journal.record('comparison-dual', compare_snapshots(setup, dual))
        with self.login('APV2C', guid=35) as (p, _):
            p.state(1, 31, [2, 2])
            p.switch(0, 31, [2, 2])
            p.menu()
            p.choose('respec')
            p.wait(lambda: p.wipe is not None, 'normal NPC reset confirmation')
            p.action('wipe', self.trainer.guid)
            p.state(0, 34, [None, 2])
        primary = self.save('primary-reset')
        assert_saved(primary, active=0, ranks=[None, 2], money=0)
        self.journal.record('comparison-primary', compare_snapshots(setup, primary))
        for active, exit_active in ((0, 1), (1, 0), (0, 0)):
            with self.login('APV2C', guid=35) as (p, _):
                p.state(active, (34, 31)[active], [None, 2])
                self.ingress(replay=True)
                self.receipts(p)
                p.switch(1-active, (34, 31)[1-active], [None, 2])
                p.switch(active, (34, 31)[active], [None, 2])
                if exit_active != active:
                    p.switch(exit_active, (34, 31)[exit_active], [None, 2])
            saved = self.save('replay-' + str(self.checkpoint))
            assert_saved(saved, active=exit_active, ranks=[None, 2], money=0)
            self.journal.record('comparison-replay-' + str(self.checkpoint), compare_snapshots(setup, saved))


def verify_dump_rows(path, rows):
    """Decode pinned mysqldump literals offline, never execute dump SQL."""
    from decimal import Decimal
    text = path.read_text()
    columns = re.findall(r'^  `([^`]+)` ', text, re.M)
    table = path.stem
    menus = (4502, 10371, 10373, 4461)
    def selected(r):
        if table == 'conditions':
            return r['SourceTypeOrReferenceId'] in (14, 15) and r['SourceGroup'] in menus
        key, values = {
            'creature': ('guid', (79788,)), 'creature_template': ('entry', (918,)),
            'creature_default_trainer': ('CreatureId', (918,)), 'trainer': ('Id', (9,)),
            'gossip_menu': ('MenuID', menus), 'gossip_menu_option': ('MenuID', menus),
            'broadcast_text': ('ID', GOSSIP_BROADCAST_IDS),
        }[table]
        return r[key] in values
    expected = []
    token = re.compile(r"'(?:[^'\\]|\\.)*'|NULL|-?\d+(?:\.\d+)?")
    escapes = {'0': '\0', 'n': '\n', 'r': '\r', 't': '\t', 'Z': '\x1a'}
    for line in text.splitlines():
        if not line.startswith('('):
            continue
        if table == 'broadcast_text':
            # The pinned dump has ID first and one tuple per line. Decode only
            # the exact selected records, using the same narrow literal decoder.
            first = re.match(r'\((\d+),', line)
            require(first is not None, 'Unsupported broadcast dump ID')
            if int(first[1]) not in GOSSIP_BROADCAST_IDS:
                continue
        body = line[1:line.rfind(')')]
        values, pos = [], 0
        while pos < len(body):
            match = token.match(body, pos)
            require(match is not None, 'Unsupported dump literal in ' + str(path))
            raw = match.group()
            if raw.startswith("'"):
                value = re.sub(r'\\(.)', lambda m: escapes.get(m[1], m[1]), raw[1:-1])
            else:
                value = None if raw == 'NULL' else Decimal(raw)
            values.append(value)
            pos = match.end()
            if pos < len(body):
                require(body[pos] == ',', 'Invalid dump delimiter')
                pos += 1
        require(len(values) == len(columns), 'Dump column count differs')
        row = dict(zip(columns, values))
        if selected(row):
            expected.append(row)
    def normalized(data):
        return sorted([{k: Decimal(str(v)) if isinstance(v, (int, float, Decimal)) else v
                        for k, v in r.items()} for r in data], key=lambda r: repr(sorted(r.items())))
    if rows is not None:
        if table == 'creature' and rows and 'id' in rows[0]:
            require(all(r.get('id2') == r.get('id3') == 0 and 'id1' in r and 'id' not in r
                        for r in expected), 'Single-template schema cannot represent source alternatives')
            expected = [{('id' if k == 'id1' else k): v for k, v in r.items()
                         if k not in ('id2', 'id3')} for r in expected]
        require(normalized(rows) == normalized(expected), 'Live trainer dump differs: ' + table)
    return expected


BOOKKEEPING = {'totaltime', 'leveltime', 'logout_time', 'latency', 'rest_bonus', 'is_logout_resting'}
POSITION = {'position_x', 'position_y', 'position_z', 'orientation', 'map', 'zone',
            'taximask', 'exploredZones'}
TALENT_SPELLS = {13741, 13793, 13792, 63644, 63645}


def source_tp(before, after, player_events, gm_events):
    from tools.validate_checks import DBC
    from verify_class_systems import DBC_DIR
    areas = DBC(DBC_DIR / 'AreaTable.dbc')
    require(not gm_events, 'Control must have already explored the setup area')
    for guid, events in ((35, player_events), (13, gm_events)):
        old = next(r for r in before['characters'] if r['guid'] == guid)
        new = next(r for r in after['characters'] if r['guid'] == guid)
        expected = [int(v) for v in old['exploredZones'].split()]
        require(new['xp'] == old['xp'] and new['level'] == old['level'], 'TP changed XP/level')
        require(new['taximask'] == old['taximask'], 'TP unexpectedly changed taxi unlocks')
        for area, xp in events:
            require(guid == 35 and xp == 0 and area in areas.rows, 'Unexpected TP event')
            row = areas.rows[area]
            require(row[1] == 0 and (area == 1519 or row[2] == 1519) and row[10] == 10
                    and max(0, 100 - ((50 - row[10] - 5) * 5)) == 0,
                    'TP exploration must be source-confirmed Stormwind level10 with zero XP')
            offset, bit = divmod(row[3], 32)
            require(offset < len(expected) and not expected[offset] & (1 << bit), 'Duplicate/preexplored TP event')
            expected[offset] |= 1 << bit
        require([int(v) for v in new['exploredZones'].split()] == expected,
                'Explored bits differ from actual zero-XP TP events')


# BattlefieldWG's 60-second save persists this uint32 millisecond countdown without players.
AUTOMATIC_WORLDSTATE_KEYS = {3781}
AP_MERCHANT_SPAWNS = range(9005000, 9005010)
AMBIENT_WORLD_MAPS = (0, 1, 530, 571, 609)  # Map.dbc type0 includes the autonomous Scarlet Enclave NPC battle.


@cache
def ambient_creature_spawns():
    from verify_artisan_runtime import SOURCE
    text = (SOURCE / 'data/sql/base/db_world/creature.sql').read_text()
    # Map::SaveCreatureRespawnTime stores m_spawnId, not a player GUID or runtime counter.
    spawns = {int(guid): int(map_id) for guid, map_id in re.findall(
        r'^\((\d+),\d+,\d+,\d+,(\d+),', text, re.M)}
    update = (SOURCE / 'data/sql/updates/db_world/2026_07_21_00.sql').read_text()
    require('\n(128897, 28822, 609, 0, 0, 1, 1, 0, 2389.6025,' in update,
            'Pinned Scarlet Miner spawn update changed')
    spawns[128897] = 609
    event = (SOURCE / 'data/sql/updates/db_world/2026_08_04_00.sql').read_text()
    require('SET @GUID := 53048;' in event, 'Pinned Cold Wind event spawn base changed')
    event_spawns = {int(offset): (int(entry), int(map_id)) for offset, entry, map_id in
                    re.findall(r'^\(@GUID\+(\d+)\s*,\s*(\d+),\s*(\d+),', event, re.M)}
    require(event_spawns == {0: (25446, 571), 1: (25453, 571),
                            **{offset: (25244, 571) for offset in range(3, 15)}},
            'Pinned Cold Wind event spawn identities changed')
    spawns.update({53048 + offset: map_id for offset, (_, map_id) in event_spawns.items()})
    return spawns


def compare_ambient(table, old, new):
    """Audit explicit world-owned rows; retain AP spawns and other worldstates exactly."""
    if table == 'worldstates':
        for rows in (old, new):
            require(all(set(r) == {'entry', 'value', 'comment'}
                        and type(r['entry']) is int and 0 <= r['entry'] < 2**32
                        and type(r['value']) is int and 0 <= r['value'] < 2**32
                        and (r['comment'] is None or type(r['comment']) is str) for r in rows)
                    and len({r['entry'] for r in rows}) == len(rows), 'Invalid worldstate shape/type')
        previous = {r['entry']: r for r in old}
        require(previous.keys() == {r['entry'] for r in new}, 'Worldstate inventory changed')
        for row in new:
            prior = previous[row['entry']]
            require(row == prior or (row['entry'] in AUTOMATIC_WORLDSTATE_KEYS
                    and row['comment'] == prior['comment']), 'Protected worldstate changed')
    else:
        require(table == 'creature_respawn', 'Unknown ambient table')
        spawns = ambient_creature_spawns()
        def dynamic(row):
            return (row['guid'] not in AP_MERCHANT_SPAWNS and row['guid'] != TRAINER_SPAWN
                    and row['instanceId'] == 0 and row['mapId'] in AMBIENT_WORLD_MAPS
                    and spawns.get(row['guid']) == row['mapId'])
        for rows in (old, new):
            require(all(set(r) == {'guid', 'respawnTime', 'mapId', 'instanceId'}
                        and all(type(v) is int and 0 <= v < (2**16 if k == 'mapId' else 2**32)
                                for k, v in r.items()) and r['guid'] > 0 for r in rows)
                    and len({(r['guid'], r['instanceId']) for r in rows}) == len(rows),
                    'Invalid creature respawn shape/type')
        require([r for r in old if not dynamic(r)] == [r for r in new if not dynamic(r)],
                'Protected AP/trainer/instance/unknown creature respawn changed')
    return dict(before_rows=len(old), after_rows=len(new),
                removed_or_changed=[r for r in old if r not in new],
                added_or_changed=[r for r in new if r not in old])


def compare_snapshots(before, after, *, setup=False, at_time=None):
    """Keep raw snapshots intact; audit world ambient separately from protected state."""
    require(before.keys() == after.keys(), 'Table inventory changed')
    ambient = {}
    for table in before:
        old, new = before[table], after[table]
        if table in ('creature_respawn', 'worldstates'):
            ambient[table] = compare_ambient(table, old, new)
            continue
        if old == new:
            continue
        if table == 'characters':
            require({r['guid'] for r in old} == {r['guid'] for r in new}, 'Character roster changed')
            old_by = {r['guid']: r for r in old}
            for row in new:
                guid = row['guid']
                previous = old_by[guid]
                allow = set()
                if guid in (13, 35):
                    allow |= BOOKKEEPING
                if setup and guid in (13, 35):
                    allow |= POSITION | {'playerFlags'}
                    require((row['playerFlags'] ^ previous['playerFlags']) & ~0x20 == 0,
                            'TP changed flags other than city resting')
                if guid == 35:
                    allow |= {'money'} if setup else {'money', 'talentGroupsCount', 'activeTalentGroup',
                                                       'resettalents_cost', 'resettalents_time', 'power4'}
                    if not setup:
                        require(0 <= row['power4'] <= 100, 'Spec activation energy outside normal range')
                require({k: v for k, v in row.items() if k not in allow}
                        == {k: v for k, v in previous.items() if k not in allow},
                        'Protected character fields changed: ' + str(guid))
                if guid in (13, 35):
                    require(row['totaltime'] >= previous['totaltime'] and row['leveltime'] >= previous['leveltime'],
                            'Played time moved backwards')
                if setup and guid in (13, 35):
                    require(row['map'] == 0 and abs(row['position_x'] + 8752.3) < 5
                            and abs(row['position_y'] - 377.572) < 5 and abs(row['position_z'] - 101.139) < 5,
                            'Source TP position differs')
        elif not setup and table == 'mod_archipelago_progress':
            require([{k: v for k, v in r.items() if k != 'talent_unlocks' or r['binding_id'] != 25} for r in old]
                    == [{k: v for k, v in r.items() if k != 'talent_unlocks' or r['binding_id'] != 25} for r in new],
                    'Protected AP progress changed')
            require(next(r for r in new if r['binding_id'] == 25)['talent_unlocks'] == 1,
                    'Not exactly one talent unlock')
        elif not setup and table == 'mod_archipelago_reward':
            original = [r for r in old if r['binding_id'] == 25]
            receipt_guard(sorted([r for r in new if r['binding_id'] == 25], key=lambda r: r['item_index']),
                          sorted(original, key=lambda r: r['item_index']), applied=True)
            require([r for r in old if r['binding_id'] != 25] == [r for r in new if r['binding_id'] != 25],
                    'Other/frozen pending receipts changed')
        elif not setup and table in ('character_talent', 'character_spell', 'character_aura', 'character_glyphs'):
            def allowed(r):
                if r['guid'] != 35:
                    return False
                if table == 'character_glyphs':
                    require(r['spec'] in (0, 1)
                            and set(r) == {'guid', 'spec', 'glyph1', 'glyph2', 'glyph3', 'glyph4', 'glyph5', 'glyph6'}
                            and all(v == 0 for k, v in r.items() if k.startswith('glyph')), 'Unexpected saved glyph')
                    return True
                return r['spell'] in TALENT_SPELLS | ({14867} if table == 'character_aura' else set())
            require([r for r in old if not allowed(r)] == [r for r in new if not allowed(r)],
                    'Protected spell/talent/aura/glyph rows changed: ' + table)
        elif table in ('character_achievement_progress', 'character_achievement'):
            achievement_changes(before, after, table, setup=setup, at_time=at_time)
        else:
            raise RuntimeError('Unexpected durable change in ' + table)
    return dict(protected_comparison_passed=True, ambient_world_audit=ambient)


def achievement_changes(before, after, table, *, setup, at_time=None):
    now = int(time.time()) if at_time is None else at_time
    old, new = before[table], after[table]
    if table == 'character_achievement':
        allowed = lambda r: not setup and r['guid'] == 35 and r['achievement'] == 2716
        require([r for r in old if not allowed(r)] == [r for r in new if not allowed(r)],
                'Unrelated achievement changed')
        added = [r for r in new if allowed(r)]
        require(len(added) == 1 and now-1800 <= added[0]['date'] <= now,
                'Unexpected dual-spec achievement/date')
        return
    # Player::SetMoney, CheckAreaExploreAndOutdoor, resetTalents and CompletedAchievement.
    reset = next(r for r in after['characters'] if r['guid'] == 35)['resettalents_cost'] == 10000
    gain = int(not setup and not any(r['guid'] == 35 and r['achievement'] == 2716
                                    for r in before['character_achievement'])) * 10
    changes = {4224: MONEY, 1149: 1} if setup else {9619: 1, 12698: gain}
    if reset and not setup:
        changes.update({3359: 1, 3360: 10000})
    allowed = lambda r: r['guid'] == 35 and r['criteria'] in changes
    require([r for r in old if not allowed(r)] == [r for r in new if not allowed(r)],
            'Unrelated achievement criteria changed')
    previous = {r['criteria']: r for r in old if allowed(r)}
    for row in new:
        if not allowed(row):
            continue
        criterion = row['criteria']
        prior = previous.get(criterion)
        counter = prior['counter'] if prior else 0
        expected = max(counter, changes[criterion]) if criterion in (4224, 1149, 9619) else counter + changes[criterion]
        require(row['counter'] == expected and (row == prior or now-1800 <= row['date'] <= now),
                'Normal money/explore/purchase/reset criterion differs: ' + str(criterion))
        require(set(row) == {'guid', 'criteria', 'counter', 'date'}, 'Unknown criteria fields')
    require(set(previous) <= {r['criteria'] for r in new if allowed(r)}, 'Criteria deleted')


def assert_saved(data, *, active, ranks, money):
    row = next(r for r in data['characters'] if r['guid'] == 35)
    require((row['level'], row['race'], row['class'], row['talentGroupsCount'], row['activeTalentGroup'], row['money'])
            == (50, 1, 4, 2, active, money), 'Saved owned spec/economy differs')
    require(row['resettalents_cost'] == (10000 if ranks[0] is None else 0), 'Saved reset fee differs')
    expected = {}
    for spec, rank in enumerate(ranks):
        if rank is not None:
            spell = (13741, 13793, 13792)[rank]
            expected[spell] = expected.get(spell, 0) | (1 << spec)
    actual = {r['spell']: r['specMask'] for r in data['character_talent'] if r['guid'] == 35}
    require(actual == expected, 'Saved talent masks/ranks differ')
    for spell in (5277, 26669):
        require([r['specMask'] for r in data['character_spell'] if r['guid'] == 35 and r['spell'] == spell] == [255],
                'Saved Evasion SPEC_MASK_ALL changed')


def run(grant_path, owners_path, *, funded=False):
    # Only the supplied authorization files may be read until scope/TTL/owners pass.
    external_grant(grant_path, owners_path, funded=funded, inspect_processes=False)
    evidence = source_evidence()
    hashes = json.loads(json.dumps(evidence))
    authorize = lambda: external_grant(grant_path, owners_path, hashes, funded=funded)
    grant = authorize()
    require(os.environ.get('WOWPILAGO_TEST_ACCOUNT_PASSWORD') == 'test-only'
            and os.environ.get('WOWPILAGO_DB_PASSWORD') == 'test-only', 'Private credentials required')
    # Both original execution journals are consumed and immutable.
    journal = Journal(FUNDED_JOURNAL if funded else OUTPUT / 'schema-reviewed-execution', funded=funded)
    journal.record('attempt', dict(grant=grant, hashes=hashes, money_reserved=0 if funded else MONEY))
    # Exclusive intent precedes runtime observations, SQL, Store ownership and all auth.
    body_error = None
    try:
        runtime = runtime_guard(evidence)
        journal.record('runtime', runtime)
        authorize()
        import pymysql
        with pymysql.connect(host='127.0.0.1', port=13317, user='root', password='test-only', autocommit=True,
                             cursorclass=pymysql.cursors.DictCursor, connect_timeout=5, read_timeout=15, write_timeout=15) as db:
            runner, completed = None, False
            try:
                runner = TalentRunner(db, journal, authorize, funded=funded)
                if funded:
                    runner.continue_funded()
                else:
                    runner.execute()
                completed = True
            except BaseException as exc:
                body_error = exc
                journal.record('failure', dict(error=str(exc), preserved=True))
                raise
            finally:
                if runner is not None:
                    try:
                        if runner.store is not None:
                            runner.store.close()
                    finally:
                        # Both bounded waits run even when Store.close or the first wait fails.
                        try:
                            runner.offline(35)
                        finally:
                            runner.offline(13)
                    final = runner.save('final-preserved')
                    if hasattr(runner, 'setup_baseline'):
                        journal.record('comparison-final', compare_snapshots(runner.setup_baseline, final))
                        if completed:
                            assert_saved(final, active=0, ranks=[None, 2], money=0)
                    elif funded and hasattr(runner, 'before_setup'):
                        journal.record('comparison-final-readonly',
                                       funded_continuity(runner.before_setup, final, login_bookkeeping=True))
    except BaseException as exc:
        # Includes runtime/SQL-connect/constructor/cleanup failures, never overwrites body evidence.
        name = 'cleanup-failure' if body_error is not None else 'failure'
        if exc is not body_error:
            journal.record(name, dict(error=str(exc), preserved=True))
        raise
    journal.record('pass', dict(status='PASS_NATIVE_FABRICATED_INGRESS', actor=35, earned=34,
                              free_primary=34, free_secondary=31, release_gate=False))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--source-evidence', action='store_true', help='Read pinned local files only')
    mode.add_argument('--run', action='store_true', help='Requires a fresh external parent grant and one-shot intent')
    mode.add_argument('--continue-funded', action='store_true', help='Fresh parent-funded grant; no setup/money retry')
    parser.add_argument('--grant', type=Path)
    parser.add_argument('--owners', type=Path)
    args = parser.parse_args(argv)
    if args.run or args.continue_funded:
        require(args.grant is not None and args.owners is not None,
                ('--continue-funded' if args.continue_funded else '--run') + ' requires parent --grant and --owners; no authorization supplied')
        return run(args.grant, args.owners, funded=True) if args.continue_funded else run(args.grant, args.owners)
    print(json.dumps(source_evidence() if args.source_evidence else PLAN, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
