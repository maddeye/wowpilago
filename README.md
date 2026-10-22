# WoWPilago

Play World of Warcraft 3.3.5a as an [Archipelago](https://archipelago.gg/) multiworld game. Complete curated WoW checks to send items to other players. Receive level-cap upgrades, travel unlocks, selected abilities and equipment rewards in return.

**The goal is character level 80.** Raids, legendary equipment and collecting every ability are not required to win.

> **Experimental, not a finished release.** This repository contains working integrations and native-client tests, but a complete 1-80 multiworld playthrough and several combat, equipment and crash-safety gates remain open. Use a dedicated test realm and fresh characters. See [TODO.md](TODO.md) and [VALIDATION.md](VALIDATION.md).

## What it does

- Tracks curated quests, level milestones, exploration, dungeon bosses, dungeon clears and optional raid bosses.
- Combines normal WoW leveling with Archipelago-controlled caps, expansion access, riding, selected class abilities and reserved talent points.
- Provides personal equipment merchants with voucher prices and the same stock in each supported city. Named legendaries arrive directly.
- Keeps rewards and checks in a persistent database outbox. Offline characters and full bags leave deliveries pending rather than discarding them.
- Authorizes AP equipment per item instance. Ordinary items keep their normal requirements; class, armor and weapon proficiency rules still apply.

There are 300 global check definitions, not 300 checks in every seed. Race, class, faction and category options determine a slot's actual checks. The default Human Warrior configuration has 213. The [implementation notes](docs/IMPLEMENTATION.md) explain the item pool and progression rules.

## Requirements

| Component | Supported target |
| --- | --- |
| WoW client | 3.3.5a, build 12340, interface 30300. Not Classic or retail. |
| Server | The pinned mod-playerbots AzerothCore fork, with this project's core patch. Not an arbitrary upstream checkout. |
| Archipelago | 0.6.8 at the commit in [support.json](support.json). |
| Database | MySQL 8.4. |
| Bridge | Python 3.11 or newer. |
| Characters | Nine non-DK classes and 52 legal race/class profiles. Death Knights are not supported. |

You must supply your own client and extracted server data. **This repository does not distribute the WoW client, MPQs, maps or DBC files.** Source pins are recorded in [support.json](support.json); build details and the playerbots pin are in [docs/BUILD.md](docs/BUILD.md).

## How the pieces fit

```text
WoW client + optional addon
          |
Patched AzerothCore + WoWPilago module
          |
        MySQL <----> Python bridge <----> Archipelago room
```

The module handles gameplay rules, check credit, purchases and physical reward delivery. The bridge connects one character to one AP slot. It does not directly edit character levels or inventory.

| Directory | Contents |
| --- | --- |
| `apworld/wowpilago/` | APWorld, player options and authoritative JSON catalogs. |
| `src/` and `patches/` | Native module and patches for the pinned core/playerbots sources. |
| `bridge/` and `sql/` | AP connection, persistent state, atomic reward effects and database privileges. |
| `addon/WoWPilago/` | Optional personal-shop interface and reward notifications. |
| `tests/`, `tools/`, `docs/` | Tests, packaging/build tools and technical documentation. |

## Try the source and build packages

From a checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r bridge/requirements.txt
python tools/build_catalog.py --check
python -m unittest discover -s tests -v
python tools/package.py
```

Packaging creates `dist/wowpilago.apworld` and `dist/WoWPilago.zip`, including license texts and third-party notices. It does not start a realm or modify any database. Generated packages are ignored by Git.

The portable suite uses a C++ compiler and Lua 5.1/LuaJIT for its corresponding tests. Private native recordings, external source trees and connected SQL fixtures are optional integration inputs. Tests that need missing inputs report named skips. A skip is not a native verification pass. GitHub Actions runs the portable checks without database credentials or game assets.

To run the APWorld's generation and seed tests, use an Archipelago Python environment with its dependencies installed:

```bash
/path/to/AP/python tests/verify_world.py /path/to/Archipelago
/path/to/AP/python tests/simulate_seeds.py /path/to/Archipelago --seeds 2000
```

## Set up a realm

This is an operator installation, not a client-only addon. Back up existing databases first. Do not use the private development fixture scripts against a production realm.

1. **Build the pinned server.** Follow [docs/BUILD.md](docs/BUILD.md). The build tool snapshots the pinned core and playerbots sources, applies the required patches and builds into a new directory. It does not deploy or alter a shared checkout. For manual integration, copy only `src/` into `modules/mod-archipelago/src/`, not your entire working directory.
2. **Install the SQL before starting the module.** Use your own database names and administrator account if they differ from these defaults:

   ```bash
   mysql -u YOUR_ADMIN -p acore_characters < sql/v2.sql
   mysql -u YOUR_ADMIN -p acore_characters < sql/v2_effects.sql
   mysql -u YOUR_ADMIN -p acore_world < sql/world.sql
   ```

3. **Configure the worldserver.** Require `CharacterDatabase.WorkerThreads = 1`, `MaxPlayerLevel = 80` and `Rate.Talent = 1`. Preserve normal inventory and save handling. See the [core patch contract](docs/CORE_PATCH.md).
4. **Generate an AP room.** Install `dist/wowpilago.apworld` in Archipelago and start with [examples/player.yaml](examples/player.yaml). For the optional shop UI, extract `dist/WoWPilago.zip` into the client's `Interface/AddOns/` directory.
5. **Create and bind a fresh character.** Its race/class must match the generated slot. Leave it offline at level 1 with XP 0, then configure and start the bridge below. After binding, log in normally.

The seed/team/slot binding is permanent. Use a fresh character for a new seed. Do not clear receipt tables, delete item instances or reset saved progress to retry an installation. Protocol 1 is retired; preserve its history during an upgrade.

### Connect the bridge

Create a dedicated database account with a random password. Review [docs/SECURITY.md](docs/SECURITY.md), then apply [sql/bridge_permissions.sql](sql/bridge_permissions.sql) for that account's actual connection host. Keep MySQL private.

```bash
cp examples/bridge.toml bridge.toml
# Edit the server URL, slot name, character GUID and database settings.
read -rsp 'Database password: ' WOWPILAGO_DB_PASSWORD; echo
export WOWPILAGO_DB_PASSWORD
python -m bridge.client bridge.toml
```

An optional room password goes in `WOWPILAGO_AP_PASSWORD`, not the TOML file. Use `wss://` or an authenticated tunnel for remote rooms. Local `bridge.toml` and environment files are ignored by Git; never commit real credentials.

## In game

`.archipelago status` shows your slot, cap, riding, vouchers, pending deliveries and completed-check state. Visit a supported city merchant to spend vouchers. The addon presents categories, item tooltips and purchase confirmation; the categorized gossip shop also works without it.

The stock client can reject an over-level item before sending an equip request. Use `.archipelago equip <item GUID> <slot 0..18>` for an authorized AP item, and `.archipelago use <item GUID>` for supported equipped on-use items. These commands do not waive class, proficiency, target or cooldown rules. Ground-target on-use items remain a limitation.

## Verification and limits

Native stock-client testing has exercised all six check types on the current binary, including save-before-milestone ordering, a five-boss dungeon clear and normal relog persistence. Those particular checks used an isolated administrator-assisted fixture, not ordinary combat or a complete playthrough. Separate tests cover a graphical shop purchase and real AP reconnect/delivery paths.

[VALIDATION.md](VALIDATION.md) distinguishes source/unit tests, isolated SQL tests, native mechanism tests and legitimate gameplay. [Native curated-check evidence](docs/verification/native-curated-checks.json) records the current check test and its preservation exception. Detailed native snapshots, client recordings and realm files live in an ignored private archive and are not part of the public checkout. The strict historical evidence audit needs that archive; public CI does not pretend to replay it. Historical evidence references are not instructions to recreate or replay those tests.

Open work includes class combat coverage, equipment effects and compatibility, content/economy balance, crash/concurrent-purchase behavior and completed multiworld goals. Publishing this source does not mark those release gates complete.

## Documentation

Start with [build instructions](docs/BUILD.md), [security and database permissions](docs/SECURITY.md), [progression/save behavior](docs/PROGRESSION_RUNTIME.md), and the [implementation decisions](docs/IMPLEMENTATION.md). [TODO.md](TODO.md) is the backlog; its checkmarks refer to named evidence rather than a release guarantee.

## License

WoWPilago's original code is licensed under [GPL-2.0-or-later](LICENSE), GNU GPL version 2 or, at your option, any later version. Upstream core/playerbots code in the patches retains its file-specific GPL/AGPL terms. The project license does not relicense Blizzard content or trademarks. Read [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) before distributing a combined server.
