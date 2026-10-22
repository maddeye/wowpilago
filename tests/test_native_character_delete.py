"""Extracted production hook + in-memory SQLite FIFO/FK model, not MySQL or core proof."""
import pathlib
import shutil
import sqlite3
import subprocess
import tempfile
import unittest

from test_native_progression import production_method

ROOT = pathlib.Path(__file__).resolve().parents[1]
HISTORIES = ("reward", "check", "progress", "stock", "purchase", "boss_credit",
             "enabled_check", "allowed_reward", "ability")
BINDING = (1 << 32) + 7


class NativeCharacterDeleteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("g++") or shutil.which("clang++")
        if compiler is None:
            raise AssertionError("a C++17 compiler is required")
        hook = production_method((ROOT / "src/APProgression.cpp").read_text(),
                                 "void OnPlayerDeleteFromDB(")
        source = r'''
#include <cassert>
#include <cstdint>
#include <iostream>
#include <memory>
#include <string>
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
std::string Format(std::string sql, uint64 value)
{
    auto at = sql.find("{}");
    assert(at != std::string::npos);
    sql.replace(at, 2, std::to_string(value));
    assert(sql.find("{}") == std::string::npos);
    return sql;
}
struct Field { uint64 value; template<class T> T Get() const { return T(value); } };
struct Result { Field field; Field* Fetch() { return &field; } };
using QueryResult = std::shared_ptr<Result>;
struct Database
{
    QueryResult Query(char const* sql, uint32 guid)
    {
        std::cout << "QUERY " << Format(sql, guid) << std::endl;
        std::string answer;
        assert(bool(std::getline(std::cin, answer)));
        if (answer == "ERROR")
        {
            std::cerr << "simulated core SQL read error\n";
            return nullptr;
        }
        if (answer == "NULL") return nullptr;
        return std::make_shared<Result>(Result{{std::stoull(answer)}});
    }
} CharacterDatabase;
struct Transaction
{
    void Append(char const* sql, uint64 value)
    {
        std::cout << "APPEND " << Format(sql, value) << std::endl;
    }
};
using CharacterDatabaseTransaction = std::shared_ptr<Transaction>;
struct PlayerScript
{
    virtual ~PlayerScript() = default;
    virtual void OnPlayerDeleteFromDB(CharacterDatabaseTransaction, uint32) = 0;
};
struct Hook : PlayerScript
{
''' + hook + r'''
};
int main(int argc, char** argv)
{
    assert(argc == 2);
    auto guid = std::stoull(argv[1]);
    assert(guid <= UINT32_MAX);
    Hook().OnPlayerDeleteFromDB(std::make_shared<Transaction>(), uint32(guid));
}
'''
        cls.directory = tempfile.TemporaryDirectory(prefix="wowpilago-delete-")
        cls.addClassCleanup(cls.directory.cleanup)
        path = pathlib.Path(cls.directory.name)
        (path / "check.cpp").write_text(source)
        cls.binary = path / "check"
        subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=undefined", "-fno-sanitize-recover=all",
                        str(path / "check.cpp"), "-o", str(cls.binary)], check=True)

    def database(self, guid, bound=True, status="connected"):
        db = sqlite3.connect(":memory:", isolation_level=None)
        self.addCleanup(db.close)
        db.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE characters (guid INTEGER PRIMARY KEY);
            CREATE TABLE mod_archipelago_binding (
                id INTEGER PRIMARY KEY, character_guid INTEGER UNIQUE,
                status TEXT NOT NULL, seed_name TEXT NOT NULL, slot INTEGER NOT NULL,
                UNIQUE(seed_name,slot),
                FOREIGN KEY(character_guid) REFERENCES characters(guid) ON DELETE SET NULL);
        """)
        self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone(), (1,))
        db.executemany("INSERT INTO characters VALUES (?)", [(guid,), (42,)])
        db.executemany("INSERT INTO mod_archipelago_binding VALUES (?,?,?,?,?)", [
            (BINDING, guid if bound else None, status, "seed", 1),
            (8, 42, "connected", "seed", 2),
            (9, None, "disconnected", "seed", 3)])
        # Reduced history payloads and binding FKs, not the production MySQL schema.
        for table in HISTORIES:
            db.execute(f"CREATE TABLE mod_archipelago_{table} ("
                       "binding_id INTEGER REFERENCES mod_archipelago_binding(id), payload TEXT)")
            db.executemany(f"INSERT INTO mod_archipelago_{table} VALUES (?,?)",
                           [(binding, f"{table}:{binding}:{state}")
                            for binding in (BINDING, 8, 9)
                            for state in (("pending", "applied") if table == "reward" else ("history",))])
        return db

    def snapshot(self, db):
        tables = ("characters", "mod_archipelago_binding") + tuple(
            f"mod_archipelago_{table}" for table in HISTORIES)
        return {table: db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
                for table in tables}

    def deletion(self, db, guid, read_error=False):
        # Pinned Player.cpp queues CHAR_DEL_CHARACTER before invoking the hook.
        statements = [f"DELETE FROM characters WHERE guid = {guid}"]
        queries = []
        with subprocess.Popen([str(self.binary), str(guid)], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
            try:
                for line in process.stdout:
                    kind, sql = line.rstrip("\n").split(" ", 1)
                    if kind == "QUERY":
                        queries.append(sql)
                        row = db.execute(sql).fetchone()
                        answer = "ERROR" if read_error else str(row[0]) if row else "NULL"
                        process.stdin.write(answer + "\n")
                        process.stdin.flush()
                    else:
                        self.assertEqual(kind, "APPEND")
                        statements.append(sql)
                code = process.wait(timeout=10)
                diagnostics = process.stderr.read()
                self.assertEqual(code, 0, diagnostics)
                self.assertEqual(diagnostics, "simulated core SQL read error\n" if read_error and queries else "")
            finally:
                if process.poll() is None:
                    process.kill()
        return statements, queries

    def execute(self, db, statements):
        db.execute("BEGIN")
        for sql in statements:
            db.execute(sql)

    def assert_histories(self, db, before):
        after = self.snapshot(db)
        for table in before:
            if table not in ("characters", "mod_archipelago_binding"):
                self.assertEqual(after[table], before[table], table)
        self.assertEqual([row for row in after["mod_archipelago_binding"] if row[0] != BINDING],
                         [row for row in before["mod_archipelago_binding"] if row[0] != BINDING])
        self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_bound_fifo_archive_and_same_guid_replacement(self):
        for guid in (0, 1, (1 << 31) - 1, 1 << 31, (1 << 32) - 1):
            for status in ("connected", "disconnected", "archived"):
                with self.subTest(guid=guid, status=status):
                    db = self.database(guid, status=status)
                    before = self.snapshot(db)
                    statements, queries = self.deletion(db, guid)
                    self.assertEqual(self.snapshot(db), before, "hook must only append writes")
                    self.execute(db, statements)
                    db.execute("COMMIT")
                    self.assertEqual(db.execute(
                        "SELECT character_guid,status FROM mod_archipelago_binding WHERE id=?",
                        (BINDING,)).fetchone(), (None, "archived"))
                    self.assertEqual(len(queries), 1)
                    self.assertEqual(len(statements), 2)
                    self.assert_histories(db, before)
                    db.execute("INSERT INTO characters VALUES (?)", (guid,))
                    self.assertEqual(db.execute(
                        "SELECT id FROM mod_archipelago_binding WHERE character_guid=?",
                        (guid,)).fetchall(), [])
                    self.assert_histories(db, before)
                    with self.assertRaises(sqlite3.IntegrityError):
                        db.execute("INSERT INTO mod_archipelago_binding VALUES (99,?,'connected','seed',1)",
                                   (guid,))

    def test_unbound_deletion_does_not_archive_detached_rows(self):
        db = self.database(1, bound=False)
        before = self.snapshot(db)
        statements, queries = self.deletion(db, 1)
        self.assertEqual(len(queries), 1)
        self.assertEqual(len(statements), 1, "unbound lookup must not append an update")
        self.execute(db, statements)
        db.execute("COMMIT")
        self.assertEqual(db.execute("SELECT guid FROM characters").fetchall(), [(42,)])
        after = self.snapshot(db)
        for table in before:
            if table != "characters":
                self.assertEqual(after[table], before[table])

    def test_rollback_restores_delete_and_archive_after_late_failure(self):
        db = self.database(1)
        before = self.snapshot(db)
        statements, _ = self.deletion(db, 1)
        self.execute(db, statements)
        self.assertEqual(db.execute(
            "SELECT character_guid,status FROM mod_archipelago_binding WHERE id=?",
            (BINDING,)).fetchone(), (None, "archived"))
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO characters VALUES (42)")
        db.execute("ROLLBACK")
        self.assertEqual(self.snapshot(db), before)

    def test_first_binding_created_after_lookup_relies_on_fk_detachment(self):
        db = self.database(1, bound=False)
        statements, queries = self.deletion(db, 1)
        self.assertEqual(len(queries), 1)
        self.assertEqual(len(statements), 1)
        # A synchronous lookup is not a lock held until the queued core transaction.
        db.execute("UPDATE mod_archipelago_binding SET character_guid=1 WHERE id=?", (BINDING,))
        before = self.snapshot(db)
        self.execute(db, statements)
        db.execute("COMMIT")
        self.assertEqual(db.execute(
            "SELECT character_guid,status FROM mod_archipelago_binding WHERE id=?",
            (BINDING,)).fetchone(), (None, "connected"))
        self.assert_histories(db, before)

    def test_read_error_limit_is_detached_but_not_immediately_archived(self):
        db = self.database(1)
        before = self.snapshot(db)
        statements, queries = self.deletion(db, 1, read_error=True)
        self.assertEqual(len(queries), 1)
        self.assertEqual(len(statements), 1)
        self.execute(db, statements)
        db.execute("COMMIT")
        self.assertEqual(db.execute(
            "SELECT character_guid,status FROM mod_archipelago_binding WHERE id=?",
            (BINDING,)).fetchone(), (None, "connected"))
        db.execute("INSERT INTO characters VALUES (1)")
        self.assertEqual(db.execute(
            "SELECT id FROM mod_archipelago_binding WHERE character_guid=1").fetchall(), [])
        self.assert_histories(db, before)


if __name__ == "__main__":
    unittest.main()
