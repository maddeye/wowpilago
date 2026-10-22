"""V1 profiles exclude Death Knights; faction follows the selected race."""
from dataclasses import dataclass

from Options import Choice, DefaultOnToggle, PerGameCommonOptions, Range


class Race(Choice):
    display_name = "Race"
    option_human = 1
    option_orc = 2
    option_dwarf = 3
    option_night_elf = 4
    option_undead = 5
    option_tauren = 6
    option_gnome = 7
    option_troll = 8
    option_blood_elf = 10
    option_draenei = 11
    default = 1


class CharacterClass(Choice):
    display_name = "Class"
    option_warrior = 1
    option_paladin = 2
    option_hunter = 3
    option_rogue = 4
    option_priest = 5
    option_shaman = 7
    option_mage = 8
    option_warlock = 9
    option_druid = 11
    default = 1


class CheckCategory(DefaultOnToggle):
    """Disabling categories removes checks, not the fixed useful reward supply.
    Too few remaining checks is an error rather than silently deleting rewards.
    """


class MerchantStock(Range):
    display_name = "Personal merchant stock size"
    range_start = 30
    range_end = 120
    default = 60


class FeaturedSets(Range):
    display_name = "Featured sets"
    range_start = 1
    range_end = 4
    default = 3


class SetPieceProbability(Range):
    display_name = "Independent featured piece inclusion percent"
    range_start = 0
    range_end = 100
    default = 80


class LegendaryCount(Range):
    display_name = "Direct named legendary count"
    range_start = 0
    range_end = 10
    default = 2


@dataclass
class WoWOptions(PerGameCommonOptions):
    character_race: Race
    character_class: CharacterClass
    quests: CheckCategory
    exploration: CheckCategory
    dungeon_bosses: CheckCategory
    dungeon_completions: CheckCategory
    level_milestones: CheckCategory
    raids: CheckCategory
    merchant_stock: MerchantStock
    featured_sets: FeaturedSets
    set_piece_probability: SetPieceProbability
    legendary_count: LegendaryCount
