"""Authoritative pure progression model for server parity tests.

XP at a cap is banked, not added to the ordinary XP bar. The bank limit is
floor(xp_for_level[cap] / 2), where xp_for_level[L] is XP from L to L+1.
An award crossing into the cap banks its remaining XP under that same limit.
Excess is discarded. Raising the cap clears and awards the bank exactly once
through ordinary leveling, using the new cap. Merely receiving another reward
without raising the cap does not release it. Level 80 discards XP and any bank.
Persistence/receipt idempotency belongs to the runtime transaction, not this model.
"""
from dataclasses import dataclass

TALENT_RESERVATION_LEVELS = tuple(range(15, 71, 5))
RIDING_LEVELS = dict(apprentice=20, journeyman=40, expert=60, artisan=70, cold_weather=77)


def level_cap(received_caps):
    return min(80, 10 + 10 * max(0, received_caps))


def talent_points(level, received_unlocks):
    if not 1 <= level <= 80 or received_unlocks < 0:
        raise ValueError("Invalid level or talent unlock count")
    eligible = sum(level >= threshold for threshold in TALENT_RESERVATION_LEVELS)
    return max(0, level - 9) - eligible + min(eligible, received_unlocks)


def riding_eligible(tier, level, received):
    if tier not in RIDING_LEVELS:
        raise ValueError(f"Unknown riding tier: {tier}")
    # Expert includes prerequisite training; useful ground rewards cannot gate flight.
    prerequisites = {"journeyman": "apprentice", "artisan": "expert", "cold_weather": "expert"}
    return (tier in received and level >= RIDING_LEVELS[tier]
            and (tier not in prerequisites or riding_eligible(prerequisites[tier], level, received)))


def ability_eligible(ability, level, learned_spells):
    return level >= ability["min_level"] and set(ability["prerequisites"]) <= set(learned_spells)


@dataclass(frozen=True)
class Experience:
    level: int
    xp: int = 0
    bank: int = 0


def award_xp(state, amount, cap, xp_for_level):
    if not 1 <= state.level <= cap <= 80 or min(state.xp, state.bank, amount) < 0:
        raise ValueError("Invalid XP state, award, or cap")
    level, xp, bank = state.level, state.xp, state.bank
    xp += amount
    while level < cap:
        required = xp_for_level[level]
        if required <= 0:
            raise ValueError("XP requirements must be positive")
        if xp < required:
            return Experience(level, xp, bank)
        xp -= required
        level += 1
    if level == 80:
        return Experience(80)
    return Experience(level, 0, min(bank + xp, xp_for_level[level] // 2))


def raise_cap(state, old_cap, new_cap, xp_for_level):
    if not state.level <= old_cap <= new_cap <= 80:
        raise ValueError("Caps must be monotonic and at least the current level")
    if new_cap == old_cap:
        return state
    return award_xp(Experience(state.level, state.xp), state.bank, new_cap, xp_for_level)
