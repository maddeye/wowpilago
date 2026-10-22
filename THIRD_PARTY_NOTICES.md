# Third-party notices

WoWPilago's original code is licensed under [GPL-2.0-or-later](LICENSE), GNU GPL version 2 or, at your option, any later version. The project license does not relicense upstream code, game content or trademarks.

## AzerothCore and playerbots patches

`patches/azerothcore-v2.patch` modifies [the mod-playerbots AzerothCore fork](https://github.com/mod-playerbots/azerothcore-wotlk) at commit `9fb906bb7296212ff42fc95ff73a92aaf8554f0d`. The affected core files carry GPL version2-or-later notices. Their upstream source context and modified upstream files remain subject to those terms. The license text is included in [LICENSES/GPL-2.0.txt](LICENSES/GPL-2.0.txt). Copyright attribution remains with the AzerothCore contributors identified by the upstream source and AUTHORS file.

`patches/playerbots-safety.patch` targets [mod-playerbots](https://github.com/mod-playerbots/mod-playerbots) at commit `2f7d9f774987d0157c6a0d0cc08c40bec3db3945`. Its affected files have different notices:

- `src/Bot/Factory/PlayerbotFactory.cpp` specifies GNU AGPL version3 or later. See [LICENSES/AGPL-3.0.txt](LICENSES/AGPL-3.0.txt).
- `src/Mgr/Guild/PlayerbotGuildMgr.cpp` specifies GNU GPL version2 or later. See [LICENSES/GPL-2.0.txt](LICENSES/GPL-2.0.txt).

The playerbots repository's top-level license file does not replace these file-specific notices. Preserve the upstream notices when applying or redistributing the patches. Distributing or operating a combined patched server can carry obligations from all applicable licenses, including the file-specific AGPL terms. No server binary is included here.

## Archipelago

The APWorld and bridge integrate with [Archipelago](https://github.com/ArchipelagoMW/Archipelago). The supported revision is recorded in [support.json](support.json). Archipelago has its own MIT license and per-directory notices. Its runtime is installed separately, not vendored into this repository.

## Catalogs and game content

The JSON catalogs contain curated identifiers, names, statistics and relationships derived from the pinned AzerothCore database and locally supplied client data. Source revisions and validation fingerprints are recorded in the catalog provenance and [support.json](support.json). Generated `src/APCatalog.h` and `addon/WoWPilago/Catalog.lua` contain projections of those catalogs. The project license covers WoWPilago's original curation and implementation, not rights in third-party material from which records were derived.

World of Warcraft and associated names and content belong to Blizzard Entertainment and their respective rights holders. This is an unofficial project with no affiliation or endorsement. No Blizzard client executable, MPQ, map, DBC, artwork or FrameXML source file is bundled. Supply and use your own game data under its applicable terms.

## Dependencies

Python and system dependencies are installed separately. Their licenses remain in force; listing a dependency does not relicense it under this project's license.
