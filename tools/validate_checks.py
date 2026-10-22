#!/usr/bin/env python3
"""Extract and revalidate the v2 curated check catalog using SELECT-only snapshots."""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
import re
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "apworld/wowpilago/data"
DEFAULT_SOURCE = ROOT.parent / "wow-test/azerothcore"
DEFAULT_DBC = ROOT.parent / "wow-test/data/client-data/dbc"
BASES = dict(quest=919500000, level=919600000, exploration=919700000,
             boss=919800000, dungeon=919900000, raid=920000000)
COUNTS = dict(quest=150, exploration=60, boss=48, dungeon=14, level=16, raid=12)
# Reviewed seeds, not arbitrary LIMIT results. Names and restrictions come from the DB.
QUEST_IDS = [
    317, 5541, 313, 315, 432, 412,
    47, 60, 62, 83, 85, 5545,
    488, 475, 2438, 919, 932, 489,
    9506, 9530, 9454, 10324, 9513, 9523,
    784, 791, 818, 786, 815, 825,
    5481, 5482, 367, 404, 365, 358,
    748, 745, 761, 11129, 743, 746,
    8463, 8472, 8475, 9035, 9062, 8480,
    # Eleven additions per physical starter zone. Preserve the six seeds above.
    179,170,183,3361,182,218,318,319,233,234,320,
    783,7,5261,33,15,18,3903,3904,6,21,2158,
    4641,788,789,4402,792,790,804,817,808,834,826,
    363,364,376,3901,3902,380,381,382,6395,375,426,
    458,456,457,459,916,4495,3519,3521,917,920,476,
    747,752,750,753,755,757,780,3376,766,833,754,
    8325,8326,8327,8346,8334,8336,8345,8335,8347,9704,9352,
    9279,9280,10302,9293,9799,9305,9314,9463,9512,9473,9505,
    # One faction-compatible quest per faction per later cap band.
    12,844,56,216,568,1387,2862,4124,5092,9443,9770,9777,11155,11167,
]
# area ID, conservative cap, faction. Exploration is zone entry, never full exploration.
ZONES = [
    (12,10,'alliance'), (1,10,'alliance'), (141,10,'alliance'), (3524,10,'alliance'),
    (1519,10,'alliance'), (1537,10,'alliance'), (1657,10,'alliance'), (3557,10,'alliance'),
    (14,10,'horde'), (85,10,'horde'), (215,10,'horde'), (3430,10,'horde'),
    (1637,10,'horde'), (1497,10,'horde'), (1638,10,'horde'), (3487,10,'horde'),
    (40,20,'any'), (38,20,'any'), (148,20,'any'), (3525,20,'any'),
    (17,20,'any'), (130,20,'any'), (3433,20,'any'), (44,20,'any'),
    (10,30,'any'), (331,30,'any'), (406,30,'any'), (11,30,'any'),
    (267,30,'any'), (36,30,'any'), (45,40,'any'), (33,40,'any'),
    (405,40,'any'), (400,40,'any'), (15,40,'any'), (3,40,'any'),
    (8,40,'any'), (357,50,'any'), (440,50,'any'), (47,50,'any'),
    (51,50,'any'), (4,60,'any'), (16,60,'any'), (28,60,'any'),
    (139,60,'any'), (490,60,'any'),
    (3483,60,'any'), (3521,70,'any'), (3519,70,'any'), (3518,70,'any'),
    (3522,70,'any'), (3523,70,'any'),
    (3537,70,'any'), (495,70,'any'), (65,80,'any'), (394,80,'any'),
    (66,80,'any'), (3711,80,'any'), (67,80,'any'), (210,80,'any'),
]
# Every listed creature must be credited on normal difficulty for a curated clear.
# map, cap, creature IDs. No heroic-only bosses or key/attunement-required instances.
DUNGEONS = [
    (543,70,[17306,17308,17537,17536]),
    (542,70,[17381,17380,17377]),
    (547,70,[17941,17991,17942]),
    (546,70,[17770,18105,17826,17882]),
    (557,70,[18341,18343,18344]),
    (575,80,[26668,26687,26693,26861]),
    (556,70,[18473,18472]),
    (554,70,[19219,19221,19220]),
    (43,30,[3669,3670,3671,3673,3653]),
    (558,70,[18371,18373]),
    (602,80,[28586,28587,28546,28923]),
    (576,80,[26731,26763,26794,26723]),
    (601,80,[28684,28921,29120]),
    (600,80,[26630,26631,27483,26632]),
]
BOSS_PREREQUISITES = {
    18373: [18371], 18473: [18472],
    26723: [26731,26763,26794],
    28921: [28684], 29120: [28921],
    28923: [28586,28587,28546],
    26861: [26668,26687,26693],
    19220: [19219,19221],
}
RAMPARTS = 'Outland/HellfireCitadel/HellfireRamparts/'
MOLTEN = 'EasternKingdoms/BlackrockMountain/MoltenCore/'
PINNACLE = 'Northrend/UtgardeKeep/UtgardePinnacle/'
# map, enum symbol, header, concrete summon/transform call, pre-transform spawn if any.
SCRIPTED = {
    17537: (543,'NPC_VAZRUDEN',RAMPARTS+'hellfire_ramparts.h',RAMPARTS+'boss_vazruden_the_herald.cpp',None),
    17536: (543,'NPC_NAZAN',RAMPARTS+'hellfire_ramparts.h',RAMPARTS+'boss_vazruden_the_herald.cpp',None),
    11502: (409,'NPC_RAGNAROS',MOLTEN+'molten_core.h',MOLTEN+'boss_majordomo_executus.cpp',None),
    26668: (575,'NPC_SVALA_SORROWGRAVE',PINNACLE+'utgarde_pinnacle.h',PINNACLE+'boss_svala.cpp',29281),
}
RAIDS = [(409,i) for i in [12118,11982,12259,12057,12264,12056,12098,11988,11502]] + [
    (249,10184), (565,19044), (544,17257)]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     default=str).encode()).hexdigest()


class DBC:
    def __init__(self, path):
        self.raw = Path(path).read_bytes()
        magic, count, fields, size, strings = struct.unpack_from('<4s4I', self.raw)
        if magic != b'WDBC' or size != fields * 4 or len(self.raw) != 20 + count * size + strings:
            raise ValueError(f"Invalid WDBC layout: {path}")
        self.rows = {}
        for index in range(count):
            row = struct.unpack_from(f'<{fields}I', self.raw, 20 + index * size)
            self.rows[row[0]] = row
        self.strings = self.raw[20 + count * size:]

    def text(self, offset):
        return self.strings[offset:self.strings.index(b'\0', offset)].decode('utf-8')

    @staticmethod
    def number(word):
        return struct.unpack('<f', struct.pack('<I', word))[0]


def read_sources(connection, dbc_dir, source_dir):
    """Only SELECT statements inside a read-only consistent transaction."""
    dbcs = {name: DBC(dbc_dir / f'{name}.dbc') for name in
            ['AreaTable','Map','WorldMapArea','ChrRaces','ChrClasses','FactionTemplate','Spell']}
    queries = {
        'version': 'SELECT * FROM version',
        'updates': 'SELECT name,hash,state FROM updates ORDER BY name',
        'profiles': 'SELECT * FROM playercreateinfo ORDER BY race,class',
        'quests': '''SELECT q.ID,q.LogTitle,q.QuestLevel,q.MinLevel,q.QuestSortID,
            q.AllowableRaces,q.Flags,q.QuestInfoID,q.StartItem,q.TimeAllowed,
            q.RequiredFactionId1,q.RequiredFactionId2,q.RewardNextQuest,
            a.ProvidedItemCount,a.AllowableClasses,a.PrevQuestID,a.NextQuestID,a.ExclusiveGroup,
            a.BreadcrumbForQuestId,a.SpecialFlags,a.RequiredSkillID,
            a.RequiredMinRepFaction,a.RequiredMaxRepFaction,a.MaxLevel
            FROM quest_template q LEFT JOIN quest_template_addon a USING(ID) ORDER BY q.ID''',
        'starters': '''SELECT s.quest,s.id,t.faction FROM creature_queststarter s
            JOIN creature_template t ON t.entry=s.id ORDER BY s.quest,s.id''',
        'enders': 'SELECT quest,id FROM creature_questender ORDER BY quest,id',
        'source_items': '''SELECT entry,startquest,maxcount FROM item_template
            WHERE entry IN (SELECT StartItem FROM quest_template WHERE StartItem<>0)
            OR startquest<>0 ORDER BY entry''',
        'conditions': '''SELECT * FROM conditions WHERE SourceTypeOrReferenceId IN (19,20)
            ORDER BY SourceTypeOrReferenceId,SourceGroup,SourceEntry,SourceId,ElseGroup,
            ConditionTypeOrReference,ConditionTarget,ConditionValue1,ConditionValue2,ConditionValue3''',
        'creatures': 'SELECT entry,name,minlevel,maxlevel,ScriptName FROM creature_template ORDER BY entry',
        'spawns': 'SELECT DISTINCT id,map,spawnMask FROM creature ORDER BY id,map,spawnMask',
        'instances': 'SELECT * FROM instance_template ORDER BY map',
        'access': 'SELECT * FROM dungeon_access_template ORDER BY id',
        'access_requirements': 'SELECT * FROM dungeon_access_requirements ORDER BY dungeon_access_id,requirement_type,requirement_id,faction',
        'event_quests': '''SELECT quest FROM game_event_creature_quest UNION
            SELECT quest FROM game_event_gameobject_quest UNION SELECT entry AS quest FROM pool_quest ORDER BY quest''',
        'levels': 'SELECT DISTINCT level FROM creature_classlevelstats WHERE level BETWEEN 1 AND 80 ORDER BY level',
    }
    with connection.cursor() as cursor:
        cursor.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
        tables = {}
        for name, query in queries.items():
            cursor.execute(query)
            tables[name] = cursor.fetchall()
        early_ids = [q['ID'] for q in tables['quests'] if q['ID'] in QUEST_IDS
                     and 0 < q['QuestLevel'] <= 10 and q['MinLevel'] <= 10]
        ids = ','.join(map(str,early_ids))
        columns = ['ID','LogDescription'] + [f'RequiredNpcOrGo{i}' for i in range(1,5)]
        columns += [f'RequiredItemId{i}' for i in range(1,7)]
        query = f"SELECT {','.join(columns)} FROM quest_template WHERE ID IN ({ids}) ORDER BY ID"
        queries['early_objectives'] = query
        cursor.execute(query)
        tables['early_objectives'] = cursor.fetchall()
        items = {q[f'RequiredItemId{i}'] for q in tables['early_objectives'] for i in range(1,7)} - {0}
        create_spells = {r[0]:r for r in dbcs['Spell'].rows.values()
                         if any(r[71+i]==24 and r[107+i] in items for i in range(3))}
        spell_ids = ','.join(map(str,sorted(create_spells))) or '0'
        query = f'''SELECT entry,spellid_1,spellid_2,spellid_3,spellid_4,spellid_5 FROM item_template
            WHERE spellid_1 IN ({spell_ids}) OR spellid_2 IN ({spell_ids}) OR spellid_3 IN ({spell_ids})
            OR spellid_4 IN ({spell_ids}) OR spellid_5 IN ({spell_ids}) ORDER BY entry'''
        queries['early_crafting_items'] = query
        cursor.execute(query)
        tables['early_crafting_items'] = cursor.fetchall()
        items |= {r['entry'] for r in tables['early_crafting_items']}
        item_ids = ','.join(map(str,sorted(items)))
        query = f'''SELECT l.Item AS item,t.entry,'creature' AS kind FROM creature_loot_template l
            JOIN creature_template t ON t.lootid=l.Entry WHERE l.Item IN ({item_ids}) AND l.Reference=0 AND l.Chance<>0
            UNION SELECT l.Item,t.entry,'gameobject' FROM gameobject_loot_template l
            JOIN gameobject_template t ON t.Data1=l.Entry WHERE t.type=3 AND l.Item IN ({item_ids}) AND l.Reference=0 AND l.Chance<>0
            UNION SELECT item,entry,'vendor' FROM npc_vendor WHERE item IN ({item_ids}) ORDER BY item,kind,entry'''
        queries['early_item_sources'] = query
        cursor.execute(query)
        tables['early_item_sources'] = cursor.fetchall()
        npcs = {r['id'] for name in ('starters','enders') for r in tables[name] if r['quest'] in early_ids}
        targets = {q[f'RequiredNpcOrGo{i}'] for q in tables['early_objectives'] for i in range(1,5)}
        npcs |= {i for i in targets if i>0}
        npcs |= {r['entry'] for r in tables['early_item_sources'] if r['kind']!='gameobject'}
        objects = {-i for i in targets if i<0}
        objects |= {r['entry'] for r in tables['early_item_sources'] if r['kind']=='gameobject'}
        focuses = ','.join(map(str,sorted({r[18] for r in create_spells.values() if r[18]}))) or '0'
        query = f'SELECT entry,Data0 AS focus FROM gameobject_template WHERE type=8 AND Data0 IN ({focuses}) ORDER BY entry'
        queries['early_crafting_focuses'] = query
        cursor.execute(query)
        tables['early_crafting_focuses'] = cursor.fetchall()
        objects |= {r['entry'] for r in tables['early_crafting_focuses']}
        for name,table,entries in [('early_npc_spawns','creature',npcs),('early_go_spawns','gameobject',objects)]:
            ids = ','.join(map(str,sorted(entries)))
            query = f'''SELECT id,map,position_x,position_y,position_z FROM {table}
                WHERE id IN ({ids}) AND spawnMask&1 ORDER BY id,map,position_x,position_y,position_z'''
            queries[name] = query
            cursor.execute(query)
            tables[name] = cursor.fetchall()
    connection.rollback()
    revision = subprocess.check_output(['git','-C',str(source_dir),'rev-parse','HEAD'], text=True).strip()
    source_files = {f'src/server/scripts/{path}' for entry in SCRIPTED.values() for path in entry[2:4]}
    source_files |= {'src/server/game/Entities/Player/Player.cpp',
                     'src/server/game/Entities/Player/PlayerQuest.cpp',
                     'src/server/game/Quests/QuestDef.cpp',
                     'src/server/game/Entities/Player/KillRewarder.cpp',
                     'src/server/game/Entities/Unit/Unit.cpp',
                     'src/server/shared/DataStores/DBCStructure.h',
                     'src/server/game/Quests/QuestDef.h'}
    return {
        'tables': tables, 'dbc': dbcs, 'source_dir': source_dir, 'queries': queries,
        'provenance': {
            'source_commit': revision, 'client_build': 12340,
            'source_file_sha256': {p:hashlib.sha256((source_dir/p).read_bytes()).hexdigest() for p in sorted(source_files)},
            'world_version': tables['version'],
            'world_updates_count': len(tables['updates']),
            'table_sha256': {k: digest(v) for k,v in tables.items()},
            'dbc_sha256': {k: hashlib.sha256(v.raw).hexdigest() for k,v in dbcs.items()},
        },
    }


def top_zone(area_id, sources):
    areas = sources['dbc']['AreaTable'].rows
    seen = set()
    while areas[area_id][2]:
        if area_id in seen:
            raise ValueError(f'AreaTable ancestry cycle: {area_id}')
        seen.add(area_id)
        area_id = areas[area_id][2]
    return area_id


def expansion(area_id, sources):
    area_id = top_zone(area_id,sources)
    area = sources['dbc']['AreaTable'].rows[area_id]
    if area[1] == 571:
        return 'northrend'
    if area[1] == 530 and area_id not in (3430,3433,3487,3524,3525,3557):
        return 'outland'
    return 'azeroth'


def inside_zone(spawn, zone, sources):
    return any(r[2]==zone and r[1]==spawn['map'] and
               min(DBC.number(r[4]),DBC.number(r[5])) <= spawn['position_y'] <= max(DBC.number(r[4]),DBC.number(r[5])) and
               min(DBC.number(r[6]),DBC.number(r[7])) <= spawn['position_x'] <= max(DBC.number(r[6]),DBC.number(r[7]))
               for r in sources['dbc']['WorldMapArea'].rows.values())


def opening_evidence(checks, sources):
    """Physical witnesses, not a route, terrain, script-success or combat proof."""
    t = sources['tables']
    creatures = {r['entry']:r for r in t['creatures']}
    quests = {r['ID']:r for r in t['quests']}
    objectives = {r['ID']:r for r in t['early_objectives']}
    result = []
    for c in checks:
        if c['kind']!='quest' or c['min_cap']!=10:
            continue
        zone = c['starting_zone']
        local_npcs = [r for r in t['early_npc_spawns'] if inside_zone(r,zone,sources)]
        local_objects = [r for r in t['early_go_spawns'] if inside_zone(r,zone,sources)]
        row = dict(quest=c['wow_id'],starting_zone=zone,objectives=[])
        for role,table in [('starter','starters'),('ender','enders')]:
            entries = {r['id'] for r in t[table] if r['quest']==c['wow_id']}
            witnesses = [r for r in local_npcs if r['id'] in entries]
            row[role] = witnesses[0] if witnesses else None
        q = objectives.get(c['wow_id'])
        if q:
            for i in range(1,5):
                target = q[f'RequiredNpcOrGo{i}']
                if target:
                    witnesses = [r for r in (local_npcs if target>0 else local_objects) if r['id']==abs(target)]
                    row['objectives'].append(dict(target=target,witness=witnesses[0] if witnesses else None,
                        maxlevel=creatures[target]['maxlevel'] if target>0 and target in creatures else None))
            for i in range(1,7):
                item = q[f'RequiredItemId{i}']
                if not item:
                    continue
                provided = quests[c['wow_id']]['StartItem']==item
                links = [r for r in t['early_item_sources'] if r['item']==item]
                witnesses = [(link,r) for link in links
                    for r in (local_objects if link['kind']=='gameobject' else local_npcs)
                    if r['id']==link['entry'] and (link['kind']!='creature' or creatures[r['id']]['maxlevel']<=10)]
                witness = dict(witnesses[0][1],source=witnesses[0][0]['kind']) if witnesses else None
                if not witness and not provided:
                    for use in t['early_crafting_items']:
                        for slot in range(1,6):
                            spell = sources['dbc']['Spell'].rows.get(use[f'spellid_{slot}'])
                            if not spell or not any(spell[71+i]==24 and spell[107+i]==item for i in range(3)):
                                continue
                            inputs = [r for link in t['early_item_sources'] if link['item']==use['entry'] and link['kind']=='creature'
                                      for r in local_npcs if r['id']==link['entry'] and creatures[r['id']]['maxlevel']<=10]
                            focus_entries = {r['entry'] for r in t['early_crafting_focuses'] if r['focus']==spell[18]}
                            focuses = [r for r in local_objects if r['id'] in focus_entries]
                            if inputs and (not spell[18] or focuses):
                                witness = dict(source='item_use',item=use['entry'],spell=spell[0],input=inputs[0],
                                               focus=focuses[0] if focuses else None)
                row['objectives'].append(dict(item=item,provided=provided,witness=witness))
        result.append(row)
    return result


def faction_for_race(race, sources):
    return {7: 'alliance', 1: 'horde'}[sources['dbc']['ChrRaces'].rows[race][7]]


def quest_restrictions(q, sources):
    legal = sorted({p['race'] for p in sources['tables']['profiles'] if p['class'] != 6})
    mask = q['AllowableRaces']
    races = [r for r in legal if not mask or mask & (1 << (r-1))]
    teams = {faction_for_race(r, sources) for r in races}
    faction = next(iter(teams)) if len(teams) == 1 else 'any'
    if faction == 'any':
        # Opposing-team hostility in the starter's actual FactionTemplate blocks turn-in.
        starters = [s for s in sources['tables']['starters'] if s['quest'] == q['ID']]
        hostile = [sources['dbc']['FactionTemplate'].rows[s['faction']][5] for s in starters]
        if hostile and all(h & 4 and not h & 2 for h in hostile):
            faction = 'alliance'
        elif hostile and all(h & 2 and not h & 4 for h in hostile):
            faction = 'horde'
    classes = [c for c in sorted({p['class'] for p in sources['tables']['profiles']})
               if c != 6 and q['AllowableClasses'] and q['AllowableClasses'] & (1 << (c-1))]
    # Whole-faction masks need no redundant race list.
    allowed = [r for r in legal if faction == 'any' or faction_for_race(r,sources) == faction]
    return faction, classes, races if set(races) != set(allowed) and mask else []


def quest_parents(q, sources):
    parents = set()
    if q['PrevQuestID']:
        parents.add(abs(q['PrevQuestID']))
    for other in sources['tables']['quests']:
        if other['NextQuestID'] == q['ID']:
            parents.add(other['ID'])
    return sorted(parents)


def base_check(kind, wow_id, name, cap, exp='azeroth', faction='any', effort=10):
    return dict(key=f'{kind}_{wow_id}', kind=kind, wow_id=wow_id, name=name,
                faction=faction, classes=[], races=[], min_cap=cap, expansion=exp,
                riding='none', prerequisites=[], difficulty='solo', effort_minutes=effort,
                ap_id=BASES[kind]+wow_id)


def generate(sources):
    tables, dbcs = sources['tables'], sources['dbc']
    quests = {q['ID']:q for q in tables['quests']}
    creatures = {c['entry']:c for c in tables['creatures']}
    checks = []
    for quest_id in QUEST_IDS:
        q = quests[quest_id]
        cap = max(10, math.ceil(max(q['QuestLevel'],q['MinLevel']) / 10) * 10)
        row = base_check('quest',quest_id,f"Quest: {q['LogTitle']} [{quest_id}]",cap,
                         expansion(q['QuestSortID'],sources),effort=15)
        row['faction'], row['classes'], row['races'] = quest_restrictions(q,sources)
        row['prerequisites'] = [f'quest_{p}' for p in quest_parents(q,sources)]
        row['area_id'] = q['QuestSortID']
        row['source_area_id'] = q['QuestSortID']
        row['starting_zone'] = top_zone(q['QuestSortID'],sources)
        row['source_restrictions'] = {k:q[k] for k in ('AllowableRaces','AllowableClasses','PrevQuestID','NextQuestID','SpecialFlags','Flags')}
        checks.append(row)
    for area, cap, faction in ZONES:
        row = base_check('exploration',area,'Enter zone: '+dbcs['AreaTable'].text(dbcs['AreaTable'].rows[area][11]),
                         cap,expansion(area,sources),faction,5)
        row['map_id'] = dbcs['AreaTable'].rows[area][1]
        checks.append(row)
    for map_id, cap, bosses in DUNGEONS:
        exp = ('azeroth','outland','northrend')[dbcs['Map'].rows[map_id][63]]
        for boss in bosses:
            row = base_check('boss',boss,'Boss: '+creatures[boss]['name'],cap,exp,effort=30)
            row.update(map_id=map_id,difficulty='party',instance_difficulty='normal',
                       riding='expert' if map_id==554 else 'none')
            row['prerequisites'] = [f'boss_{b}' for b in BOSS_PREREQUISITES.get(boss,[])]
            checks.append(row)
        row = base_check('dungeon',map_id,'Clear: '+dbcs['Map'].text(dbcs['Map'].rows[map_id][5]),cap,exp,effort=60)
        row.update(map_id=map_id,boss_ids=bosses,difficulty='party',
                   riding='expert' if map_id==554 else 'none',
                   prerequisites=[f'boss_{b}' for b in bosses],completion_rule='all_curated_bosses',
                   instance_difficulty='normal',credit_scope='bound_character_same_instance_lockout')
        checks.append(row)
    for level in range(5,81,5):
        checks.append(base_check('level',level,f'Reach level {level}',max(10,math.ceil(level/10)*10),effort=30))
    for map_id,boss in RAIDS:
        row = base_check('raid',boss,'Raid: '+creatures[boss]['name'],80,
                         ('azeroth','outland','northrend')[dbcs['Map'].rows[map_id][63]],effort=120)
        row.update(map_id=map_id,difficulty='raid',filler_only=True,required=False)
        if boss == 11502:
            row['prerequisites'] = [f'raid_{b}' for m,b in RAIDS if m==409 and b!=11502]
        checks.append(row)
    profiles = []
    for p in tables['profiles']:
        if p['class'] == 6:
            continue
        area = dbcs['AreaTable'].rows[p['zone']]
        zone = top_zone(p['zone'],sources)
        profiles.append(dict(race_id=p['race'],class_id=p['class'],faction=faction_for_race(p['race'],sources),
                             starting_zone=zone,source_zone=p['zone'],map_id=p['map'],
                             position=[p['position_x'],p['position_y'],p['position_z']],orientation=p['orientation']))
    return (dict(schema_version=2,provenance=sources['provenance'],
                 credit_policy=dict(binding='one_character_per_seed_slot',deduplication='seed_slot_check_key',
                                    quest='confirmed_rewarded_turn_in',exploration='confirmed_zone_entry',
                                    level='actual_character_level',boss='core_tap_group_kill_credit',
                                    dungeon='all_curated_bosses_same_instance_lockout',
                                    account_wide=False,playerbots='normal_core_group_credit_only'),checks=checks),
            dict(schema_version=2,provenance=sources['provenance'],profiles=profiles,excluded_classes=[6]))


def filter_profile(checks, profile):
    selected = {c['key']:c for c in checks if
                c['faction'] in ('any',profile['faction']) and
                (not c['classes'] or profile['class_id'] in c['classes']) and
                (not c['races'] or profile['race_id'] in c['races'])}
    # A restriction inherited through a prerequisite also removes its descendants.
    while True:
        removed = [key for key,c in selected.items() if any(p not in selected for p in c['prerequisites'])]
        if not removed:
            return list(selected.values())
        for key in removed:
            del selected[key]


def early_checks(checks, profile):
    selected = filter_profile(checks,profile)
    accessible = set()
    while True:
        found = {c['key'] for c in selected if c['min_cap'] <= 10 and c['expansion'] == 'azeroth'
                 and c['riding'] == 'none' and set(c['prerequisites']) <= accessible}
        if found <= accessible:
            return [c for c in selected if c['key'] in accessible]
        accessible |= found


def validate(catalog, profiles, sources=None):
    checks = catalog.get('checks',[])
    invalid = []
    def fail(key, message):
        invalid.append(dict(key=key,error=message))
    required = {'key','kind','wow_id','name','faction','classes','races','min_cap',
                'expansion','riding','prerequisites','difficulty','effort_minutes','ap_id'}
    for index,c in enumerate(checks):
        extra = {'boss':{'map_id'},'raid':{'map_id'},
                 'dungeon':{'map_id','boss_ids'},'exploration':{'map_id'},
                 'quest':{'area_id','source_area_id','starting_zone'}}.get(c.get('kind'),set())
        missing = (required | extra) - c.keys()
        if missing:
            fail(f'row_{index}',f'missing fields {sorted(missing)}')
        elif not isinstance(c['wow_id'],int) or not isinstance(c['ap_id'],int):
            fail(c['key'],'WoW/AP IDs must be integers')
    if invalid:
        return dict(valid=False,invalid_rows=invalid,counts={},profiles=[])
    by_key = {c['key']:c for c in checks}
    retired = json.loads((DATA/'retired-checks.json').read_text())['checks']
    for c in checks:
        if any(c['key']==r['key'] or c['ap_id']==r['ap_id'] for r in retired):
            fail(c['key'],'permanently retired check identity')
    for field in ('key','ap_id','name'):
        if len({c[field] for c in checks}) != len(checks):
            fail('catalog',f'duplicate {field}')
    if catalog.get('schema_version') != 2 or profiles.get('schema_version') != 2:
        fail('catalog','schema_version must be 2')
    if profiles.get('excluded_classes') != [6]:
        fail('profiles','Death Knights must be explicitly excluded in v1')
    counts = Counter(c['kind'] for c in checks)
    if counts != COUNTS:
        fail('catalog',f'counts {dict(counts)} != {COUNTS}')
    for c in checks:
        key,kind,source_id = c['key'],c['kind'],c['wow_id']
        if kind not in BASES or c['ap_id'] != BASES[kind] + source_id or key != f'{kind}_{source_id}':
            fail(key,'ID contract mismatch')
        if c['faction'] not in ('any','alliance','horde') or c['min_cap'] not in range(10,81,10):
            fail(key,'invalid faction or cap')
        if c['expansion'] not in ('azeroth','outland','northrend') or c['riding'] not in ('none','expert','cold_weather'):
            fail(key,'invalid expansion or riding')
        if c['effort_minutes'] <= 0 or c['difficulty'] not in ('solo','party','raid') or 6 in c['classes']:
            fail(key,'invalid effort, difficulty or excluded class')
        for parent in c['prerequisites']:
            if parent not in by_key:
                fail(key,f'missing prerequisite {parent}')
            elif by_key[parent]['min_cap'] > c['min_cap']:
                fail(key,f'prerequisite above cap {parent}')
        if kind == 'boss' and set(c['prerequisites']) != {f'boss_{b}' for b in BOSS_PREREQUISITES.get(source_id,[])}:
            fail(key,'critical boss prerequisites differ from curated gate rules')
        if kind == 'boss' and c['map_id'] not in {d['map_id'] for d in checks if d['kind']=='dungeon'}:
            fail(key,'boss has no curated dungeon completion')
        if kind == 'dungeon':
            expected = {b['wow_id'] for b in checks if b['kind']=='boss' and b['map_id']==c['map_id']}
            if set(c['boss_ids']) != expected or set(c['prerequisites']) != {f'boss_{b}' for b in expected} or not expected:
                fail(key,'clear does not require exactly all curated bosses on its map')
            if c.get('completion_rule') != 'all_curated_bosses':
                fail(key,'ambiguous completion rule')
        if kind == 'raid' and (not c.get('filler_only') or c.get('required') is not False):
            fail(key,'raid must be filler-only and nonrequired')
        if kind == 'level' and (source_id not in range(5,81,5) or c['min_cap'] < source_id):
            fail(key,'invalid milestone')
    visiting, done = set(), set()
    def visit(key):
        if key in visiting:
            fail(key,'prerequisite cycle')
            return
        if key in done or key not in by_key:
            return
        visiting.add(key)
        for p in by_key[key]['prerequisites']:
            visit(p)
        visiting.remove(key)
        done.add(key)
    for key in by_key:
        visit(key)
    opening = opening_evidence(checks,sources) if sources else []
    if sources:
        validate_sources(checks,profiles,sources,fail)
        for row in opening:
            if not row['starter'] or not row['ender']:
                fail(f"quest_{row['quest']}",'no spawned NPC starter/ender inside physical starting zone')
            for objective in row['objectives']:
                if not objective.get('provided') and not objective['witness']:
                    fail(f"quest_{row['quest']}",'no local objective source; external item gate or unsupported objective')
                if (objective.get('maxlevel') or 0)>13:
                    fail(f"quest_{row['quest']}",'objective above conservative cap-10 level margin')
        for label,obj in [('checks',catalog),('profiles',profiles)]:
            if obj.get('provenance') != sources['provenance']:
                fail(label,'pinned source provenance differs; review before regenerating')
    coverage = []
    for p in profiles['profiles']:
        selected = filter_profile(checks,p)
        early = early_checks(checks,p)
        row = dict(race_id=p['race_id'],class_id=p['class_id'],faction=p['faction'],
                   starting_zone=p['starting_zone'],total=len(selected),early_count=len(early),
                   early_local_count=sum(c['kind']=='quest' and c.get('starting_zone')==p['starting_zone']
                                         or c['kind']=='exploration' and c['wow_id']==p['starting_zone']
                                         or c['kind']=='level' for c in early),
                   before_80=sum(c['min_cap']<80 for c in selected),
                   counts=dict(Counter(c['kind'] for c in selected)))
        coverage.append(row)
        if not 20 <= row['early_local_count'] <= 35:
            fail(f"profile_{p['race_id']}_{p['class_id']}",f"local early count {row['early_local_count']} outside 20..35")
        if row['before_80'] <= len(selected)/2:
            fail(f"profile_{p['race_id']}_{p['class_id']}",'majority not before cap 80')
    return dict(valid=not invalid,counts=dict(counts),invalid_rows=invalid,profiles=coverage,
                cap_bands=dict(sorted(Counter(c['min_cap'] for c in checks).items())),
                provenance=catalog.get('provenance'),opening_evidence=opening,
                source_queries=sources['queries'] if sources else {})


def validate_sources(checks, profiles, sources, fail):
    t,d = sources['tables'],sources['dbc']
    quests = {q['ID']:q for q in t['quests']}
    creatures = {c['entry']:c for c in t['creatures']}
    instances = {i['map'] for i in t['instances']}
    quest_keys = {c['wow_id'] for c in checks if c['kind']=='quest'}
    for c in checks:
        key,kind,wow_id = c['key'],c['kind'],c['wow_id']
        if kind == 'quest':
            q = quests.get(wow_id)
            if q is None:
                fail(key,'quest ID absent from pinned DB')
                continue
            if (q['SpecialFlags'] or 0) & (1|16) or q['Flags'] & (4096|32768):
                fail(key,'repeatable, daily or weekly quest')
            if q['QuestLevel'] < 1 or q['QuestSortID'] not in d['AreaTable'].rows:
                fail(key,'non-zone, event or introduction quest')
                continue
            if any(q[k] for k in ('ExclusiveGroup','BreadcrumbForQuestId','RequiredSkillID','RequiredMinRepFaction','RequiredMaxRepFaction','RequiredFactionId1','RequiredFactionId2','TimeAllowed','MaxLevel')):
                fail(key,'unsupported quest availability requirement')
            item = next((i for i in t['source_items'] if i['entry']==q['StartItem']),None)
            if q['StartItem'] and (item is None or q['ProvidedItemCount'] <= 0 or
                                      item['maxcount'] > 0 and q['ProvidedItemCount'] > item['maxcount']):
                fail(key,'invalid NPC-provided source item or count')
            if not q['StartItem'] and q['ProvidedItemCount']:
                fail(key,'source item count without source item')
            if any(i['startquest']==wow_id for i in t['source_items']):
                fail(key,'item-start quest is not supported')
            if (c.get('area_id'),c.get('source_area_id'),c.get('starting_zone')) != (
                    q['QuestSortID'],q['QuestSortID'],top_zone(q['QuestSortID'],sources)):
                fail(key,'quest area ancestry differs from pinned DBC/DB')
            if any(r['quest']==wow_id for r in t['event_quests']):
                fail(key,'event or pooled quest availability is not supported')
            if any(r['SourceEntry']==wow_id for r in t['conditions']):
                fail(key,'quest has unmodeled DB conditions')
            if not any(s['quest']==wow_id for s in t['starters']) or not any(s['quest']==wow_id for s in t['enders']):
                fail(key,'no creature starter or ender')
            parents = quest_parents(q,sources)
            if q['PrevQuestID'] < 0 or len(parents)>1 or any(p not in quest_keys for p in parents):
                fail(key,f'unsupported or missing chain parents {parents}')
            if set(c['prerequisites']) != {f'quest_{p}' for p in parents}:
                fail(key,'prerequisites differ from pinned DB')
            if (c['faction'],c['classes'],c['races']) != quest_restrictions(q,sources):
                fail(key,'restrictions differ from source')
            if c['min_cap'] < max(q['QuestLevel'],q['MinLevel']):
                fail(key,'cap below quest level')
            if c['expansion'] != expansion(q['QuestSortID'],sources):
                fail(key,'quest expansion mismatch')
            if c['name'] != f"Quest: {q['LogTitle']} [{wow_id}]":
                fail(key,'quest name mismatch')
        elif kind == 'exploration':
            area = d['AreaTable'].rows.get(wow_id)
            if area is None:
                fail(key,'area ID absent from pinned DBC')
            elif area[2] or c.get('map_id') != area[1] or c['expansion'] != expansion(wow_id,sources):
                fail(key,'exploration must name a top-level zone on its actual map/expansion')
        elif kind in ('boss','raid'):
            creature = creatures.get(wow_id)
            if creature is None:
                fail(key,'creature ID absent from pinned DB')
                continue
            map_id = c.get('map_id')
            map_row = d['Map'].rows.get(map_id)
            if map_id not in instances or map_row is None or map_row[2] != (2 if kind=='raid' else 1):
                fail(key,'invalid dungeon/raid map')
            spawn = any(s['id']==wow_id and s['map']==map_id and s['spawnMask'] & 1 for s in t['spawns'])
            if not spawn:
                evidence = SCRIPTED.get(wow_id)
                valid = False
                if evidence and evidence[0] == map_id:
                    _,symbol,header,implementation,transform = evidence
                    directory = sources['source_dir']/'src/server/scripts'
                    enum = (directory/header).read_text()
                    code = (directory/implementation).read_text()
                    operation = 'UpdateEntry' if transform else 'SummonCreature'
                    valid = bool(re.search(rf'\b{symbol}\s*=\s*{wow_id}\b',enum) and
                                 f'{operation}({symbol}' in code)
                    if transform:
                        valid &= any(s['id']==transform and s['map']==map_id and s['spawnMask'] & 1 for s in t['spawns'])
                    else:
                        valid &= bool(creature['ScriptName'])
                if not valid:
                    fail(key,'no normal spawn or map-specific scripted summon/transform evidence')
            if creature['maxlevel'] > c['min_cap']+3:
                fail(key,'cap below conservative creature level')
            if c['name'] != ('Raid: ' if kind=='raid' else 'Boss: ')+creature['name']:
                fail(key,'creature name mismatch')
            if map_row and c['expansion'] != ('azeroth','outland','northrend')[map_row[63]]:
                fail(key,'instance expansion mismatch')
            if map_id==554 and c['riding']!='expert':
                fail(key,'Tempest Keep entrance requires Expert Riding')
        elif kind == 'level':
            if wow_id not in {r['level'] for r in t['levels']}:
                fail(key,'milestone level absent from pinned level stats')
        elif kind == 'dungeon':
            access = [a for a in t['access'] if a['map_id']==wow_id and a['difficulty']==0]
            if len(access)!=1 or access[0]['min_level']>c['min_cap'] or access[0]['min_avg_item_level']:
                fail(key,'unmodeled normal instance entry level or item gate')
            elif any(r['dungeon_access_id']==access[0]['id'] for r in t['access_requirements']):
                fail(key,'normal instance has unmodeled quest/item entry requirements')
            if wow_id != c['map_id'] or wow_id not in instances:
                fail(key,'dungeon ID must be its instance map')
            if wow_id==554 and c['riding']!='expert':
                fail(key,'Tempest Keep entrance requires Expert Riding')
    expected = {(p['race'],p['class']):p for p in t['profiles'] if p['class']!=6}
    actual = {(p['race_id'],p['class_id']):p for p in profiles['profiles']}
    if set(actual) != set(expected) or len(actual) != len(profiles['profiles']):
        fail('profiles','legal race/class combinations differ from playercreateinfo')
    for pair,p in actual.items():
        if pair not in expected:
            continue
        src = expected[pair]
        area = d['AreaTable'].rows.get(src['zone'])
        zone = top_zone(src['zone'],sources) if area else None
        if (p['starting_zone'],p['map_id'],p['position'],p['source_zone'],p['faction']) != (
                zone,src['map'],[src['position_x'],src['position_y'],src['position_z']],src['zone'],faction_for_race(src['race'],sources)):
            fail(str(pair),'start differs from playercreateinfo/AreaTable')
        if area is None or area[1] != src['map'] or src['map'] not in d['Map'].rows:
            fail(str(pair),'start area map does not match DBC')
        if pair[0] not in d['ChrRaces'].rows or pair[1] not in d['ChrClasses'].rows:
            fail(str(pair),'race/class ID absent from pinned DBC')
        if p['orientation'] != src['orientation']:
            fail(str(pair),'start orientation differs from playercreateinfo')
        bounds = [r for r in d['WorldMapArea'].rows.values() if r[2]==zone and r[1]==src['map']]
        if not bounds or not any(min(DBC.number(r[4]),DBC.number(r[5])) <= src['position_y'] <= max(DBC.number(r[4]),DBC.number(r[5])) and
                                min(DBC.number(r[6]),DBC.number(r[7])) <= src['position_x'] <= max(DBC.number(r[6]),DBC.number(r[7])) for r in bounds):
            fail(str(pair),'start coordinates outside WorldMapArea zone bounds')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=13317)
    parser.add_argument('--user',default='root')
    parser.add_argument('--database',default='acore_world')
    parser.add_argument('--dbc',type=Path,default=DEFAULT_DBC)
    parser.add_argument('--source',type=Path,default=DEFAULT_SOURCE)
    parser.add_argument('--generate',action='store_true',help='regenerate owned JSON files only after validation succeeds')
    parser.add_argument('--offline',action='store_true',help='structural/filter checks only; no ID revalidation')
    parser.add_argument('--report',type=Path,help='write a JSON coverage report')
    args = parser.parse_args(argv)
    sources = None
    if args.offline and args.generate:
        parser.error('--generate requires live read-only source validation')
    if not args.offline:
        import pymysql
        connection = pymysql.connect(host=args.host,port=args.port,user=args.user,
            password=os.environ.get('WOWPILAGO_DB_PASSWORD',''),database=args.database,
            cursorclass=pymysql.cursors.DictCursor,autocommit=False)
        try:
            sources = read_sources(connection,args.dbc,args.source)
        finally:
            connection.close()
    if args.generate:
        catalog,profiles = generate(sources)
    else:
        catalog = json.loads((DATA/'checks.json').read_text())
        profiles = json.loads((DATA/'profiles.json').read_text())
    report = validate(catalog,profiles,sources)
    if args.generate and report['valid']:
        DATA.mkdir(parents=True,exist_ok=True)
        for filename,value in [('checks.json',catalog),('profiles.json',profiles)]:
            (DATA/filename).write_text(json.dumps(value,indent=2)+'\n')
    if args.report:
        args.report.write_text(json.dumps(report,indent=2,default=str)+'\n')
    print(json.dumps(report,indent=2,default=str))
    return 0 if report['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
