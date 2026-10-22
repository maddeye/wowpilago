"""Offline contracts and rejection cases. Run live provenance separately with --live."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('validate_rewards', ROOT / 'tools/validate_rewards.py')
rewards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rewards)


class RewardCatalogTests(unittest.TestCase):
    def setUp(self):
        self.gear = json.loads((rewards.DATA / 'gear.json').read_text())
        self.abilities = json.loads((rewards.DATA / 'abilities.json').read_text())

    def errors(self):
        return '\n'.join(rewards.validate(self.gear, self.abilities))

    def test_complete_catalog(self):
        self.assertEqual(self.errors(), '')

    def test_duplicate_item_rejected(self):
        self.gear['items'].append(copy.deepcopy(self.gear['items'][0]))
        self.assertIn('duplicate item ID', self.errors())

    def test_legendary_vendor_price_rejected(self):
        next(i for i in self.gear['items'] if i['quality'] == 5)['price'] = 8
        self.assertIn('incorrect price', self.errors())

    def test_quality_pricing(self):
        for quality, exp, item_class, expected in [(2, 2, 4, 1), (3, 0, 2, 2),
                (4, 0, 4, 3), (4, 1, 4, 4), (4, 2, 4, 5),
                (4, 0, 2, 6), (4, 1, 2, 7), (4, 2, 2, 8), (5, 2, 2, 0)]:
            entry = 19019 if exp == 0 else 34334 if exp == 1 else 49623
            self.assertEqual(rewards.price(dict(Quality=quality, entry=entry, **{'class': item_class})), expected)

    def test_weapon_proficiency_not_just_class_mask(self):
        sword = next(i for i in self.gear['items'] if i['wow_id'] == 19019)
        self.assertNotIn(11, sword['allowable_classes'])
        sword['allowable_classes'].append(11)
        self.assertIn('incompatible proficiency', self.errors())

    def test_plate_proficiency_rejected(self):
        plate = next(i for i in self.gear['items'] if i['item_class'] == 4 and i['item_subclass'] == 4)
        plate['allowable_classes'].append(8)
        self.assertIn('incompatible proficiency', self.errors())

    def test_missing_set_piece_rejected(self):
        piece = self.gear['sets'][0]['pieces'][0]
        self.gear['items'] = [i for i in self.gear['items'] if i['wow_id'] != piece]
        self.assertIn('missing piece', self.errors())

    def test_wrong_set_relationship_rejected(self):
        piece = self.gear['sets'][0]['pieces'][0]
        next(i for i in self.gear['items'] if i['wow_id'] == piece)['set_id'] = 0
        self.assertIn('wrong set relationship', self.errors())

    def test_real_featured_piece_counts(self):
        for s in self.gear['sets']:
            if s['wow_id'] == 699:
                self.assertEqual(len(s['pieces']), 2)
                continue
            self.assertEqual(len(s['pieces']), 8 if s['wow_id'] < 600 or 668 <= s['wow_id'] <= 684 else 5)
        for cls in rewards.CLASSES:
            featured = [s for s in self.gear['sets'] if cls in s['class_ids'] and s['wow_id'] != 699]
            self.assertGreaterEqual(len(featured), 4)
            self.assertEqual({s['expansion'] for s in featured}, {0, 1, 2})

    def test_hybrid_spec_roles_in_featured_sets(self):
        items = {i['wow_id']: i for i in self.gear['items']}
        expected = {1: {'tank', 'melee'}, 2: {'tank', 'melee', 'healer'},
                    5: {'caster', 'healer'}, 7: {'caster', 'healer', 'melee'},
                    11: {'caster', 'healer', 'melee', 'tank'}}
        for cls, roles in expected.items():
            actual = {r for s in self.gear['sets'] if cls in s['class_ids'] and s['wow_id'] != 699
                      for piece in s['pieces'] for r in items[piece]['roles']}
            self.assertLessEqual(roles, actual, f'class {cls}')

    def test_class_role_policy(self):
        self.assertEqual(self.gear['class_roles'], {
            '1': ['melee', 'tank'], '2': ['melee', 'healer', 'tank'], '3': ['ranged'],
            '4': ['melee'], '5': ['caster', 'healer'], '7': ['melee', 'caster', 'healer'],
            '8': ['caster'], '9': ['caster'], '11': ['melee', 'tank', 'caster', 'healer']})
        # Mage coverage must not depend on fictitious physical roles.
        for item in self.gear['items']:
            if 8 in item['allowable_classes']:
                item['roles'] = [r for r in item['roles'] if r == 'caster'] or ['healer']
        self.assertNotIn('class 8: missing viable role coverage', self.errors())

    def test_generic_utility_is_not_spec_coverage(self):
        for item in self.gear['items']:
            if len(item['roles']) < 5:
                item['roles'] = [r for r in item['roles'] if r != 'healer'] or ['caster']
        self.assertIn('class 2: missing viable role coverage', self.errors())

    def role_row(self, stats=(), **fields):
        row = dict({'class': 4, 'subclass': 0, 'AllowableClass': -1}, **fields)
        for n in range(1, 11):
            row[f'stat_type{n}'], row[f'stat_value{n}'] = stats[n - 1] if n <= len(stats) else (0, 0)
        return row

    def test_roles_do_not_invent_specializations(self):
        self.assertEqual(rewards.roles(self.role_row()), [])
        self.assertEqual(rewards.roles(self.role_row([(4, 20), (7, 20)])), ['melee'])
        self.assertEqual(rewards.roles(self.role_row([(3, 20), (5, 20)])), ['melee', 'ranged'])
        self.assertEqual(set(rewards.roles(self.role_row([(7, 20)]))),
                         {'caster', 'healer', 'melee', 'ranged', 'tank'})
        self.assertEqual(rewards.roles(self.role_row([(5, 20)])), ['caster', 'healer'])

    def test_classic_spell_bonuses_and_triggered_effects(self):
        spell = [0] * 119
        # Blade of Wizardry's spell 34611 has these actual DBC effects.
        spell[95:98], spell[110:113] = [13, 135, 0], [126, 126, 0]
        dbc = {'Spell': SimpleNamespace(by_id={34611: spell})}
        row = self.role_row(spellid_1=34611, spelltrigger_1=1)
        self.assertEqual(rewards.roles(row, dbc), ['caster', 'healer'])
        spell[95:98] = [99, 124, 0]  # Classic Attack Power equip aura.
        self.assertEqual(rewards.roles(row, dbc), ['melee', 'ranged'])
        trigger = [0] * 119
        trigger[116] = 34611
        dbc['Spell'].by_id[123] = trigger
        row['spellid_1'] = 123
        self.assertEqual(rewards.roles(row, dbc), ['melee', 'ranged'])
        spell[80:83] = [0xFFFFFFFF, 0xFFFFFFFF, 0]
        self.assertEqual(rewards.roles(row, dbc), [])

    def test_feral_and_hunter_sets_are_not_caster_gear(self):
        sets = {s['wow_id']: s for s in self.gear['sets']}
        items = {i['wow_id']: i for i in self.gear['items']}
        for sid in (640, 676, 798, 651, 669, 794):
            for piece in sets[sid]['pieces']:
                self.assertFalse({'caster', 'healer'} & set(items[piece]['roles']), piece)

    def test_legendary_mask_and_future_proficiency(self):
        items = {i['wow_id']: i for i in self.gear['items']}
        self.assertEqual(items[32837]['allowable_classes'], [1, 4])
        self.assertEqual(items[32838]['allowable_classes'], [1, 4])
        self.assertEqual(items[49623]['allowable_classes'], [1, 2])
        self.assertNotIn(8, items[46017]['allowable_classes'])
        self.assertNotIn(11, items[19019]['allowable_classes'])
        self.assertIn(4, items[19019]['allowable_classes'])
        self.assertIn(7, items[17182]['allowable_classes'])
        self.assertEqual(set(rewards.LEGENDS), {i['wow_id'] for i in items.values() if i['quality'] == 5})

    def test_ability_id_rejected(self):
        self.abilities['abilities'][0]['ap_id'] += 1
        self.assertIn('incorrect AP ID', self.errors())

    def test_overlapping_rank_rejected(self):
        self.abilities['abilities'][1]['ranks'].append(100)
        self.assertIn('overlapping ranks', self.errors())

    def test_missing_bank_eligibility_rejected(self):
        self.abilities['abilities'][0]['prerequisites'] = []
        self.assertIn('missing rank eligibility', self.errors())

    def test_bank_levels_and_baseline_requirements(self):
        spells = {a['base_spell']: a for a in self.abilities['abilities']}
        self.assertEqual(spells[6552]['min_level'], 38)
        self.assertIn({'kind': 'baseline_spells', 'spell_ids': [2458]}, spells[6552]['prerequisites'])
        self.assertIn({'kind': 'baseline_spells', 'spell_ids': [768]}, spells[1850]['prerequisites'])
        self.assertEqual(spells[370]['ranks'], [370, 8012])
        self.assertEqual([p['min_level'] for p in spells[370]['prerequisites'] if p['kind'] == 'rank_eligibility'], [12, 32])
        self.assertNotIn(8012, spells)
        for essential in (2457, 2458, 71, 768, 5487, 883, 688):
            self.assertNotIn(essential, spells)

    def test_dk_explicitly_excluded(self):
        self.assertNotIn(6, rewards.CLASSES)
        self.abilities['abilities'][0]['class_id'] = 6
        self.assertIn('exclude DK', self.errors())

    def source_fixture(self, talent=False, class_mask=128):
        spell = [0] * 137
        spell[39] = 20
        return {
            'Talent': SimpleNamespace(rows=[(1, 0, 0, 0, 1953, 0, 0, 0, 0)] if talent else []),
            'Spell': SimpleNamespace(by_id={1953: spell}, text=lambda offset: 'Blink'),
            'SkillLineAbility': SimpleNamespace(rows=[(1, 237, 1953, 0, class_mask)]),
        }

    def test_talent_granted_source_rejected(self):
        with patch.object(rewards, 'CANDIDATES', {8: [1953]}), patch.object(rewards, 'query', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'talent spell'):
                rewards.curate_abilities(self.source_fixture(talent=True), [])

    def test_missing_trainer_source_rejected(self):
        with patch.object(rewards, 'CANDIDATES', {8: [1953]}), patch.object(rewards, 'query', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'no trainer'):
                rewards.curate_abilities(self.source_fixture(), [])

    def test_wrong_class_source_rejected(self):
        with patch.object(rewards, 'CANDIDATES', {8: [1953]}), patch.object(rewards, 'query', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'no class skill-line'):
                rewards.curate_abilities(self.source_fixture(class_mask=1), [])

    def test_nonbase_rank_source_rejected(self):
        chain = [{'first_spell_id': '1', 'spell_id': '1953', 'rank': '2'}]
        with patch.object(rewards, 'CANDIDATES', {8: [1953]}), patch.object(rewards, 'query', return_value=chain):
            with self.assertRaisesRegex(ValueError, 'not the first rank'):
                rewards.curate_abilities(self.source_fixture(), [])

    def test_read_only_boundary(self):
        with patch.object(rewards.subprocess, 'run') as run:
            for sql in ('DELETE FROM item_template', 'SELECT 1; DROP TABLE item_template', 'UPDATE npc_trainer SET ReqLevel=1'):
                with self.assertRaises(ValueError):
                    rewards.query(sql)
            run.assert_not_called()

    def test_bad_dbc_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'bad.dbc'
            file.write_bytes(b'FAIL' + bytes(16))
            with self.assertRaisesRegex(ValueError, 'invalid DBC'):
                rewards.Dbc(file)


if __name__ == '__main__':
    unittest.main()
