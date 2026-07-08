import enum
from typing import Iterable
from . import item_tables, item_names
from .item_tables import key_item_table
from ..mission_tables import campaign_mission_table, SC2Campaign, SC2Mission, SC2Race

"""
Item name groups, given to Archipelago and used in YAMLs and /received filtering.
For non-developers the following will be useful:
* Items with a bracket get groups named after the unbracketed part
  * eg. "Advanced Healing AI (Medivac)" is accessible as "Advanced Healing AI"
  * The exception to this are item names that would be ambiguous (eg. "Resource Efficiency")
* Item flaggroups get unique groups as well as combined groups for numbered flaggroups
  * eg. "Unit" contains all units, "Armory" contains "Armory 1" through "Armory 6"
  * The best place to look these up is at the bottom of Items.py
* Items that have a parent are grouped together
  * eg. "Zergling Items" contains all items that have "Zergling" as a parent
  * These groups do NOT contain the parent item
  * This currently does not include items with multiple potential parents, like some LotV unit upgrades
* All items are grouped by their race ("Terran", "Protoss", "Zerg", "Any")
* Hand-crafted item groups can be found at the bottom of this file
"""


def _intersection(left: Iterable[str], right: Iterable[str]) -> tuple[str, ...]:
    return tuple(x for x in left if x in right)


item_name_groups: dict[str, list[str] | tuple[str, ...]] = {}

# Groups for use in world logic
item_name_groups["Missions"] = ["Beat " + mission.mission_name for mission in SC2Mission]
item_name_groups["WoL Missions"] = (
    ["Beat " + mission.mission_name for mission in campaign_mission_table[SC2Campaign.WOL]]
    + ["Beat " + mission.mission_name for mission in campaign_mission_table[SC2Campaign.PROPHECY]]
)

# These item name groups should not show up in documentation
unlisted_item_name_groups = {
    "Missions", "WoL Missions",
    item_tables.TerranItemType.Progressive.display_name,
    item_tables.TerranItemType.Nova_Gear.display_name,
    item_tables.TerranItemType.Mercenary.display_name,
    item_tables.ZergItemType.Ability.display_name,
    item_tables.ZergItemType.Morph.display_name,
    item_tables.ZergItemType.Strain.display_name,
    item_tables.ProtossItemType.Artanis_Items.display_name,
}

# Some item names only differ in bracketed parts
# These items are ambiguous for short-hand name groups
bracketless_duplicates: set[str]
# This is a list of names in ItemNames with bracketed parts removed, for internal use
_shortened_names = [(name[:name.find(' (')] if '(' in name else name)
                    for name in [item_names.__dict__[name] for name in item_names.__dir__() if not name.startswith('_')]]
# Remove the first instance of every short-name from the full item list
bracketless_duplicates = set(_shortened_names)
for name in bracketless_duplicates:
    _shortened_names.remove(name)
# The remaining short-names are the duplicates
bracketless_duplicates = set(_shortened_names)
del _shortened_names

# All items get sorted into their data type
for item, data in item_tables.item_table.items():
    # Items get assigned to their flaggroup's display type
    item_name_groups.setdefault(data.type.display_name, []).append(item)
    # Items with a bracket get a short-hand name group for ease of use in YAMLs
    if '(' in item:
        short_name = item[:item.find(' (')]
        # Ambiguous short-names are dropped
        if short_name not in bracketless_duplicates:
            item_name_groups[short_name] = [item]
            # Short-name groups are unlisted
            unlisted_item_name_groups.add(short_name)
    # Items with a parent get assigned to their parent's group
    if data.parent:
        # The parent groups need a special name, otherwise they are ambiguous with the parent
        parent_group = f"{data.parent} Items"
        item_name_groups.setdefault(parent_group, []).append(item)
        # Parent groups are unlisted
        unlisted_item_name_groups.add(parent_group)
    # All items get assigned to their race's group
    race_group = data.race.name.capitalize()
    item_name_groups.setdefault(race_group, []).append(item)


# Hand-made groups
class ItemGroupNames:
    TERRAN_ITEMS = "Terran Items"
    """All Terran items"""
    TERRAN_UNITS = "Terran Units"
    TERRAN_BASIC_CORE_UNITS = "Terran Basic Core Units"
    TERRAN_BASIC_STARTER_UNITS = "Terran Basic Starter Units"
    TERRAN_ADVANCED_CORE_UNITS = "Terran Advanced Core Units"
    TERRAN_ADVANCED_STARTER_UNITS = "Terran Advanced Starter Units"
    TERRAN_CHAOS_STARTER_UNITS = "Terran Chaos Starter Units"
    TERRAN_GENERIC_UPGRADES = "Terran Generic Upgrades"
    """+attack/armour upgrades"""
    TERRAN_MOBILE_DETECTION = "Terran Mobile Detection"
    TERRAN_DETECTION = "Terran Detection"
    BARRACKS_UNITS = "Barracks Units"
    FACTORY_UNITS = "Factory Units"
    STARPORT_UNITS = "Starport Units"
    WOL_UNITS = "WoL Units"
    WOL_MERCS = "WoL Mercenaries"
    WOL_BUILDINGS = "WoL Buildings"
    WOL_UPGRADES = "WoL Upgrades"
    WOL_ITEMS = "WoL Items"
    """All items from vanilla WoL. Note some items are progressive where level 2 is not vanilla."""
    NCO_UNITS = "NCO Units"
    NCO_BUILDINGS = "NCO Buildings"
    NCO_UNIT_TECHNOLOGY = "NCO Unit Technology"
    NCO_BASELINE_UPGRADES = "NCO Baseline Upgrades"
    NCO_UPGRADES = "NCO Upgrades"
    NOVA_EQUIPMENT = "Nova Equipment"
    NOVA_WEAPONS = "Nova Weapons"
    NOVA_GADGETS = "Nova Gadgets"
    NOVA_SUITS = "Nova Suits"
    NCO_MAX_PROGRESSIVE_ITEMS = "NCO +Items"
    """NCO item groups that should be set to maximum progressive amounts"""
    NCO_MIN_PROGRESSIVE_ITEMS = "NCO -Items"
    """NCO item groups that should be set to minimum progressive amounts (1)"""
    TERRAN_BUILDINGS = "Terran Buildings"
    TERRAN_MERCENARIES = "Terran Mercenaries"
    TERRAN_STIMPACKS = "Terran Stimpacks"
    TERRAN_PROGRESSIVE_UPGRADES = "Terran Progressive Upgrades"
    TERRAN_ORIGINAL_PROGRESSIVE_UPGRADES = "Terran Original Progressive Upgrades"
    """Progressive items where level 1 appeared in WoL"""
    TERRAN_SC1_UNITS = "Terran SC1 Units"
    TERRAN_SC1_BUILDINGS = "Terran SC1 Buildings"
    TERRAN_LADDER_UNITS = "Terran Ladder Units"
    TERRAN_ROYAL_GUARD_UNITS = "Terran Royal Guard Units"
    ORBITAL_COMMAND_ABILITIES = "Orbital Command Abilities"
    WOL_ORBITAL_COMMAND_ABILITIES = "WoL Command Center Abilities"
    COOP_RAYNOR_UNITS = "Co-op Raynor Units"
    COOP_SWANN_UNITS = "Co-op Swann Units"
    COOP_NOVA_UNITS = "Co-op Nova Units"
    COOP_HAN_AND_HORNER_UNITS = "Co-op Han and Horner Units"
    COOP_MENGSK_UNITS = "Co-op Mengsk Units"

    ZERG_ITEMS = "Zerg Items"
    ZERG_UNITS = "Zerg Units"
    ZERG_BASIC_CORE_UNITS = "Zerg Basic Core Units"
    ZERG_BASIC_STARTER_UNITS = "Zerg Basic Starter Units"
    ZERG_ADVANCED_CORE_UNITS = "Zerg Advanced Core Units"
    ZERG_ADVANCED_STARTER_UNITS = "Zerg Advanced Starter Units"
    ZERG_CHAOS_STARTER_UNITS = "Zerg Chaos Starter Units"
    ZERG_NONMORPH_UNITS = "Zerg Non-morph Units"
    ZERG_GENERIC_UPGRADES = "Zerg Generic Upgrades"
    """+attack/armour upgrades"""
    ZERG_MOBILE_DETECTION = "Zerg Mobile Detection"
    ZERG_DETECTION = "Zerg Detection"
    HOTS_UNITS = "HotS Units"
    HOTS_BUILDINGS = "HotS Buildings"
    HOTS_STRAINS = "HotS Strains"
    """Vanilla HotS strains (the upgrades you play a mini-mission for)"""
    HOTS_MUTATIONS = "HotS Mutations"
    """Vanilla HotS Mutations (basic toggleable unit upgrades)"""
    HOTS_GLOBAL_UPGRADES = "HotS Global Upgrades"
    HOTS_MORPHS = "HotS Morphs"
    KERRIGAN_ABILITIES = "Kerrigan Abilities"
    KERRIGAN_HOTS_ABILITIES = "Kerrigan HotS Abilities"
    KERRIGAN_ACTIVE_ABILITIES = "Kerrigan Active Abilities"
    KERRIGAN_LOGIC_ACTIVE_ABILITIES = "Kerrigan Logic Active Abilities"
    KERRIGAN_SOLO_ACTIVE_ABILITIES = "Kerrigan Solo Active Abilities"
    KERRIGAN_PASSIVES = "Kerrigan Passives"
    KERRIGAN_TIER_1 = "Kerrigan Tier 1"
    KERRIGAN_TIER_2 = "Kerrigan Tier 2"
    KERRIGAN_TIER_3 = "Kerrigan Tier 3"
    KERRIGAN_TIER_4 = "Kerrigan Tier 4"
    KERRIGAN_TIER_5 = "Kerrigan Tier 5"
    KERRIGAN_TIER_6 = "Kerrigan Tier 6"
    KERRIGAN_TIER_7 = "Kerrigan Tier 7"
    KERRIGAN_ULTIMATES = "Kerrigan Ultimates"
    KERRIGAN_LOGIC_ULTIMATES = "Kerrigan Logic Ultimates"
    KERRIGAN_NON_ULTIMATES = "Kerrigan Non-Ultimates"
    KERRIGAN_NON_ULTIMATE_ACTIVE_ABILITIES = "Kerrigan Non-Ultimate Active Abilities"
    HOTS_ITEMS = "HotS Items"
    """All items from vanilla HotS"""
    OVERLORD_UPGRADES = "Overlord Upgrades"
    ZERG_MORPHS = "Zerg Morphs"
    ZERG_MERCENARIES = "Zerg Mercenaries"
    ZERG_BUILDINGS = "Zerg Buildings"
    """All items from Stukov co-op subfaction"""
    INFESTED_TERRAN_UNITS = "Infested Terran Units"
    INFESTED_TERRAN_ITEMS = "Infested Terran Items"
    INFESTED_TERRAN_UPGRADES = "Infested Terran Upgrades"
    ZERG_SC1_UNITS = "Zerg SC1 Units"
    ZERG_LADDER_UNITS = "Zerg Ladder Units"
    COOP_KERRIGAN_UNITS = "Co-op Kerrigan Units"
    COOP_ZAGARA_UNITS = "Co-op Zagara Units"
    COOP_ABATHUR_UNITS = "Co-op Abathur Units"
    COOP_STUKOV_UNITS = "Co-op Stukov Units"
    COOP_DEHAKA_UNITS = "Co-op Dehaka Units"
    COOP_STETMANN_UNITS = "Co-op Stetmann Units"

    PROTOSS_ITEMS = "Protoss Items"
    PROTOSS_UNITS = "Protoss Units"
    PROTOSS_BASIC_CORE_UNITS = "Protoss Basic Core Units"
    PROTOSS_BASIC_STARTER_UNITS = "Protoss Basic Starter Units"
    PROTOSS_ADVANCED_CORE_UNITS = "Protoss Advanced Core Units"
    PROTOSS_ADVANCED_STARTER_UNITS = "Protoss Advanced Starter Units"
    PROTOSS_CHAOS_STARTER_UNITS = "Protoss Chaos Starter Units"
    PROTOSS_GENERIC_UPGRADES = "Protoss Generic Upgrades"
    """+attack/armour upgrades"""
    PROTOSS_MOBILE_DETECTION = "Protoss Mobile Detection"
    PROTOSS_DETECTION = "Protoss Detection"
    GATEWAY_UNITS = "Gateway Units"
    ROBO_UNITS = "Robo Units"
    STARGATE_UNITS = "Stargate Units"
    PROPHECY_UNITS = "Prophecy Units"
    PROPHECY_BUILDINGS = "Prophecy Buildings"
    LOTV_UNITS = "LotV Units"
    LOTV_ITEMS = "LotV Items"
    LOTV_GLOBAL_UPGRADES = "LotV Global Upgrades"
    SOA_PASSIVES = "SOA Passive Abilities"
    SOA_ITEMS = "SOA"
    PROTOSS_GLOBAL_UPGRADES = "Protoss Global Upgrades"
    PROTOSS_BUILDINGS = "Protoss Buildings"
    WAR_COUNCIL = "Protoss War Council Upgrades"
    AIUR_UNITS = "Aiur"
    NERAZIM_UNITS = "Nerazim"
    TAL_DARIM_UNITS = "Tal'Darim"
    PURIFIER_UNITS = "Purifier"
    PROTOSS_SC1_UNITS = "Protoss SC1 Units"
    PROTOSS_SC1_BUILDINGS = "Protoss SC1 Buildings"
    PROTOSS_LADDER_UNITS = "Protoss Ladder Units"
    NEXUS_UNITS = "Nexus Units"
    COOP_ARTANIS_UNITS = "Co-op Artanis Units"
    COOP_VORAZUN_UNITS = "Co-op Vorazun Units"
    COOP_KARAX_UNITS = "Co-op Karax Units"
    COOP_ALARAK_UNITS = "Co-op Alarak Units"
    COOP_FENIX_UNITS = "Co-op Fenix Units"
    COOP_ZERATUL_UNITS = "Co-op Zeratul Units"
    ARTANIS_ABILITIES = "Artanis Abilities"
    ARTANIS_WEAPON_ASPECT_ACTIVE = "Artanis Weapon Aspect Active"
    ARTANIS_WEAPON_ASPECT_PASSIVE = "Artanis Weapon Aspect Passive"
    ARTANIS_ACTIVE_ABILITIES = "Artanis Global Actives"
    ARTANIS_PASSIVE_ABILITIES = "Artanis Global Passives"

    VANILLA_ITEMS = "Vanilla Items"
    OVERPOWERED_ITEMS = "Overpowered Items"
    DISABLED_ITEMS = "Disabled Items"
    UNRELEASED_ITEMS = "Unreleased Items"
    LEGACY_ITEMS = "Legacy Items"

    KEYS = "Keys"

    @classmethod
    def get_all_group_names(cls) -> set[str]:
        return {
            name for identifier, name in cls.__dict__.items()
            if not identifier.startswith('_')
            and not identifier.startswith('get_')
        }


class LogicRating(enum.IntFlag):
    """"""
    NONE = 0
    BASIC_STARTER       = 0b00001
    ADVANCED_STARTER    = 0b00010
    BASIC_EXTRA         = 0b00100
    ADVANCED_EXTRA      = 0b01000

    is_basic_core = BASIC_STARTER | BASIC_EXTRA
    is_advanced_core = BASIC_STARTER | ADVANCED_STARTER | BASIC_EXTRA | ADVANCED_EXTRA
    is_advanced_starter = BASIC_STARTER | ADVANCED_STARTER
    is_basic_starter = BASIC_STARTER


# Terran
item_name_groups[ItemGroupNames.TERRAN_ITEMS] = terran_items = [
    item_name for item_name, item_data in item_tables.item_table.items()
    if item_data.race == SC2Race.TERRAN
]

item_name_groups[ItemGroupNames.TERRAN_UNITS] = terran_units = [
    item_name for item_name, item_data in item_tables.item_table.items()
    if item_data.type in (
    item_tables.TerranItemType.Unit, item_tables.TerranItemType.Unit_2, item_tables.TerranItemType.Mercenary)
]
_terran_core_units = {
    item_names.MARINE: LogicRating.BASIC_STARTER,
    item_names.MARAUDER: LogicRating.BASIC_STARTER,
    item_names.REAPER: LogicRating.BASIC_STARTER,
    item_names.DOMINION_TROOPER: LogicRating.BASIC_STARTER,
    item_names.HELLION: LogicRating.BASIC_STARTER,
    item_names.VULTURE: LogicRating.BASIC_STARTER,
    item_names.GOLIATH: LogicRating.BASIC_STARTER,
    item_names.DIAMONDBACK: LogicRating.BASIC_STARTER,
    item_names.SIEGE_TANK: LogicRating.BASIC_STARTER,
    item_names.WARHOUND: LogicRating.BASIC_STARTER,
    item_names.VIKING: LogicRating.BASIC_STARTER,
    # Note(mm): Iffy on this one, as it can't block zerglings on e.g. Evacuation, and has a 60s build time
    item_names.BANSHEE: LogicRating.BASIC_STARTER,

    item_names.MEDIC: LogicRating.BASIC_EXTRA,  # No attack
    item_names.AEGIS_GUARD: LogicRating.BASIC_EXTRA,
    item_names.FIELD_RESPONSE_THETA: LogicRating.BASIC_EXTRA,  # Healer
    item_names.MEDIVAC: LogicRating.BASIC_EXTRA,  # Healer
    item_names.BULWARK_COMPANY: LogicRating.BASIC_EXTRA,
    item_names.SHOCK_DIVISION: LogicRating.BASIC_EXTRA,
    item_names.NIGHT_HAWK: LogicRating.BASIC_EXTRA,
    item_names.NIGHT_WOLF: LogicRating.BASIC_EXTRA,
    item_names.PRIDE_OF_AUGUSTGRAD: LogicRating.BASIC_EXTRA,
    item_names.SKY_FURY: LogicRating.BASIC_EXTRA,
    item_names.THOR: LogicRating.BASIC_EXTRA | LogicRating.ADVANCED_STARTER,            # Tech time
    item_names.BATTLECRUISER: LogicRating.BASIC_EXTRA | LogicRating.ADVANCED_STARTER,   # Tech time
    item_names.SON_OF_KORHAL: LogicRating.BASIC_EXTRA | LogicRating.ADVANCED_STARTER,

    item_names.FIREBAT: LogicRating.ADVANCED_STARTER,
    item_names.HERC: LogicRating.ADVANCED_STARTER,
    item_names.GHOST: LogicRating.ADVANCED_STARTER,
    item_names.SPECTRE: LogicRating.ADVANCED_STARTER,
    item_names.CYCLONE: LogicRating.ADVANCED_STARTER,

    item_names.PREDATOR: LogicRating.ADVANCED_EXTRA,            # Weak, can't be healed if follow-up units are healers
    item_names.WRAITH: LogicRating.ADVANCED_EXTRA,              # Weak, can't be healed if follow-up units are healers
    item_names.WIDOW_MINE: LogicRating.ADVANCED_EXTRA,          # Weak, no building attack baseline
    item_names.RAVEN: LogicRating.ADVANCED_EXTRA,               # Caster
    item_names.SCIENCE_VESSEL: LogicRating.ADVANCED_EXTRA,      # Caster
    item_names.LIBERATOR: LogicRating.ADVANCED_EXTRA,           # Technical, no building attack baseline
    item_names.VALKYRIE: LogicRating.ADVANCED_EXTRA,            # Air-to-air
    item_names.EMPERORS_SHADOW: LogicRating.ADVANCED_EXTRA,     # Caster, expensive
    item_names.EMPERORS_GUARDIAN: LogicRating.ADVANCED_EXTRA,   # Technical, expensive
    item_names.BLACKHAMMER: LogicRating.ADVANCED_EXTRA,         # Primarily anti-air, expensive

    item_names.HERCULES: LogicRating.NONE,
}
item_name_groups[ItemGroupNames.TERRAN_BASIC_STARTER_UNITS] = terran_basic_starter_units = [
    _item_name for _item_name, _rating in _terran_core_units.items() if _rating & LogicRating.is_basic_starter
]
item_name_groups[ItemGroupNames.TERRAN_BASIC_CORE_UNITS] = terran_basic_units = [
    _item_name for _item_name, _rating in _terran_core_units.items() if _rating & LogicRating.is_basic_core
]
item_name_groups[ItemGroupNames.TERRAN_ADVANCED_STARTER_UNITS] = terran_advanced_starter_units = [
    _item_name for _item_name, _rating in _terran_core_units.items() if _rating & LogicRating.is_advanced_starter
]
item_name_groups[ItemGroupNames.TERRAN_ADVANCED_CORE_UNITS] = terran_advanced_units = [
    _item_name for _item_name, _rating in _terran_core_units.items() if _rating & LogicRating.is_advanced_core
]
item_name_groups[ItemGroupNames.TERRAN_CHAOS_STARTER_UNITS] = terran_chaos_starter_units = [
    # Infantry
    item_names.MARINE,
    item_names.FIREBAT,
    item_names.MARAUDER,
    item_names.REAPER,
    item_names.HERC,
    item_names.DOMINION_TROOPER,
    item_names.GHOST,
    item_names.SPECTRE,
    # Vehicles
    item_names.HELLION,
    item_names.VULTURE,
    item_names.SIEGE_TANK,
    item_names.WARHOUND,
    item_names.GOLIATH,
    item_names.DIAMONDBACK,
    item_names.THOR,
    item_names.PREDATOR,
    item_names.CYCLONE,
    # Ships
    item_names.WRAITH,
    item_names.VIKING,
    item_names.BANSHEE,
    item_names.RAVEN,
    item_names.BATTLECRUISER,
    # RG
    item_names.SON_OF_KORHAL,
    item_names.AEGIS_GUARD,
    item_names.EMPERORS_SHADOW,
    item_names.BULWARK_COMPANY,
    item_names.SHOCK_DIVISION,
    item_names.BLACKHAMMER,
    item_names.SKY_FURY,
    item_names.NIGHT_WOLF,
    item_names.NIGHT_HAWK,
    item_names.PRIDE_OF_AUGUSTGRAD,
]
item_name_groups[ItemGroupNames.TERRAN_GENERIC_UPGRADES] = terran_generic_upgrades = [
    item_name for item_name, item_data in item_tables.item_table.items()
    if item_data.type == item_tables.TerranItemType.Upgrade
]
item_name_groups[ItemGroupNames.TERRAN_MOBILE_DETECTION] = terran_mobile_detection = (
    item_names.RAVEN,
    item_names.SCIENCE_VESSEL,
    item_names.COMMAND_CENTER_SCANNER_SWEEP,
)
item_name_groups[ItemGroupNames.TERRAN_DETECTION] = terran_detection = (
    *terran_mobile_detection,
    item_names.MISSILE_TURRET,
)
barracks_wa_group = (
    item_names.MARINE, item_names.FIREBAT, item_names.MARAUDER,
    item_names.REAPER, item_names.GHOST, item_names.SPECTRE, item_names.HERC,
    item_names.DOMINION_TROOPER,
)
item_name_groups[ItemGroupNames.BARRACKS_UNITS] = barracks_units = (
    *barracks_wa_group,
    item_names.MEDIC,
    item_names.SON_OF_KORHAL,
    item_names.FIELD_RESPONSE_THETA,
    item_names.AEGIS_GUARD,
    item_names.EMPERORS_SHADOW,
)
factory_wa_group = (
    item_names.HELLION, item_names.VULTURE, item_names.GOLIATH, item_names.DIAMONDBACK,
    item_names.SIEGE_TANK, item_names.THOR, item_names.PREDATOR,
    item_names.CYCLONE, item_names.WARHOUND,
)
item_name_groups[ItemGroupNames.FACTORY_UNITS] = factory_units = (
    *factory_wa_group,
    item_names.WIDOW_MINE,
    item_names.BULWARK_COMPANY,
    item_names.SHOCK_DIVISION,
    item_names.BLACKHAMMER,
)
starport_wa_group = (
    item_names.WRAITH,
    item_names.VIKING,
    item_names.BANSHEE,
    item_names.BATTLECRUISER,
    item_names.LIBERATOR,
    item_names.VALKYRIE,
    item_names.RAVEN_HUNTER_SEEKER_WEAPON,
)
item_name_groups[ItemGroupNames.STARPORT_UNITS] = starport_units = (
    item_names.MEDIVAC, item_names.WRAITH, item_names.VIKING, item_names.BANSHEE,
    item_names.BATTLECRUISER, item_names.HERCULES, item_names.SCIENCE_VESSEL, item_names.RAVEN,
    item_names.LIBERATOR, item_names.VALKYRIE, item_names.PRIDE_OF_AUGUSTGRAD, item_names.SKY_FURY,
    item_names.EMPERORS_GUARDIAN, item_names.NIGHT_HAWK, item_names.NIGHT_WOLF,
)
terran_basic_barracks_units = _intersection(terran_basic_units, barracks_wa_group)
terran_basic_factory_units = _intersection(terran_basic_units, factory_wa_group)
terran_basic_starport_units = _intersection(terran_basic_units, starport_wa_group)
terran_advanced_barracks_units = _intersection(terran_advanced_units, barracks_wa_group)
terran_advanced_factory_units = _intersection(terran_advanced_units, factory_wa_group)
terran_advanced_starport_units = _intersection(terran_advanced_units, starport_wa_group)
terran_chaos_infantry_units = (
    *barracks_wa_group,
    item_names.WAR_PIGS,
    item_names.HAMMER_SECURITIES,
    item_names.DEVIL_DOGS,
    item_names.DEATH_HEADS,
)
terran_chaos_vehicle_units = (
    *factory_wa_group,
    item_names.SPARTAN_COMPANY,
    item_names.SIEGE_BREAKERS,
    item_names.JOTUN,
)
terran_chaos_ship_units = (
    *(_x for _x in starport_wa_group if _x != item_names.RAVEN_HUNTER_SEEKER_WEAPON),
    item_names.SCIENCE_VESSEL,
    item_names.RAVEN,
    item_names.HELS_ANGELS,
    item_names.DUSK_WINGS,
    item_names.JACKSONS_REVENGE,
    item_names.WINGED_NIGHTMARES,
    item_names.MIDNIGHT_RIDERS,
    item_names.BRYNHILDS,
)
item_name_groups[ItemGroupNames.TERRAN_MERCENARIES] = terran_mercenaries = tuple(
    item_name for item_name, item_data in item_tables.item_table.items()
    if item_data.type == item_tables.TerranItemType.Mercenary
)
item_name_groups[ItemGroupNames.NCO_UNITS] = nco_units = [
    item_names.MARINE, item_names.MARAUDER, item_names.REAPER,
    item_names.HELLION, item_names.GOLIATH, item_names.SIEGE_TANK,
    item_names.RAVEN, item_names.LIBERATOR, item_names.BANSHEE, item_names.BATTLECRUISER,
    item_names.HERC,  # From that one bonus objective in mission 5
]
item_name_groups[ItemGroupNames.NCO_BUILDINGS] = nco_buildings = [
    item_names.BUNKER, item_names.MISSILE_TURRET, item_names.PLANETARY_FORTRESS,
]
item_name_groups[ItemGroupNames.NOVA_EQUIPMENT] = nova_equipment = [
    *[item_name for item_name, item_data in item_tables.item_table.items()
      if item_data.type == item_tables.TerranItemType.Nova_Gear],
    item_names.NOVA_PROGRESSIVE_STEALTH_SUIT_MODULE,
]
item_name_groups[ItemGroupNames.NOVA_WEAPONS] = nova_weapons = [
    item_names.NOVA_C20A_CANISTER_RIFLE,
    item_names.NOVA_HELLFIRE_SHOTGUN,
    item_names.NOVA_PLASMA_RIFLE,
    item_names.NOVA_MONOMOLECULAR_BLADE,
    item_names.NOVA_BLAZEFIRE_GUNBLADE,
]
item_name_groups[ItemGroupNames.NOVA_GADGETS] = nova_gadgets = [
    item_names.NOVA_STIM_INFUSION,
    item_names.NOVA_PULSE_GRENADES,
    item_names.NOVA_FLASHBANG_GRENADES,
    item_names.NOVA_IONIC_FORCE_FIELD,
    item_names.NOVA_HOLO_DECOY,
]
item_name_groups[ItemGroupNames.NOVA_SUITS] = nova_suits = [
    item_names.NOVA_PROGRESSIVE_STEALTH_SUIT_MODULE,
    item_names.NOVA_JUMP_SUIT_MODULE,
    item_names.NOVA_ENERGY_SUIT_MODULE,
    item_names.NOVA_ARMORED_SUIT_MODULE,
]
item_name_groups[ItemGroupNames.WOL_UNITS] = wol_units = [
    item_names.MARINE, item_names.MEDIC, item_names.FIREBAT, item_names.MARAUDER, item_names.REAPER,
    item_names.HELLION, item_names.VULTURE, item_names.GOLIATH,  item_names.DIAMONDBACK, item_names.SIEGE_TANK,
    item_names.MEDIVAC, item_names.WRAITH, item_names.VIKING, item_names.BANSHEE, item_names.BATTLECRUISER,
    item_names.GHOST, item_names.SPECTRE, item_names.THOR,
    item_names.PREDATOR, item_names.HERCULES,
    item_names.SCIENCE_VESSEL, item_names.RAVEN,
]
item_name_groups[ItemGroupNames.WOL_MERCS] = wol_mercs = [
    item_names.WAR_PIGS, item_names.DEVIL_DOGS, item_names.HAMMER_SECURITIES,
    item_names.SPARTAN_COMPANY, item_names.SIEGE_BREAKERS,
    item_names.HELS_ANGELS, item_names.DUSK_WINGS, item_names.JACKSONS_REVENGE,
]
item_name_groups[ItemGroupNames.WOL_BUILDINGS] = wol_buildings = [
    item_names.BUNKER, item_names.MISSILE_TURRET, item_names.SENSOR_TOWER,
    item_names.PERDITION_TURRET, item_names.PLANETARY_FORTRESS,
    item_names.HIVE_MIND_EMULATOR, item_names.PSI_DISRUPTER,
]
item_name_groups[ItemGroupNames.TERRAN_BUILDINGS] = terran_buildings = [
    *[
        item_name for item_name, item_data in item_tables.item_table.items()
        if item_data.type == item_tables.TerranItemType.Building or item_name in wol_buildings
    ],
    item_names.PSI_SCREEN,
    item_names.SONIC_DISRUPTER,
    item_names.PSI_INDOCTRINATOR,
    item_names.ARGUS_AMPLIFIER,
]
item_name_groups[ItemGroupNames.TERRAN_ROYAL_GUARD_UNITS] = [
    # Elite Barracks
    item_names.SON_OF_KORHAL, item_names.FIELD_RESPONSE_THETA,
    item_names.AEGIS_GUARD, item_names.EMPERORS_SHADOW,
    # Elite Factory
    item_names.BULWARK_COMPANY,
    item_names.SHOCK_DIVISION, item_names.BLACKHAMMER,
    # Elite Starport
    item_names.PRIDE_OF_AUGUSTGRAD, item_names.SKY_FURY,
    item_names.NIGHT_HAWK, item_names.EMPERORS_GUARDIAN,
    item_names.NIGHT_WOLF,
]
item_name_groups[ItemGroupNames.ORBITAL_COMMAND_ABILITIES] = orbital_command_abilities = [
    item_names.COMMAND_CENTER_SCANNER_SWEEP,
    item_names.COMMAND_CENTER_MULE,
    item_names.COMMAND_CENTER_EXTRA_SUPPLIES,
]
item_name_groups[ItemGroupNames.WOL_ORBITAL_COMMAND_ABILITIES] = wol_orbital_command_abilities = [
    item_names.COMMAND_CENTER_SCANNER_SWEEP,
    item_names.COMMAND_CENTER_MULE,
]
spider_mine_sources = [
    item_names.VULTURE,
    item_names.REAPER_SPIDER_MINES,
    item_names.SIEGE_TANK_SPIDER_MINES,
    item_names.RAVEN_SPIDER_MINES,
]
item_name_groups[ItemGroupNames.TERRAN_SC1_UNITS] = [
    item_names.MARINE,
    item_names.FIREBAT,
    item_names.GHOST,
    item_names.MEDIC,
    item_names.VULTURE,
    item_names.SIEGE_TANK,
    item_names.GOLIATH,
    item_names.WRAITH,
    # No dropship
    item_names.SCIENCE_VESSEL,
    item_names.BATTLECRUISER,
    item_names.VALKYRIE,
]
item_name_groups[ItemGroupNames.TERRAN_SC1_BUILDINGS] = [
    item_names.BUNKER,
    item_names.MISSILE_TURRET,
]
item_name_groups[ItemGroupNames.TERRAN_LADDER_UNITS] = [
    item_names.MARINE,
    item_names.MARAUDER,
    item_names.REAPER,
    item_names.GHOST,
    item_names.HELLION,
    item_names.WIDOW_MINE,
    item_names.SIEGE_TANK,
    item_names.THOR,
    item_names.CYCLONE,
    item_names.VIKING,
    item_names.MEDIVAC,
    item_names.LIBERATOR,
    item_names.RAVEN,
    item_names.BANSHEE,
    item_names.BATTLECRUISER,
]

# Terran Upgrades
item_name_groups[ItemGroupNames.WOL_UPGRADES] = wol_upgrades = [
    # Armory Base
    item_names.BUNKER_PROJECTILE_ACCELERATOR, item_names.BUNKER_NEOSTEEL_BUNKER,
    item_names.MISSILE_TURRET_TITANIUM_HOUSING, item_names.MISSILE_TURRET_HELLSTORM_BATTERIES,
    item_names.SCV_ADVANCED_CONSTRUCTION, item_names.SCV_DUAL_FUSION_WELDERS,
    item_names.PROGRESSIVE_FIRE_SUPPRESSION_SYSTEM, item_names.COMMAND_CENTER_MULE, item_names.COMMAND_CENTER_SCANNER_SWEEP,
    # Armory Infantry
    item_names.MARINE_STIMPACK, item_names.MARINE_COMBAT_SHIELD,
    item_names.MEDIC_ADVANCED_MEDIC_FACILITIES, item_names.MEDIC_STABILIZER_MEDPACKS,
    item_names.FIREBAT_INCINERATOR_GAUNTLETS, item_names.FIREBAT_JUGGERNAUT_PLATING,
    item_names.MARAUDER_CONCUSSIVE_SHELLS, item_names.MARAUDER_KINETIC_FOAM,
    item_names.REAPER_U238_ROUNDS, item_names.REAPER_G4_CLUSTERBOMB,
    # Armory Vehicles
    item_names.HELLION_TWIN_LINKED_FLAMETHROWER, item_names.HELLION_THERMITE_FILAMENTS,
    item_names.SPIDER_MINE_CERBERUS_MINE, item_names.VULTURE_PROGRESSIVE_REPLENISHABLE_MAGAZINE,
    item_names.GOLIATH_MULTI_LOCK_WEAPONS_SYSTEM, item_names.GOLIATH_ARES_CLASS_TARGETING_SYSTEM,
    item_names.DIAMONDBACK_PROGRESSIVE_TRI_LITHIUM_POWER_CELL, item_names.DIAMONDBACK_SHAPED_HULL,
    item_names.SIEGE_TANK_MAELSTROM_ROUNDS, item_names.SIEGE_TANK_SHAPED_BLAST,
    # Armory Starships
    item_names.MEDIVAC_RAPID_DEPLOYMENT_TUBE, item_names.MEDIVAC_ADVANCED_HEALING_AI,
    item_names.WRAITH_PROGRESSIVE_TOMAHAWK_POWER_CELLS, item_names.WRAITH_DISPLACEMENT_FIELD,
    item_names.VIKING_RIPWAVE_MISSILES, item_names.VIKING_PHOBOS_CLASS_WEAPONS_SYSTEM,
    item_names.BANSHEE_PROGRESSIVE_CROSS_SPECTRUM_DAMPENERS, item_names.BANSHEE_SHOCKWAVE_MISSILE_BATTERY,
    item_names.BATTLECRUISER_PROGRESSIVE_MISSILE_PODS, item_names.BATTLECRUISER_PROGRESSIVE_DEFENSIVE_MATRIX,
    # Armory Dominion
    item_names.GHOST_OCULAR_IMPLANTS, item_names.GHOST_CRIUS_SUIT,
    item_names.SPECTRE_PSIONIC_LASH, item_names.SPECTRE_NYX_CLASS_CLOAKING_MODULE,
    item_names.THOR_330MM_BARRAGE_CANNON, item_names.THOR_PROGRESSIVE_IMMORTALITY_PROTOCOL,
    # Lab Zerg
    item_names.BUNKER_FORTIFIED_BUNKER, item_names.BUNKER_SHRIKE_TURRET,
    item_names.PROGRESSIVE_REGENERATIVE_BIO_STEEL, item_names.CELLULAR_REACTOR,
    # Other 3 levels are units/buildings (Perdition, PF, Hercules, Predator, HME, Psi Disrupter)
    # Lab Protoss
    item_names.VANADIUM_PLATING, item_names.ULTRA_CAPACITORS,
    item_names.AUTOMATED_REFINERY, item_names.MICRO_FILTERING,
    item_names.ORBITAL_DEPOTS, item_names.COMMAND_CENTER_COMMAND_CENTER_REACTOR,
    item_names.ORBITAL_STRIKE, item_names.TECH_REACTOR,
    # Other level is units (Raven, Science Vessel)
]
item_name_groups[ItemGroupNames.TERRAN_STIMPACKS] = terran_stimpacks = [
    item_names.MARINE_STIMPACK,
    item_names.MARAUDER_STIMPACK,
    item_names.REAPER_STIMPACK,
    item_names.FIREBAT_STIMPACK,
    item_names.HELLION_STIMPACK,
]
item_name_groups[ItemGroupNames.TERRAN_ORIGINAL_PROGRESSIVE_UPGRADES] = terran_original_progressive_upgrades = [
    item_names.PROGRESSIVE_FIRE_SUPPRESSION_SYSTEM,
    item_names.VULTURE_PROGRESSIVE_REPLENISHABLE_MAGAZINE,
    item_names.DIAMONDBACK_PROGRESSIVE_TRI_LITHIUM_POWER_CELL,
    item_names.WRAITH_PROGRESSIVE_TOMAHAWK_POWER_CELLS,
    item_names.BANSHEE_PROGRESSIVE_CROSS_SPECTRUM_DAMPENERS,
    item_names.BATTLECRUISER_PROGRESSIVE_MISSILE_PODS,
    item_names.BATTLECRUISER_PROGRESSIVE_DEFENSIVE_MATRIX,
    item_names.THOR_PROGRESSIVE_IMMORTALITY_PROTOCOL,
    item_names.PROGRESSIVE_REGENERATIVE_BIO_STEEL,
]
item_name_groups[ItemGroupNames.NCO_BASELINE_UPGRADES] = nco_baseline_upgrades = [
    item_names.BUNKER_NEOSTEEL_BUNKER,  # Baseline from mission 2
    item_names.BUNKER_FORTIFIED_BUNKER,  # Baseline from mission 2
    item_names.MARINE_COMBAT_SHIELD,   # Baseline from mission 2
    item_names.MARAUDER_KINETIC_FOAM,  # Baseline outside WOL
    item_names.MARAUDER_CONCUSSIVE_SHELLS,  # Baseline from mission 2
    item_names.REAPER_BALLISTIC_FLIGHTSUIT, # Baseline from mission 2
    item_names.HELLION_HELLBAT,  # Baseline from mission 3
    item_names.GOLIATH_INTERNAL_TECH_MODULE,  # Baseline from mission 4
    item_names.GOLIATH_SHAPED_HULL,
    # ItemNames.GOLIATH_RESOURCE_EFFICIENCY,  # Supply savings baseline in NCO, mineral savings is non-NCO
    item_names.SIEGE_TANK_SHAPED_HULL,  # Baseline NCO gives +10; this upgrade gives +25
    item_names.SIEGE_TANK_SHAPED_BLAST,  # Baseline from mission 3
    item_names.LIBERATOR_RAID_ARTILLERY,  # Baseline in mission 5
    item_names.RAVEN_BIO_MECHANICAL_REPAIR_DRONE,  # Baseline in mission 5
    item_names.BATTLECRUISER_TACTICAL_JUMP,
    item_names.BATTLECRUISER_MOIRAI_IMPULSE_DRIVE,
    item_names.PROGRESSIVE_FIRE_SUPPRESSION_SYSTEM,  # Baseline from mission 2
    item_names.ORBITAL_DEPOTS,  # Baseline from mission 2
    item_names.COMMAND_CENTER_SCANNER_SWEEP,  # In NCO you must actually morph Command Center into Orbital Command
    item_names.COMMAND_CENTER_EXTRA_SUPPLIES,  # But in AP this works WoL-style
] + nco_buildings
item_name_groups[ItemGroupNames.NCO_UNIT_TECHNOLOGY] = nco_unit_technology = [
    item_names.MARINE_LASER_TARGETING_SYSTEM,
    item_names.MARINE_STIMPACK,
    item_names.MARINE_MEDPACK,
    item_names.MARINE_MAGRAIL_MUNITIONS,
    item_names.MARINE_OPTIMIZED_LOGISTICS,
    item_names.MARAUDER_LASER_TARGETING_SYSTEM,
    item_names.MARAUDER_INTERNAL_TECH_MODULE,
    item_names.MARAUDER_STIMPACK,
    item_names.MARAUDER_MEDPACK,
    item_names.MARAUDER_MAGRAIL_MUNITIONS,
    item_names.REAPER_SPIDER_MINES,
    item_names.REAPER_LASER_TARGETING_SYSTEM,
    item_names.REAPER_STIMPACK,
    item_names.REAPER_MEDPACK,
    item_names.REAPER_ADVANCED_CLOAKING_FIELD,
    # Reaper special ordnance gives anti-building attack, which is baseline in AP
    item_names.HELLION_JUMP_JETS,
    item_names.HELLION_STIMPACK,
    item_names.HELLION_MEDPACK,
    item_names.HELLION_SMART_SERVOS,
    item_names.HELLION_OPTIMIZED_LOGISTICS,
    item_names.HELLION_THERMITE_FILAMENTS,  # Called Infernal Pre-Igniter in NCO
    item_names.GOLIATH_ARES_CLASS_TARGETING_SYSTEM,  # Called Laser Targeting System in NCO
    item_names.GOLIATH_JUMP_JETS,
    item_names.GOLIATH_OPTIMIZED_LOGISTICS,
    item_names.GOLIATH_MULTI_LOCK_WEAPONS_SYSTEM,
    item_names.SIEGE_TANK_SPIDER_MINES,
    item_names.SIEGE_TANK_JUMP_JETS,
    item_names.SIEGE_TANK_INTERNAL_TECH_MODULE,
    item_names.SIEGE_TANK_SMART_SERVOS,
    # Tanks can't get Laser targeting system in NCO
    item_names.BANSHEE_INTERNAL_TECH_MODULE,
    item_names.BANSHEE_PROGRESSIVE_CROSS_SPECTRUM_DAMPENERS,
    item_names.BANSHEE_SHOCKWAVE_MISSILE_BATTERY,  # Banshee Special Ordnance
    # Banshees can't get laser targeting systems in NCO
    item_names.LIBERATOR_CLOAK,
    item_names.LIBERATOR_SMART_SERVOS,
    item_names.LIBERATOR_OPTIMIZED_LOGISTICS,
    # Liberators can't get laser targeting system in NCO
    item_names.RAVEN_SPIDER_MINES,
    item_names.RAVEN_INTERNAL_TECH_MODULE,
    item_names.RAVEN_RAILGUN_TURRET,        # Raven Magrail Munitions
    item_names.RAVEN_HUNTER_SEEKER_WEAPON,  # Raven Special Ordnance
    item_names.BATTLECRUISER_INTERNAL_TECH_MODULE,
    item_names.BATTLECRUISER_CLOAK,
    item_names.BATTLECRUISER_ATX_LASER_BATTERY,  # Battlecruiser Special Ordnance
    item_names.PROGRESSIVE_REGENERATIVE_BIO_STEEL,
]
item_name_groups[ItemGroupNames.NCO_UPGRADES] = nco_upgrades = nco_baseline_upgrades + nco_unit_technology
item_name_groups[ItemGroupNames.NCO_MAX_PROGRESSIVE_ITEMS] = nco_unit_technology + nova_equipment + terran_generic_upgrades
item_name_groups[ItemGroupNames.NCO_MIN_PROGRESSIVE_ITEMS] = nco_units + nco_baseline_upgrades
item_name_groups[ItemGroupNames.TERRAN_PROGRESSIVE_UPGRADES] = terran_progressive_items = [
    item_name for item_name, item_data in item_tables.item_table.items()
    if item_data.type in (item_tables.TerranItemType.Progressive, item_tables.TerranItemType.Progressive_2)
]
item_name_groups[ItemGroupNames.WOL_ITEMS] = vanilla_wol_items = (
    wol_units
    + wol_buildings
    + wol_mercs
    + wol_upgrades
    + orbital_command_abilities
    + terran_generic_upgrades
)

# Co-op Terran
item_name_groups[ItemGroupNames.COOP_RAYNOR_UNITS] = [
    item_names.MARINE,
    item_names.MARAUDER,
    item_names.FIREBAT,
    item_names.MEDIC,
    item_names.VULTURE,
    item_names.SIEGE_TANK,
    item_names.VIKING,
    item_names.BANSHEE,
    item_names.BATTLECRUISER,
]
item_name_groups[ItemGroupNames.COOP_SWANN_UNITS] = [
    item_names.HELLION,
    # (Hellbat)
    item_names.GOLIATH,
    item_names.SIEGE_TANK,
    item_names.CYCLONE,
    item_names.THOR,
    item_names.WRAITH,
    item_names.HERCULES,
    item_names.SCIENCE_VESSEL,
]
item_name_groups[ItemGroupNames.COOP_NOVA_UNITS] = [
    # Note: Co-op Nova has elite variants of these units
    item_names.MARINE,
    item_names.MARAUDER,
    item_names.GHOST,
    item_names.HELLION,
    # (Hellbat)
    item_names.GOLIATH,
    item_names.SIEGE_TANK,
    item_names.LIBERATOR,
    item_names.BANSHEE,
    item_names.RAVEN,
]
item_name_groups[ItemGroupNames.COOP_HAN_AND_HORNER_UNITS] = [
    # Not implemented: Assault Galleon
    item_names.REAPER,
    item_names.WIDOW_MINE,
    item_names.HELLION,
    # (Hellbat)
    # Note: Co-op Horner has elite variants of these units
    item_names.WRAITH,
    item_names.VIKING,
    item_names.RAVEN,
    item_names.BATTLECRUISER,
]
item_name_groups[ItemGroupNames.COOP_MENGSK_UNITS] = [
    item_names.AEGIS_GUARD,
    item_names.EMPERORS_SHADOW,
    item_names.SHOCK_DIVISION,
    item_names.BLACKHAMMER,
    item_names.PRIDE_OF_AUGUSTGRAD,
    item_names.SKY_FURY,
    item_names.DOMINION_TROOPER,
    item_names.MEDIVAC,  # Imperial Intercessor
    # Not implemented: Imperial Witness
]

# Zerg
item_name_groups[ItemGroupNames.ZERG_ITEMS] = zerg_items = [
    item_name for item_name, item_data in item_tables.item_table.items()
    if item_data.race == SC2Race.ZERG
]
item_name_groups[ItemGroupNames.ZERG_BUILDINGS] = zerg_buildings = [
    item_names.SPINE_CRAWLER,
    item_names.SPORE_CRAWLER,
    item_names.BILE_LAUNCHER,
    item_names.INFESTED_BUNKER,
    item_names.INFESTED_MISSILE_TURRET,
    item_names.NYDUS_WORM,
    item_names.ECHIDNA_WORM]
item_name_groups[ItemGroupNames.ZERG_NONMORPH_UNITS] = zerg_nonmorph_units = [
    item_name for item_name, item_data in item_tables.item_table.items()
    if item_data.type in (
        item_tables.ZergItemType.Unit, item_tables.ZergItemType.Mercenary
    )
       and item_name not in zerg_buildings
]
item_name_groups[ItemGroupNames.ZERG_MORPHS] = zerg_morphs = [
    item_name for item_name, item_data in item_tables.item_table.items() if item_data.type == item_tables.ZergItemType.Morph
]
item_name_groups[ItemGroupNames.ZERG_UNITS] = zerg_units = zerg_nonmorph_units + zerg_morphs
# For W/A upgrades
zerg_ground_units = [
    item_names.ZERGLING,
    item_names.HIVE_QUEEN,
    item_names.SWARM_QUEEN,
    item_names.ROACH, item_names.HYDRALISK, item_names.ABERRATION,
    item_names.SWARM_HOST, item_names.INFESTOR, item_names.ULTRALISK, item_names.BANELING,
    item_names.LURKER, item_names.IMPALER, item_names.TYRANNOZOR,
    item_names.RAVAGER, item_names.DEFILER, item_names.PRIMAL_IGNITER,
    item_names.PYGALISK,
    item_names.INFESTED_MARINE, item_names.INFESTED_BUNKER, item_names.INFESTED_DIAMONDBACK,
    item_names.INFESTED_SIEGE_TANK,
]
_zerg_core_units = {
    item_names.SWARM_QUEEN: LogicRating.BASIC_STARTER,
    item_names.ROACH: LogicRating.BASIC_STARTER,
    item_names.HYDRALISK: LogicRating.BASIC_STARTER,
    item_names.ABERRATION: LogicRating.BASIC_STARTER,
    item_names.PYGALISK: LogicRating.BASIC_STARTER,
    item_names.INFESTED_DIAMONDBACK: LogicRating.BASIC_STARTER,

    # item_names.BROOD_LORD: LogicRating.BASIC_EXTRA,
    # item_names.GUARDIAN: LogicRating.BASIC_EXTRA,
    # item_names.TYRANNOZOR: LogicRating.BASIC_EXTRA,
    # item_names.PRIMAL_IGNITER: LogicRating.BASIC_EXTRA | LogicRating.ADVANCED_STARTER,
    # item_names.LURKER: LogicRating.BASIC_EXTRA | LogicRating.ADVANCED_STARTER,
    # item_names.IMPALER: LogicRating.BASIC_EXTRA | LogicRating.ADVANCED_STARTER,
    item_names.ZERGLING: LogicRating.BASIC_EXTRA | LogicRating.ADVANCED_STARTER,
    item_names.MUTALISK: LogicRating.BASIC_EXTRA | LogicRating.ADVANCED_STARTER,
    item_names.SWARM_HOST: LogicRating.BASIC_EXTRA | LogicRating.ADVANCED_STARTER,
    item_names.ULTRALISK: LogicRating.BASIC_EXTRA | LogicRating.ADVANCED_STARTER,
    item_names.INFESTED_MARINE: LogicRating.BASIC_EXTRA | LogicRating.ADVANCED_STARTER,
    item_names.INFESTED_BANSHEE: LogicRating.BASIC_EXTRA | LogicRating.ADVANCED_STARTER,

    # item_names.RAVAGER: LogicRating.ADVANCED_STARTER,

    item_names.INFESTOR: LogicRating.ADVANCED_EXTRA,  # Caster
    item_names.HIVE_QUEEN: LogicRating.ADVANCED_EXTRA,  # Caster
    item_names.BROOD_QUEEN: LogicRating.ADVANCED_EXTRA,  # Caster
    item_names.DEFILER: LogicRating.ADVANCED_EXTRA,  # Caster
    item_names.INFESTED_SIEGE_TANK: LogicRating.ADVANCED_EXTRA,
    item_names.BULLFROG: LogicRating.ADVANCED_EXTRA,
    item_names.CORRUPTOR: LogicRating.ADVANCED_EXTRA,  # Air-to-air
    item_names.INFESTED_LIBERATOR: LogicRating.ADVANCED_EXTRA,  # Air-to-air
    # item_names.VIPER: LogicRating.ADVANCED_EXTRA,
    # item_names.DEVOURER: LogicRating.ADVANCED_EXTRA,

    item_names.SCOURGE: LogicRating.NONE,  # Air-to-air, suicide
    # item_names.BANELING: LogicRating.NONE,
}
item_name_groups[ItemGroupNames.ZERG_BASIC_STARTER_UNITS] = zerg_basic_starter_units = [
    _item_name for _item_name, _rating in _zerg_core_units.items() if _rating & LogicRating.is_basic_starter
]
item_name_groups[ItemGroupNames.ZERG_BASIC_CORE_UNITS] = zerg_basic_units = [
    _item_name for _item_name, _rating in _zerg_core_units.items() if _rating & LogicRating.is_basic_core
]
item_name_groups[ItemGroupNames.ZERG_ADVANCED_STARTER_UNITS] = zerg_advanced_starter_units = [
    _item_name for _item_name, _rating in _zerg_core_units.items() if _rating & LogicRating.is_advanced_starter
]
item_name_groups[ItemGroupNames.ZERG_ADVANCED_CORE_UNITS] = zerg_advanced_units = [
    _item_name for _item_name, _rating in _zerg_core_units.items() if _rating & LogicRating.is_advanced_core
]
item_name_groups[ItemGroupNames.ZERG_CHAOS_STARTER_UNITS] = zerg_chaos_starter_units = [
    item_names.ZERGLING,
    item_names.SWARM_QUEEN,
    item_names.HIVE_QUEEN,
    item_names.ROACH,
    item_names.HYDRALISK,
    item_names.ABERRATION,
    item_names.SWARM_HOST,
    item_names.MUTALISK,
    item_names.ULTRALISK,
    item_names.PYGALISK,
    item_names.INFESTED_MARINE,
    item_names.INFESTED_BUNKER,
    item_names.INFESTED_DIAMONDBACK,
    item_names.INFESTED_SIEGE_TANK,
    item_names.INFESTED_BANSHEE,
]
zerg_melee_wa = [
    item_names.ZERGLING, item_names.ABERRATION, item_names.ULTRALISK, item_names.BANELING,
    item_names.TYRANNOZOR, item_names.INFESTED_BUNKER, item_names.PYGALISK,
]
zerg_ranged_wa = [
    item_names.HIVE_QUEEN,
    item_names.SWARM_QUEEN,
    item_names.ROACH, item_names.HYDRALISK, item_names.SWARM_HOST,
    item_names.LURKER, item_names.IMPALER, item_names.TYRANNOZOR,
    item_names.RAVAGER, item_names.PRIMAL_IGNITER, item_names.INFESTED_MARINE,
    item_names.INFESTED_BUNKER, item_names.INFESTED_DIAMONDBACK, item_names.INFESTED_SIEGE_TANK,
]
zerg_air_units = [
    item_names.MUTALISK, item_names.VIPER, item_names.BROOD_LORD,
    item_names.CORRUPTOR, item_names.BROOD_QUEEN, item_names.SCOURGE, item_names.GUARDIAN,
    item_names.DEVOURER, item_names.INFESTED_BANSHEE, item_names.INFESTED_LIBERATOR,
]
zerg_basic_melee_units = _intersection(zerg_basic_units, zerg_melee_wa)
zerg_basic_ranged_units = _intersection(zerg_basic_units, zerg_ranged_wa)
zerg_basic_air_units = _intersection(zerg_basic_units, zerg_air_units)
zerg_basic_melee_morphs = (
    item_names.TYRANNOZOR,
)
zerg_basic_ranged_morphs = (
    item_names.PRIMAL_IGNITER,
    item_names.LURKER,
    item_names.IMPALER,
)
zerg_basic_air_morphs = (
    item_names.BROOD_LORD,
    item_names.GUARDIAN,
)
zerg_advanced_melee_units = _intersection(zerg_advanced_units, zerg_melee_wa)
zerg_advanced_ranged_units = _intersection(zerg_advanced_units, zerg_ranged_wa)
zerg_advanced_air_units = _intersection(zerg_advanced_units, zerg_air_units)
zerg_advanced_melee_morphs = zerg_basic_melee_morphs
zerg_advanced_ranged_morphs = (
    *zerg_basic_ranged_morphs,
    item_names.RAVAGER,
)
zerg_advanced_air_morphs = (
    *zerg_basic_air_morphs,
    item_names.VIPER,
    item_names.DEVOURER,
)
zerg_chaos_melee_units = (
    *(_x for _x in zerg_melee_wa if _x not in zerg_morphs),
    item_names.HUNTERLING,
    item_names.DEVOURING_ONES,
    item_names.WISE_OLD_TORRASQUE,
)
zerg_chaos_ranged_units = (
    *(_x for _x in zerg_ranged_wa if _x not in zerg_morphs),
    item_names.INFESTED_SIEGE_BREAKERS,
    item_names.HUNTER_KILLERS,
    item_names.CAUSTIC_HORRORS,
)
zerg_chaos_air_units = (
    *(_x for _x in zerg_air_units if _x not in zerg_morphs),
    item_names.INFESTED_DUSK_WINGS,
)

item_name_groups[ItemGroupNames.ZERG_GENERIC_UPGRADES] = zerg_generic_upgrades = [
    item_name for item_name, item_data in item_tables.item_table.items()
    if item_data.type == item_tables.ZergItemType.Upgrade
]
item_name_groups[ItemGroupNames.ZERG_MOBILE_DETECTION] = zerg_mobile_detection = (
    item_names.OVERSEER,
    item_names.BROOD_QUEEN,
)
item_name_groups[ItemGroupNames.ZERG_DETECTION] = zerg_detection = (
    *zerg_mobile_detection,
    item_names.SPORE_CRAWLER,
    item_names.INFESTED_MISSILE_TURRET,
)
item_name_groups[ItemGroupNames.HOTS_UNITS] = hots_units = [
    item_names.ZERGLING, item_names.SWARM_QUEEN, item_names.ROACH, item_names.HYDRALISK,
    item_names.ABERRATION, item_names.SWARM_HOST, item_names.MUTALISK,
    item_names.INFESTOR, item_names.ULTRALISK,
    item_names.BANELING,
    item_names.LURKER,
    item_names.IMPALER,
    item_names.VIPER,
    item_names.BROOD_LORD,
]
item_name_groups[ItemGroupNames.HOTS_BUILDINGS] = hots_buildings = [
    item_names.SPINE_CRAWLER,
    item_names.SPORE_CRAWLER,
]
item_name_groups[ItemGroupNames.HOTS_MORPHS] = hots_morphs = [
    item_names.BANELING,
    item_names.IMPALER,
    item_names.LURKER,
    item_names.VIPER,
    item_names.BROOD_LORD,
]
item_name_groups[ItemGroupNames.ZERG_MERCENARIES] = zerg_mercenaries = [
    item_name for item_name, item_data in item_tables.item_table.items() if item_data.type == item_tables.ZergItemType.Mercenary
]
item_name_groups[ItemGroupNames.KERRIGAN_ABILITIES] = kerrigan_abilities = [
    item_name for item_name, item_data in item_tables.item_table.items() if item_data.type == item_tables.ZergItemType.Ability
]
item_name_groups[ItemGroupNames.KERRIGAN_PASSIVES] = kerrigan_passives = [
    item_names.KERRIGAN_HEROIC_FORTITUDE, item_names.KERRIGAN_CHAIN_REACTION,
    item_names.KERRIGAN_INFEST_BROODLINGS, item_names.KERRIGAN_FURY, item_names.KERRIGAN_ABILITY_EFFICIENCY,
]
item_name_groups[ItemGroupNames.KERRIGAN_ACTIVE_ABILITIES] = kerrigan_active_abilities = [
    item_name for item_name in kerrigan_abilities if item_name not in kerrigan_passives
]
item_name_groups[ItemGroupNames.KERRIGAN_LOGIC_ACTIVE_ABILITIES] = kerrigan_logic_active_abilities = [
    item_name for item_name in kerrigan_active_abilities if item_name != item_names.KERRIGAN_ASSIMILATION_AURA
]
item_name_groups[ItemGroupNames.KERRIGAN_SOLO_ACTIVE_ABILITIES] = kerrigan_solo_active_abilities = [
    item_name for item_name in kerrigan_logic_active_abilities if item_name != item_names.KERRIGAN_WILD_MUTATION
]
item_name_groups[ItemGroupNames.KERRIGAN_TIER_1] = kerrigan_tier_1 = [
    item_names.KERRIGAN_KINETIC_BLAST, item_names.KERRIGAN_HEROIC_FORTITUDE, item_names.KERRIGAN_LEAPING_STRIKE
]
item_name_groups[ItemGroupNames.KERRIGAN_TIER_2] = kerrigan_tier_2= [
    item_names.KERRIGAN_CRUSHING_GRIP, item_names.KERRIGAN_CHAIN_REACTION, item_names.KERRIGAN_PSIONIC_SHIFT
]
item_name_groups[ItemGroupNames.KERRIGAN_TIER_3] = kerrigan_tier_3 = [
    item_names.TWIN_DRONES, item_names.AUTOMATED_EXTRACTORS, item_names.ZERGLING_RECONSTITUTION
]
item_name_groups[ItemGroupNames.KERRIGAN_TIER_4] = kerrigan_tier_4 = [
    item_names.KERRIGAN_MEND, item_names.KERRIGAN_SPAWN_BANELINGS, item_names.KERRIGAN_WILD_MUTATION
]
item_name_groups[ItemGroupNames.KERRIGAN_TIER_5] = kerrigan_tier_5 = [
    item_names.MALIGNANT_CREEP, item_names.VESPENE_EFFICIENCY, item_names.OVERLORD_IMPROVED_OVERLORDS
]
item_name_groups[ItemGroupNames.KERRIGAN_TIER_6] = kerrigan_tier_6 = [
    item_names.KERRIGAN_INFEST_BROODLINGS, item_names.KERRIGAN_FURY, item_names.KERRIGAN_ABILITY_EFFICIENCY
]
item_name_groups[ItemGroupNames.KERRIGAN_TIER_7] = kerrigan_tier_7 = [
    item_names.KERRIGAN_APOCALYPSE, item_names.KERRIGAN_SPAWN_LEVIATHAN, item_names.KERRIGAN_DROP_PODS
]
item_name_groups[ItemGroupNames.KERRIGAN_ULTIMATES] = kerrigan_ultimates = [
    *kerrigan_tier_7, item_names.KERRIGAN_ASSIMILATION_AURA, item_names.KERRIGAN_IMMOBILIZATION_WAVE
]
item_name_groups[ItemGroupNames.KERRIGAN_NON_ULTIMATES] = kerrigan_non_ultimates = [
    item for item in kerrigan_abilities if item not in kerrigan_ultimates
]
item_name_groups[ItemGroupNames.KERRIGAN_LOGIC_ULTIMATES] = kerrigan_logic_ultimates = [
    item for item in kerrigan_ultimates if item != item_names.KERRIGAN_ASSIMILATION_AURA
]
item_name_groups[ItemGroupNames.KERRIGAN_NON_ULTIMATE_ACTIVE_ABILITIES] = kerrigan_non_ulimate_active_abilities = [
    item for item in kerrigan_non_ultimates if item in kerrigan_active_abilities
]
item_name_groups[ItemGroupNames.KERRIGAN_HOTS_ABILITIES] = kerrigan_hots_abilities = [
    ability for tiers in [
        kerrigan_tier_1, kerrigan_tier_2, kerrigan_tier_4, kerrigan_tier_6, kerrigan_tier_7
    ] for ability in tiers
]

item_name_groups[ItemGroupNames.OVERLORD_UPGRADES] = [
    item_names.OVERLORD_ANTENNAE,
    item_names.OVERLORD_VENTRAL_SACS,
    item_names.OVERLORD_GENERATE_CREEP,
    item_names.OVERLORD_PNEUMATIZED_CARAPACE,
    item_names.OVERLORD_IMPROVED_OVERLORDS,
    item_names.OVERSEER,
]
item_name_groups[ItemGroupNames.ZERG_SC1_UNITS] = [
    item_names.ZERGLING,
    item_names.HYDRALISK,
    item_names.MUTALISK,
    item_names.SCOURGE,
    item_names.BROOD_QUEEN,
    item_names.DEFILER,
    item_names.ULTRALISK,
    item_names.LURKER,
    item_names.DEVOURER,
    item_names.GUARDIAN,
    item_names.DEVOURING_ONES,
    item_names.HUNTER_KILLERS,
    item_names.WISE_OLD_TORRASQUE,
]
item_name_groups[ItemGroupNames.ZERG_LADDER_UNITS] = [
    item_names.ZERGLING,
    item_names.HIVE_QUEEN,
    item_names.BANELING,
    item_names.ROACH,
    item_names.RAVAGER,
    item_names.OVERSEER,
    item_names.HYDRALISK,
    item_names.LURKER,
    item_names.MUTALISK,
    item_names.CORRUPTOR,
    item_names.VIPER,
    item_names.BROOD_LORD,
    item_names.INFESTOR,
    item_names.SWARM_HOST,
    item_names.ULTRALISK,
]

# Zerg Upgrades
item_name_groups[ItemGroupNames.HOTS_STRAINS] = hots_strains = [
    item_name for item_name, item_data in item_tables.item_table.items() if item_data.type == item_tables.ZergItemType.Strain
]
item_name_groups[ItemGroupNames.HOTS_MUTATIONS] = hots_mutations = [
    item_names.ZERGLING_HARDENED_CARAPACE, item_names.ZERGLING_ADRENAL_OVERLOAD, item_names.ZERGLING_METABOLIC_BOOST,
    item_names.BANELING_CORROSIVE_ACID, item_names.BANELING_RUPTURE, item_names.BANELING_REGENERATIVE_ACID,
    item_names.ROACH_HYDRIODIC_BILE, item_names.ROACH_ADAPTIVE_PLATING, item_names.ROACH_TUNNELING_CLAWS,
    item_names.HYDRALISK_FRENZY, item_names.HYDRALISK_ANCILLARY_CARAPACE, item_names.HYDRALISK_GROOVED_SPINES,
    item_names.SWARM_HOST_BURROW, item_names.SWARM_HOST_RAPID_INCUBATION, item_names.SWARM_HOST_PRESSURIZED_GLANDS,
    item_names.MUTALISK_VICIOUS_GLAIVE, item_names.MUTALISK_RAPID_REGENERATION, item_names.MUTALISK_SUNDERING_GLAIVE,
    item_names.ULTRALISK_BURROW_CHARGE, item_names.ULTRALISK_TISSUE_ASSIMILATION, item_names.ULTRALISK_MONARCH_BLADES,
]
item_name_groups[ItemGroupNames.HOTS_GLOBAL_UPGRADES] = hots_global_upgrades = [
    item_names.ZERGLING_RECONSTITUTION,
    item_names.OVERLORD_IMPROVED_OVERLORDS,
    item_names.AUTOMATED_EXTRACTORS,
    item_names.TWIN_DRONES,
    item_names.MALIGNANT_CREEP,
    item_names.VESPENE_EFFICIENCY,
]
item_name_groups[ItemGroupNames.HOTS_ITEMS] = vanilla_hots_items = (
    hots_units
    + hots_buildings
    + kerrigan_hots_abilities
    + hots_mutations
    + hots_strains
    + hots_global_upgrades
    + zerg_generic_upgrades
)

# Zerg - Infested Terran
item_name_groups[ItemGroupNames.INFESTED_TERRAN_UNITS] = infterr_units = [
    item_names.INFESTED_MARINE,
    item_names.INFESTED_BUNKER,
    item_names.BULLFROG,
    item_names.INFESTED_DIAMONDBACK,
    item_names.INFESTED_SIEGE_TANK,
    item_names.INFESTED_LIBERATOR,
    item_names.INFESTED_BANSHEE,
]
item_name_groups[ItemGroupNames.INFESTED_TERRAN_UPGRADES] = infterr_upgrades = [
    item_names.INFESTED_SCV_BUILD_CHARGES,
    item_names.INFESTED_MARINE_PLAGUED_MUNITIONS,
    item_names.INFESTED_MARINE_RETINAL_AUGMENTATION,
    item_names.INFESTED_BUNKER_CALCIFIED_ARMOR,
    item_names.INFESTED_BUNKER_REGENERATIVE_PLATING,
    item_names.INFESTED_BUNKER_ENGORGED_BUNKERS,
    item_names.BULLFROG_WILD_MUTATION,
    item_names.BULLFROG_BROODLINGS,
    item_names.BULLFROG_HARD_IMPACT,
    item_names.BULLFROG_RANGE,
    item_names.INFESTED_DIAMONDBACK_CAUSTIC_MUCUS,
    item_names.INFESTED_DIAMONDBACK_CONCENTRATED_SPEW,
    item_names.INFESTED_DIAMONDBACK_PROGRESSIVE_FUNGAL_SNARE,
    item_names.INFESTED_DIAMONDBACK_VIOLENT_ENZYMES,
    item_names.INFESTED_SIEGE_TANK_ACIDIC_ENZYMES,
    item_names.INFESTED_SIEGE_TANK_BALANCED_ROOTS,
    item_names.INFESTED_SIEGE_TANK_DEEP_TUNNEL,
    item_names.INFESTED_SIEGE_TANK_PROGRESSIVE_AUTOMATED_MITOSIS,
    item_names.INFESTED_SIEGE_TANK_SEISMIC_SONAR,
    item_names.INFESTED_LIBERATOR_CLOUD_DISPERSAL,
    item_names.INFESTED_LIBERATOR_DEFENDER_MODE,
    item_names.INFESTED_LIBERATOR_VIRAL_CONTAMINATION,
    item_names.INFESTED_BANSHEE_FLESHFUSED_TARGETING_OPTICS,
    item_names.INFESTED_BANSHEE_BRACED_EXOSKELETON,
    item_names.INFESTED_BANSHEE_RAPID_HIBERNATION,
    item_names.INFESTED_DIAMONDBACK_FRIGHTFUL_FLESHWELDER,
    item_names.INFESTED_SIEGE_TANK_FRIGHTFUL_FLESHWELDER,
    item_names.INFESTED_LIBERATOR_FRIGHTFUL_FLESHWELDER,
    item_names.INFESTED_BANSHEE_FRIGHTFUL_FLESHWELDER,
    item_names.INFESTED_MISSILE_TURRET_BIOELECTRIC_PAYLOAD,
    item_names.INFESTED_MISSILE_TURRET_ACID_SPORE_VENTS,
]
item_name_groups[ItemGroupNames.INFESTED_TERRAN_ITEMS] = (
    infterr_units
    + infterr_upgrades
    + [item_names.INFESTED_MISSILE_TURRET]
)
# Co-op Zerg
item_name_groups[ItemGroupNames.COOP_KERRIGAN_UNITS] = [
    item_names.ZERGLING,
    item_names.HIVE_QUEEN,
    item_names.HYDRALISK,
    item_names.LURKER,
    item_names.ULTRALISK,
    item_names.MUTALISK,
    item_names.BROOD_LORD,
]
item_name_groups[ItemGroupNames.COOP_ZAGARA_UNITS] = [
    item_names.ZERGLING,
    item_names.HIVE_QUEEN,
    item_names.BANELING,
    item_names.ABERRATION,
    item_names.SCOURGE,
    item_names.CORRUPTOR,
    # item_names.BILE_LAUNCHER,
]
item_name_groups[ItemGroupNames.COOP_ABATHUR_UNITS] = [
    item_names.ROACH,
    item_names.RAVAGER,
    item_names.SWARM_HOST,
    item_names.MUTALISK,
    item_names.GUARDIAN,
    item_names.DEVOURER,
    item_names.VIPER,  # From larva
    item_names.SWARM_QUEEN,
    # Not implemented: Brutalisk
    # Not implemented: Leviathan
]
item_name_groups[ItemGroupNames.COOP_STUKOV_UNITS] = [
    # Not implemented: Infested Colonist
    item_names.INFESTED_MARINE,
    item_names.INFESTED_BUNKER,
    item_names.INFESTED_DIAMONDBACK,
    item_names.INFESTED_SIEGE_TANK,
    item_names.INFESTED_LIBERATOR,
    item_names.INFESTED_BANSHEE,
    item_names.BROOD_QUEEN,
    item_names.OVERSEER,
]
item_name_groups[ItemGroupNames.COOP_DEHAKA_UNITS] = [
    # Note: Co-op Dehaka has reskinned versions of most of these units
    item_names.ZERGLING,
    # Not implemented: Ravasaur
    item_names.ROACH,
    item_names.PRIMAL_IGNITER,
    item_names.GUARDIAN,  # Morphs from 2 roaches
    item_names.HYDRALISK,
    item_names.MUTALISK,  # Morphs from 2 hydralisks
    item_names.IMPALER,
    item_names.SWARM_HOST,  # Primal Host
    # Not implemented: Creeper Host
    item_names.ULTRALISK,
    item_names.TYRANNOZOR,
]
item_name_groups[ItemGroupNames.COOP_STETMANN_UNITS] = [
    # Note: Co-op Stetmann has different variants of these units
    item_names.ZERGLING,
    item_names.BANELING,
    item_names.HYDRALISK,
    item_names.LURKER,
    item_names.CORRUPTOR,
    item_names.BROOD_LORD,  # Mecha Battlecarrier Lord
    item_names.INFESTOR,
    item_names.ULTRALISK,
]

# Protoss
item_name_groups[ItemGroupNames.PROTOSS_ITEMS] = protoss_items = [
    item_name for item_name, item_data in item_tables.item_table.items()
    if item_data.race == SC2Race.PROTOSS
]
item_name_groups[ItemGroupNames.PROTOSS_UNITS] = protoss_units = [
    item_name for item_name, item_data in item_tables.item_table.items()
    if item_data.type in (item_tables.ProtossItemType.Unit, item_tables.ProtossItemType.Unit_2)
]
_protoss_core_units = {
    item_names.ZEALOT: LogicRating.BASIC_STARTER,
    item_names.CENTURION: LogicRating.BASIC_STARTER,
    item_names.SENTINEL: LogicRating.BASIC_STARTER,
    item_names.STALKER: LogicRating.BASIC_STARTER,
    item_names.INSTIGATOR: LogicRating.BASIC_STARTER,
    item_names.SLAYER: LogicRating.BASIC_STARTER,
    item_names.DRAGOON: LogicRating.BASIC_STARTER,
    item_names.ADEPT: LogicRating.BASIC_STARTER,
    item_names.DARK_TEMPLAR: LogicRating.BASIC_STARTER,
    item_names.AVENGER: LogicRating.BASIC_STARTER,
    item_names.IMMORTAL: LogicRating.BASIC_STARTER,
    item_names.VANGUARD: LogicRating.BASIC_STARTER,
    item_names.STALWART: LogicRating.BASIC_STARTER,
    item_names.VOID_RAY: LogicRating.BASIC_STARTER,

    item_names.SUPPLICANT: LogicRating.BASIC_EXTRA,
    item_names.SENTRY: LogicRating.BASIC_EXTRA,  # Healer
    item_names.ENERGIZER: LogicRating.BASIC_EXTRA,  # Autocast caster
    item_names.HAVOC: LogicRating.BASIC_EXTRA,  # Autocast caster
    item_names.PULSAR: LogicRating.BASIC_EXTRA,  # Autocast caster
    item_names.CARRIER: LogicRating.BASIC_EXTRA,  # Tech time
    item_names.SKYLORD: LogicRating.BASIC_EXTRA,  # Tech time
    item_names.TRIREME: LogicRating.BASIC_EXTRA,  # Tech time
    item_names.TEMPEST: LogicRating.BASIC_EXTRA,  # Tech time
    item_names.BLOOD_HUNTER: LogicRating.BASIC_EXTRA | LogicRating.ADVANCED_STARTER,
    item_names.ANNIHILATOR: LogicRating.BASIC_EXTRA | LogicRating.ADVANCED_STARTER,
    item_names.COLOSSUS: LogicRating.BASIC_EXTRA | LogicRating.ADVANCED_STARTER,  # Tech time
    item_names.WRATHWALKER: LogicRating.BASIC_EXTRA | LogicRating.ADVANCED_STARTER,  # Tech time
    item_names.REAVER: LogicRating.BASIC_EXTRA | LogicRating.ADVANCED_STARTER,  # Tech time
    item_names.SKIRMISHER: LogicRating.BASIC_EXTRA | LogicRating.ADVANCED_STARTER,
    item_names.DESTROYER: LogicRating.BASIC_EXTRA | LogicRating.ADVANCED_STARTER,
    item_names.DAWNBRINGER: LogicRating.BASIC_EXTRA | LogicRating.ADVANCED_STARTER,
    item_names.MOTHERSHIP_TALDARIM: LogicRating.BASIC_EXTRA,
    item_names.MOTHERSHIP_PURIFIER: LogicRating.BASIC_EXTRA,
    item_names.MOTHERSHIP_AIUR: LogicRating.BASIC_EXTRA,

    item_names.ORACLE: LogicRating.ADVANCED_STARTER,
    item_names.DARK_ARCHON: LogicRating.ADVANCED_STARTER,

    item_names.HIGH_TEMPLAR: LogicRating.ADVANCED_EXTRA,  # Expensive Caster
    item_names.ASCENDANT: LogicRating.ADVANCED_EXTRA,  # Expensive Caster, blood orb damages buildings
    item_names.SIGNIFIER: LogicRating.ADVANCED_EXTRA,  # Expensive Caster
    item_names.DISRUPTOR: LogicRating.ADVANCED_EXTRA,  # Technical
    item_names.PHOENIX: LogicRating.ADVANCED_EXTRA,  # Air-to-air
    item_names.MIRAGE: LogicRating.ADVANCED_EXTRA,  # Air-to-air
    item_names.CORSAIR: LogicRating.ADVANCED_EXTRA,  # Air-to-air
    item_names.SCOUT: LogicRating.ADVANCED_EXTRA,
    item_names.OPPRESSOR: LogicRating.ADVANCED_EXTRA,
    item_names.CALADRIUS: LogicRating.ADVANCED_EXTRA,  # Air-to-air
    item_names.MISTWING: LogicRating.ADVANCED_EXTRA,
    item_names.ARBITER: LogicRating.ADVANCED_EXTRA,  # Expensive Caster

    item_names.WARP_PRISM: LogicRating.NONE,
    item_names.OBSERVER: LogicRating.NONE,
}
item_name_groups[ItemGroupNames.PROTOSS_BASIC_STARTER_UNITS] = protoss_basic_starter_units = [
    _item_name for _item_name, _rating in _protoss_core_units.items() if _rating & LogicRating.is_basic_starter
]
item_name_groups[ItemGroupNames.PROTOSS_BASIC_CORE_UNITS] = protoss_basic_units = [
    _item_name for _item_name, _rating in _protoss_core_units.items() if _rating & LogicRating.is_basic_core
]
item_name_groups[ItemGroupNames.PROTOSS_ADVANCED_STARTER_UNITS] = protoss_advanced_starter_units = [
    _item_name for _item_name, _rating in _protoss_core_units.items() if _rating & LogicRating.is_advanced_starter
]
item_name_groups[ItemGroupNames.PROTOSS_ADVANCED_CORE_UNITS] = protoss_advanced_units = [
    _item_name for _item_name, _rating in _protoss_core_units.items() if _rating & LogicRating.is_advanced_core
]
item_name_groups[ItemGroupNames.PROTOSS_CHAOS_STARTER_UNITS] = protoss_chaos_starter_units = [
    # Gateway
    item_names.ZEALOT,
    item_names.CENTURION,
    item_names.SENTINEL,
    item_names.SUPPLICANT,
    item_names.STALKER,
    item_names.INSTIGATOR,
    item_names.SLAYER,
    item_names.DRAGOON,
    item_names.ADEPT,
    item_names.SENTRY,
    item_names.ENERGIZER,
    item_names.AVENGER,
    item_names.DARK_TEMPLAR,
    item_names.BLOOD_HUNTER,
    item_names.HIGH_TEMPLAR,
    item_names.SIGNIFIER,
    item_names.ASCENDANT,
    item_names.DARK_ARCHON,
    # Robo
    item_names.IMMORTAL,
    item_names.ANNIHILATOR,
    item_names.VANGUARD,
    item_names.STALWART,
    item_names.COLOSSUS,
    item_names.WRATHWALKER,
    item_names.REAVER,
    item_names.DISRUPTOR,
    # Stargate
    item_names.SKIRMISHER,
    item_names.SCOUT,
    item_names.MISTWING,
    item_names.OPPRESSOR,
    item_names.PULSAR,
    item_names.VOID_RAY,
    item_names.DESTROYER,
    item_names.DAWNBRINGER,
    item_names.ARBITER,
    item_names.ORACLE,
    item_names.CARRIER,
    item_names.TRIREME,
    item_names.SKYLORD,
    item_names.TEMPEST,
    item_names.MOTHERSHIP_TALDARIM,
    # Nexus
    item_names.MOTHERSHIP_AIUR,
    item_names.MOTHERSHIP_PURIFIER,
]
protoss_ground_wa = (
    item_names.ZEALOT, item_names.CENTURION, item_names.SENTINEL, item_names.SUPPLICANT,
    item_names.SENTRY, item_names.ENERGIZER,
    item_names.STALKER, item_names.INSTIGATOR, item_names.SLAYER, item_names.DRAGOON, item_names.ADEPT,
    item_names.HIGH_TEMPLAR, item_names.SIGNIFIER, item_names.ASCENDANT,
    item_names.DARK_TEMPLAR, item_names.BLOOD_HUNTER, item_names.AVENGER,
    item_names.DARK_ARCHON,
    item_names.IMMORTAL, item_names.ANNIHILATOR, item_names.VANGUARD, item_names.STALWART,
    item_names.COLOSSUS, item_names.WRATHWALKER,
    item_names.REAVER,
)
protoss_air_wa = (
    item_names.WARP_PRISM_PHASE_BLASTER,
    item_names.PHOENIX, item_names.MIRAGE, item_names.CORSAIR, item_names.SKIRMISHER,
    item_names.VOID_RAY, item_names.DESTROYER, item_names.PULSAR, item_names.DAWNBRINGER,
    item_names.CARRIER, item_names.SKYLORD, item_names.TRIREME,
    item_names.SCOUT, item_names.TEMPEST, item_names.MOTHERSHIP_TALDARIM,
    item_names.MOTHERSHIP_AIUR, item_names.MOTHERSHIP_PURIFIER,
    item_names.ARBITER, item_names.ORACLE, item_names.OPPRESSOR,
    item_names.CALADRIUS, item_names.MISTWING,
)
protoss_basic_ground_units = _intersection(protoss_basic_units, protoss_ground_wa)
protoss_basic_air_units = _intersection(protoss_basic_units, protoss_air_wa)
protoss_advanced_ground_units = _intersection(protoss_advanced_units, protoss_ground_wa)
protoss_advanced_air_units = _intersection(protoss_advanced_units, protoss_air_wa)
protoss_chaos_ground_units = protoss_ground_wa
protoss_chaos_air_units = protoss_air_wa
item_name_groups[ItemGroupNames.PROTOSS_GENERIC_UPGRADES] = protoss_generic_upgrades = [
    item_name for item_name, item_data in item_tables.item_table.items()
    if item_data.type == item_tables.ProtossItemType.Upgrade
]
item_name_groups[ItemGroupNames.PROTOSS_MOBILE_DETECTION] = protoss_mobile_detection = (
    item_names.OBSERVER,
    item_names.ORACLE,
)
item_name_groups[ItemGroupNames.PROTOSS_DETECTION] = protoss_detection = (
    *protoss_mobile_detection,
    item_names.PHOTON_CANNON,
)
item_name_groups[ItemGroupNames.LOTV_UNITS] = lotv_units = [
    item_names.ZEALOT, item_names.CENTURION, item_names.SENTINEL,
    item_names.STALKER, item_names.DRAGOON, item_names.ADEPT,
    item_names.SENTRY, item_names.HAVOC, item_names.ENERGIZER,
    item_names.HIGH_TEMPLAR, item_names.DARK_ARCHON, item_names.ASCENDANT,
    item_names.DARK_TEMPLAR, item_names.AVENGER, item_names.BLOOD_HUNTER,
    item_names.IMMORTAL, item_names.ANNIHILATOR, item_names.VANGUARD,
    item_names.COLOSSUS, item_names.WRATHWALKER, item_names.REAVER,
    item_names.PHOENIX, item_names.MIRAGE, item_names.CORSAIR,
    item_names.VOID_RAY, item_names.DESTROYER, item_names.ARBITER,
    item_names.CARRIER, item_names.TEMPEST, item_names.MOTHERSHIP_TALDARIM,
]
item_name_groups[ItemGroupNames.PROPHECY_UNITS] = prophecy_units = [
    item_names.ZEALOT, item_names.STALKER, item_names.HIGH_TEMPLAR, item_names.DARK_TEMPLAR,
    # Note(mm): Technically, LotV immortal is different from Prophecy immortal
    item_names.OBSERVER, item_names.IMMORTAL, item_names.COLOSSUS,
    item_names.PHOENIX, item_names.VOID_RAY, item_names.CARRIER,
]
item_name_groups[ItemGroupNames.PROPHECY_BUILDINGS] = prophecy_buildings = [
    item_names.PHOTON_CANNON,
]
item_name_groups[ItemGroupNames.GATEWAY_UNITS] = gateway_units = [
    item_names.ZEALOT, item_names.CENTURION, item_names.SENTINEL, item_names.SUPPLICANT,
    item_names.STALKER, item_names.INSTIGATOR, item_names.SLAYER,
    item_names.SENTRY, item_names.HAVOC, item_names.ENERGIZER,
    item_names.DRAGOON, item_names.ADEPT, item_names.DARK_ARCHON,
    item_names.HIGH_TEMPLAR, item_names.SIGNIFIER, item_names.ASCENDANT,
    item_names.DARK_TEMPLAR, item_names.AVENGER, item_names.BLOOD_HUNTER,
]
item_name_groups[ItemGroupNames.ROBO_UNITS] = robo_units = [
    item_names.WARP_PRISM, item_names.OBSERVER,
    item_names.IMMORTAL, item_names.ANNIHILATOR, item_names.VANGUARD, item_names.STALWART,
    item_names.COLOSSUS, item_names.WRATHWALKER,
    item_names.REAVER, item_names.DISRUPTOR,
]
item_name_groups[ItemGroupNames.STARGATE_UNITS] = stargate_units = [
    item_names.PHOENIX, item_names.SKIRMISHER, item_names.MIRAGE, item_names.CORSAIR,
    item_names.VOID_RAY, item_names.DESTROYER, item_names.PULSAR, item_names.DAWNBRINGER,
    item_names.CARRIER, item_names.SKYLORD, item_names.TRIREME,
    item_names.TEMPEST, item_names.SCOUT, item_names.MOTHERSHIP_TALDARIM,
    item_names.ARBITER, item_names.ORACLE, item_names.OPPRESSOR,
    item_names.CALADRIUS, item_names.MISTWING,
]
item_name_groups[ItemGroupNames.NEXUS_UNITS] = nexus_units = [
    item_names.MOTHERSHIP_AIUR, item_names.MOTHERSHIP_PURIFIER,
]
item_name_groups[ItemGroupNames.PROTOSS_BUILDINGS] = protoss_buildings = [
    item_name for item_name, item_data in item_tables.item_table.items()
    if item_data.type == item_tables.ProtossItemType.Building
]
item_name_groups[ItemGroupNames.AIUR_UNITS] = [
    item_names.ZEALOT, item_names.DRAGOON, item_names.SENTRY, item_names.AVENGER, item_names.HIGH_TEMPLAR,
    item_names.IMMORTAL, item_names.REAVER, item_names.MOTHERSHIP_AIUR,
    item_names.PHOENIX, item_names.SCOUT, item_names.ARBITER, item_names.CARRIER,
]
item_name_groups[ItemGroupNames.NERAZIM_UNITS] = [
    item_names.CENTURION, item_names.STALKER, item_names.DARK_TEMPLAR, item_names.SIGNIFIER, item_names.DARK_ARCHON,
    item_names.ANNIHILATOR,
    item_names.CORSAIR, item_names.ORACLE, item_names.VOID_RAY, item_names.MISTWING,
]
item_name_groups[ItemGroupNames.TAL_DARIM_UNITS] = [
    item_names.SUPPLICANT, item_names.SLAYER, item_names.HAVOC, item_names.BLOOD_HUNTER, item_names.ASCENDANT,
    item_names.VANGUARD, item_names.WRATHWALKER,
    item_names.SKIRMISHER, item_names.DESTROYER, item_names.SKYLORD, item_names.MOTHERSHIP_TALDARIM, item_names.OPPRESSOR,
]
item_name_groups[ItemGroupNames.PURIFIER_UNITS] = [
    item_names.SENTINEL, item_names.ADEPT, item_names.INSTIGATOR, item_names.ENERGIZER,
    item_names.STALWART, item_names.COLOSSUS, item_names.DISRUPTOR,
    item_names.MIRAGE, item_names.DAWNBRINGER, item_names.TRIREME, item_names.TEMPEST,
    item_names.CALADRIUS, item_names.MOTHERSHIP_PURIFIER,
]
item_name_groups[ItemGroupNames.SOA_PASSIVES] = spear_of_adun_passives = [
    item_names.RECONSTRUCTION_BEAM,
    item_names.OVERWATCH,
    item_names.GUARDIAN_SHELL,
]
spear_of_adun_actives = [
    *[item_name for item_name, item_data in item_tables.item_table.items() if item_data.type == item_tables.ProtossItemType.Spear_Of_Adun],
    item_names.SOA_PROGRESSIVE_PROXY_PYLON,
]
item_name_groups[ItemGroupNames.SOA_ITEMS] = soa_items = spear_of_adun_actives + spear_of_adun_passives
lotv_soa_items = [
    item_name
    for item_name in soa_items
    if item_name not in (item_names.SOA_PYLON_OVERCHARGE, item_names.OVERWATCH)
]
item_name_groups[ItemGroupNames.PROTOSS_GLOBAL_UPGRADES] = [
    item_name for item_name, item_data in item_tables.item_table.items() if item_data.type == item_tables.ProtossItemType.Solarite_Core
]
item_name_groups[ItemGroupNames.LOTV_GLOBAL_UPGRADES] = lotv_global_upgrades = [
    item_names.NEXUS_OVERCHARGE,
    item_names.ORBITAL_ASSIMILATORS,
    item_names.WARP_HARMONIZATION,
    item_names.MATRIX_OVERLOAD,
    item_names.GUARDIAN_SHELL,
    item_names.RECONSTRUCTION_BEAM,
]
item_name_groups[ItemGroupNames.WAR_COUNCIL] = war_council_upgrades = [
    item_name for item_name, item_data in item_tables.item_table.items()
    if item_data.type in (item_tables.ProtossItemType.War_Council, item_tables.ProtossItemType.War_Council_2)
]

lotv_war_council_upgrades = [
    item_name for item_name, item_data in item_tables.item_table.items()
    if (
        item_name in war_council_upgrades
        and item_data.parent in item_name_groups[ItemGroupNames.LOTV_UNITS]
        # Destroyers get a custom (non-vanilla) buff, not a nerf over their vanilla council state
        and item_name != item_names.DESTROYER_REFORGED_BLOODSHARD_CORE
    )
]
item_name_groups[ItemGroupNames.LOTV_ITEMS] = vanilla_lotv_items = (
    lotv_units
    + protoss_buildings
    + lotv_soa_items
    + lotv_global_upgrades
    + protoss_generic_upgrades
    + lotv_war_council_upgrades
)
item_name_groups[ItemGroupNames.PROTOSS_SC1_UNITS] = [
    item_names.ZEALOT,
    item_names.DRAGOON,
    item_names.HIGH_TEMPLAR,
    item_names.DARK_TEMPLAR,
    item_names.DARK_ARCHON,
    item_names.DARK_TEMPLAR_DARK_ARCHON_MELD,
    # No shuttle
    item_names.REAVER,
    item_names.OBSERVER,
    item_names.SCOUT,
    item_names.CARRIER,
    item_names.ARBITER,
    item_names.CORSAIR,
]
item_name_groups[ItemGroupNames.PROTOSS_SC1_BUILDINGS] = [
    item_names.PHOTON_CANNON,
    item_names.SHIELD_BATTERY,
]
item_name_groups[ItemGroupNames.PROTOSS_LADDER_UNITS] = [
    item_names.ZEALOT,
    item_names.STALKER,
    item_names.SENTRY,
    item_names.ADEPT,
    item_names.HIGH_TEMPLAR,
    item_names.DARK_TEMPLAR,
    item_names.DARK_TEMPLAR_ARCHON_MERGE,
    item_names.OBSERVER,
    item_names.WARP_PRISM,
    item_names.IMMORTAL,
    item_names.COLOSSUS,
    item_names.DISRUPTOR,
    item_names.PHOENIX,
    item_names.VOID_RAY,
    item_names.ORACLE,
    item_names.CARRIER,
    item_names.TEMPEST,
    item_names.MOTHERSHIP_AIUR,  # Replace: Aiur Mothership
]
# Co-op Protoss
item_name_groups[ItemGroupNames.COOP_ARTANIS_UNITS] = [
    item_names.ZEALOT,
    item_names.DRAGOON,
    item_names.HIGH_TEMPLAR,
    # High Archon
    item_names.IMMORTAL,
    item_names.REAVER,
    item_names.PHOENIX,
    item_names.TEMPEST,
]
item_name_groups[ItemGroupNames.COOP_VORAZUN_UNITS] = [
    item_names.CENTURION,
    item_names.STALKER,
    item_names.DARK_TEMPLAR,
    item_names.DARK_ARCHON,
    item_names.CORSAIR,
    item_names.VOID_RAY,
    item_names.ORACLE,
]
item_name_groups[ItemGroupNames.COOP_KARAX_UNITS] = [
    item_names.SENTINEL,
    item_names.ENERGIZER,
    item_names.IMMORTAL,
    item_names.COLOSSUS,
    item_names.MIRAGE,
    item_names.CARRIER,
]
item_name_groups[ItemGroupNames.COOP_ALARAK_UNITS] = [
    item_names.SUPPLICANT,
    item_names.SLAYER,
    item_names.HAVOC,
    item_names.ASCENDANT,
    item_names.VANGUARD,
    item_names.WARP_PRISM,
    item_names.DESTROYER,  # Death Fleet, P3
    item_names.MOTHERSHIP_TALDARIM,  # Death Fleet, P3
]
item_name_groups[ItemGroupNames.COOP_FENIX_UNITS] = [
    item_names.SENTINEL,  # Legionnaire
    item_names.ADEPT,
    item_names.SENTRY,  # Conservator
    item_names.IMMORTAL,
    item_names.COLOSSUS,
    item_names.DISRUPTOR,
    item_names.SCOUT,
    item_names.CARRIER,
]
item_name_groups[ItemGroupNames.COOP_ZERATUL_UNITS] = [
    # Note: Co-op Zeratul has elite variants of these units
    item_names.STALKER,  # Ambusher
    item_names.SENTRY,  # Shieldguard
    item_names.AVENGER,  # Void Templar
    item_names.IMMORTAL,  # Enforcer
    item_names.DISRUPTOR,  # Abrogator
    item_names.WARP_PRISM,  # Void Array
]
item_name_groups[ItemGroupNames.ARTANIS_WEAPON_ASPECT_ACTIVE] = artanis_weapon_aspect_active = [
    item_names.ARTANIS_EXTERMINATE,
    item_names.ARTANIS_CLEANSING_SMITE,
    item_names.ARTANIS_SHADOW_SLICE,
    item_names.ARTANIS_BLADE_WALTZ,
]
item_name_groups[ItemGroupNames.ARTANIS_WEAPON_ASPECT_PASSIVE] = artanis_weapon_aspect_passive = [
    item_names.ARTANIS_MALASHS_MALEVOLENCE,
    item_names.ARTANIS_CLOLARIONS_CONFIDENCE,
    item_names.ARTANIS_RASZAGALS_RHYTHM,
    item_names.ARTANIS_TASSADARS_TEACHINGS,
]
artanis_weapon_aspect_pairs = [
    (item_names.ARTANIS_BLADE_WALTZ, item_names.ARTANIS_TASSADARS_TEACHINGS),
    (item_names.ARTANIS_SHADOW_SLICE, item_names.ARTANIS_RASZAGALS_RHYTHM),
    (item_names.ARTANIS_CLEANSING_SMITE, item_names.ARTANIS_CLOLARIONS_CONFIDENCE),
    (item_names.ARTANIS_EXTERMINATE, item_names.ARTANIS_MALASHS_MALEVOLENCE),
]
item_name_groups[ItemGroupNames.ARTANIS_ACTIVE_ABILITIES] = artanis_active_abilities = [
    item_names.ARTANIS_LIGHTNING_DASH,
    item_names.ARTANIS_PHASE_PRISM,
    item_names.ARTANIS_VOLTAIC_SHOCK,
    item_names.ARTANIS_ASTRAL_WIND,
    item_names.ARTANIS_STRENGTH_IN_UNITY,
    item_names.ARTANIS_SUPPRESSION_PULSE,
]
item_name_groups[ItemGroupNames.ARTANIS_PASSIVE_ABILITIES] = artanis_passive_abilities = [
    item_names.ARTANIS_VALOR_OF_THE_FIRSTBORN,
    item_names.ARTANIS_RESURGENCE,
    item_names.ARTANIS_PSIONIC_ASSAULT,
    item_names.ARTANIS_FORCE_OF_WILL,
    item_names.ARTANIS_TEMPERED_IN_TWILIGHT,
    item_names.ARTANIS_SHIELD_OVERLOAD,
]
item_name_groups[ItemGroupNames.ARTANIS_ABILITIES] = artanis_abilities = [
    *artanis_active_abilities,
    *artanis_passive_abilities,
    *artanis_weapon_aspect_active,
    *artanis_weapon_aspect_passive,
]

# Faction-agnostic groups
item_name_groups[ItemGroupNames.VANILLA_ITEMS] = vanilla_items = (
    vanilla_wol_items + vanilla_hots_items + vanilla_lotv_items
)

item_name_groups[ItemGroupNames.OVERPOWERED_ITEMS] = overpowered_items = [
    # Terran general
    item_names.SIEGE_TANK_GRADUATING_RANGE,
    item_names.RAVEN_HUNTER_SEEKER_WEAPON,
    item_names.BATTLECRUISER_ATX_LASER_BATTERY,
    item_names.PROGRESSIVE_REGENERATIVE_BIO_STEEL,
    item_names.MECHANICAL_KNOW_HOW,
    item_names.MERCENARY_MUNITIONS,

    # Terran Mind Control
    item_names.HIVE_MIND_EMULATOR,
    item_names.PSI_INDOCTRINATOR,
    item_names.ARGUS_AMPLIFIER,

    # Zerg Mind Control
    item_names.INFESTOR,

    # Protoss Mind Control
    item_names.DARK_ARCHON_INDOMITABLE_WILL,

    # Nova
    item_names.NOVA_PLASMA_RIFLE,

    # Kerrigan
    item_names.KERRIGAN_APOCALYPSE,
    item_names.KERRIGAN_DROP_PODS,
    item_names.KERRIGAN_SPAWN_LEVIATHAN,
    item_names.KERRIGAN_IMMOBILIZATION_WAVE,

    # SOA
    item_names.SOA_TIME_STOP,
    item_names.SOA_SOLAR_LANCE,
    item_names.SOA_DEPLOY_FENIX,
    # Note: This is more an issue of having multiple ults at the same time, rather than solar bombardment in particular.
    # Can be removed from the list if we get an SOA ult combined cooldown or energy cost on it.
    item_names.SOA_SOLAR_BOMBARDMENT,

    # Protoss general
    item_names.QUATRO,
    item_names.MOTHERSHIP_TALDARIM_INTEGRATED_POWER,

    # Mindless Broodwar garbage
    item_names.GHOST_BARGAIN_BIN_PRICES,
    item_names.SPECTRE_BARGAIN_BIN_PRICES,
    item_names.REAVER_BARGAIN_BIN_PRICES,
    item_names.SCOUT_SUPPLY_EFFICIENCY,
]

# Opt-In items that do not show up by default.
# These items need to be explicitly added, either by certain options
# or by putting them into locked items or start inventory
item_name_groups[ItemGroupNames.DISABLED_ITEMS] = disabled_items = [
    # Trap items
    item_names.TRAP_GHOST_SPAWN,
]

# Items not aimed to be officially released
# These need further balancing, and they shouldn't generate normally unless explicitly locked
item_name_groups[ItemGroupNames.UNRELEASED_ITEMS] = unreleased_items = [
    # Nothing here for now
]

# A place for traits that were released before but are to be taken down by default.
# If an item gets split to multiple ones, the original one should be set deprecated instead (see Orbital Command for an example).
# This is a place if you want to nerf or disable by default a previously released trait.
# Currently, it disables only the topmost level of the progressives.
# Don't place here anything that's present in the vanilla campaigns (if it's overpowered, use overpowered items instead)
item_name_groups[ItemGroupNames.LEGACY_ITEMS] = legacy_items = [
    item_names.ASCENDANT_ARCHON_MERGE,
    item_names.IMMORTAL_ADVANCED_TARGETING,
]

item_name_groups[ItemGroupNames.KEYS] = keys = [
    item_name for item_name in key_item_table.keys()
]

# ####################### #
#   Internal-use groups   #
# ####################### #
ENEMY_WITHIN_ZERG_STANDARD_UNITS = (
    item_names.ZERGLING, item_names.ROACH, item_names.HYDRALISK,
)
ENEMY_WITHIN_ZERG_BASELINE_UNITS = ENEMY_WITHIN_ZERG_STANDARD_UNITS + (item_names.INFESTOR,)
ENEMY_WITHIN_ZERG_MORPHLING_UNITS = (
    item_names.BANELING,
    item_names.IMPALER,
    item_names.LURKER,
    item_names.PRIMAL_IGNITER,
    item_names.RAVAGER,
)
ENEMY_WITHIN_TERRAN_STANDARD_UNITS = (
    item_names.MARINE,
    item_names.MARAUDER,
    item_names.REAPER,
    item_names.GHOST,
    item_names.SPECTRE,
    item_names.DOMINION_TROOPER,
    item_names.SIEGE_TANK,
    item_names.VIKING,
    item_names.PREDATOR,
    item_names.DIAMONDBACK,
    item_names.GOLIATH,
    item_names.CYCLONE,
    item_names.WARHOUND,
)
ENEMY_WITHIN_TERRAN_ADVANCED_UNITS = (
    item_names.VULTURE,
)
ENEMY_WITHIN_TERRAN_UNITS = ENEMY_WITHIN_TERRAN_STANDARD_UNITS + ENEMY_WITHIN_TERRAN_ADVANCED_UNITS
ENEMY_WITHIN_PROTOSS_STANDARD_UNITS = (
    item_names.ZEALOT,
    item_names.CENTURION,
    item_names.STALKER,
    item_names.INSTIGATOR,
    item_names.SLAYER,
    item_names.DRAGOON,
    item_names.ADEPT,
    item_names.DARK_TEMPLAR,
    item_names.AVENGER,
    item_names.BLOOD_HUNTER,
    item_names.IMMORTAL,
    item_names.ANNIHILATOR,
    item_names.STALWART,
    item_names.VANGUARD,
    item_names.REAVER,
)
ENEMY_WITHIN_PROTOSS_ADVANCED_UNITS = (
    item_names.HIGH_TEMPLAR,
    item_names.SIGNIFIER,
    item_names.ASCENDANT,
    item_names.DISRUPTOR,
)
ENEMY_WITHIN_PROTOSS_UNITS = ENEMY_WITHIN_PROTOSS_STANDARD_UNITS + ENEMY_WITHIN_PROTOSS_STANDARD_UNITS

TEMPLARS_RETURN_PROTOSS_UNITS = (
    item_names.IMMORTAL,
    item_names.ANNIHILATOR,
    item_names.VANGUARD,
    item_names.COLOSSUS,
    item_names.WRATHWALKER,
    item_names.REAVER,
    item_names.DARK_TEMPLAR,
    item_names.HIGH_TEMPLAR,
    item_names.ENERGIZER,
    item_names.SENTRY,
)
