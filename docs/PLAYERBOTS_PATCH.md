# Playerbots enchantment bounds patch

## Pin and digest

- Upstream playerbots commit: `2f7d9f774987d0157c6a0d0cc08c40bec3db3945`.
- Patch: `patches/playerbots-safety.patch`.
- Patch SHA-256: `cc41814799c3aba0c994c66d9bcfa58fc9bcc86ba9144c3a9aa728bda796fd0a`.
- Original `src/Bot/Factory/PlayerbotFactory.cpp` SHA-256: `d67e8e95c120cb8ea788d335fd64a4df03f36114cb14938bbbdecea34ad4bc87`.
- Patched Factory SHA-256: `8457f86e0e5b7134000de8e703193956faff39c5295e73e2f6ca25bff6df9bf5`.

## Change and scope

`PlayerbotFactory::EnchantItem`, around line 2700, used the item-stat enum range
`ITEM_MOD_MANA .. MAX_ITEM_MOD` as an enchantment-effect array index. That range
is 0 through 48. The pinned core's `SpellItemEnchantmentEntry::type` and
`spellid` arrays each have `MAX_SPELL_ITEM_ENCHANTMENT_EFFECTS`, exactly three
entries. Index 3 is already out of bounds.

The patch changes only the loop initializer and bound to
`0 .. MAX_SPELL_ITEM_ENCHANTMENT_EFFECTS`. The stat-type filter, `AddItemStats`,
`CheckItemStats`, enchantment and spell requirements, random selection, and
application logic remain unchanged. It does not change the existing first-spell
lookup or attempt to redesign enchantment selection.

Caller and related-loop inspection at the pin found no active direct
`EnchantItem` calls. The three calls in Factory are commented out, and its header
retains the declaration. This does not make the invalid loop safe to ship.
`PlayerbotFactory::AddItemStats` classifies the selected stat IDs. The separate
`RandomItemMgr::AddItemStats` handles item-template stats, not these arrays.
`StatsCollector::CollectEnchantStats` already iterates with the three-effect
bound. The other Factory `spellid[0]` reference near line 465 is commented out;
the active first-spell lookup near line 2694 stays unchanged.

## Application

`tools/build_realm.py` archives the exact playerbots Git commit, then invokes
`apply_playerbots_patch` on that archive before source fingerprinting or
compilation. It never patches the dirty host module. The helper rejects Git
checkouts, unsafe Factory paths, changed patch bytes and unknown Factory
fingerprints. Reapplication accepts only the exact patched fingerprint.
The helper is not an upstream-version detector; the build's pinned Git archive
provides the provenance, and the fingerprints guard the one changed file.

The manifest's `playerbots_safety_patch` records the upstream commit, patch
digest, original/patched file digests and application state. The patch and build
tool are included in the run's snapshotted inputs. The main core patch remains
unchanged at SHA-256
`3524780ac845b301fb606bcd74d80899669f5a18a8867f23cbade9fa06948c28`.

## Executed regression

```bash
.venv/bin/python -m unittest discover -s tests -p test_playerbots_patch.py -v
```

Requires the local pinned repositories and a C++ compiler with ASan/UBSan.
`CORE_PATCH_SOURCE` can select another local core clone; `CXX` selects the
compiler. Tests read Git objects and patch temporary archives, never the host
working tree.

The regression extracts the actual patched loop and `AddItemStats` implementation.
It compiles them with the actual pinned enchantment struct, effect-count define,
item-mod enum and enchantment-type enum. All eight stat/non-stat combinations
across the three slots execute under address, undefined-behavior and bounds
sanitizers. Assertions verify the resulting caster, attack and tank counters,
including the first and last effects and skipped non-stat effects. The same
program with the original loop must fail under UBSan at index 3. Additional tests
check application, reapplication, modified-source rejection, checkout rejection
and patch-digest rejection without writes.

The cached refresh also recompiles the complete patched Factory translation
unit and relinks the full server with the current WoWPilago sources. This is
build and selection-loop evidence, not gameplay verification. No realm starts,
deployment, host-core edits or database writes are part of this procedure.

## Remaining warning

`PlayerbotAIConfig::GetTimestampStr` near line 984 can report
`-Wformat-truncation`. It uses bounded `snprintf` into `char buf[32]` for a local
log timestamp. Ordinary current-year timestamps fit; GCC also considers wider
integer representations. Truncation is not a buffer overrun and is unrelated to
the enchantment selection path. The warning is retained rather than expanding
this safety patch.
