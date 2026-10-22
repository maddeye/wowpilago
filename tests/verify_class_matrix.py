"""Native nine-class fixture executor. Offline by default; --run requires parent release."""
import argparse
from copy import deepcopy
from contextlib import contextmanager, redirect_stdout
import hashlib
import json
import os
import secrets
import struct
import time
from pathlib import Path
import sys

import verify_artisan_runtime as artisan
from verify_runtime import SmokeClient, initial_spells, selection_packet, say_packet
from verify_class_systems import items, emit
from verify_travel_runtime import packed_guid, spell_go
from realm_client import create_character
from provision_realm import UUID, check_account
from bridge.catalog import Catalog, filter_profile
from verify_runtime import Runner, guard_account, manifest_fixture, require, LABEL
from verify_class_systems import DBC_DIR, expected_points
from tools.validate_checks import DBC

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / '.local/class-matrix-plan/final-two'
SEMANTIC = '4611c269173e443bff425e85a255fa086315ffdec0657c9098982d8e6fe9e1b0'
WORLD = '3b9b2bf9f946a1eeef5908e440ed917132c0559c4bc483ba14be199060641809'
BASE = '0edea8dba721f996f00cf0b5c95e3576fff1ad4dd6e637fd8c0ad45b06f1285b'
PATCH = '76342b88b9864f85525771ba51de7c2b78467343027075b83184bc76356aca6c'
ACCOUNTS = tuple('APV2' + c for c in 'BCDEF')
BUDGET_SECONDS = 3600
# Class, race, ordinary starting combat spell. Hunter cannot be Human.
PROFILES = ((1, 1, 78), (2, 1, 635), (3, 2, 75), (4, 1, 1752),
            (5, 1, 585), (7, 2, 403), (8, 1, 133), (9, 1, 686), (11, 4, 5176))


def selected_classes(classes=None):
    selected = list(classes) if classes is not None else [p[0] for p in PROFILES]
    require(selected and len(selected) == len(set(selected))
            and all(type(c) is int and c in {p[0] for p in PROFILES} for c in selected),
            'Classes must be a nonempty unique legal matrix subset; DK excluded')
    return selected


def authorize_selection(release, classes):
    require(release.get('authorized_classes') == classes
            and classes == [9, 11] and release.get('creation_limit') == len(classes)
            and release.get('prior_partial_guid_preserved') == 39,
            'Final-two release must authorize exactly selected classes and creation limit; preserve GUID39')


def select_profiles(catalog):
    require(catalog.version == SEMANTIC, 'Catalog changed; review matrix before proceeding')
    selected = []
    for class_id, race, _ in PROFILES:
        matches = [p for p in catalog.profiles if (p['class_id'], p['race_id']) == (class_id, race)]
        require(len(matches) == 1, 'Unsupported or ambiguous race/class')
        selected.append(deepcopy(matches[0]))
    require({p['faction'] for p in selected} == {'alliance', 'horde'}, 'Missing faction')
    require(not any(p['class_id'] == 6 for p in catalog.profiles), 'DK unexpectedly supported')
    return selected


def class_manifest(catalog, profile, seed):
    """Keep the shared complete wire format; replace every class-dependent section."""
    require(profile in select_profiles(catalog), 'Not a matrix profile; DK excluded AP v1')
    raw = deepcopy(manifest_fixture(catalog, seed))
    class_id = profile['class_id']
    featured = next(s for s in catalog.documents['gear']['sets'] if class_id in s['class_ids'])
    stock = [{'wow_id': g['wow_id'], 'price': g['price'], 'max_purchases': 1}
             for g in sorted(catalog.gear.values(), key=lambda g: g['wow_id'])
             if g['quality'] != 5 and class_id in g['allowable_classes']
             and catalog.class_roles[class_id].intersection(g['roles'])
             and g['wow_id'] not in featured['pieces']][:30]
    require(len(stock) == 30, 'Insufficient legal stock')
    raw['profile'] = deepcopy(profile)
    raw['options'].update(character_race=profile['race_id'], character_class=class_id, legendary_count=0)
    raw['selected_checks'] = filter_profile(catalog.checks, profile)
    codes = {r['ap_id'] for r in catalog.generic}
    codes.update(a['ap_id'] for a in catalog.abilities if a['class_id'] == class_id)
    raw['rewards'] = {str(code): {k: catalog.definitions[code][k] for k in ('kind', 'value')}
                      for code in sorted(codes)}
    raw['legendary_ids'] = []
    raw['merchant'].update(stock=stock, total_cost=sum(g['price'] for g in stock),
                           featured_sets=[dict(set_id=featured['wow_id'], pieces=sorted(featured['pieces']),
                                               rolled_pieces=[])])
    catalog.parse(raw, seed, 1)
    return raw


def select_chain(catalog, class_id, spells):
    """Prefer a ranked chain without consumable, skill or totem setup."""
    candidates = []
    for ability in catalog.abilities:
        if ability['class_id'] != class_id:
            continue
        baseline = [s for p in ability['prerequisites'] if p['kind'] == 'baseline_spells'
                    for s in p['spell_ids']]
        if baseline and not (class_id == 1 and baseline == [2457]):
            continue  # Avoid form acquisition setup; Warrior's starting stance is checked at login.
        ranks = [p for p in ability['prerequisites'] if p['kind'] == 'rank_eligibility']
        if len(ranks) < 2 or any(p[k] for p in ranks for k in
                                ('required_spell', 'required_skill', 'required_skill_rank',
                                 'totem_items', 'totem_categories', 'reagents')):
            continue
        require([p['spell_id'] for p in ranks] == ability['ranks'], 'Rank order changed')
        levels = [spells.rows[p['spell_id']][39] for p in ranks]
        require(levels == [p['min_level'] for p in ranks], 'DBC/catalog normal levels disagree')
        if not 1 < levels[0] < levels[1] <= 80:
            continue
        candidates.append((ability, levels))
    require(candidates, 'No safe ranked chain for class ' + str(class_id))
    ability, levels = min(candidates, key=lambda pair: (pair[1][0], pair[0]['base_spell']))
    return dict(name=ability['name'], ap_id=ability['ap_id'], base_spell=ability['base_spell'],
                ranks=ability['ranks'][:2], levels=levels[:2], prerequisites=ability['prerequisites'])


def capacity_budget(cases, snapshots):
    """Pure planning over a future SELECT snapshot, never assumes current free slots."""
    require(set(snapshots) == set(ACCOUNTS), 'Need all five marked account snapshots')
    remaining = {}
    for account in ACCOUNTS:
        row, count = snapshots[account]
        guard_account(row, account)
        require(type(row['id']) is int and row['id'] > 1 and type(count) is int and 0 <= count <= 10,
                'Invalid account ID/count')
        remaining[account] = 10 - count
    assigned = []
    for case in cases:
        account = next((a for a in ACCOUNTS if remaining[a]), None)
        require(account is not None, 'Insufficient capacity; preserve all fixtures, do not delete')
        remaining[account] -= 1
        assigned.append(dict(class_id=case['profile']['class_id'], account=account))
    return dict(assignments=assigned, remaining=remaining)


def fixture_guard(row, *, account_id, name, profile, known, bindings):
    require(row is not None and type(row['guid']) is int and row['guid'] > 4
            and row['guid'] in known, 'Protected or not-known-created GUID')
    require(profile['class_id'] != 6 and row['account'] == account_id and row['name'] == name
            and row['race'] == profile['race_id'] and row['class'] == profile['class_id'],
            'Actual race/class/ownership mismatch before login')
    require(row['online'] == 0 and row['level'] == 1 and not bindings,
            'Must bind fresh offline level 1 only; never reset history')


def released_evidence():
    """Future preflight only. Reuse strict build/process guards, then matrix release."""
    evidence = artisan.build_evidence()
    release = json.loads((OUTPUT / 'release.json').read_text())
    require(release.get('owned_release') is True and release.get('mail_lifetime_fixed') is True
            and release.get('manifest_sha256') == evidence['manifest_sha256']
            and release.get('world_sha256') == evidence['world_sha256'] == WORLD,
            'Matrix parent release missing/mismatched')
    manifest = json.loads((artisan.BUILD / 'manifest.json').read_text())
    require(artisan.digest(artisan.BUILD / 'base-manifest.json') == BASE
            and manifest.get('base_manifest_sha256') == BASE
            and release.get('base_manifest_sha256') == BASE
            and manifest.get('patch_sha256') == PATCH,
            'Preserved base manifest or combined mail-fixed patch mismatch')
    inventory = json.loads((artisan.BUILD / 'source-files.sha256.json').read_text())
    for name in ('SpellAuras.cpp', 'SpellAuraDefines.h'):
        path = 'src/server/game/Spells/Auras/' + name
        require(artisan.digest(artisan.SOURCE / path) == inventory[path], 'Native aura helper changed')
    runtime = artisan.runtime_evidence(evidence)
    return dict(build=evidence, runtime=runtime, release=release)


def aura_spells(data):
    """Actual AuraApplication::BuildUpdatePacket layout, including optional fields."""
    guid, offset = packed_guid(data)
    spells = set()
    while offset < len(data):
        require(len(data) >= offset + 5, 'Truncated aura header')
        _, spell = struct.unpack_from('<BI', data, offset)
        offset += 5
        if not spell:
            continue
        require(len(data) >= offset + 3, 'Truncated aura flags')
        flags, _, _ = struct.unpack_from('<BBB', data, offset)
        offset += 3
        if not flags & 8:
            _, offset = packed_guid(data, offset)
        if flags & 32:
            offset += 8
        require(not flags & 64, 'Pinned native aura writer does not emit effect amounts')
        require(offset <= len(data), 'Truncated aura fields')
        spells.add(spell)
    return guid, spells


class MatrixClient(SmokeClient):
    def __init__(self, sock, authorize, runner, setup):
        self.runner, self.setup = runner, setup
        self.casts, self.failures, self.auras = [], [], []
        self.initial_spell_packet = None

        def checked_authorize(guid, events):
            require(guid > 4 and (not setup or guid == 13), 'Protected matrix login GUID')
            authorize(guid, events)
            if not setup and runner.guid is None:
                fixture_guard(runner.character(guid), account_id=runner.account_row(runner.account)['id'],
                              name=runner.names[guid], profile=runner.case['profile'], known=runner.known,
                              bindings=runner.query('SELECT id FROM acore_characters.mod_archipelago_binding WHERE character_guid=%s', (guid,)))
                runner.save('first-login-authorized', dict(guid=guid, profile=runner.case['profile'], label=LABEL))
        super().__init__(sock, checked_authorize)

    def send(self, opcode, payload=b''):
        self.runner.deadline_check()
        require(opcode in (0x1ED, 0x37, 0x36, 0x3D, 0x4B, 0x1DC, 0x391,
                           0x13D, 0x95, 0x12E), 'Matrix opcode not allowed')
        if opcode == 0x36:
            require(not self.setup and payload == create_character(
                self.runner.pending_name, race=self.runner.case['profile']['race_id'],
                class_id=self.runner.case['profile']['class_id']), 'Unexpected creation profile')
        elif opcode == 0x13D:
            require(self.setup and payload == selection_packet(self.runner.guid), 'Wrong GM selection')
        elif opcode == 0x95:
            require(self.setup and payload == say_packet(self.runner.allowed_command), 'Unapproved chat')
        elif opcode == 0x12E:
            require(not self.setup and self.runner.case['profile']['class_id'] == 8
                    and payload == struct.pack('<BIBI', 1, 168, 0, 0), 'Only starting Frost Armor cast')
        super().send(opcode, payload)
        emit('matrix_packet', direction='client', opcode=hex(opcode), raw=payload.hex(), label=LABEL)

    def connect(self, account, auth, realm, name, **kwargs):
        self.runner.pending_name = name
        return super().connect(account, auth, realm, name, **kwargs)

    def process(self, opcode, payload):
        if opcode == 0x12A:
            self.initial_spell_packet = bytes(payload)
        if opcode in (0x12A, 0x132, 0x130, 0x495, 0x496):
            emit('matrix_packet', direction='server', opcode=hex(opcode), raw=payload.hex(), label=LABEL)
        if opcode == 0x132:
            self.casts.append(spell_go(payload))
        elif opcode == 0x130:
            require(len(payload) == 6, 'Invalid cast failure')
            self.failures.append(struct.unpack('<BIB', payload))
        elif opcode in (0x495, 0x496):
            self.auras.append(aura_spells(payload))
        super().process(opcode, payload)

    def logout(self):
        # Cleanup remains permitted after the scheduling deadline.
        self.runner.cleaning = True
        try:
            super().logout()
        finally:
            self.runner.cleaning = False


class MatrixRunner(Runner):
    reuse_control = artisan.ArtisanRunner.reuse_control

    def __init__(self, db, account, case, *, deadline=None, output=None):
        require(account in ACCOUNTS, 'Protected account')
        super().__init__(db, account)
        self.case = case
        require(case['profile'] in select_profiles(Catalog()), 'Not a typed Catalog profile')
        self.deadline = deadline if deadline is not None else time.monotonic() + BUDGET_SECONDS
        self.output = output
        self.created = self.cleaning = False
        self.guid = self.store = None
        self.codes, self.receipts = [], []
        self.level, self.cap = 1, 10
        self.allowed_command = ''
        self.baseline = None
        self.login_sequence = 0
        self.permitted = False

    def deadline_check(self):
        require(self.cleaning or time.monotonic() < self.deadline,
                f'{BUDGET_SECONDS}-second matrix deadline; preserve partial fixture/history')

    @contextmanager
    def login(self, account, *, guid=None):
        self.deadline_check()
        require(account in (self.account, 'TEST'), 'Protected account')
        setup = account == 'TEST'
        if guid is None:
            require(not setup and not self.created, 'One creation only; never create TEST or retry')
            row = self.account_row(account)
            guard_account(row, account)
            count = self.query('SELECT COUNT(*) AS n FROM acore_characters.characters WHERE account=%s',
                               (row['id'],))[0]['n']
            require(count < 10, 'Capacity changed')
            self.created = True
            self.save('reservation', dict(account=account, profile=self.case['profile'], label=LABEL))
        else:
            require(guid > 4 and guid in self.known and guid == (13 if setup else self.guid),
                    'Not owned fixture/control')
        self.client_type = lambda sock, authorize: MatrixClient(sock, authorize, self, setup)
        profile = None if setup else self.case['profile']
        result = None
        try:
            with Runner.login(self, account, guid=guid, expected_profile=profile) as result:
                if guid is None:
                    self.guid = result[1]
                    self.save('creation', dict(guid=self.guid, name=self.names[self.guid],
                                              account=account, profile=profile, label=LABEL))
                if not setup:
                    self.login_sequence += 1
                    self.native_spells(result[0])
                yield result
        except BaseException:
            # Shared login skips its post-with offline wait when the body raises.
            if result is not None:
                self.offline(result[1])
            raise

    def native_spells(self, player):
        """Only this connection's INITIAL_SPELLS is evidence, never saved default rows."""
        raw = player.initial_spell_packet
        require(raw is not None and player.spells is not None, 'Missing fresh INITIAL_SPELLS packet')
        known = initial_spells(raw)
        require(known == player.spells, 'Native spell packet/client mismatch')
        result = dict(guid=self.guid, login_sequence=self.login_sequence,
                      spells=sorted(known), raw=raw.hex(), sha256=hashlib.sha256(raw).hexdigest())
        self.save('login-' + str(self.login_sequence), result)
        if self.baseline is None:
            require(self.case['baseline_spell'] in known, 'Starting baseline missing')
            require(not set(self.case['chain']['ranks']) & known, 'Selected chain already starting-known')
            prerequisites = {s for p in self.case['chain']['prerequisites'] if p['kind'] == 'baseline_spells'
                             for s in p['spell_ids']}
            require(prerequisites <= known, 'Missing starting form prerequisite')
            self.baseline = set(known)
        require(self.baseline <= known, 'Starting baseline spell lost from fresh native packet')
        eligible = []
        for spell, level in zip(self.case['chain']['ranks'], self.case['chain']['levels']):
            if self.permitted and self.level >= level:
                eligible.append(spell)
            else:
                require(spell not in known, 'Locked/ineligible selected rank in native packet')
        # Core hides superseded lower ranks from INITIAL_SPELLS, not from saved learned rows.
        require(not eligible or eligible[-1] in known, 'Eligible active rank missing from native packet')
        return result

    def save(self, name, value):
        if self.output is not None:
            with (self.output / (name + '.json')).open('x') as handle:
                json.dump(value, handle, default=str, indent=2)

    def setup_command(self, name, command, level, cap):
        chain = self.case['chain']
        allowed = {'.learn ' + str(s) for s in chain['ranks']}
        targets = {1, *(n for level_gate in chain['levels'] for n in (level_gate - 1, level_gate))}
        allowed.update('.levelup ' + name + ' ' + str(n - level) for n in targets if level < n <= cap)
        require(command in allowed, 'Only forward capped fixture setup and selected class learns')
        return command

    def command(self, gm, command, *, cap_probe=False):
        self.deadline_check()
        if cap_probe:
            require(self.level == 1 and self.cap == 10 and command ==
                    '.levelup ' + self.names[self.guid] + ' 10', 'Only initial cap-11 negative probe')
            self.allowed_command = command
        else:
            self.allowed_command = self.setup_command(self.names[self.guid], command, self.level, self.cap)
        gm.send(0x13D, selection_packet(self.guid))
        emit('matrix_fixture_command', command=command, messages=gm.command(command), label=LABEL)

    def queue(self, player, gm, codes):
        self.deadline_check()
        require(codes and all(c in (919100001, self.case['chain']['ap_id']) for c in codes),
                'Unexpected ingress')
        require(self.store.receive(len(self.codes), items(codes)), 'Ingress rejected')
        self.codes.extend(codes)
        emit('matrix_fake_ingress', guid=self.guid, codes=codes, seed=self.seed, label=LABEL)
        end = min(self.deadline, time.monotonic() + 45)
        while time.monotonic() < end:
            rows = self.reward_rows()
            if len(rows) == len(self.codes) and all(r['applied'] == 1 for r in rows):
                artisan.guard_receipts(rows, self.codes, self.receipts)
                return
            player.stay(.2)
            gm.stay(.05)
        raise RuntimeError('Native receipt timeout; preserve history')

    def reward_rows(self):
        return self.query('SELECT * FROM acore_characters.mod_archipelago_reward WHERE binding_id=%s ORDER BY item_index',
                          (self.binding,))

    def immutable(self):
        rows = self.query('SELECT * FROM acore_characters.mod_archipelago_binding WHERE id=%s', (self.binding,))
        return [{k: v for k, v in row.items() if k not in ('status', 'heartbeat')} for row in rows]

    def state(self, label, *, permitted):
        self.deadline_check()
        self.permitted = permitted
        # A post-action reload proves the baseline again; the previous login packet is stale.
        with self.login(self.account, guid=self.guid) as (player, _):
            native = dict(guid=self.guid, login_sequence=self.login_sequence,
                          spells=sorted(player.spells), raw=player.initial_spell_packet.hex(),
                          sha256=hashlib.sha256(player.initial_spell_packet).hexdigest())
        row = self.offline(self.guid)
        require(row['level'] == self.level and row['race'] == self.case['profile']['race_id']
                and row['class'] == self.case['profile']['class_id'], 'Saved level/profile mismatch')
        spells = self.query('SELECT * FROM acore_characters.character_spell WHERE guid=%s ORDER BY spell', (self.guid,))
        known = {r['spell'] for r in spells if not r.get('disabled', 0)}
        for spell, level in zip(self.case['chain']['ranks'], self.case['chain']['levels']):
            require((spell in known) == (permitted and self.level >= level), 'Native rank gate mismatch')
        rows = self.reward_rows()
        artisan.guard_receipts(rows, self.codes, self.receipts)
        self.receipts = deepcopy(rows)
        require(self.immutable() == self.original_binding, 'Immutable binding changed')
        progress = self.query('SELECT * FROM acore_characters.mod_archipelago_progress WHERE binding_id=%s', (self.binding,))
        require(len(progress) == 1 and progress[0]['cap_items'] == (self.cap - 10) // 10,
                'Native cap receipt differs')
        result = dict(character=row, spells=spells, lastFreshNativeSpellSet=native,
                      receipts=rows, progress=progress,
                      binding=self.immutable(), label=LABEL)
        self.save(label, result)
        emit('matrix_saved_gate', guid=self.guid, phase=label, level=self.level,
             ranks=self.case['chain']['ranks'], permitted=permitted, label=LABEL)
        return result

    def execute(self):
        from bridge.v2 import Store
        self.deadline_check()
        catalog = Catalog()
        control = self.reuse_control()
        self.seed = 'fabricated-class-matrix-' + secrets.token_hex(16)
        raw = class_manifest(catalog, self.case['profile'], self.seed)
        self.save('manifest', raw)
        with self.login(self.account) as (player, _):
            self.save('initial', dict(guid=self.guid, spells=sorted(self.baseline),
                                     login_sequence=self.login_sequence, label=LABEL))
        fresh = self.offline(self.guid)
        fixture_guard(fresh, account_id=self.account_row(self.account)['id'], name=self.names[self.guid],
                      profile=self.case['profile'], known=self.known,
                      bindings=self.query('SELECT id FROM acore_characters.mod_archipelago_binding WHERE character_guid=%s', (self.guid,)))
        self.save('fresh-offline', dict(character=fresh,
                  spells=self.query('SELECT * FROM acore_characters.character_spell WHERE guid=%s ORDER BY spell',
                                    (self.guid,)), label=LABEL))
        self.deadline_check()
        self.store = Store(dict(host='127.0.0.1', port=13317, user='root',
                                database='acore_characters'), self.guid, catalog)
        try:
            self.binding = self.store.bind(self.seed, 0, 1, raw)
            self.store.status('disconnected')
            self.original_binding = self.immutable()
            require(len(self.original_binding) == 1, 'Missing binding')
            self.state('bound', permitted=False)
            with self.login('TEST', guid=control) as (gm, _):
                with self.login(self.account, guid=self.guid) as (player, _):
                    if self.case['profile']['class_id'] == 8:
                        require(168 in player.spells, 'Starting Frost Armor absent; no GM fallback')
                        player.casts.clear()
                        player.auras.clear()
                        player.send(0x12E, struct.pack('<BIBI', 1, 168, 0, 0))
                        player.stay(3)
                        require((self.guid, self.guid, 1, 168) in player.casts
                                and not any(f[:2] == (1, 168) for f in player.failures)
                                and any(g == self.guid and 168 in spells for g, spells in player.auras),
                                'Native Frost Armor SPELL_GO/aura missing')
                        emit('native_baseline_self_cast', guid=self.guid, spell=168, label=LABEL)
                    for spell in self.case['chain']['ranks']:
                        self.command(gm, '.learn ' + str(spell))
                self.state('locked', permitted=False)
                with self.login(self.account, guid=self.guid) as (player, _):
                    self.queue(player, gm, [self.case['chain']['ap_id']])
                    for spell in self.case['chain']['ranks']:
                        self.command(gm, '.learn ' + str(spell))
                self.state('early-permission', permitted=True)
                with self.login(self.account, guid=self.guid):
                    self.command(gm, '.levelup ' + self.names[self.guid] + ' 10', cap_probe=True)
                self.state('cap-bypass-denied', permitted=True)
                for target in sorted(set(self.case['checkpoints']) - {1}):
                    self.deadline_check()
                    with self.login(self.account, guid=self.guid) as (player, _):
                        while target > self.cap:
                            self.queue(player, gm, [919100001])
                            self.cap += 10
                        self.command(gm, '.levelup ' + self.names[self.guid] + ' ' + str(target - self.level))
                        self.level = target
                        player.stay(.5)
                        for spell in self.case['chain']['ranks']:
                            self.command(gm, '.learn ' + str(spell))
                    self.state('level-' + str(target), permitted=True)
                with self.login(self.account, guid=self.guid):
                    pass
                before = self.state('relog', permitted=True)
                require(self.store.receive(0, items(self.codes)), 'Identical replay rejected')
                with self.login(self.account, guid=self.guid):
                    pass
                after = self.state('replay', permitted=True)
                require(all(before[k] == after[k] for k in ('spells', 'receipts', 'progress', 'binding')),
                        'Replay changed saved AP state')
        finally:
            self.store.close()


def protected_snapshot(runner, guids, binding_ids):
    """Freeze every preexisting character and AP row, not only originals 1..4."""
    result = {'account_access': sorted(runner.query('SELECT * FROM acore_auth.account_access'),
                                       key=lambda r: str(sorted(r.items())))}
    for table, column in (('characters', 'guid'), ('character_spell', 'guid'),
                          ('character_talent', 'guid'), ('character_aura', 'guid'),
                          ('character_inventory', 'guid'), ('character_skills', 'guid'),
                          ('item_instance', 'owner_guid')):
        rows = runner.query('SELECT * FROM acore_characters.' + table)
        rows = [r for r in rows if r[column] in guids]
        if table == 'characters':
            rows = [{k: v for k, v in r.items() if r['guid'] != 13 or
                     k in ('guid', 'name', 'account', 'race', 'class', 'level', 'online')} for r in rows]
        result[table] = sorted(rows, key=lambda r: str(sorted(r.items())))
    bindings = runner.query('SELECT * FROM acore_characters.mod_archipelago_binding')
    frozen = binding_ids
    result['bindings'] = sorted((r for r in bindings if r['id'] in frozen), key=lambda r: r['id'])
    for table in ('progress', 'reward', 'enabled_check', 'allowed_reward', 'check', 'boss_credit',
                  'ability', 'stock', 'purchase', 'authorized_item'):
        rows = runner.query('SELECT * FROM acore_characters.mod_archipelago_' + table)
        result['ap_' + table] = sorted((r for r in rows if r['binding_id'] in frozen),
                                      key=lambda r: str(sorted(r.items())))
    return result


def execute_matrix(db, prepared, output, deadline):
    runners = []
    observer = Runner(db, 'APV2B')
    require(observer.query('SELECT @@server_uuid AS uuid') == [dict(uuid=UUID)], 'Wrong private database')
    require(not observer.query('SELECT guid FROM acore_characters.characters WHERE online<>0')
            and not observer.query('SELECT id FROM acore_auth.account WHERE online<>0'), 'All fixtures must be offline')
    snapshots = {}
    for account in ACCOUNTS:
        row = observer.account_row(account)
        guard_account(row, account)
        private = observer.query('SELECT email,reg_mail,salt,verifier FROM acore_auth.account WHERE id=%s', (row['id'],))
        require(len(private) == 1, 'Missing private marked credentials')
        check_account(private[0], account, 'test-only')
        count = observer.query('SELECT COUNT(*) AS n FROM acore_characters.characters WHERE account=%s', (row['id'],))[0]['n']
        snapshots[account] = (row, count)
    budget = capacity_budget(prepared['cases'], snapshots)
    (output / 'capacity.json').write_text(json.dumps(dict(snapshots=snapshots, budget=budget), indent=2))
    guids = observer.before
    binding_ids = {r['id'] for r in observer.query('SELECT id FROM acore_characters.mod_archipelago_binding')}
    before = protected_snapshot(observer, guids, binding_ids)
    (output / 'before.json').write_text(json.dumps(before, default=str, indent=2))
    results = []
    try:
        for case, assignment in zip(prepared['cases'], budget['assignments']):
            require(time.monotonic() < deadline, f'{BUDGET_SECONDS}-second deadline before class')
            directory = output / ('class-' + str(case['profile']['class_id']))
            directory.mkdir()
            runner = MatrixRunner(db, assignment['account'], case, deadline=deadline, output=directory)
            runners.append(runner)
            result = dict(class_id=case['profile']['class_id'], status='FAIL', label=LABEL)
            results.append(result)
            try:
                runner.execute()
            except Exception as exc:
                result.update(error=str(exc), guid=runner.guid,
                              known_attempt_guids=sorted(runner.known - {13}))
                raise
            result.update(status='PASS native fixture gates', guid=runner.guid)
    finally:
        after = protected_snapshot(observer, guids, binding_ids)
        (output / 'after.json').write_text(json.dumps(after, default=str, indent=2))
        unchanged = before == after
        summary = dict(classes=results, protected_unchanged=unchanged,
                       owned_guids=[r.guid for r in runners], label=LABEL)
        (output / 'summary.json').write_text(json.dumps(summary, indent=2))
        require(unchanged, 'Protected preexisting history changed; no reset/recovery')
    return summary


def plan(catalog=None, spells=None, classes=None):
    classes = selected_classes(classes)
    catalog = catalog or Catalog()
    spells = spells or DBC(DBC_DIR / 'Spell.dbc')
    cases = []
    profiles = {p['class_id']: p for p in select_profiles(catalog)}
    for class_id in classes:
        profile = profiles[class_id]
        baseline = next(p[2] for p in PROFILES if p[0] == class_id)
        seed = 'fabricated-class-matrix-plan-class-' + str(profile['class_id'])
        raw = class_manifest(catalog, profile, seed)
        chain = select_chain(catalog, profile['class_id'], spells)
        require(baseline not in {s for a in catalog.abilities for s in a['ranks']},
                'Baseline became AP-selected')
        cases.append(dict(profile=profile, seed=seed, manifest=raw, chain=chain,
                          baseline_spell=baseline, baseline_dbc_level=spells.rows[baseline][39],
                          checkpoints=[1, chain['levels'][0] - 1, chain['levels'][0],
                                       chain['levels'][1] - 1, chain['levels'][1]]))
    return dict(status='PREPARED_NOT_EXECUTED', label=LABEL, network_without_run=False,
                build=str(artisan.BUILD), catalog_version=catalog.version, cases=cases,
                capacity=dict(accounts=ACCOUNTS, planned_creates=len(cases), max_per_account=10,
                              proposed_free_slots=dict(APV2B=2, APV2C=2, APV2D=2, APV2E=2, APV2F=1),
                              snapshot='NOT QUERIED; capacity_budget requires future marked role0 offline SELECT data',
                              TEST='zero creates; proved known-created GM13 only', excluded=['APV2A', 'originals 1..4']),
                baseline_cast=dict(class_id=8, spell=168, target='normal self Frost Armor at level 1',
                                   dbc_level=spells.rows[168][39], required='native CAST success plus aura; no GM learn'),
                talents=dict(level80_available=expected_points(80, 12), matrix_spending=0,
                             prior_warrior_spent=6, prior_warrior_rows=[130, 126]),
                dk=dict(status='EXCLUDED AP v1', class_id=6, live='NOT EXECUTED', normal_start_level=55,
                        gates=['reject Catalog profile and Store binding', 'no APWorld class option',
                               'unbound core start remains level 55, no GM level or AP rewards'],
                        future_account='APV2F level77 may qualify; eligibility/capacity NOT verified',
                        separate_case='only after explicit safety/capacity release; source-only is not creation proof'),
                budget=dict(estimated_minutes=[16, 20] if classes == [9, 11] else [30, 60],
                            hard_stop_seconds=1800 if classes == [9, 11] else BUDGET_SECONDS,
                            checkpoints='before each class and phase; no retry or second creation; preserve partials'),
                missing=['native execution', 'baseline rotation/combat viability for nine classes',
                         'real GUI/full gameplay', 'explicit parent release'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='requires explicit matching parent release')
    parser.add_argument('--classes', type=int, nargs='+', help='legal class IDs; default all nine')
    args = parser.parse_args(argv)
    classes = selected_classes(args.classes)
    if not args.run:
        print(json.dumps(plan(classes=classes), indent=2))
        return 0
    deadline = time.monotonic() + (1800 if classes == [9, 11] else BUDGET_SECONDS)
    # No network, credentials or DB access until the matrix-specific release is present.
    require((OUTPUT / 'release.json').is_file(), 'Explicit matrix parent release required')
    release = json.loads((OUTPUT / 'release.json').read_text())
    require(release.get('owned_release') is True and release.get('mail_lifetime_fixed') is True,
            'Explicit matrix parent release required')
    require(not (OUTPUT / 'attempt.json').exists(),
            'Existing matrix attempt preserved; parent must review a new exclusive namespace')
    authorize_selection(release, classes)
    from verify_crash_runtime import no_other_runners
    no_other_runners()  # Read-only exclusion check, never crash/restart helpers.
    evidence = released_evidence()
    prepared = plan(classes=classes)
    require(os.environ.get('WOWPILAGO_TEST_ACCOUNT_PASSWORD') == 'test-only'
            and os.environ.get('WOWPILAGO_DB_PASSWORD') == 'test-only', 'Private credentials required')
    output = OUTPUT / ('attempt-' + secrets.token_hex(12))
    with (OUTPUT / 'attempt.json').open('x') as handle:
        json.dump(dict(output=str(output), label=LABEL), handle)
    output.mkdir()
    (output / 'attempt.json').write_text(json.dumps(dict(evidence=evidence, plan=prepared), indent=2))
    import pymysql
    with (output / 'run.jsonl').open('x', buffering=1) as log, redirect_stdout(log):
        with pymysql.connect(host='127.0.0.1', port=13317, user='root', password='test-only',
                             autocommit=True, cursorclass=pymysql.cursors.DictCursor,
                             connect_timeout=5, read_timeout=15, write_timeout=15) as db:
            try:
                execute_matrix(db, prepared, output, deadline)
            except Exception as exc:
                emit('matrix_aborted', error=str(exc), label=LABEL)
                raise
    return 0


if __name__ == '__main__':
    sys.exit(main())
