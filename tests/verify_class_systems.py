"""Bounded GM0 native class checks with fabricated AP ingress, not release proof.

No arguments is an offline plan. Runtime creates exactly one player and one GM.
Existing helpers and production sources are imported/read, never changed.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import struct
import sys
import time

from verify_runtime import Runner, require, guard_account, manifest_fixture, selection_packet, LABEL
from bridge.catalog import Catalog
from tools.validate_checks import DBC

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / '.local/v2-build/20261019T150600.624050Z/source'
DBC_DIR = ROOT.parent / 'wow-test/data/client-data/dbc'
ACCOUNTS = ('APV2C', 'APV2D', 'APV2E', 'APV2F')
RIDING = (33388, 33391, 34090, 34091, 54197)
PLAN = {'label': LABEL, 'accounts': ACCOUNTS, 'creates': 'one GM0 human warrior and one fresh TEST GM3',
        'checks': ['forward-only caps and native quest XP bank/release',
                   'early/later talent unlock, native spend/tier gates and 71-point ceiling',
                   'riding permissions and 20/40/60/70/77 spell eligibility',
                   'Charge locked/base/rank/minimum-level gates, save/relogin/replay'],
        'excluded': ['real AP room', 'UI/travel/procs', 'bot enablement', 'SQL character changes']}


def emit(kind, **values):
    print(json.dumps({'event': kind, **values}, default=str, sort_keys=True), flush=True)


def expected_points(level, unlocks):
    require(type(level) is int and 1 <= level <= 80, 'Invalid level')
    require(type(unlocks) is int and 0 <= unlocks <= 12, 'Invalid unlocks')
    reserved = min(12, max(0, (level - 10) // 5))
    return max(0, level - 9) - reserved + min(unlocks, reserved)


def items(codes):
    return [{'class': 'NetworkItem', 'item': code, 'location': -1, 'player': 0, 'flags': 0}
            for code in codes]


def talent_packet(talent, rank):
    require(type(talent) is int and talent > 0 and type(rank) is int and 0 <= rank < 5,
            'Invalid talent action')
    return struct.pack('<II', talent, rank)


def fixture_guard(account, row, count, *, setup=False):
    require(account == 'TEST' if setup else account in ACCOUNTS, 'Protected account')
    guard_account(row, account, setup=setup)
    require(count < 10, 'Account has no free character slot')


def source_evidence():
    """Read actual DBCs and the clean pinned module, rather than guessing IDs."""
    hashes = {}
    for name in ('APProgression.h', 'APProgression.cpp', 'APCatalog.h'):
        current = (ROOT / 'src' / name).read_bytes()
        pinned = (SOURCE / 'modules/mod-archipelago/src' / name).read_bytes()
        require(current == pinned, 'Pinned module differs: ' + name)
        hashes[name] = hashlib.sha256(pinned).hexdigest()
    talents, tabs = DBC(DBC_DIR / 'Talent.dbc'), DBC(DBC_DIR / 'TalentTab.dbc')
    require(talents.rows[130][2] == 0 and tabs.rows[talents.rows[130][1]][20] == 1
            and talents.rows[130][4:9] == (16462, 16463, 16464, 16465, 16466), 'Talent 130 changed')
    require(talents.rows[126][2] == 1 and talents.rows[126][13] == 0, 'Tier probe changed')
    spells = DBC(DBC_DIR / 'Spell.dbc')
    selected = {str(i): list(spells.rows[i]) for i in (*RIDING, 458, 23227, 63680, 63624, 100, 6178, 11578)}
    return {'source': str(SOURCE), 'module_sha256': hashes, 'dbc_talents': {
        str(i): list(talents.rows[i]) for i in (130, 126)}, 'dbc_spell_rows': selected,
        'quest_xp_80': list(DBC(DBC_DIR / 'QuestXP.dbc').rows[80])}


class ClassRunner(Runner):
    def __init__(self, db, account):
        require(account in ACCOUNTS, 'Only independent APV2C..F fixtures allowed')
        super().__init__(db, account)
        self.created_accounts = set()
        self.codes = []
        self.unlocks = 0
        self.spent = 0
        self.flags = 0
        self.cap = 10
        self.level = 1

    @contextmanager
    def login(self, account, *, guid=None):
        if guid is None:
            require(account not in self.created_accounts, 'Only one fresh character per account per run')
            count = self.query('SELECT COUNT(*) AS n FROM acore_characters.characters WHERE account=%s',
                               (self.account_row(account)['id'],))[0]['n']
            fixture_guard(account, self.account_row(account), count, setup=account == 'TEST')
            self.created_accounts.add(account)
        else:
            require(guid > 4 and account in (self.account, 'TEST'), 'Protected login')
        with super().login(account, guid=guid) as result:
            yield result

    def queue(self, *codes):
        require(codes, 'Empty ingress is not a test')
        require(self.store.receive(len(self.codes), items(codes)), 'Queue rejected')
        self.codes.extend(codes)
        emit('fixture_ingress', codes=codes, count=len(self.codes), label=LABEL)

    def wait_rewards(self, player):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            rows = self.query('SELECT ap_item,applied FROM acore_characters.mod_archipelago_reward '
                              'WHERE binding_id=%s ORDER BY item_index', (self.binding,))
            if len(rows) == len(self.codes) and all(r['applied'] for r in rows):
                require([r['ap_item'] for r in rows] == self.codes, 'Receipt identity mismatch')
                return
            player.stay(.25)
            self.gm.stay(.05)
        raise RuntimeError('Native receipt timeout')

    def command(self, command):
        self.gm.stay(.05)
        emit('gm_setup_command', command=command, messages=self.gm.command(command))

    def state(self, label):
        row = self.offline(self.guid)
        progress = self.query('SELECT * FROM acore_characters.mod_archipelago_progress WHERE binding_id=%s',
                              (self.binding,))[0]
        spells = self.query('SELECT spell,specMask FROM acore_characters.character_spell WHERE guid=%s ORDER BY spell', (self.guid,))
        talents = self.query('SELECT spell,specMask FROM acore_characters.character_talent WHERE guid=%s ORDER BY spell', (self.guid,))
        result = {'level': row['level'], 'xp': row['xp'], 'progress': progress,
                  'spells': spells, 'talents': talents}
        emit('saved_state', label=label, **result)
        require(row['level'] == self.level, 'Saved level differs at ' + label)
        require(progress['talent_unlocks'] == self.unlocks and progress['riding_flags'] == self.flags,
                'Saved class permissions differ')
        return result

    @contextmanager
    def phase(self, label):
        self.gm.stay(.05)
        with self.login(self.account, guid=self.guid) as (player, _):
            self.wait_rewards(player)
            # The native handler responds even to unknown talent 0, without spending.
            player.send(0x251, struct.pack('<II', 0, 0))
            player.stay(.3)
            yield player
            player.send(0x251, struct.pack('<II', 0, 0))
            player.stay(.3)
            require(player.talent_points == expected_points(self.level, self.unlocks) - self.spent,
                    'Native free talent points differ at ' + label)
            emit('talent_points', label=label, level=self.level, free=player.talent_points,
                 spent=self.spent, unlocks=self.unlocks)
        self.gm.stay(.05)
        self.last = self.state(label)

    def learn_talent(self, player, talent, rank, *, allowed):
        before = player.talent_points
        player.send(0x251, talent_packet(talent, rank))
        player.stay(.3)
        require(player.talent_points == before - int(allowed), 'Talent acceptance differs')
        self.spent += int(allowed)
        emit('talent_action', talent=talent, rank=rank, allowed=allowed, free=player.talent_points)

    def spell_check(self, present=(), absent=()):
        saved = {r['spell'] for r in self.last['spells']}
        require(set(present) <= saved and not set(absent) & saved, 'Saved spell eligibility differs')
        emit('spell_gate_pass', present=present, absent=absent, level=self.level)

    def advance(self, target):
        require(self.level < target <= self.cap, 'Refusing backward or above-cap setup')
        self.command('.levelup ' + self.names[self.guid] + ' ' + str(target - self.level))
        self.level = target

    def execute_classes(self):
        from bridge.v2 import Store
        emit('source_evidence', **source_evidence())
        smoke = (ROOT / '.local/native-runtime-smoke-third.log').read_text()
        require('"result": "PASS bounded native smoke"' in smoke, 'Third smoke not settled with PASS')
        emit('accounts_before', rows=self.query('SELECT a.id,a.username,a.online,COUNT(c.guid) AS characters '
             'FROM acore_auth.account a LEFT JOIN acore_characters.characters c ON c.account=a.id GROUP BY a.id'))
        # Check both before creating either. Never authenticate TEST while another session owns it.
        for account in (self.account, 'TEST'):
            row = self.account_row(account)
            require(row is not None, 'Missing fixture account')
            count = self.query('SELECT COUNT(*) AS n FROM acore_characters.characters WHERE account=%s', (row['id'],))[0]['n']
            fixture_guard(account, row, count, setup=account == 'TEST')
        emit('database_version', rows=self.query('SELECT * FROM acore_world.version'))
        catalog = Catalog()
        seed = 'fabricated-class-systems-' + secrets.token_hex(12)
        raw = manifest_fixture(catalog, seed)
        with self.login(self.account) as (_, self.guid):
            emit('fixture_created', guid=self.guid, name=self.names[self.guid], seed=seed, catalog=catalog.version)
        self.store = Store(dict(host='127.0.0.1', port=13317, user='root', database='acore_characters'), self.guid, catalog)
        try:
            self.binding = self.store.bind(seed, 0, 1, raw)
            self.store.status('disconnected')
            emit('fixture_bound', guid=self.guid, binding=self.binding, label=LABEL)
            with self.login('TEST') as (self.gm, gm_guid):
                emit('gm_fixture', guid=gm_guid, name=self.names[gm_guid])
                self.gm.send(0x13D, selection_packet(self.guid))
                self.queue(919100020)
                self.unlocks = 1
                with self.phase('early unlock at level 1'):
                    pass
                # Native XP path, fabricated GM quest setup, not legitimate quest completion.
                with self.phase('quest XP reaches initial cap and saturates bank') as player:
                    for verb in ('add', 'complete', 'reward'):
                        self.command('.quest ' + verb + ' 13108 ' + self.names[self.guid])
                    player.stay(1)
                    self.level = 10
                xp10 = self.query('SELECT Experience FROM acore_world.player_xp_for_level WHERE Level=10')[0]['Experience']
                require(self.last['progress']['banked_xp'] == xp10 // 2 and self.last['xp'] == 0,
                        'Quest XP did not reach cap and full bank')
                with self.phase('locked ability and early tier rejection') as player:
                    self.command('.learn 100')
                    self.command('.learn 6178')
                    self.learn_talent(player, 126, 0, allowed=False)
                    self.learn_talent(player, 130, 0, allowed=True)
                    self.command('.levelup ' + self.names[self.guid] + ' 1')
                self.spell_check(absent=(100, 6178))
                require(self.last['level'] == 10, 'Cap bypassed')
                self.queue(919100001, 919101100, 919100011)
                self.cap, self.flags = 20, 2
                with self.phase('cap release and base ability'):
                    pass
                require(self.last['xp'] == xp10 // 2 and self.last['progress']['banked_xp'] == 0, 'Exact bank release failed')
                self.spell_check(present=(100,), absent=(6178, 33388, 33391))
                # Move only forward. Every ten levels requires another native AP cap receipt.
                for target in (14, 15, 19, 20, 25, 26, 30, 39, 40, 45, 46, 50, 59, 60, 69, 70, 76, 77, 80):
                    if target > self.cap:
                        self.queue(919100001)
                        self.cap += 10
                    with self.phase('level ' + str(target)) as player:
                        self.advance(target)
                        player.send(0x251, struct.pack('<II', 0, 0))
                        player.stay(.3)
                        if target == 14:
                            for rank in range(1, 5):
                                self.learn_talent(player, 130, rank, allowed=True)
                        if target == 15:
                            self.learn_talent(player, 126, 0, allowed=True)
                        if target == 20:
                            self.command('.learn 33388')  # Missing apprentice flag, journeyman alone is insufficient.
                            self.command('.learn 33391')
                        if target == 25:
                            self.command('.learn 6178')
                        if target == 26:
                            self.command('.learn 6178')
                        if target == 45:
                            self.command('.learn 11578')
                        if target == 46:
                            self.command('.learn 11578')
                    if target == 20:
                        self.spell_check(absent=(33388, 33391))
                        self.queue(919100010, 919100012, 919100013, 919100014)
                        self.flags = 31
                        with self.phase('riding flags at 20'):
                            pass
                    if target == 25:
                        self.spell_check(absent=(6178,))
                    if target >= 26:
                        self.spell_check(present=(100, 6178))
                    if target == 45:
                        self.spell_check(absent=(11578,))
                    if target >= 46:
                        self.spell_check(present=(11578,))
                    if target >= 20:
                        present = [s for s, level in zip(RIDING, (20, 40, 60, 70, 77)) if target >= level]
                        absent = [s for s in RIDING if s not in present]
                        self.spell_check(present=present, absent=absent)
                require(expected_points(80, 1) == 60, 'Late release precondition differs')
                self.queue(*([919100020] * 11))
                self.unlocks = 12
                with self.phase('later release to 71 total points'):
                    pass
                require(expected_points(80, self.unlocks) == 71, 'Ceiling differs')
                saved = self.last
                require(self.store.receive(0, items(self.codes)), 'Identical ingress replay rejected')
                with self.phase('full relog and identical replay'):
                    pass
                require(saved == self.last, 'Replay/relog changed saved class state')
                emit('PASS', guid=self.guid, binding=self.binding, gm_guid=gm_guid, label=LABEL,
                     missing=['real UI/travel/procs', 'trainer respec and dual-spec switches',
                              'other classes including DK', 'real AP-room ingress/gameplay'])
        finally:
            self.store.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--account', choices=ACCOUNTS, default='APV2C')
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps(PLAN, indent=2))
        return 0
    require(os.environ.get('WOWPILAGO_TEST_ACCOUNT_PASSWORD') == 'test-only', 'Set fixture password environment')
    require(os.environ.get('WOWPILAGO_DB_PASSWORD') == 'test-only', 'Requires test-only DB')
    import pymysql
    with pymysql.connect(host='127.0.0.1', port=13317, user='root', password=os.environ['WOWPILAGO_DB_PASSWORD'],
                         autocommit=True, cursorclass=pymysql.cursors.DictCursor,
                         connect_timeout=5, read_timeout=15, write_timeout=15) as db:
        ClassRunner(db, args.account).execute_classes()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        emit('FAIL', error=str(exc), preserved='all fixtures, queues and history')
        sys.exit(1)
