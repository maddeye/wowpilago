#!/usr/bin/env python3
"""Validate curated rewards; --rebuild and --live use SELECT-only world/DBC sources."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'apworld/wowpilago/data'
DBC = ROOT.parent / 'wow-test/data/client-data/dbc'
# Canonical policy lives in JSON so offline validation needs no AP imports.
CLASS_ROLES = json.loads((DATA / 'gear.json').read_text())['class_roles']
CLASSES = (1, 2, 3, 4, 5, 7, 8, 9, 11)
# Item subclass -> WoW skill line, including proficiencies trainable later.
WEAPON_SKILLS = {0: 44, 1: 172, 2: 45, 3: 46, 4: 54, 5: 160,
                 6: 229, 7: 43, 8: 55, 10: 136, 13: 473, 15: 173,
                 16: 176, 18: 226, 19: 228}
ARMOR_SKILLS = {1: 415, 2: 414, 3: 413, 4: 293, 6: 433}
# Offline audit snapshot of SkillRaceClassInfo.dbc. --live checks it again.
SKILL_CLASSES = {
    44: (1, 2, 3, 4, 7), 172: (1, 2, 3, 7), 45: (1, 3, 4),
    46: (1, 3, 4), 54: (1, 2, 4, 5, 7, 11), 160: (1, 2, 7, 11),
    229: (1, 2, 3, 11), 43: (1, 2, 3, 4, 8, 9), 55: (1, 2, 3),
    136: (1, 3, 5, 7, 8, 9, 11), 473: (1, 3, 4, 7, 11),
    173: (1, 3, 4, 5, 7, 8, 9, 11), 176: (1, 3, 4), 226: (1, 3, 4),
    228: (5, 8, 9), 415: CLASSES, 414: (1, 2, 3, 4, 7, 11),
    413: (1, 2, 3, 7), 293: (1, 2), 433: (1, 2, 7),
}
LEGENDS = (19019, 17182, 46017, 49623, 34334, 32837, 32838,
           22589, 22630, 22631, 22632)
CANDIDATES = {
    1: [100, 20252, 6552, 871, 20230, 1719, 5246, 1161],
    2: [642, 633, 1022, 1044, 6940, 1038, 10326, 19752],
    3: [781, 5384, 1499, 13809, 19801, 1543, 5116, 3045],
    4: [2983, 5277, 1856, 1766, 2094, 408, 1725, 31224],
    5: [586, 8122, 605, 6346, 9484, 32375, 1706, 2096],
    7: [556, 2484, 8143, 8177, 3738, 2894, 51514, 370],
    8: [1953, 122, 2139, 45438, 118, 130, 30449, 66],
    9: [5782, 5484, 6789, 29858, 698, 6229, 5697, 710],
    11: [1850, 5211, 22812, 29166, 20484, 2637, 5209, 5229],
}


def query(sql):
    """The only database entry point. Never accepts a write statement."""
    if not sql.lstrip().upper().startswith('SELECT ') or ';' in sql:
        raise ValueError('only a single SELECT is permitted')
    result = subprocess.run(
        ['docker', 'exec', 'wow-test-database-1', 'mysql', '-uroot',
         '-ptest-only', '--batch', '--raw', 'acore_world', '-e', sql],
        check=True, capture_output=True, text=True)
    return list(csv.DictReader(io.StringIO(result.stdout), delimiter='\t'))


class Dbc:
    def __init__(self, path):
        data = Path(path).read_bytes()
        magic, count, fields, size, strings = struct.unpack_from('<4s4I', data)
        if magic != b'WDBC' or size != fields * 4 or len(data) != 20 + count * size + strings:
            raise ValueError(f'invalid DBC: {path}')
        self.rows = [struct.unpack_from(f'<{fields}I', data, 20 + i * size)
                     for i in range(count)]
        self.by_id = {row[0]: row for row in self.rows}
        self.strings = data[20 + count * size:]

    def text(self, offset):
        return self.strings[offset:self.strings.index(b'\0', offset)].decode('utf-8')


def sources(dbc_dir):
    return {name: Dbc(dbc_dir / (name + '.dbc')) for name in
            ('ItemSet', 'Spell', 'Talent', 'SkillRaceClassInfo', 'SkillLineAbility', 'Map')}


def compatibility(row, dbc):
    skill = (WEAPON_SKILLS if row['class'] == 2 else ARMOR_SKILLS).get(row['subclass'])
    mask = row['AllowableClass']
    result = []
    for cls in CLASSES:
        bit = 1 << (cls - 1)
        if not mask & bit:
            continue
        if row['class'] == 4 and row['subclass'] == 0:
            # Holdables, rings, necklaces, cloaks and trinkets have no armor skill.
            result.append(cls)
        elif skill and any(r[1] == skill and r[3] & bit for r in dbc['SkillRaceClassInfo'].rows):
            result.append(cls)
    return result


def expansion(row):
    if row['entry'] in (19019, 17182, 22589, 22630, 22631, 22632):
        return 0
    if row['entry'] in (34334, 32837, 32838):
        return 1
    if row['entry'] in (46017, 49623):
        return 2
    # Curated pools deliberately avoid recycled low IDs and pre-expansion rewards.
    return 0 if row['entry'] < 23000 else 1 if row['entry'] < 36000 else 2


def price(row):
    if row['Quality'] == 5:
        return 0
    if row['Quality'] in (2, 3):
        return row['Quality'] - 1
    exp = expansion(row)
    if row['class'] == 2:
        return 6 + exp
    return 3 + exp


def roles(row, dbc=None):
    if '_roles' in row:
        return row['_roles']
    stats = {row[f'stat_type{i}'] for i in range(1, 11) if row[f'stat_value{i}'] > 0}
    result = set()
    neutral = bool(stats & {1, 7} or any(row.get(s + '_res', 0) for s in
                   ('holy', 'fire', 'nature', 'frost', 'shadow', 'arcane')))

    def spell_roles(spell_id, seen):
        nonlocal neutral
        if not dbc or spell_id in seen or spell_id not in dbc['Spell'].by_id:
            return
        spell = dbc['Spell'].by_id[spell_id]
        for n in range(3):
            aura, misc, points = spell[95 + n], spell[110 + n], spell[80 + n]
            # DBC int32 fields are read as uint32. Negative debuffs are not gear bonuses.
            if points >= 0x80000000:
                continue
            if aura == 29:  # MOD_STAT: strength, agility, stamina, intellect, spirit.
                if misc < 5:
                    stats.add((4, 3, 7, 5, 6)[misc])
            elif aura == 13 and misc & 126:
                result.add('caster')
            elif aura in (135, 136):
                result.add('healer')
            elif aura in (99, 166):
                result.add('melee')
            elif aura in (124, 167):
                result.add('ranged')
            elif aura in (47, 49, 51):
                result.add('tank')
            elif aura == 189 and misc & 0x1E:  # Defense/dodge/parry/block ratings.
                result.add('tank')
            elif aura == 85 and misc == 0:  # Mana regeneration also appears on Hunter gear.
                stats.add(43)
            elif aura in (22, 34, 133, 250):  # Resistance or increased health.
                neutral = True
            if spell[116 + n]:
                spell_roles(spell[116 + n], seen | {spell_id})

    for n in range(1, 6):
        # On-hit weapon spells often debuff the enemy, not the wielder.
        if row.get(f'spelltrigger_{n}') in (0, 1):
            spell_roles(row.get(f'spellid_{n}', 0), set())
    if stats & {3, 38, 44}:
        result.update(('melee', 'ranged'))
    if stats & {4, 16, 19, 28, 37}:
        result.add('melee')
    if stats & {17, 20, 29, 39}:
        result.add('ranged')
    if stats & {12, 13, 14, 15, 48} or (row['class'] == 4 and row['subclass'] == 6):
        result.add('tank')
    if stats & {18, 42, 47}:
        result.add('caster')
    if 41 in stats:
        result.add('healer')
    if stats & {21, 30, 45}:
        result.update(('caster', 'healer'))
    # Intellect on Hunter, enhancement or feral gear does not make it caster gear.
    if stats & {5, 6, 43} and not result & {'melee', 'ranged'}:
        result.update(('caster', 'healer'))
    if row['class'] == 4 and row['subclass'] == 2 and stats & {3, 4} and row['AllowableClass'] & 1024:
        result.add('tank')
    if row['class'] == 2 and row['subclass'] in (2, 3, 16, 18):
        result.add('ranged')
    if row['class'] == 2 and row['subclass'] == 19:
        result.add('caster')
    if not result and row['class'] == 2:
        result.add('melee')  # Actual melee damage, not invented spell stats.
    if not result and neutral:
        result.update(role for values in CLASS_ROLES.values() for role in values)
    return sorted(result)


def item_rows():
    fields = ['entry', 'name', 'Quality', 'class', 'subclass', 'InventoryType',
              'AllowableClass', 'RequiredSkill', 'RequiredSkillRank', 'RequiredLevel',
              'ItemLevel', 'itemset', 'requiredspell', 'AllowableRace',
              'RequiredReputationFaction', 'RequiredReputationRank', 'Flags', 'FlagsExtra']
    fields += [f'{s}{i}' for i in range(1, 11) for s in ('stat_type', 'stat_value')]
    fields += [f'{s}_{i}' for i in range(1, 6) for s in ('spellid', 'spelltrigger')]
    fields += [s + '_res' for s in ('holy', 'fire', 'nature', 'frost', 'shadow', 'arcane')]
    fields += ['RandomProperty', 'RandomSuffix']
    rows = query('SELECT ' + ','.join('`' + f + '`' for f in fields) +
                 ' FROM item_template WHERE Quality BETWEEN 2 AND 5 AND class IN (2,4) AND InventoryType > 0 ORDER BY entry')
    return {int(r['entry']): {k: v if k == 'name' else int(v) for k, v in r.items()} for r in rows}


def make_item(row, dbc):
    return dict(wow_id=row['entry'], name=row['name'], quality=row['Quality'],
                expansion=expansion(row), inventory_type=row['InventoryType'],
                item_class=row['class'], item_subclass=row['subclass'],
                allowable_classes=compatibility(row, dbc), required_skill=row['RequiredSkill'],
                required_skill_rank=row['RequiredSkillRank'], required_level=row['RequiredLevel'],
                item_level=row['ItemLevel'], set_id=row['itemset'], price=price(row), roles=roles(row))


def loot_expansions(dbc):
    refs = {}
    for r in query('SELECT Entry,Item,Reference FROM reference_loot_template'):
        refs.setdefault(int(r['Entry']), []).append((int(r['Item']), int(r['Reference'])))

    def contents(ref, visited):
        if ref in visited:
            return set()
        result = set()
        for item, child in refs.get(ref, []):
            if item:
                result.add(item)
            if child:
                result.update(contents(child, visited | {ref}))
        return result

    expanded = {ref: contents(ref, set()) for ref in refs}
    evidence = {}
    for r in query('SELECT DISTINCT l.Item,l.Reference,c.map FROM creature_loot_template l '
                   'JOIN creature_template t ON t.lootid=l.Entry JOIN creature c ON c.id=t.entry'):
        map_id = int(r['map'])
        if map_id not in dbc['Map'].by_id:
            continue
        exp = dbc['Map'].by_id[map_id][63]
        for item in {int(r['Item'])} | expanded.get(int(r['Reference']), set()):
            if item:
                evidence.setdefault(item, set()).add(exp)
    return evidence


def curate_gear(rows, dbc, evidence):
    # Tier 1, tier 2, tier 4, tier 6, tier 7. Full DBC memberships, not guessed counts.
    set_ids = {
        1: [209, 218, 654, 655, 672, 673, 787, 788],
        2: [208, 217, 624, 625, 626, 679, 680, 681, 789, 790, 791],
        3: [206, 215, 651, 669, 794], 4: [204, 213, 621, 668, 801],
        5: [202, 211, 663, 664, 674, 675, 804, 805],
        7: [207, 216, 631, 632, 633, 682, 683, 684, 795, 796, 797],
        8: [201, 210, 648, 671, 803], 9: [203, 212, 645, 670, 802],
        11: [205, 214, 638, 639, 640, 676, 677, 678, 798, 799, 800],
    }
    for row in rows.values():
        row['_roles'] = roles(row, dbc)
    selected = set()
    sets = []
    for cls, ids in set_ids.items():
        for sid in ids:
            record = dbc['ItemSet'].by_id[sid]
            pieces = [i for i in record[18:35] if i]
            if sid >= 787:
                # Tier-7 DBC item arrays contain unused 437xx copies with wrong DB set IDs.
                pieces = [i for i, r in rows.items() if r['itemset'] == sid and i < 40000]
            if not pieces or any(i not in rows or cls not in compatibility(rows[i], dbc) for i in pieces):
                raise ValueError(f'set {sid} is not complete/compatible for class {cls}')
            selected.update(pieces)
            sets.append(dict(wow_id=sid, name=dbc['ItemSet'].text(record[1]),
                             class_ids=[cls], pieces=pieces, expansion=expansion(rows[pieces[0]])))
    # Two alternatives per facet keep 120-entry stock fillable even when featured rolls are zero.
    for cls in CLASSES:
        for exp in range(3):
            pool = [r for r in rows.values() if r['Quality'] in (2, 3, 4)
                    and not r['itemset'] and cls in compatibility(r, dbc)
                    and not r['RandomProperty'] and not r['RandomSuffix']
                    and expansion(r) == exp and exp in evidence.get(r['entry'], set()) and not r['requiredspell']
                    and r['RequiredSkill'] == 0 and r['AllowableRace'] in (-1, 0, 2147483647)
                    and not r['RequiredReputationFaction'] and not r['FlagsExtra'] & 3
                    and 'test' not in r['name'].lower() and 'deprecated' not in r['name'].lower()
                    and ((exp == 0 and 20 <= r['RequiredLevel'] <= 60 and r['ItemLevel'] <= 92)
                         or (exp == 1 and 58 <= r['RequiredLevel'] <= 70 and 80 <= r['ItemLevel'] <= 164)
                         or (exp == 2 and 68 <= r['RequiredLevel'] <= 80 and r['ItemLevel'] >= 130))]
            for quality in (2, 3, 4):
                for slot in (1, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 21, 22, 23, 25, 26):
                    for role in CLASS_ROLES[str(cls)]:
                        candidates = [r for r in pool if r['Quality'] == quality and r['InventoryType'] == slot and role in roles(r)]
                        selected.update(r['entry'] for r in sorted(
                            candidates, key=lambda r: (-r['ItemLevel'], r['entry']))[:2])
    selected.update(LEGENDS)
    sets.append(dict(wow_id=699, name='The Twin Blades of Azzinoth', class_ids=[1, 4],
                     pieces=[32838, 32837], expansion=1))
    return dict(schema_version=2, class_roles=CLASS_ROLES,
                items=[make_item(rows[i], dbc) for i in sorted(selected)], sets=sets)


def trainer_rows():
    return [{k: int(v) for k, v in r.items()} for r in query(
        'SELECT ID,SpellID,ReqLevel,ReqSpell,ReqSkillLine,ReqSkillRank FROM npc_trainer')]


def curate_abilities(dbc, trainers):
    talent_spells = {spell for row in dbc['Talent'].rows for spell in row[4:9] if spell}
    ranks = query('SELECT first_spell_id,spell_id,`rank` FROM spell_ranks ORDER BY first_spell_id,`rank`')
    chains = {}
    for row in ranks:
        chains.setdefault(int(row['first_spell_id']), []).append(int(row['spell_id']))
    result = []
    for cls, spells in CANDIDATES.items():
        for base in spells:
            chain = chains.get(base, [base])
            if any(int(r['spell_id']) == base and int(r['first_spell_id']) != base for r in ranks):
                raise ValueError(f'{base}: not the first rank')
            if talent_spells.intersection(chain):
                raise ValueError(f'talent spell {base}')
            record = dbc['Spell'].by_id[base]
            bit = 1 << (cls - 1)
            associations = dbc['SkillLineAbility'].rows
            if not any(r[2] == base and (r[4] & bit or
                       (r[4] == 0 and any(s[1] == r[1] and s[4] & bit for s in associations)))
                       for r in associations):
                raise ValueError(f'{base}: no class skill-line association for {cls}')
            requirements = []
            for spell in chain:
                entries = [r for r in trainers if r['SpellID'] == spell]
                if not entries:
                    raise ValueError(f'no trainer for {spell}')
                entry = min(entries, key=lambda r: (r['ReqLevel'], r['ID']))
                level = max(entry['ReqLevel'], dbc['Spell'].by_id[spell][39])
                requirements.append(dict(kind='rank_eligibility', spell_id=spell, min_level=level,
                                         required_spell=entry['ReqSpell'], required_skill=entry['ReqSkillLine'],
                                         required_skill_rank=entry['ReqSkillRank'],
                                         totem_items=[i for i in dbc['Spell'].by_id[spell][50:52] if i],
                                         totem_categories=[i for i in dbc['Spell'].by_id[spell][222:224] if i],
                                         reagents=[dict(wow_id=i, count=n) for i, n in
                                                   zip(dbc['Spell'].by_id[spell][52:60], dbc['Spell'].by_id[spell][60:68])
                                                   if 0 < i < 0xFFFFFFFF and n]))
            # DBC stance mask bits are ShapeshiftForm IDs minus one. Baseline, never AP gates.
            if record[12]:
                requirements.append(dict(kind='baseline_form_mask', mask=record[12]))
            if record[68] != 0xFFFFFFFF:
                requirements.append(dict(kind='equipped_item', item_class=record[68],
                                         subclass_mask=record[69], inventory_mask=record[70]))
            baseline = {100: [2457], 20252: [2458], 6552: [2458], 871: [71],
                        20230: [2457], 1719: [2458], 1850: [768],
                        5211: [5487], 5209: [5487], 5229: [5487]}
            if base in baseline:
                requirements.append(dict(kind='baseline_spells', spell_ids=baseline[base]))
            result.append(dict(class_id=cls, base_spell=base, name=dbc['Spell'].text(record[136]),
                               min_level=requirements[0]['min_level'], ranks=chain,
                               ap_id=919101000 + base, prerequisites=requirements))
    return dict(schema_version=2, abilities=result)


def validate(gear, abilities):
    errors = []
    def require(ok, message):
        if not ok:
            errors.append(message)
    require(gear.get('schema_version') == abilities.get('schema_version') == 2, 'schema version must be 2')
    require(gear.get('class_roles') == CLASS_ROLES, 'class role policy differs from canonical JSON')
    require(set(CLASS_ROLES) == set(map(str, CLASSES)) and all(
        values and set(values) <= {'caster', 'healer', 'melee', 'tank', 'ranged'}
        for values in CLASS_ROLES.values()), 'invalid class role policy')
    items = gear['items']
    ids = {r['wow_id']: r for r in items}
    require(len(ids) == len(items), 'duplicate item ID')
    set_ids = {s['wow_id'] for s in gear['sets']}
    require(len(set_ids) == len(gear['sets']), 'duplicate set ID')
    fields = set('wow_id name quality expansion inventory_type item_class item_subclass allowable_classes required_skill required_skill_rank required_level item_level set_id price roles'.split())
    for item in items:
        label = str(item['wow_id'])
        require(set(item) == fields, f'{label}: item fields differ from contract')
        require(item['quality'] in (2, 3, 4, 5), f'{label}: invalid quality')
        require(item['expansion'] in (0, 1, 2), f'{label}: invalid expansion')
        require(bool(item['allowable_classes']) and set(item['allowable_classes']) <= set(CLASSES), f'{label}: invalid classes')
        skill = (WEAPON_SKILLS if item['item_class'] == 2 else ARMOR_SKILLS).get(item['item_subclass'])
        normal = CLASSES if item['item_class'] == 4 and item['item_subclass'] == 0 else SKILL_CLASSES.get(skill, ())
        require(set(item['allowable_classes']) <= set(normal), f'{label}: incompatible proficiency')
        require(bool(item['roles']) and set(item['roles']) <= {'caster', 'healer', 'melee', 'tank', 'ranged'}, f'{label}: invalid roles')
        expected = 0 if item['quality'] == 5 else item['quality'] - 1 if item['quality'] < 4 else (6 if item['item_class'] == 2 else 3) + item['expansion']
        require(item['price'] == expected, f'{label}: incorrect price')
        require(not item['set_id'] or item['set_id'] in set_ids, f'{label}: orphan set membership')
    for s in gear['sets']:
        require(len(s['pieces']) == len(set(s['pieces'])) and bool(s['pieces']), f"{s['wow_id']}: duplicate/empty pieces")
        for piece in s['pieces']:
            require(piece in ids, f"{s['wow_id']}: missing piece {piece}")
            if piece in ids:
                require(ids[piece]['set_id'] == s['wow_id'], f'{piece}: wrong set relationship')
                require(set(s['class_ids']) <= set(ids[piece]['allowable_classes']), f'{piece}: incompatible set class')
                require(ids[piece]['expansion'] == s['expansion'], f'{piece}: wrong set expansion')
    seen_spells = set()
    require(set(a['class_id'] for a in abilities['abilities']) == set(CLASSES), 'ability classes must exclude DK and cover all nine classes')
    for a in abilities['abilities']:
        base = a['base_spell']
        require(a['ap_id'] == 919101000 + base, f'{base}: incorrect AP ID')
        require(bool(a['ranks']) and a['ranks'][0] == base, f'{base}: invalid base rank')
        require(not seen_spells.intersection(a['ranks']) and len(a['ranks']) == len(set(a['ranks'])), f'{base}: overlapping ranks')
        seen_spells.update(a['ranks'])
        reqs = [p for p in a['prerequisites'] if p['kind'] == 'rank_eligibility']
        require([p['spell_id'] for p in reqs] == a['ranks'], f'{base}: missing rank eligibility')
        require(bool(reqs) and a['min_level'] == reqs[0]['min_level'], f'{base}: wrong minimum level')
        require(all(1 <= p['min_level'] <= 80 for p in reqs), f'{base}: invalid rank level')
        require([p['min_level'] for p in reqs] == sorted(p['min_level'] for p in reqs), f'{base}: rank levels decrease')
    for cls in CLASSES:
        shop = [i for i in items if cls in i['allowable_classes'] and i['quality'] != 5
                and set(i['roles']) & set(CLASS_ROLES[str(cls)])]
        require(len(shop) >= 120, f'class {cls}: fewer than 120 stock candidates')
        require({2, 3, 4} <= {i['quality'] for i in shop}, f'class {cls}: missing quality')
        featured_sizes = [len(s['pieces']) for s in gear['sets'] if cls in s['class_ids']
                          and all(piece in ids and ids[piece]['quality'] != 5 for piece in s['pieces'])]
        require(len(featured_sizes) >= 4, f'class {cls}: fewer than four sets')
        require(len(shop) >= 120 + sum(sorted(featured_sizes)[-4:]),
                f'class {cls}: insufficient candidates for 120 stock with four zero-roll featured sets')
        require(sum(cls in i['allowable_classes'] and i['quality'] == 5 for i in items) >= 2, f'class {cls}: fewer than two compatible legends')
        require(sum(a['class_id'] == cls for a in abilities['abilities']) == 8, f'class {cls}: expected eight abilities')
        for exp in range(3):
            pool = [i for i in shop if i['expansion'] == exp]
            # Wrath loot greens use unknown random affixes; do not invent their stats.
            require({3, 4} <= {i['quality'] for i in pool}, f'class {cls}, expansion {exp}: missing quality')
            require({11, 12} <= {i['inventory_type'] for i in pool}, f'class {cls}, expansion {exp}: missing rings/trinkets')
            require(any(i['item_class'] == 2 for i in pool), f'class {cls}, expansion {exp}: no weapons')
        require(set(CLASS_ROLES[str(cls)]) <= {r for i in shop if len(i['roles']) < 5
                                              for r in i['roles']}, f'class {cls}: missing viable role coverage')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='compare every field to live SELECT-only sources')
    parser.add_argument('--rebuild', action='store_true', help='rerun bounded curation into the two owned catalogs')
    parser.add_argument('--dbc-dir', type=Path, default=DBC)
    args = parser.parse_args()
    if args.rebuild or args.live:
        dbc = sources(args.dbc_dir)
        expected_gear = curate_gear(item_rows(), dbc, loot_expansions(dbc))
        expected_abilities = curate_abilities(dbc, trainer_rows())
    if args.rebuild:
        DATA.mkdir(parents=True, exist_ok=True)
        for name, content in [('gear', expected_gear), ('abilities', expected_abilities)]:
            (DATA / (name + '.json')).write_text(json.dumps(content, indent=2) + '\n')
    gear = json.loads((DATA / 'gear.json').read_text())
    abilities = json.loads((DATA / 'abilities.json').read_text())
    errors = validate(gear, abilities)
    if args.live:
        if gear != expected_gear:
            errors.append('gear differs from live source curation')
        if abilities != expected_abilities:
            errors.append('abilities differ from live source curation')
        for skill, classes in SKILL_CLASSES.items():
            actual = tuple(c for c in CLASSES if any(r[1] == skill and r[3] & (1 << (c - 1)) for r in dbc['SkillRaceClassInfo'].rows))
            if actual != classes:
                errors.append(f'skill {skill}: offline compatibility snapshot differs from DBC')
        for name in ('ItemSet', 'Spell', 'Talent', 'SkillRaceClassInfo', 'SkillLineAbility', 'Map'):
            print(name + '.dbc sha256 ' + hashlib.sha256((args.dbc_dir / (name + '.dbc')).read_bytes()).hexdigest())
    for cls in CLASSES:
        legal = [i for i in gear['items'] if cls in i['allowable_classes'] and i['quality'] != 5]
        shop = [i for i in legal if set(i['roles']) & set(CLASS_ROLES[str(cls)])]
        vendor_ids = {i['wow_id'] for i in shop}
        featured = sum(cls in s['class_ids'] and set(s['pieces']) <= vendor_ids for s in gear['sets'])
        legends = sum(cls in i['allowable_classes'] and i['quality'] == 5 for i in gear['items'])
        print(f'class {cls}: legal={len(legal)}, shop={len(shop)}, legendary={legends}, featured_sets={featured}')
    print(f'{len(gear["items"])} items, {len(gear["sets"])} sets, {len(abilities["abilities"])} abilities')
    if errors:
        raise SystemExit('\n'.join(errors))
    print('Reward catalog validation passed')


if __name__ == '__main__':
    main()
