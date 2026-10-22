"""Execute production menu policies and generator validation; optionally exercise SQL in an isolated schema."""
import copy
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('merchant_sql', ROOT / 'tools/build_world_sql.py')
world = importlib.util.module_from_spec(spec)
spec.loader.exec_module(world)


def fixture():
    return [dict(id=str(i + 1), name=world.SOURCES.get(city, city), map=str(map_id),
                 position_x=str(i * 100), position_y='20', position_z='30', orientation='1')
            for i, (city, map_id) in enumerate(world.CITIES)]


class MerchantTests(unittest.TestCase):
    def test_production_cpp_menu_policies(self):
        source = r'''
#include "APMerchant.h"
#include <cassert>
#include <set>
#include <limits>
using namespace WoWPilago::Merchant;
int main()
{
    assert(Category(13, 0) == 0 && Category(14, 0) == 0 && Category(23, 0) == 0);
    assert(Category(5, 0) == 1 && Category(16, 0) == 1);
    assert(Category(2, 0) == 2 && Category(11, 0) == 2 && Category(12, 0) == 2);
    assert(Category(5, 100) == 3);
    for (unsigned count = 30; count <= 120; ++count)
    {
        std::vector<Stock> stock;
        std::uint64_t cost = 0;
        for (unsigned i = 0; i < count; ++i)
        {
            stock.push_back({static_cast<std::uint16_t>(i), 10000+i, i%8+1, i%4, i%3==0});
            if (i%3) cost += i%8+1;
        }
        assert(RemainingCost(stock) == cost);
        std::set<unsigned> seen;
        for (unsigned category=0; category<4; ++category)
            for (unsigned page=0; page<10; ++page)
            {
                auto rows=Page(stock,category,page);
                assert(rows.size() <= PageSize && rows.size()+4 < 32);
                for (auto const& row: rows)
                {
                    assert(row.category == category && seen.insert(row.index).second);
                    auto selected = Selection(stock, BuyAction+row.index);
                    assert(row.sold ? selected == nullptr : selected && selected->entry == row.entry);
                }
            }
        assert(seen.size() == count); // Sold entries remain visible as well.
        assert(!Selection(stock, BuyAction+count));
        assert(!Selection(stock, 0) && !Selection(stock, BuyAction-1));
        assert(!Selection(stock, std::numeric_limits<std::uint32_t>::max()));
        assert(Page(stock,4,0).empty() && Page(stock,0,10).empty());
        // Every entry in one category still fits ten pages, including 120-entry configurations.
        for (auto& row: stock) row.category=0;
        unsigned total=0;
        for (unsigned page=0; page<10; ++page) total += Page(stock,0,page).size();
        assert(total == count);
        auto other=stock;
        other[1].entry=999;
        assert(Selection(other,BuyAction+1)->entry==999);
        assert(Selection(stock,BuyAction+1)->entry==10001); // No shared NPC stock.
    }
}
'''
        with tempfile.TemporaryDirectory(prefix='merchant-policy-') as directory:
            path = Path(directory)
            (path / 'test.cpp').write_text(source)
            subprocess.run([shutil.which('g++') or 'clang++', '-std=c++17', '-Wall', '-Wextra',
                            '-Werror', '-fsanitize=undefined', '-I', str(ROOT / 'src'),
                            str(path / 'test.cpp'), '-o', str(path / 'test')], check=True)
            subprocess.run([str(path / 'test')], check=True)

    def test_generator_rerun_and_source_guards(self):
        teleports = fixture()
        sql = world.generate(teleports, [], [], [])
        self.assertEqual(sql.count('INSERT INTO creature (guid,'), 10)
        own = [dict(entry=str(world.ENTRY), name=world.NAME, ScriptName=world.SCRIPT)]
        spawns = [dict(guid=str(world.FIRST_GUID+i), id=str(world.ENTRY), Comment=world.MARKER)
                  for i in range(10)]
        self.assertEqual(sql, world.generate(teleports, own, spawns, []))
        for templates, creatures in [([dict(own[0], name='Foreign')], []),
                                     ([], [dict(spawns[0], id='1')]),
                                     ([], [dict(spawns[0], Comment='Foreign')]),
                                     ([], [dict(spawns[0], guid='123')])]:
            with self.assertRaises(ValueError):
                world.generate(teleports, templates, creatures, [])
        for key, value in [('map', '999'), ('position_x', 'nan'), ('position_y', '20000')]:
            bad = copy.deepcopy(teleports)
            bad[0][key] = value
            with self.assertRaises(ValueError):
                world.generate(bad, [], [], [])
        with self.assertRaises(ValueError):
            world.generate(teleports[1:], [], [], [])
        with self.assertRaises(ValueError):
            world.generate(teleports + [teleports[0]], [], [], [])
        near = dict(teleports[0], guid='1', id='1')
        with self.assertRaises(ValueError):
            world.generate(teleports, [], [], [near])
        near['map'] = '999'
        world.generate(teleports, [], [], [near])
        for sql in ['DELETE FROM creature', 'SELECT 1; DELETE FROM creature', 'SELECT @x', 'SELECT 1 -- hi']:
            with self.assertRaises(ValueError):
                world.query(sql)

    @unittest.skipUnless(os.environ.get('WOWPILAGO_MERCHANT_SQL_TEST') == '1',
                         'set WOWPILAGO_MERCHANT_SQL_TEST=1 for disposable MySQL schema tests')
    def test_sql_install_rerun_and_collisions(self):
        # Unique test schema only. Never execute installation against acore_world.
        schema = 'wowpilago_merchant_test_' + uuid.uuid4().hex[:12]
        env = dict(os.environ, MYSQL_PWD=os.environ['WOWPILAGO_DB_PASSWORD'])
        command = ['docker', 'run', '--rm', '-i', '--network', 'host', '-e', 'MYSQL_PWD', 'mysql:8.4',
                   'mysql', '--protocol=TCP', '-h127.0.0.1', '-P13317', '-uroot', '--batch', '--raw']

        def execute(sql, success=True):
            result = subprocess.run(command, input=sql, env=env, capture_output=True, text=True)
            if success:
                self.assertEqual(result.returncode, 0, result.stderr)
            else:
                self.assertNotEqual(result.returncode, 0)
                self.assertRegex(result.stderr, 'collision|overlap')
            return result.stdout

        try:
            execute(f'CREATE DATABASE {schema};')
            prefix = f'USE {schema};\n'
            execute(prefix + '''
CREATE TABLE creature_template LIKE acore_world.creature_template;
CREATE TABLE creature_template_model LIKE acore_world.creature_template_model;
CREATE TABLE creature LIKE acore_world.creature;
INSERT INTO creature_template (entry,name,ScriptName) VALUES (42,'Foreign','foreign_script');
INSERT INTO creature (guid,id,map,position_x,position_y,position_z,orientation,spawntimesecs,Comment)
VALUES (42,42,0,15000,15000,0,0,120,'foreign');
''')
            sql = (ROOT / 'sql/world.sql').read_text()
            execute(prefix + sql)
            execute(prefix + sql)
            result = execute(prefix + 'SELECT COUNT(*) AS n FROM creature WHERE id=900500;'
                             'SELECT name FROM creature_template WHERE entry=42;')
            self.assertIn('\n10\n', result)
            self.assertIn('Foreign', result)
            execute(prefix + "UPDATE creature_template SET ScriptName='foreign' WHERE entry=900500;")
            execute(prefix + sql, success=False)
            execute(prefix + "UPDATE creature_template SET ScriptName='archipelago_merchant' WHERE entry=900500;"
                    "UPDATE creature SET id=42 WHERE guid=9005000;")
            execute(prefix + sql, success=False)
            self.assertIn('\n42\n', execute(prefix + 'SELECT id FROM creature WHERE guid=9005000;'))
            execute(prefix + "UPDATE creature SET id=900500 WHERE guid=9005000;"
                    "INSERT INTO creature (guid,id,Comment) VALUES (43,900500,'WoWPilago merchant v2');")
            execute(prefix + sql, success=False)
            execute(prefix + 'DELETE FROM creature WHERE guid=43;'
                    'INSERT INTO creature (guid,id,map,position_x,position_y,position_z) '
                    'SELECT 44,42,map,position_x,position_y,position_z FROM creature WHERE guid=9005000;')
            execute(prefix + sql, success=False)
            self.assertIn('\n12\n', execute(prefix + 'SELECT COUNT(*) FROM creature WHERE id=42 OR id=900500;'))
        finally:
            execute(f'DROP DATABASE IF EXISTS {schema};')


if __name__ == '__main__':
    unittest.main()
