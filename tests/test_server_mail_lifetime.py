"""Execute the patched login method and its delayed callback, without a realm or DB."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_core_patch import SOURCE, function, patcher

MAIL_SOURCE = "src/server/scripts/World/server_mail.cpp"


class ServerMailLifetimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_dir() or not shutil.which("c++"):
            raise unittest.SkipTest("pinned core clone and c++ required")
        cls.temp = tempfile.TemporaryDirectory(prefix="wowpilago-mail-test-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.archive = cls.root / "archive"
        cls.archive.mkdir()
        archive = subprocess.run(
            ["git", "-C", str(SOURCE), "archive", patcher.COMMIT, *patcher.FINGERPRINTS],
            stdout=subprocess.PIPE, check=True,
        )
        subprocess.run(["tar", "-x", "-C", str(cls.archive)], input=archive.stdout, check=True)
        cls.work = cls.root / "patched"
        shutil.copytree(cls.archive, cls.work)
        assert patcher.apply(cls.work) == "applied"
        assert patcher.apply(cls.work) == "already applied"
        method = function((cls.work / MAIL_SOURCE).read_text(), "void OnPlayerLogin(")
        program = cls.root / "callback.cpp"
        program.write_text(STUBS + "struct ServerMailReward : PlayerScript {\n" + method + "\n};\n" + CHECKS)
        cls.binary = cls.root / "callback"
        subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror",
                        str(program), "-o", str(cls.binary)], check=True)

    def run_callback(self, scenario):
        subprocess.run([str(self.binary), scenario], check=True)

    def test_delayed_after_logout(self):
        self.run_callback("logout")

    def test_different_character_same_session(self):
        self.run_callback("different")

    def test_same_character_current(self):
        self.run_callback("same")

    def test_already_rewarded(self):
        self.run_callback("rewarded")

    def test_mail_source_required_and_fingerprinted(self):
        for state in ("missing", "modified", "unsafe"):
            with self.subTest(state=state):
                target = self.root / state
                shutil.copytree(self.archive, target)
                mail = target / MAIL_SOURCE
                if state == "modified":
                    mail.write_text(mail.read_text() + "\n// dirty\n")
                else:
                    mail.unlink()
                    if state == "unsafe":
                        mail.symlink_to(self.archive / MAIL_SOURCE)
                before = {p: p.read_bytes() for p in target.rglob("*") if p.is_file()}
                with self.assertRaisesRegex(ValueError, "core source"):
                    patcher.apply(target)
                self.assertEqual(before, {p: p.read_bytes() for p in target.rglob("*") if p.is_file()})


STUBS = r'''
#include <cassert>
#include <cstdint>
#include <functional>
#include <map>
#include <string>
#include <utility>
#include <vector>
using uint32 = uint32_t;
struct ObjectGuid {
    uint64_t value;
    uint32 GetCounter() const { return uint32(value); }
    bool operator==(ObjectGuid const&) const = default;
};
constexpr int TEAM_ALLIANCE = 0, CHAR_SEL_MAIL_SERVER_CHARACTER = 1;
using PreparedQueryResult = bool;
struct ServerMailItems { int id; };
struct ServerMailCondition { int id; };
struct ServerMail {
    uint32 id = 39713, senderEntry = 19506, moneyA = 10, moneyH = 20;
    std::vector<ServerMailItems> itemsA{{1}}, itemsH{{2}};
    std::vector<ServerMailCondition> conditions{{8}};
    std::string subject = "test", body = "body";
};
struct CharacterDatabasePreparedStatement {
    uint32 guid = 0, mail = 0;
    void SetData(int index, uint32 value) { (index == 0 ? guid : mail) = value; }
};
using Callback = std::function<void(PreparedQueryResult)>;
struct Query {
    Callback WithPreparedCallback(Callback callback) { return callback; }
};
struct Database {
    CharacterDatabasePreparedStatement stmt;
    auto* GetPreparedStatement(int id) { assert(id == CHAR_SEL_MAIL_SERVER_CHARACTER); return &stmt; }
    Query AsyncQuery(CharacterDatabasePreparedStatement* value) { assert(value == &stmt); return {}; }
} CharacterDatabase;
struct Processor {
    std::vector<Callback> pending;
    void AddCallback(Callback callback) { pending.push_back(std::move(callback)); }
    void Complete(bool rewarded) {
        auto ready = std::move(pending);
        for (auto& callback : ready) callback(rewarded);
    }
};
struct Player;
struct WorldSession {
    Player* current = nullptr;
    Processor processor;
    Player* GetPlayer() { return current; }
    Processor& GetQueryProcessor() { return processor; }
};
struct Player {
    WorldSession* session;
    ObjectGuid guid;
    int team;
    WorldSession* GetSession() { return session; }
    ObjectGuid GetGUID() const { return guid; }
    int GetTeamId() { return team; }
};
struct PlayerScript { virtual void OnPlayerLogin(Player*) = 0; };
struct MailManager {
    std::map<uint32, ServerMail> store{{39713, ServerMail{}}};
    int deliveries = 0;
    Player* recipient = nullptr;
    auto const& GetAllServerMailStore() { return store; }
    void SendServerMail(Player* player, uint32 id, uint32 sender, uint32 money,
                        std::vector<ServerMailItems> const& items,
                        std::vector<ServerMailCondition> const& conditions,
                        std::string const& subject, std::string const& body) {
        assert(player);
        auto const& mail = store.at(id);
        assert(id == mail.id && sender == mail.senderEntry);
        bool alliance = player->GetTeamId() == TEAM_ALLIANCE;
        assert(money == (alliance ? mail.moneyA : mail.moneyH));
        assert(&items == (alliance ? &mail.itemsA : &mail.itemsH));
        assert(&conditions == &mail.conditions && subject == mail.subject && body == mail.body);
        ++deliveries;
        recipient = player;
    }
} manager, *sServerMailMgr = &manager;
'''

CHECKS = r'''
int main(int argc, char** argv) {
    assert(argc == 2);
    std::string scenario = argv[1];
    for (int team : {TEAM_ALLIANCE, 1}) {
        manager.deliveries = 0;
        manager.recipient = nullptr;
        WorldSession session;
        Player original{&session, ObjectGuid{22}, team};
        // Same low counter, different full GUID: compare ObjectGuid, not just counter.
        Player other{&session, ObjectGuid{(uint64_t(1) << 32) | 22}, team};
        session.current = &original;
        ServerMailReward reward;
        reward.OnPlayerLogin(&original);
        assert(session.processor.pending.size() == 1 && manager.deliveries == 0);
        assert(CharacterDatabase.stmt.guid == 22 && CharacterDatabase.stmt.mail == 39713);
        if (scenario == "logout") session.current = nullptr;
        else if (scenario == "different") session.current = &other;
        else assert(scenario == "same" || scenario == "rewarded");
        session.processor.Complete(scenario == "rewarded");
        bool delivered = scenario == "same";
        assert(manager.deliveries == (delivered ? 1 : 0));
        assert(manager.recipient == (delivered ? &original : nullptr));
    }
}
'''


if __name__ == "__main__":
    unittest.main()
