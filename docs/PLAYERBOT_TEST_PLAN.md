# Playerbot-assisted verification plan

Status: source investigation only. Every runtime action below is UNTESTED by this investigation. Nothing here authorizes a restart, character creation, config edit, or DB write. Only this document was created. No preparation script is needed for the bounded manual route.

## 1. Freeze and approval gate

1. Parent must first close the smoke gate recorded in `docs/PLAYTHROUGH.md`, obtain explicit merchant/pilot agent release, and approve a maintenance window. Never restart or reload while those agents are live. Do not run existing provisioning or verification scripts merely to prepare bots. Some create fixtures or modify state.
2. Use only the private realm and private client. Preserve APV2A / Apjourney / GUID 4 as the normal security-0 human AP character. APV2B/C/D remain other agents' fixtures. Never use TEST1/2/3. Never modify the original dirty core or playerbots checkout.
3. Match the deployed binary to the selected manifest before enabling. Investigated source root, abbreviated `S` below, is `.local/v2-build/20261019T150600.624050Z/source`. `post-curation-manifest.json` pins core `9fb906bb7296212ff42fc95ff73a92aaf8554f0d`, playerbots `2f7d9f774987d0157c6a0d0cc08c40bec3db3945`, and the three-effect Factory bounds patch `cc41814799c3aba0c994c66d9bcfa58fc9bcc86ba9144c3a9aa728bda796fd0a`. Do not assume the source directory alone proves which binary is running.
4. Record baseline config/binary hashes, account/character roster, binding/check/reward rows, XP/money/items/quests, and the current AP room/save. Existing earned checks and legitimate AP rewards are not reset. `docs/LIVE_V2.md` records prior connectivity evidence, not a new result from this plan.
5. STOP on an unexpected account, binding, level, item, bot, or startup write. Preserve evidence. Do not repair state with SQL, GM commands, or character deletion.

### Read-only preflight for the parent

Run these SELECTs only through the parent's existing private read-only DB connection. They were not executed here. A failed query is a blocker, not permission to create a table. Do not print credentials.

```sql
SELECT a.id,a.username,c.guid,c.name,c.race,c.class,c.level,c.xp,c.money,c.online,
       c.map,c.zone,c.position_x,c.position_y,c.position_z
FROM acore_auth.account a
LEFT JOIN acore_characters.characters c ON c.account=a.id
WHERE a.username IN ('APV2A','APV2B','APV2C','APV2D')
ORDER BY a.username,c.guid;

SELECT id,character_guid,character_name,character_account,seed_name,team,slot,status
FROM acore_characters.mod_archipelago_binding
ORDER BY id;

SELECT account_type,COUNT(*) AS accounts
FROM acore_playerbots_v2.playerbots_account_type GROUP BY account_type;
SELECT COUNT(*) AS random_bot_rows
FROM acore_playerbots_v2.playerbots_random_bots;
SELECT COUNT(*) AS linked_accounts
FROM acore_playerbots_v2.playerbots_account_links;
SELECT id,username FROM acore_auth.account
WHERE LEFT(LOWER(username),6)='rndbot';
```

Require APV2A to contain only the known Apjourney before creation; afterward it must contain only Apjourney and the explicitly approved one or two new helpers. Require no helper binding, no APV2A random/addclass classification, no existing account links, no random-bot rows, no random account prefix matches, and an empty `playerbots_account_type` table. Inspect actual account access entries to confirm APV2A security 0; do not grant GM rights. If the private prefix differs from the pinned default `rndbot`, check that prefix instead too.

Why such a strict empty-pool gate? `RandomPlayerbotFactory::CalculateTotalAccountCount`, lines 318–428, returns existing account-type totals even when the requested random count is zero. `CreateRandomBots`, lines 453–704, then loops that total to create accounts/characters. Zero config counts alone are NOT a universal no-creation guarantee. With all three requested counts zero and no existing pool, the calculated total is zero. Startup still submits account-type UPDATEs and may initialize module data. Enabling is not read-only, even with zero bots. Parent must approve those private-module writes later, after checking the pool. Do not clean up a nonempty pool to make this gate pass.

## 2. Proposed manual-only config change

Target only `.local/v2-realm/config/modules/playerbots.conf`, during the approved window. This is a proposed diff, NOT applied. Keep every existing explicit disabling line and DB setting. Change the existing Enabled line and append only the absent keys below. Reject duplicate keys rather than relying on parse order.

```diff
-AiPlayerbot.Enabled = 0
+AiPlayerbot.Enabled = 1
+AiPlayerbot.AllowAccountBots = 1
+AiPlayerbot.AllowGuildBots = 0
+AiPlayerbot.AllowTrustedAccountBots = 0
+AiPlayerbot.MaxAddedBots = 2
+AiPlayerbot.BotCheats = ""
+AiPlayerbot.SummonWhenGroup = 0
+AiPlayerbot.SummonAtInnkeepersEnabled = 0
+AiPlayerbot.ReviveBotWhenSummoned = 0
+AiPlayerbot.BotRepairWhenSummon = 0
+AiPlayerbot.SyncQuestWithPlayer = 0
+AiPlayerbot.SyncQuestForPlayer = 0
```

This is the smallest proposed safety diff over the inspected private config, not a standalone replacement. `MaxAddedBots = 1` is sufficient if only one helper is approved. It limits the master's loaded/loading bots, not an explicit character allowlist. Same-account characters are the permission boundary; never add AP characters, including Apjourney, as bots.

The current file already explicitly keeps the following disabled. Recheck their effective values before any start:

| Area | Values that must remain |
| --- | --- |
| Population/login | `RandomBotAutologin=0`, `BotAutologin=0`, `MinRandomBots=0`, `MaxRandomBots=0`, `RandomBotAccountCount=0`, `AddClassAccountPoolSize=0`, `AddClassCommand=0`, `EnablePeriodicOnlineOffline=0` |
| Destructive/social generation | `DeleteRandomBotAccounts=0`, `DeleteRandomBotGuilds=0`, `DeleteRandomBotArenaTeams=0`, `RandomBotGuildCount=0`, all three `RandomBotArenaTeam{2v2,3v3,5v5}Count=0` |
| Progression | `AutoDoQuests=0`, `AutoUpgradeEquip=0`, `AutoLearnQuestSpells=0`, `AutoLearnTrainerSpells=0`, `AutoPickTalents=0`, `AutoTeleportForLevel=0`, `LevelBrackets.Enabled=0`, `ResetBotLevel.Enabled=0`, `DisableRandomLevels=1`, `RandombotStartingLevel=1` |
| Human/control | `SelfBotLevel=0`, `CommandServerPort=0`, `RandomBotJoinBG=0`, `RandomBotAutoJoinBG=0`, `Playerbots.Updates.EnableDatabases=0` |

All names in the table have prefix `AiPlayerbot.` except `Playerbots.Updates.EnableDatabases`. Key spelling, including `RandombotStartingLevel`, matters. Ordinary loot upgrades are not Factory gear generation. Do not disable normal earned loot/equipment use merely because `AutoEquipUpgradeLoot` exists.

Pinned source evidence under `S/modules/mod-playerbots/`:

| Source | What it establishes |
| --- | --- |
| `src/PlayerbotAIConfig.cpp:184–186,243–244,545–564,626–644,715–750` | Account permissions, login, default cheats `food,taxi,raid`, summon defaults, quest sync, progression and selfbot keys. An empty cheat list yields no configured cheat bits. |
| `conf/playerbots.conf.dist:136–189,447–451,631` | Shipped descriptions/defaults, not safe values to copy wholesale. |
| `src/Bot/PlayerbotMgr.cpp:83–145,583–604` | Same-account login allowed; guild/linked/addclass alternatives; cap counts loading bots; addclass accounts can be Factory-randomized on login. Helpers must not be in that pool. |
| `src/Ai/Base/Actions/TalkToQuestGiverAction.cpp:27–45` and `QuestAction.cpp:187–250` | Quest synchronization can call `CompleteQuest`, bypass distance, and fall back to `AddQuest`. Both sync settings must be zero for honest objective evidence. |
| `src/Script/WorldThr/PlayerbotOperations.h:35–89` | Bot add creates/joins a real group; default group summon can teleport the helper. Disable it, start helpers locally, and walk. |

`AutoDoQuests=0` does not by itself disable quest-sync completion. `BotCheats=""` does not prohibit a later chat `cheat +...` command. Fresh helpers plus a command allowlist are required. No `self`, `initself`, `init`, `refresh`, `random`, `level`, `levelup`, `quests` manager operation, `addclass`, `addaccount`, `rndbot`, autogear, cheat changes, summon, teleport, or reset commands during the normal run. The whispered `quests` inspection/turn-in command below is a different operation from the forbidden manager `quests` Factory operation.

## 3. Fresh helpers and exact ordinary commands

### Normal character creation

1. After approval, use the ordinary APV2A character-selection screen. Click Create New Character. Create one Human Paladin named `Aphelperone`, if available, with ordinary appearance choices. A second Human Priest named `Aphelpertwo` is optional. Do not overwrite an existing name. Use the actually accepted names in every command below.
2. These are ordinary level-1 characters in the same Northshire start as Apjourney, not DKs or template/factory bots. Account limits inspected in private `worldserver.conf` are 10 characters per realm and 50 per account; normal UI/server validation still decides availability. No new account, guild, account link, GM level, item, money, XP, learned spell, or AP binding is created administratively.
3. If needed, enter each helper normally, confirm level 1 and starting possessions/location, then log out through the client. Do not quest on helpers first. Before bot login, use SELECTs to record their actual GUIDs and confirm no rows in `mod_archipelago_binding` for either. Never infer GUIDs as 5/6. Never bind helpers through a seed manifest or AP UI.
4. Log into Apjourney normally. Verify ordinary `.archipelago status` still works and retains the existing slot/cap/rewards. In the pinned snapshot the human predicate is named `Human`, `APProgression.cpp:54–60`, and rejects both a bot session and any PlayerbotAI. This is the safety property referred to as `NativeHuman()` elsewhere. Do not weaken either form. A PlayerbotMgr on a human is not PlayerbotAI.
5. Add one approved helper by name, inspect party frames, then optionally add the second. Wait for completed login before continuing. On an abort, remove only the helper already requested, never try a wildcard.

### Chat allowlist

Type these in Apjourney's ordinary chat box. Full command names avoid uncertain `.bot` aliases. The dot manager commands are registered with `SEC_PLAYER`, not GM, in `src/Script/PlayerbotCommandScript.cpp:34–45`. Parser/help is `PlayerbotMgr.cpp:861–904`; add/remove branches are at 682–715. Whisper handling is in `src/Script/Playerbots.cpp:171` onward.

```text
.playerbots bot
.playerbots bot list
.playerbots bot add Aphelperone
/w Aphelperone help
/w Aphelperone cheat ?
/w Aphelperone follow
/w Aphelperone nc ?
/w Aphelperone co ?
```

`cheat ?` inspects, it does not enable cheats. Require no configured or local active cheats. `help` enumerates supported actions/strategies from this build, `HelpAction.cpp:23–35`. Record its actual output. `nc ?` and `co ?` inspect current noncombat/combat strategies, `ChangeStrategyAction.cpp`. No bare `assist` command is assumed.

For a damage helper, after confirming the help output:

```text
/w Aphelperone nc -travel,-rpg,-grind,-stay
/w Aphelperone co +dps assist
/w Aphelperone follow
```

`ChatShortcutActions.cpp:53–54` implements follow, removing grind/passive and setting follow. `Ai/Base/StrategyContext.h:95,218,238` registers travel/follow/dps assist. Preserve class defaults instead of replacing the whole strategy set. Priest healing behavior must be observed before trusting it; level-1 helpers do not have high-level roles or spells. Repeat per second helper, not a party-wide broadcast.

For one ordinary combat trial, Apjourney selects and tags a nearby level-appropriate enemy through the client, then:

```text
/w Aphelperone attack
```

`ChatCommandHandlerStrategy.cpp:49–51` maps `attack` to attack-my-target and `follow` to its shortcut. Pilot controls navigation, targets, pulls, survival, loot, and turn-ins. No AFK grind or independent travel strategy. Use `/w Aphelperone stay` to stop movement when needed. To resume, whisper `nc -stay` then `follow`; the pinned follow shortcut does not itself remove the noncombat stay strategy. Walk together, use normal transport and resurrection, and pay normal training/repair/travel costs. No bot `summon`, `teleport`, `taxi` shortcut or innkeeper summon.

For quests, pilot accepts through the actual nearby NPC UI. Place helper within interaction range of that NPC and whisper `accept ` followed by a real shift-clicked quest link, not a fabricated hyperlink. `AcceptQuestAction.cpp:32–99` extracts that link and finds the questgiver; `QuestAction.cpp:210–250` uses the normal session accept handler. Avoid `accept *`: the pinned action has an uninitialized local GUID on some wildcard/no-quest paths. Use normal quest sharing UI only for quests actually shareable.

After earning all objectives, select the actual nearby turn-in NPC and whisper:

```text
/w Aphelperone quests
```

This reports/processes the helper's quests at the selected NPC through `QuestAction::Execute` and `TalkToQuestGiverAction`. It may turn in completed helper quests, so it is not read-only. With both sync flags zero, it must not manufacture missing objectives for either character. If choice rewards need another action, stop and consult the actual `help`/`reward` response rather than guessing. The pilot always completes its own turn-in through the normal UI.

### Human pilot automation limit

Helpers follow and assist the human; they do not steer a normal human character. Enabling selfbot to pilot GUID 4 violates AP's human guard and can abort profile validation. Do not try it. The current addon has no quest autoaccept handler found in this inspection. Ordinary visible UI clicks, or a separately reviewed client addon that only accepts an offered nearby quest, could reduce clicks without granting objectives. Neither supplies navigation/combat/full autoplay. No client memory store, direct DB updates, injected completion packets, forged checks, or `CompleteQuest` synchronization is acceptable evidence.

## 4. Verification route and full TODO coverage

### First session, stop after the opening slice

1. Capture baseline `.archipelago status`, actual party frames, helper level/gear/quests, and module startup logs. Confirm no new random accounts or nonapproved online bots after enablement. Re-run read-only roster/pool checks. Any unexpected generation stops the session.
2. At Northshire, use the route already DB-confirmed in `docs/PLAYTHROUGH.md`: Deputy Willem at approximately `-8947.64,-132.319,83.7199`, accept 783 A Threat Within; walk to Marshal McBride at `-8902.59,-162.606,82.0223` and turn it in normally. Each helper accepts/turns in independently and in range. No assertion that quest 783 itself is an enabled AP check.
3. Complete quest 7's eight Kobold Vermin, entry 6, using normal combat. Record one pilot-tag/helper-assist kill and one helper-initiated party kill while the pilot is alive and nearby. Compare actual objective/XP changes, not just combat text. Both characters must actually loot their own required items where required. Party membership does not duplicate quest drops.
4. At normal level 2, follow 783 → 5261 → 33 → 3903 → 3904. Quest 33 needs eight items 50432; quest 3904 needs eight items 11119. Milly is near `-8850.29,-224.03,81.7778`. Also follow 783 → 18 → 6, gathering eight items 752 and Garrick's item 182. Turn in through pilot UI. Check actual slot-enabled locations before expecting AP output: catalog examples are Milly 3903 → `919503903`, Harvest 3904 → `919503904`, Garrick 6 → `919500006`.
5. Capture actual AP outbox/acknowledgment and received item indices, then normal helper removal and pilot relog. Require no duplicate location/reward application. Initial Elwynn location `919700012` may already be acknowledged from the earlier session; do not count it as new. Stop here for parent review before expanding the route.

### Evidence rules for parties and checks

Use read-only before/after snapshots of `mod_archipelago_check`, `mod_archipelago_reward`, `mod_archipelago_boss_credit`, binding/progress rows, real character quest/XP/item state, AP server logs/save, and client captures. Schema is `sql/v2.sql`. Record seed/team/slot, actual character GUIDs, source/binary hash, map/instance/difficulty, victim or quest ID, expected enabled location IDs, timestamp and observed delta. A missing enabled check is not a failure of an excluded location. Never insert a result to make a test pass.

| Case | Expected evidence and isolation |
| --- | --- |
| Quest | Pilot incomplete objectives produce no AP quest check. Actual rewarded turn-in produces exactly the enabled location. Helper turn-in alone does not credit the pilot. Retest already-completed content only on a separately approved fresh fixture, not by resetting Apjourney. |
| Level / exploration | Pilot's actual earned levels 5,10,… and real zone entry report their enabled checks once. Helpers crossing a zone/level without pilot movement/leveling do not advance the pilot. Do not teleport for coverage. |
| Boss / dungeon | At earned appropriate level, use a catalog-enabled normal instance. Pilot alive, same map, within core group reward distance, helper contributes/lands final blow. Expect one boss check and dungeon completion only after every catalog-required boss in the same save/reset identity. Normal 25-player raids are handled separately. |
| Negative party cases | Unbound helper never gets an AP binding/check/reward. Use other approved fixtures for pilot absent, out-of-range, corpse, wrong difficulty, and different-instance/reset cases; do not kill/delete/reset or move the journey character administratively to manufacture them. Repeat kill/turn-in/reconnect never duplicates slot credit. |

Pinned `APProgression.cpp:244–301` routes boss credit through KillRewarder, human binding, same-map/group-distance/alive-without-corpse rules and allowed difficulty. Dungeon accumulation keys include instance ID and reset epoch. Source coverage is not runtime proof that helper final blows traverse the callback. That is a required actual party test. One or two level-matched helpers cannot certify every dungeon or any raid's feasibility.

### Continue toward 80, not toward a power carry

Keep helpers on ordinary earned progression. If they outlevel the pilot while it is AP-capped, stop adventuring and obtain cap progression through real enabled checks and real peer gameplay, or remove the overlevel helper. Do not change helper levels or disable XP through GM/DB commands. During a bank test, record the brief level drift and remove helpers before it becomes a power carry. No Factory-generated gear, level, spells, talents, money or quest completions. Legitimate AP rewards earned by the seed, including unusually strong AP gear, are allowed and must be distinguished from helper cheats.

Suggested geographic sequence is Northshire → Elwynn → Westfall, then faction/class-appropriate normal zones and dungeons selected from the actual slot's enabled catalog at each cap band 10/20/30/40/50/60/70/80. This is a staged verification route, not a claimed solved quest-by-quest 1–80 path. Before each band, check current seed reachability and normal travel prerequisites. Never require a cap to obtain itself, nor a raid/legendary/ability reward to reach victory. Outland/Northrend travel waits for actual AP access; flying waits for eligible riding rewards. Victory requires actual level 80, not a bot's level or receiving the final cap.

### Coverage ledger for the whole TODO

A playerbot session supplies party gameplay evidence, not completion of all TODO requirements. Keep `TODO.md` and `docs/requirements-evidence.json` unchanged until requirement-specific evidence is reviewed.

| TODO sections | Required route/evidence beyond the opening |
| --- | --- |
| 0–2, 11 | Real quest, exploration, milestone, boss, dungeon and optional raid events; party credit and unbound helpers; durable outgoing checks/incoming indices, relog/reconnect. Persistence/crash/security checks need separately authorized fixtures and interruption windows. |
| 3–6 | Earn each cap/bank transition, blocked/unblocked regional travel through each real route, riding eligibility/use, talent reservation/spending/respec/dual spec, trainer/rank/ability timing. Both factions and all supported classes require fresh approved profiles; the existing unsupported DK policy is not overturned by this run. |
| 7–9 | Coordinate with merchant agent for all-city shared personal stock, purchase/voucher arithmetic, one-copy rules, legitimate low-level AP item/proc/set use and non-AP controls. Full bags, transfers, disconnect/transaction/crash cases belong on isolated approved fixtures. Helpers must not receive transferred AP gear. Distribution/pool math remains seed/unit-test evidence, not bot evidence. |
| 10, 12 | Run actual normal 1–80 journey, retain per-band viability/economy notes, and actual cross-game outgoing/incoming delivery with the official peer. Seed logic/reachability tests and all faction/class coverage remain separate gates. Neither one starter party nor reaching 80 closes all tests. |
| 13–14 | Catalog/raid/class-challenge decisions need explicit design sign-off; M3–M7 close only against their own runtime and hardening evidence. A bot run cannot decide open design questions or certify a release. |

## 5. Teardown and stop conditions

In a safe area, out of combat, remove only the approved helpers by exact name:

```text
.playerbots bot remove Aphelpertwo
.playerbots bot remove Aphelperone
.playerbots bot list
```

Skip the second-helper removal if it was never created/added. `ProcessBotCommand` remove/logout/rm calls `LogoutPlayerBot`, not character deletion. Wait for completion and confirm helpers offline through read-only character queries. Then normal pilot logout. Do not use delete-character UI, SQL DELETE, pool deletion flags, or account unlinking as teardown.

At the next explicitly approved maintenance window, parent restores the saved config including `Enabled=0` and verifies the disabled state. Never restart immediately just to complete this checklist while merchant/pilot agents are active. Preserve earned characters, AP history and evidence. If ordinary logout is blocked, hold the scene and ask the parent; do not force a process kill.

Stop on master AI attachment, helper AP binding, unexpected random generation, any synthetic quest completion, active cheats, free summon/resurrection/repair, unexplained items/XP, AP receipt/check divergence, a source/binary mismatch, or interference with another agent. All bot login, grouping, combat, quest, travel, logout and 1–80 behavior in this plan remains runtime-untested.
