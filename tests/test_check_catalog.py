"""Catalog relationships, profile filtering, and opt-in real DB rejection tests."""
import copy
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest

from tools.validate_checks import (
    DATA, DBC, DEFAULT_DBC, DEFAULT_SOURCE, early_checks, filter_profile,
    generate, read_sources, validate,
)


def load_catalogs():
    return (json.loads((DATA/'checks.json').read_text()),
            json.loads((DATA/'profiles.json').read_text()))


class CheckCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog,self.profiles = load_catalogs()
        self.checks = self.catalog['checks']
        self.human = next(p for p in self.profiles['profiles'] if p['race_id']==1 and p['class_id']==1)
        self.orc = next(p for p in self.profiles['profiles'] if p['race_id']==2 and p['class_id']==1)

    def test_all_profiles_keep_closed_chains_and_early_checks(self):
        report = validate(self.catalog,self.profiles)
        self.assertEqual(report['invalid_rows'],[])
        self.assertTrue(report['valid'])
        for profile,coverage in zip(self.profiles['profiles'],report['profiles']):
            with self.subTest(race=profile['race_id'],class_id=profile['class_id']):
                rows = filter_profile(self.checks,profile)
                keys = {c['key'] for c in rows}
                self.assertTrue(all(set(c['prerequisites']) <= keys for c in rows))
                self.assertEqual(coverage['total'],len(rows))
                early = early_checks(self.checks,profile)
                local = [c for c in early if c['kind']=='level'
                         or c['kind']=='quest' and c['starting_zone']==profile['starting_zone']
                         or c['kind']=='exploration' and c['wow_id']==profile['starting_zone']]
                self.assertTrue(20 <= len(local) <= 35)
                self.assertEqual(coverage['early_local_count'],len(local))
                self.assertEqual(len(local),20)
                self.assertEqual(sum(c['kind']=='quest' for c in local),17)
                self.assertEqual(coverage['early_count'],len(early))
                self.assertGreaterEqual(len(early),len(local))
                self.assertGreater(coverage['before_80'],coverage['total']/2)

    def test_faction_filters_have_different_real_quests(self):
        alliance = {c['key'] for c in early_checks(self.checks,self.human)}
        horde = {c['key'] for c in early_checks(self.checks,self.orc)}
        self.assertEqual({'quest_47','quest_60','quest_784','quest_825'} & alliance,
                         {'quest_47','quest_60'})
        self.assertEqual({'quest_47','quest_60','quest_784','quest_825'} & horde,
                         {'quest_784','quest_825'})
        self.assertEqual({'level_5','level_10'} & alliance & horde,{'level_5','level_10'})

    def test_filtered_prerequisite_removes_descendant(self):
        parent = next(c for c in self.checks if c['key']=='quest_488')
        child = next(c for c in self.checks if c['key']=='quest_489')
        self.assertIn(child['key'],{c['key'] for c in filter_profile(self.checks,self.human)})
        parent['classes'] = [8]
        selected = {c['key'] for c in filter_profile(self.checks,self.human)}
        self.assertEqual(selected & {parent['key'],child['key']},set())
        mage = dict(self.human,class_id=8)
        self.assertEqual({c['key'] for c in filter_profile(self.checks,mage)} & {parent['key'],child['key']},
                         {'quest_488','quest_489'})

    def test_early_filter_requires_unlocked_travel_and_parent(self):
        before = {c['key'] for c in early_checks(self.checks,self.human)}
        parent = next(c for c in self.checks if c['key']=='quest_488')
        parent['riding'] = 'expert'
        after = {c['key'] for c in early_checks(self.checks,self.human)}
        self.assertEqual(before-after,{'quest_488','quest_489'})
        parent['riding'] = 'none'
        parent['expansion'] = 'outland'
        self.assertEqual({c['key'] for c in early_checks(self.checks,self.human)},after)

    def test_dungeon_missing_one_boss_is_not_a_clear(self):
        dungeon = next(c for c in self.checks if c['kind']=='dungeon')
        dungeon['boss_ids'].pop()
        report = validate(self.catalog,self.profiles)
        self.assertIn(dict(key=dungeon['key'],error='clear does not require exactly all curated bosses on its map'),
                      report['invalid_rows'])
        self.assertFalse(report['valid'])

    def test_broken_chain_and_cycle_report_locations(self):
        quest = next(c for c in self.checks if c['key']=='quest_47')
        quest['prerequisites'] = ['quest_99999999']
        report = validate(self.catalog,self.profiles)
        self.assertIn(dict(key='quest_47',error='missing prerequisite quest_99999999'),report['invalid_rows'])
        quest['prerequisites'] = ['quest_47']
        report = validate(self.catalog,self.profiles)
        self.assertIn(dict(key='quest_47',error='prerequisite cycle'),report['invalid_rows'])
        retired = json.loads((DATA/'retired-checks.json').read_text())['checks'][0]
        quest.update({k:retired[k] for k in ('key','ap_id','wow_id')},prerequisites=[])
        self.assertIn(dict(key=quest['key'],error='permanently retired check identity'),
                      validate(self.catalog,self.profiles)['invalid_rows'])

    def test_raid_cannot_silently_allow_progression(self):
        raid = next(c for c in self.checks if c['kind']=='raid')
        raid['filler_only'] = False
        report = validate(self.catalog,self.profiles)
        self.assertIn(dict(key=raid['key'],error='raid must be filler-only and nonrequired'),report['invalid_rows'])

    def test_missing_contract_field_is_a_report_not_a_key_error(self):
        del self.checks[0]['wow_id']
        self.assertEqual(validate(self.catalog,self.profiles)['invalid_rows'],
                         [dict(key='row_0',error="missing fields ['wow_id']")])

    def test_dbc_parser_reads_records_and_rejects_truncation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'sample.dbc'
            payload = struct.pack('<4s4I2I',b'WDBC',1,2,8,6,42,1)+b'\0Name\0'
            path.write_bytes(payload)
            dbc = DBC(path)
            self.assertEqual(dbc.text(dbc.rows[42][1]),'Name')
            path.write_bytes(payload[:-1])
            with self.assertRaisesRegex(ValueError,'Invalid WDBC layout'):
                DBC(path)


@unittest.skipUnless(os.environ.get('WOWPILAGO_DB_PASSWORD'),'set WOWPILAGO_DB_PASSWORD to revalidate against the pinned MySQL')
class LiveCheckCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pymysql
        connection = pymysql.connect(host=os.environ.get('WOW_DB_HOST','127.0.0.1'),
            port=int(os.environ.get('WOW_DB_PORT','13317')),user=os.environ.get('WOW_DB_USER','root'),
            password=os.environ['WOWPILAGO_DB_PASSWORD'],database='acore_world',
            cursorclass=pymysql.cursors.DictCursor)
        try:
            cls.sources = read_sources(connection,DEFAULT_DBC,DEFAULT_SOURCE)
        finally:
            connection.close()

    def test_shipped_catalog_matches_read_only_sources_and_regeneration(self):
        catalog,profiles = load_catalogs()
        report = validate(catalog,profiles,self.sources)
        self.assertEqual(report['invalid_rows'],[])
        self.assertTrue(report['valid'])
        self.assertEqual(generate(self.sources),(catalog,profiles))
        self.assertEqual(len(report['opening_evidence']),136)
        for row in report['opening_evidence']:
            self.assertIsNotNone(row['starter'])
            self.assertIsNotNone(row['ender'])
            self.assertTrue(all(o.get('provided') or o['witness'] for o in row['objectives']))
        for quest,area,zone in [(8325,3431,3430),(9279,3526,3524)]:
            row = next(c for c in catalog['checks'] if c['key']==f'quest_{quest}')
            self.assertEqual((row['area_id'],row['source_area_id'],row['starting_zone'],row['expansion']),
                             (area,area,zone,'azeroth'))
        for quest in (233,234,320,754):
            source = next(q for q in self.sources['tables']['quests'] if q['ID']==quest)
            self.assertGreater(source['StartItem'],0)
            self.assertGreater(source['ProvidedItemCount'],0)
        retired = json.loads((DATA/'retired-checks.json').read_text())['checks']
        self.assertEqual(len(retired),88)
        later = {c['wow_id'] for c in catalog['checks'] if c['kind']=='quest' and c['min_cap']>10}
        self.assertEqual(later,{12,56,216,568,844,1387,2862,4124,5092,9443,9770,9777,11155,11167})
        for faction in ('alliance','horde'):
            for cap in range(20,81,10):
                self.assertTrue(any(c['kind']=='quest' and c['min_cap']==cap and c['faction'] in ('any',faction)
                                    for c in catalog['checks']))
        self.assertFalse({c['ap_id'] for c in catalog['checks']} & {c['ap_id'] for c in retired})

    def test_nonexistent_quest_and_area_ids_are_rejected_by_sources(self):
        for kind,error in [('quest','quest ID absent from pinned DB'),
                           ('exploration','area ID absent from pinned DBC')]:
            with self.subTest(kind=kind):
                catalog,profiles = load_catalogs()
                row = next(c for c in catalog['checks'] if c['kind']==kind)
                delta = 99999999-row['wow_id']
                row.update(key=f'{kind}_99999999',wow_id=99999999,ap_id=row['ap_id']+delta)
                report = validate(catalog,profiles,self.sources)
                self.assertIn(dict(key=row['key'],error=error),report['invalid_rows'])
                self.assertFalse(report['valid'])

    def test_existing_boss_on_wrong_map_is_rejected(self):
        catalog,profiles = load_catalogs()
        row = next(c for c in catalog['checks'] if c['key']=='boss_17306')
        row['map_id'] = 547
        report = validate(catalog,profiles,self.sources)
        self.assertIn(dict(key=row['key'],error='no normal spawn or map-specific scripted summon/transform evidence'),
                      report['invalid_rows'])

    def test_forged_race_class_start_is_rejected(self):
        catalog,profiles = load_catalogs()
        profiles['profiles'][0]['class_id'] = 6
        report = validate(catalog,profiles,self.sources)
        self.assertIn(dict(key='profiles',error='legal race/class combinations differ from playercreateinfo'),
                      report['invalid_rows'])
        catalog,profiles = load_catalogs()
        sources = copy.deepcopy(self.sources)
        sources['tables']['early_npc_spawns'] = []
        report = validate(catalog,profiles,sources)
        self.assertIn(dict(key='quest_233',error='no spawned NPC starter/ender inside physical starting zone'),
                      report['invalid_rows'])

    def test_repeatable_real_quest_and_forged_race_mask_are_rejected(self):
        catalog,profiles = load_catalogs()
        quest = next(q for q in self.sources['tables']['quests'] if (q['SpecialFlags'] or 0) & 1)
        row = next(c for c in catalog['checks'] if c['kind']=='quest')
        delta = quest['ID']-row['wow_id']
        row.update(key=f"quest_{quest['ID']}",wow_id=quest['ID'],ap_id=row['ap_id']+delta)
        report = validate(catalog,profiles,self.sources)
        self.assertIn(dict(key=row['key'],error='repeatable, daily or weekly quest'),report['invalid_rows'])
        catalog,profiles = load_catalogs()
        row = next(c for c in catalog['checks'] if c['key']=='quest_47')
        row['races'] = [2]
        report = validate(catalog,profiles,self.sources)
        self.assertIn(dict(key=row['key'],error='restrictions differ from source'),report['invalid_rows'])
        for mutation,error in [('count','invalid NPC-provided source item or count'),
                               ('template','invalid NPC-provided source item or count'),
                               ('item_start','item-start quest is not supported'),
                               ('external','no local objective source; external item gate or unsupported objective')]:
            with self.subTest(mutation=mutation):
                catalog,profiles = load_catalogs()
                sources = copy.deepcopy(self.sources)
                q = next(q for q in sources['tables']['quests'] if q['ID']==233)
                if mutation=='count':
                    q['ProvidedItemCount'] = 0
                elif mutation=='template':
                    sources['tables']['source_items'] = [i for i in sources['tables']['source_items'] if i['entry']!=2187]
                elif mutation=='item_start':
                    next(i for i in sources['tables']['source_items'] if i['entry']==2187)['startquest'] = 233
                else:
                    q['StartItem'] = 0
                    q['ProvidedItemCount'] = 0
                report = validate(catalog,profiles,sources)
                self.assertIn(dict(key='quest_233',error=error),report['invalid_rows'])


if __name__ == '__main__':
    unittest.main()
