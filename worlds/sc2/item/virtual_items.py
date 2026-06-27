"""
Stores item mappings and helpers for virtual items.

Virtual items are a generation-time logic performance trick.
During fill, the multiworld will try to add and remove items and recalculate logic rules to see if locations
are reachable.
By overriding a world's `collect()` and `remove()` functions, we run extra checks as side-effects,
and store the result as part of the CollectionState using keys that aren't items the the world called
virtual items.

This is useful to recalculate and cache the results of expensive logic checks only when necessary,
taking advantage of the common situation where a logic function will be called more often than its constituent
items will be collected/removed.
"""
from typing import TYPE_CHECKING
from dataclasses import dataclass, field
import enum
from .item_tables import item_table
from . import item_names

if TYPE_CHECKING:
    from BaseClasses import Item
    from collections import Counter


class VirtualItem(enum.IntFlag):
    NONE = 0
    TERRAN_INFANTRY_ARMOR = enum.auto()
    TERRAN_INFANTRY_WEAPON = enum.auto()
    TERRAN_VEHICLE_ARMOR = enum.auto()
    TERRAN_VEHICLE_WEAPON = enum.auto()
    TERRAN_SHIP_ARMOR = enum.auto()
    TERRAN_SHIP_WEAPON = enum.auto()
    ZERG_MELEE_ATTACK = enum.auto()
    ZERG_RANGED_ATTACK = enum.auto()
    ZERG_GROUND_ARMOR = enum.auto()
    ZERG_AIR_ATTACK = enum.auto()
    ZERG_AIR_ARMOR = enum.auto()
    PROTOSS_GROUND_ARMOR = enum.auto()
    PROTOSS_GROUND_WEAPON = enum.auto()
    PROTOSS_AIR_ARMOR = enum.auto()
    PROTOSS_AIR_WEAPON = enum.auto()
    # Note(mm): shield tracking isn't linear when bundling by air/ground; not used by logic

    KERRIGAN_LEVEL = enum.auto()

    TERRAN_UPGRADE = (
        TERRAN_INFANTRY_WEAPON
        | TERRAN_INFANTRY_ARMOR
        | TERRAN_VEHICLE_WEAPON
        | TERRAN_VEHICLE_ARMOR
        | TERRAN_SHIP_WEAPON
        | TERRAN_SHIP_ARMOR
    ),
    ZERG_UPGRADE = (
        ZERG_MELEE_ATTACK
        | ZERG_RANGED_ATTACK
        | ZERG_GROUND_ARMOR
        | ZERG_AIR_ATTACK
        | ZERG_AIR_ARMOR
    )
    PROTOSS_UPGRADE = (
        PROTOSS_GROUND_WEAPON
        | PROTOSS_GROUND_ARMOR
        | PROTOSS_AIR_WEAPON
        | PROTOSS_AIR_ARMOR
    )


@dataclass(slots=True, frozen=True)
class LinearEffect:
    virtual_item: VirtualItem
    magnitude: int = 1


LINEAR_EFFECTS: dict[int | None, LinearEffect] = {
    # Terran Weapon/armour ups
    item_table[item_names.PROGRESSIVE_TERRAN_INFANTRY_WEAPON].code: LinearEffect(VirtualItem.TERRAN_INFANTRY_WEAPON),
    item_table[item_names.PROGRESSIVE_TERRAN_INFANTRY_ARMOR].code: LinearEffect(VirtualItem.TERRAN_INFANTRY_ARMOR),
    item_table[item_names.PROGRESSIVE_TERRAN_VEHICLE_WEAPON].code: LinearEffect(VirtualItem.TERRAN_VEHICLE_WEAPON),
    item_table[item_names.PROGRESSIVE_TERRAN_VEHICLE_ARMOR].code: LinearEffect(VirtualItem.TERRAN_VEHICLE_ARMOR),
    item_table[item_names.PROGRESSIVE_TERRAN_SHIP_WEAPON].code: LinearEffect(VirtualItem.TERRAN_SHIP_WEAPON),
    item_table[item_names.PROGRESSIVE_TERRAN_SHIP_ARMOR].code: LinearEffect(VirtualItem.TERRAN_SHIP_ARMOR),
    item_table[item_names.PROGRESSIVE_TERRAN_WEAPON_UPGRADE].code: LinearEffect(VirtualItem.TERRAN_INFANTRY_WEAPON|VirtualItem.TERRAN_VEHICLE_WEAPON|VirtualItem.TERRAN_SHIP_WEAPON),
    item_table[item_names.PROGRESSIVE_TERRAN_ARMOR_UPGRADE].code: LinearEffect(VirtualItem.TERRAN_INFANTRY_ARMOR|VirtualItem.TERRAN_VEHICLE_ARMOR|VirtualItem.TERRAN_SHIP_ARMOR),
    item_table[item_names.PROGRESSIVE_TERRAN_INFANTRY_UPGRADE].code: LinearEffect(VirtualItem.TERRAN_INFANTRY_WEAPON|VirtualItem.TERRAN_INFANTRY_ARMOR),
    item_table[item_names.PROGRESSIVE_TERRAN_VEHICLE_UPGRADE].code: LinearEffect(VirtualItem.TERRAN_VEHICLE_WEAPON|VirtualItem.TERRAN_VEHICLE_ARMOR),
    item_table[item_names.PROGRESSIVE_TERRAN_SHIP_UPGRADE].code: LinearEffect(VirtualItem.TERRAN_SHIP_WEAPON|VirtualItem.TERRAN_SHIP_ARMOR),
    item_table[item_names.PROGRESSIVE_TERRAN_WEAPON_ARMOR_UPGRADE].code: LinearEffect(VirtualItem.TERRAN_UPGRADE),
    # Zerg Weapon/armour ups
    item_table[item_names.PROGRESSIVE_ZERG_MELEE_ATTACK].code: LinearEffect(VirtualItem.ZERG_MELEE_ATTACK),
    item_table[item_names.PROGRESSIVE_ZERG_MISSILE_ATTACK].code: LinearEffect(VirtualItem.ZERG_RANGED_ATTACK),
    item_table[item_names.PROGRESSIVE_ZERG_GROUND_CARAPACE].code: LinearEffect(VirtualItem.ZERG_GROUND_ARMOR),
    item_table[item_names.PROGRESSIVE_ZERG_FLYER_ATTACK].code: LinearEffect(VirtualItem.ZERG_AIR_ATTACK),
    item_table[item_names.PROGRESSIVE_ZERG_FLYER_CARAPACE].code: LinearEffect(VirtualItem.ZERG_AIR_ARMOR),
    item_table[item_names.PROGRESSIVE_ZERG_WEAPON_UPGRADE].code: LinearEffect(VirtualItem.ZERG_MELEE_ATTACK|VirtualItem.ZERG_RANGED_ATTACK|VirtualItem.ZERG_AIR_ATTACK),
    item_table[item_names.PROGRESSIVE_ZERG_ARMOR_UPGRADE].code: LinearEffect(VirtualItem.ZERG_GROUND_ARMOR|VirtualItem.ZERG_AIR_ARMOR),
    item_table[item_names.PROGRESSIVE_ZERG_GROUND_UPGRADE].code: LinearEffect(VirtualItem.ZERG_MELEE_ATTACK|VirtualItem.ZERG_RANGED_ATTACK|VirtualItem.ZERG_GROUND_ARMOR),
    item_table[item_names.PROGRESSIVE_ZERG_FLYER_UPGRADE].code: LinearEffect(VirtualItem.ZERG_AIR_ATTACK|VirtualItem.ZERG_AIR_ARMOR),
    item_table[item_names.PROGRESSIVE_ZERG_WEAPON_ARMOR_UPGRADE].code: LinearEffect(VirtualItem.ZERG_UPGRADE),
    # Protoss Weapon/armour ups
    item_table[item_names.PROGRESSIVE_PROTOSS_GROUND_WEAPON].code: LinearEffect(VirtualItem.PROTOSS_GROUND_WEAPON),
    item_table[item_names.PROGRESSIVE_PROTOSS_GROUND_ARMOR].code: LinearEffect(VirtualItem.PROTOSS_GROUND_ARMOR),
    item_table[item_names.PROGRESSIVE_PROTOSS_AIR_WEAPON].code: LinearEffect(VirtualItem.PROTOSS_AIR_WEAPON),
    item_table[item_names.PROGRESSIVE_PROTOSS_AIR_ARMOR].code: LinearEffect(VirtualItem.PROTOSS_AIR_ARMOR),
    item_table[item_names.PROGRESSIVE_PROTOSS_WEAPON_UPGRADE].code: LinearEffect(VirtualItem.PROTOSS_GROUND_WEAPON|VirtualItem.PROTOSS_AIR_WEAPON),
    item_table[item_names.PROGRESSIVE_PROTOSS_ARMOR_UPGRADE].code: LinearEffect(VirtualItem.PROTOSS_GROUND_ARMOR|VirtualItem.PROTOSS_AIR_ARMOR),
    item_table[item_names.PROGRESSIVE_PROTOSS_GROUND_UPGRADE].code: LinearEffect(VirtualItem.PROTOSS_GROUND_WEAPON|VirtualItem.PROTOSS_GROUND_ARMOR),
    item_table[item_names.PROGRESSIVE_PROTOSS_AIR_UPGRADE].code: LinearEffect(VirtualItem.PROTOSS_AIR_WEAPON|VirtualItem.PROTOSS_AIR_ARMOR),
    item_table[item_names.PROGRESSIVE_PROTOSS_WEAPON_ARMOR_UPGRADE].code: LinearEffect(VirtualItem.PROTOSS_UPGRADE),
    item_table[item_names.QUATRO].code: LinearEffect(VirtualItem.PROTOSS_UPGRADE),
    # Kerrigan Levels
    item_table[item_names.KERRIGAN_LEVELS_10].code: LinearEffect(VirtualItem.KERRIGAN_LEVEL, 10),
    item_table[item_names.KERRIGAN_LEVELS_9].code: LinearEffect(VirtualItem.KERRIGAN_LEVEL, 9),
    item_table[item_names.KERRIGAN_LEVELS_8].code: LinearEffect(VirtualItem.KERRIGAN_LEVEL, 8),
    item_table[item_names.KERRIGAN_LEVELS_7].code: LinearEffect(VirtualItem.KERRIGAN_LEVEL, 7),
    item_table[item_names.KERRIGAN_LEVELS_6].code: LinearEffect(VirtualItem.KERRIGAN_LEVEL, 6),
    item_table[item_names.KERRIGAN_LEVELS_5].code: LinearEffect(VirtualItem.KERRIGAN_LEVEL, 5),
    item_table[item_names.KERRIGAN_LEVELS_4].code: LinearEffect(VirtualItem.KERRIGAN_LEVEL, 4),
    item_table[item_names.KERRIGAN_LEVELS_3].code: LinearEffect(VirtualItem.KERRIGAN_LEVEL, 3),
    item_table[item_names.KERRIGAN_LEVELS_2].code: LinearEffect(VirtualItem.KERRIGAN_LEVEL, 2),
    item_table[item_names.KERRIGAN_LEVELS_1].code: LinearEffect(VirtualItem.KERRIGAN_LEVEL, 1),
    item_table[item_names.KERRIGAN_LEVELS_14].code: LinearEffect(VirtualItem.KERRIGAN_LEVEL, 14),
    item_table[item_names.KERRIGAN_LEVELS_35].code: LinearEffect(VirtualItem.KERRIGAN_LEVEL, 35),
    item_table[item_names.KERRIGAN_LEVELS_70].code: LinearEffect(VirtualItem.KERRIGAN_LEVEL, 70),
}


def after_add_item(inventory: 'Counter[str]', item: 'Item') -> None:
    effect = LINEAR_EFFECTS.get(item.code)
    if effect is not None:
        for target in effect.virtual_item:
            inventory[target.name] += effect.magnitude  # type: ignore[index]


def after_remove_item(inventory: 'Counter[str]', item: 'Item') -> None:
    effect = LINEAR_EFFECTS.get(item.code)
    if effect is not None:
        for target in effect.virtual_item:
            inventory[target.name] -= effect.magnitude  # type: ignore[index]
