from typing import TYPE_CHECKING, Callable, TypeVar, Iterable
import enum

from BaseClasses import CollectionState, Location
from .item.item_groups import kerrigan_non_ultimates
from .item.virtual_items import VirtualItem
from .options import (
    RequiredTactics,
    AllInMap,
    GrantStoryTech,
    SpearOfAdunPassiveAbilityPresence,
    MissionOrder,
)
from .mission_tables import SC2Race, SC2Campaign, SC2Mission
from .tables import HeroFlag
from .item import item_groups, item_names, item_tables

if TYPE_CHECKING:
    from . import SC2World


T = TypeVar('T')


KERRIGAN_MAX_LEVEL = 9999
SOA_MACRO_SCALING = 0.8
"""
Scaling factor for how heavily SOA abilities and passives are weighted
relative to macro upgrades in the macro rating.
"""


def min2(a: int, b: int) -> int:
    """`min()` that only takes two values; faster than baseline int by about 2x"""
    if a <= b:
        return a
    return b


class LogicSeries(enum.IntFlag):
    CoreUnit = enum.auto()
    PowerComp = enum.auto()
    AntiAir = enum.auto()
    MacroPower = enum.auto()
    DefenseRating = enum.auto()
    Detection = enum.auto()
    Kerrigan = enum.auto()
    Nova = enum.auto()
    Artanis = enum.auto()

    heroes = Kerrigan | Nova | Artanis


def updateable(func: T) -> T:
    """
    Mark a function as something that gets monkey-patched,
    and thus shouldn't be used as a top-level logic function.
    """
    func.updateable = True  # type: ignore[attr-defined]
    return func


class SC2Logic:
    @staticmethod
    def series(logic_series: LogicSeries, race: SC2Race, tier: int) -> Callable[[T], T]:
        def identity(x: T) -> T:
            x.series_info = (logic_series, race, tier)  # type: ignore[attr-defined]
            return x
        return identity

    def __init__(self, world: "SC2World") -> None:
        # Note: Don't store a reference to the world so we can cache this object on the world object
        self.player = world.player
        self.logic_level = world.options.required_tactics.value
        self.advanced_tactics = self.logic_level != RequiredTactics.option_basic
        self.take_over_ai_allies = bool(world.options.take_over_ai_allies)
        self.kerrigan_levels_per_mission_completed = world.options.kerrigan_levels_per_mission_completed.value
        self.kerrigan_levels_per_mission_completed_cap = world.options.kerrigan_levels_per_mission_completed_cap.value
        if self.kerrigan_levels_per_mission_completed_cap < 0:
            self.kerrigan_levels_per_mission_completed_cap = KERRIGAN_MAX_LEVEL
        self.kerrigan_total_level_cap = world.options.kerrigan_total_level_cap.value
        if self.kerrigan_total_level_cap < 0:
            self.kerrigan_total_level_cap = KERRIGAN_MAX_LEVEL
        self.morphling_enabled = bool(world.options.enable_morphling.value)
        self.grant_story_tech = world.options.grant_story_tech.value
        self.spear_of_adun_presence = world.options.spear_of_adun_presence.value
        self.spear_of_adun_passive_presence = world.options.spear_of_adun_passive_ability_presence.value
        self.enabled_campaigns = {
            campaign for campaign in SC2Campaign if campaign.campaign_name in world.options.enabled_campaigns
        }

        self.mission_order = world.options.mission_order.value
        self.generic_upgrade_missions = world.options.generic_upgrade_missions.value
        self.all_in_map = world.options.all_in_map.value
        self.enabled_heroes = frozenset(world.options.enabled_heroes.value)
        self.war_council_upgrades = not world.options.war_council_nerfs.value
        self.protoss_base_macro_rating = 3 if not world.options.war_council_nerfs else 0
        self.hero_presence_option = world.options.hero_presence.value
        self.generic_upgrade_missions = world.options.generic_upgrade_missions.value

        # Must be set externally for accurate logic checking of upgrade level when generic_upgrade_missions is checked
        self.total_mission_count = 1

        # Conditionally changed by the world after finalizing missions
        self.hero_presence: dict[SC2Mission, HeroFlag] = {}
        self.grant_hero_items: set[SC2Mission] = set()
        """Tracks missions for which the client will automatically add items up to basic hero competency"""

        # Conditionally set to False by the world after culling items
        self.has_barracks_unit: bool = True
        self.has_factory_unit: bool = True
        self.has_starport_unit: bool = True
        self.has_zerg_melee_unit: bool = True
        self.has_zerg_ranged_unit: bool = True
        self.has_zerg_air_unit: bool = True
        self.has_protoss_ground_unit: bool = True
        self.has_protoss_air_unit: bool = True

        # Function Caches
        self.series_functions: dict[tuple[LogicSeries, SC2Race, int], Callable] = {}
        for name in dir(self):
            if hasattr(self, name):
                obj = getattr(self, name)
                if hasattr(obj, 'series_info'):
                    assert obj.series_info not in self.series_functions, (
                        f"Series key {obj.series_info} was redefined"
                    )
                    self.series_functions[obj.series_info] = obj
        self.unit_count_functions: dict[tuple[SC2Race, int, int], Callable[[CollectionState], bool]] = {}
        self.power_comp_functions: dict[tuple[SC2Race, int, int], Callable[[CollectionState], bool]] = {}
        self.rating_functions: dict[tuple[SC2Race, LogicSeries, int], Callable[[CollectionState], bool]] = {}

        # Function registry
        self.name_to_function: dict[str, Callable[[CollectionState], bool]] = {
            func: getattr(self, func)
            for func in dir(self)
            if not func.startswith('_')
            and not hasattr(getattr(self, func), 'updateable')
            and callable(getattr(self, func))
        }

        # Logic level-based groups
        if self.logic_level == RequiredTactics.option_basic:
            self.upgradeable_barracks_units: Iterable[str] = item_groups.terran_basic_barracks_units
            self.upgradeable_factory_units: Iterable[str] = item_groups.terran_basic_factory_units
            self.upgradeable_starport_units: Iterable[str] = item_groups.terran_basic_starport_units
            self.upgradeable_zerg_melee_units: Iterable[str] = item_groups.zerg_basic_melee_units
            self.upgradeable_zerg_ranged_units: Iterable[str] = item_groups.zerg_basic_ranged_units
            self.upgradeable_zerg_air_units: Iterable[str] = item_groups.zerg_basic_air_units
            self.upgradeable_zerg_melee_morphs: Iterable[str] = item_groups.zerg_basic_melee_morphs
            self.upgradeable_zerg_ranged_morphs: Iterable[str] = item_groups.zerg_basic_ranged_morphs
            self.upgradeable_zerg_air_morphs: Iterable[str] = item_groups.zerg_basic_air_morphs
            self.upgradeable_protoss_ground_units: Iterable[str] = item_groups.protoss_basic_ground_units
            self.upgradeable_protoss_air_units: Iterable[str] = item_groups.protoss_basic_air_units
        elif self.logic_level == RequiredTactics.option_advanced:
            self.upgradeable_barracks_units = item_groups.terran_advanced_barracks_units
            self.upgradeable_factory_units = item_groups.terran_advanced_factory_units
            self.upgradeable_starport_units = item_groups.terran_advanced_starport_units
            self.upgradeable_zerg_melee_units = item_groups.zerg_advanced_melee_units
            self.upgradeable_zerg_ranged_units = item_groups.zerg_advanced_ranged_units
            self.upgradeable_zerg_air_units = item_groups.zerg_advanced_air_units
            self.upgradeable_zerg_melee_morphs = item_groups.zerg_advanced_melee_morphs
            self.upgradeable_zerg_ranged_morphs = item_groups.zerg_advanced_ranged_morphs
            self.upgradeable_zerg_air_morphs = item_groups.zerg_advanced_air_morphs
            self.upgradeable_protoss_ground_units = item_groups.protoss_advanced_ground_units
            self.upgradeable_protoss_air_units = item_groups.protoss_advanced_air_units
        else:  # option_chaos
            self.upgradeable_barracks_units = item_groups.terran_chaos_infantry_units
            self.upgradeable_factory_units = item_groups.terran_chaos_vehicle_units
            self.upgradeable_starport_units = item_groups.terran_chaos_ship_units
            self.upgradeable_zerg_melee_units = item_groups.zerg_chaos_melee_units
            self.upgradeable_zerg_ranged_units = item_groups.zerg_chaos_ranged_units
            self.upgradeable_zerg_air_units = item_groups.zerg_chaos_air_units
            self.upgradeable_zerg_melee_morphs = item_groups.zerg_advanced_melee_morphs
            self.upgradeable_zerg_ranged_morphs = item_groups.zerg_advanced_ranged_morphs
            self.upgradeable_zerg_air_morphs = item_groups.zerg_advanced_air_morphs
            self.upgradeable_protoss_ground_units = item_groups.protoss_chaos_ground_units
            self.upgradeable_protoss_air_units = item_groups.protoss_chaos_air_units

        # Transition functions
        assert self.wa_upgrade_count.updateable  # type: ignore[attr-defined]
        if self.generic_upgrade_missions > 0:
            self.wa_upgrade_count = self._wa_upgrade_count_generic_filtering  # type: ignore[method-assign]
        else:
            self.wa_upgrade_count = self._wa_upgrade_count_items  # type: ignore[method-assign]

        assert self.kerrigan_levels_from_missions.updateable  # type: ignore[attr-defined]
        if (self.kerrigan_levels_per_mission_completed > 0
            and self.kerrigan_levels_per_mission_completed_cap != 0
        ):
            self.kerrigan_levels_from_missions = self._kerrigan_levels_from_missions_filtering  # type: ignore[method-assign]

    # ###################################################################################################### #
    # region Transition functions .......................................................................... #
    # ###################################################################################################### #

    def transition_prefill(self) -> None:
        """Transition mutable functions from item filtering versions to placement versions"""
        if (self.kerrigan_levels_per_mission_completed > 0
            and self.kerrigan_levels_per_mission_completed_cap != 0
        ):
            self.kerrigan_levels_from_missions = self._kerrigan_levels_from_missions_placement  # type: ignore

    @updateable
    def wa_upgrade_count(self, item: VirtualItem, state: CollectionState) -> int:
        return 0

    def _wa_upgrade_count_items(self, item: VirtualItem, state: CollectionState) -> int:
        return state.count(item.name, self.player)  # type: ignore[arg-type]

    def _wa_upgrade_count_generic_filtering(self, item: VirtualItem, state: CollectionState) -> int:
        return item_tables.WEAPON_ARMOR_UPGRADE_MAX_LEVEL

    def _wa_upgrade_count_generic_placement(self, item: VirtualItem, state: CollectionState) -> int:
        return (
            int(
                100
                / self.generic_upgrade_missions
                * state.count_group("Missions", self.player)
            ) // self.total_mission_count
            + self._wa_upgrade_count_items(item, state)
        )

    def kerrigan_levels_from_items(self, state: CollectionState) -> int:
        return state.count(VirtualItem.KERRIGAN_LEVEL.name, self.player)

    @updateable
    def kerrigan_levels_from_missions(self, state: CollectionState) -> int:
        return 0

    def _kerrigan_levels_from_missions_filtering(self, state: CollectionState) -> int:
        return min2(
            self.kerrigan_levels_per_mission_completed * self.total_mission_count,
            self.kerrigan_levels_per_mission_completed_cap
        )

    def _kerrigan_levels_from_missions_placement(self, state: CollectionState) -> int:
        return min2(
            self.kerrigan_levels_per_mission_completed * state.count_group("Missions", self.player),
            self.kerrigan_levels_per_mission_completed_cap
        )

    def kerrigan_levels(self, state: CollectionState, target: int) -> bool:
        return (
            self.kerrigan_levels_from_items(state)
            + self.kerrigan_levels_from_missions(state)
        ) >= target

    # endregion Transition-functions

    # ###################################################################################################### #
    # region Generic ....................................................................................... #
    # ###################################################################################################### #

    def soa_power_rating(self, state: CollectionState) -> int:
        """Points system out of 17. Excluding OP items gives max 13. Recommend requiring no more than 10."""
        power_rating = 0
        # Spear of Adun Ultimates (Strongest) (max 4)
        if state.has(item_names.SOA_TIME_STOP, self.player):
            power_rating += 4
        elif (
            state.has(item_names.SOA_PURIFIER_BEAM, self.player)
            or state.has(item_names.SOA_SOLAR_BOMBARDMENT, self.player)
        ):
            power_rating += 3

        # Spear of Adun ability that consumes energy (Strongest, then second strongest / 2) (max 11)
        soa_energy_ratings = (
            (item_names.SOA_SOLAR_LANCE, 8, 1,),
            (item_names.SOA_DEPLOY_FENIX, 7, 1,),
            (item_names.SOA_TEMPORAL_FIELD, 6, 1,),
            (item_names.SOA_PROGRESSIVE_PROXY_PYLON, 5, 2,),
            (item_names.SOA_SHIELD_OVERCHARGE, 5, 1,),
            (item_names.SOA_ORBITAL_STRIKE, 4, 1,),
        )
        found_main_weapon = False
        for item, rating, count in soa_energy_ratings:
            if state.has(item, self.player, count):
                if not found_main_weapon:
                    power_rating += rating
                    found_main_weapon = True
                else:
                    power_rating += rating // 2
                    break
        # Mass Recall (Negligible energy cost)
        if state.has(item_names.SOA_MASS_RECALL, self.player):
            power_rating += 2
        return int(power_rating * SOA_MACRO_SCALING)

    def soa_passive_power_rating(self, state: CollectionState) -> int:
        power_score = 0
        if state.has(item_names.RECONSTRUCTION_BEAM, self.player):
            power_score += 4
        if state.has(item_names.GUARDIAN_SHELL, self.player):
            power_score += 3
        if state.has(item_names.OVERWATCH, self.player):
            power_score += 2
        return int(power_score * SOA_MACRO_SCALING)

    # endregion Generic

    # ###################################################################################################### #
    # region Global Terran ................................................................................. #
    # ###################################################################################################### #

    @series(LogicSeries.PowerComp, SC2Race.TERRAN, 1)
    def terran_upgraded_unit(self, state: CollectionState, upgrade: int) -> bool:
        return (
            (
                self.wa_upgrade_count(VirtualItem.TERRAN_INFANTRY_WEAPON, state) >= upgrade
                and self.wa_upgrade_count(VirtualItem.TERRAN_INFANTRY_ARMOR, state) >= upgrade
                and state.has_any(self.upgradeable_barracks_units, self.player)
            )
            or (
                self.wa_upgrade_count(VirtualItem.TERRAN_VEHICLE_WEAPON, state) >= upgrade
                and self.wa_upgrade_count(VirtualItem.TERRAN_VEHICLE_ARMOR, state) >= upgrade
                and state.has_any(self.upgradeable_factory_units, self.player)
            )
            or (
                self.wa_upgrade_count(VirtualItem.TERRAN_SHIP_WEAPON, state) >= upgrade
                and self.wa_upgrade_count(VirtualItem.TERRAN_SHIP_ARMOR, state) >= upgrade
                and state.has_any(self.upgradeable_starport_units, self.player)
            )
        )

    @series(LogicSeries.PowerComp, SC2Race.TERRAN, 2)
    def terran_competent_comp(self, state: CollectionState, upgrade: int = 1) -> bool:
        # Infantry with Healing
        infantry_weapons = self.wa_upgrade_count(VirtualItem.TERRAN_INFANTRY_WEAPON, state)
        infantry_armor = self.wa_upgrade_count(VirtualItem.TERRAN_INFANTRY_ARMOR, state)
        higher_upgrade = upgrade + 1 if upgrade < 3 else 3
        infantry = state.has_any((
            item_names.MARINE, item_names.DOMINION_TROOPER, item_names.MARAUDER
        ), self.player)
        if (infantry_weapons >= higher_upgrade
            and infantry_armor >= upgrade
            and infantry
            and self.terran_bio_heal(state)
        ):
            return True
        has_mineral_dump = self.terran_mineral_dump(state)
        # Mass Air-To-Ground
        ship_weapons = self.wa_upgrade_count(VirtualItem.TERRAN_SHIP_WEAPON, state)
        ship_armor = self.wa_upgrade_count(VirtualItem.TERRAN_SHIP_ARMOR, state)
        if ship_weapons >= upgrade and ship_armor >= upgrade:
            air = (
                state.has_any((item_names.BANSHEE, item_names.BATTLECRUISER), self.player)
                or state.has_all((item_names.LIBERATOR, item_names.LIBERATOR_RAID_ARTILLERY), self.player)
                or (state.has_all((item_names.VALKYRIE, item_names.VALKYRIE_FLECHETTE_MISSILES), self.player)
                    and ship_weapons >= higher_upgrade
                )
            )
            if air and has_mineral_dump:
                return True
        # Strong Mech
        vehicle_weapons = self.wa_upgrade_count(VirtualItem.TERRAN_VEHICLE_WEAPON, state)
        vehicle_armor = self.wa_upgrade_count(VirtualItem.TERRAN_VEHICLE_ARMOR, state)
        mech_heal = self.terran_sustainable_mech_heal(state)
        if vehicle_weapons >= upgrade and vehicle_armor >= upgrade:
            strong_vehicle = state.has_any((item_names.THOR, item_names.SIEGE_TANK), self.player)
            if strong_vehicle and has_mineral_dump:
                return True
            # Mech with Healing
            vehicle = state.has_any((
                item_names.GOLIATH,
                item_names.WARHOUND,
                item_names.DIAMONDBACK,
            ), self.player)
            if mech_heal and vehicle:
                return True
        if self.advanced_tactics and vehicle_armor >= upgrade:
            # Cyclones don't require attack upgrades
            if (mech_heal
                and (
                    state.has(item_names.CYCLONE, self.player)
                    and state.count_from_list_unique((
                        item_names.CYCLONE_MAG_FIELD_ACCELERATORS,
                        item_names.CYCLONE_RAPID_FIRE_LAUNCHERS,
                        item_names.CYCLONE_RESOURCE_EFFICIENCY,
                    ), self.player) >= upgrade
                )
            ):
                return True
        # Strong Royal Guard, doesn't take w/a upgrades
        return (
            has_mineral_dump
            and state.has_any((
                item_names.AEGIS_GUARD,
                item_names.BULWARK_COMPANY,
                item_names.NIGHT_WOLF,
                item_names.PRIDE_OF_AUGUSTGRAD,
            ), self.player)
        )

    @series(LogicSeries.PowerComp, SC2Race.TERRAN, 3)
    def terran_ultimate_comp(self, state: CollectionState, upgrade: int = 2) -> bool:
        """
        Can attack heavily defended bases
        """
        if not self.terran_competent_comp(state, upgrade):
            return False
        has_infantry_upgrades = (
            self.wa_upgrade_count(VirtualItem.TERRAN_INFANTRY_WEAPON, state) >= upgrade
            and self.wa_upgrade_count(VirtualItem.TERRAN_INFANTRY_ARMOR, state) >= upgrade
        )
        has_vehicle_upgrades = (
            self.wa_upgrade_count(VirtualItem.TERRAN_VEHICLE_WEAPON, state) >= upgrade
            and self.wa_upgrade_count(VirtualItem.TERRAN_VEHICLE_ARMOR, state) >= upgrade
        )
        has_ship_upgrades = (
            self.wa_upgrade_count(VirtualItem.TERRAN_SHIP_WEAPON, state) >= upgrade
            and self.wa_upgrade_count(VirtualItem.TERRAN_SHIP_ARMOR, state) >= upgrade
        )
        return (
            (
                has_vehicle_upgrades
                and state.has(item_names.SIEGE_TANK, self.player)
                and state.has_any((
                    item_names.SIEGE_TANK_JUMP_JETS,
                    item_names.SIEGE_TANK_SMART_SERVOS,
                    item_names.SIEGE_TANK_MAELSTROM_ROUNDS,
                ), self.player)
            )
            or (
                has_ship_upgrades
                and (
                    state.has_all((item_names.BATTLECRUISER, item_names.BATTLECRUISER_ATX_LASER_BATTERY), self.player)
                    or state.has_all((item_names.LIBERATOR, item_names.LIBERATOR_RAID_ARTILLERY), self.player)
                    or state.has_all((item_names.RAVEN, item_names.RAVEN_HUNTER_SEEKER_WEAPON), self.player)
                )
            )
            or (
                self.advanced_tactics
                and (
                    state.has_all((item_names.VIKING, item_names.VIKING_SHREDDER_ROUNDS), self.player)
                    or state.has_all((item_names.BANSHEE, item_names.BANSHEE_SHOCKWAVE_MISSILE_BATTERY), self.player)
                    or (
                        has_infantry_upgrades
                        and state.has_all((
                            item_names.GHOST,
                            item_names.GHOST_RESOURCE_EFFICIENCY,
                            # Note(mm): To account for snipe being weaker vs protoss
                            item_names.GHOST_EMP_ROUNDS
                        ), self.player)
                    )
                )
            )
        )

    @series(LogicSeries.AntiAir, SC2Race.TERRAN, 1)
    def terran_any_anti_air(self, state: CollectionState) -> bool:
        return (
            state.has_any(
                (
                    # Barracks
                    item_names.MARINE,
                    item_names.WAR_PIGS,
                    item_names.SON_OF_KORHAL,
                    item_names.DOMINION_TROOPER,
                    item_names.GHOST,
                    item_names.SPECTRE,
                    item_names.EMPERORS_SHADOW,
                    # Factory
                    item_names.GOLIATH,
                    item_names.SPARTAN_COMPANY,
                    item_names.BULWARK_COMPANY,
                    item_names.CYCLONE,
                    item_names.WIDOW_MINE,
                    item_names.THOR,
                    item_names.JOTUN,
                    item_names.BLACKHAMMER,
                    # Ships
                    item_names.WRAITH,
                    item_names.WINGED_NIGHTMARES,
                    item_names.NIGHT_HAWK,
                    item_names.VIKING,
                    item_names.HELS_ANGELS,
                    item_names.SKY_FURY,
                    item_names.LIBERATOR,
                    item_names.MIDNIGHT_RIDERS,
                    item_names.EMPERORS_GUARDIAN,
                    item_names.VALKYRIE,
                    item_names.BRYNHILDS,
                    item_names.BATTLECRUISER,
                    item_names.JACKSONS_REVENGE,
                    item_names.PRIDE_OF_AUGUSTGRAD,
                    item_names.RAVEN,
                    # Buildings
                    item_names.MISSILE_TURRET,
                ),
                self.player,
            )
            or state.has_all((item_names.REAPER, item_names.REAPER_JET_PACK_OVERDRIVE), self.player)
            or state.has_all((item_names.PLANETARY_FORTRESS, item_names.PLANETARY_FORTRESS_IBIKS_TRACKING_SCANNERS), self.player)
            or (
                state.has(item_names.MEDIVAC, self.player)
                and state.has_any((item_names.SIEGE_TANK, item_names.SIEGE_BREAKERS, item_names.SHOCK_DIVISION), self.player)
                and state.count(item_names.SIEGE_TANK_PROGRESSIVE_TRANSPORT_HOOK, self.player) >= 2
            )
        )

    @series(LogicSeries.AntiAir, SC2Race.TERRAN, 2)
    def terran_basic_anti_air(self, state: CollectionState) -> bool:
        """
        Basic AA to deal with few air units
        """
        return (
            state.has_any((
                # Units
                item_names.MARINE,
                item_names.DOMINION_TROOPER,
                item_names.THOR,
                item_names.CYCLONE,
                item_names.BATTLECRUISER,
                item_names.WRAITH,
                # Buildings
                item_names.MISSILE_TURRET,
                # Mercs
                item_names.WAR_PIGS,
                item_names.SPARTAN_COMPANY,
                item_names.WINGED_NIGHTMARES,
                # RG
                item_names.SON_OF_KORHAL,
                item_names.BULWARK_COMPANY,
            ), self.player)
            or (
                # Use as regular attacking unit on standard
                state.has(item_names.GHOST, self.player)
                and (self.advanced_tactics or state.has(item_names.GHOST_RESOURCE_EFFICIENCY, self.player))
            )
            or (
                # Use as regular attacking unit on standard
                state.has(item_names.SPECTRE, self.player)
                and (self.advanced_tactics or state.has(item_names.SPECTRE_RESOURCE_EFFICIENCY, self.player))
            )
            or (
                state.has(item_names.VALKYRIE, self.player)
                and (self.advanced_tactics or state.has(item_names.VALKYRIE_FLECHETTE_MISSILES, self.player))
            )
            or (
                state.has(item_names.RAVEN, self.player)
                and (self.advanced_tactics or state.has(item_names.RAVEN_HUNTER_SEEKER_WEAPON, self.player))
            )
            or (self.advanced_tactics
                and (
                    state.has_any((
                        item_names.WIDOW_MINE,
                        item_names.VIKING,  # air-to-air
                        item_names.LIBERATOR,  # air-to-air
                        item_names.SKY_FURY,  # air-to-air
                        item_names.PRIDE_OF_AUGUSTGRAD,
                        item_names.BLACKHAMMER,
                        item_names.EMPERORS_SHADOW,
                        item_names.EMPERORS_GUARDIAN,
                        item_names.NIGHT_HAWK,
                        # Mercs
                        item_names.HELS_ANGELS,  # air-to-air
                        item_names.BRYNHILDS,  # air-to-air
                    ), self.player)
                    or state.has_all((item_names.REAPER, item_names.REAPER_JET_PACK_OVERDRIVE), self.player)
                )
            )
        )

    @series(LogicSeries.AntiAir, SC2Race.TERRAN, 3)
    def terran_competent_anti_air(self, state: CollectionState) -> bool:
        """
        Good AA unit
        """
        has_bio_heal = self.terran_bio_heal(state)
        air_upgrade_level = self.wa_upgrade_count(VirtualItem.TERRAN_SHIP_WEAPON, state)
        return (
            state.has(item_names.GOLIATH, self.player)
            or (
                (
                    state.has_any((
                        item_names.MARINE,
                        item_names.DOMINION_TROOPER,
                    ), self.player)
                    or state.has_all((
                        item_names.GHOST,
                        item_names.GHOST_EMP_ROUNDS,  # Anti-protoss compensation for snipe
                        item_names.GHOST_RESOURCE_EFFICIENCY,
                    ), self.player)
                    or (self.advanced_tactics
                        and state.has_all((
                            item_names.SPECTRE,
                            item_names.SPECTRE_RESOURCE_EFFICIENCY,
                        ), self.player)
                    )
                )
                and has_bio_heal
                and self.wa_upgrade_count(VirtualItem.TERRAN_INFANTRY_WEAPON, state) >= 2
            )
            or (
                has_bio_heal
                and state.has(item_names.SON_OF_KORHAL, self.player)
            )
            or (
                state.has(item_names.CYCLONE, self.player)
                and state.count_from_list_unique((
                    item_names.CYCLONE_MAG_FIELD_ACCELERATORS,
                    item_names.CYCLONE_RAPID_FIRE_LAUNCHERS,
                    item_names.CYCLONE_RESOURCE_EFFICIENCY,
                ), self.player) >= 2
            )
            or state.has_all((item_names.THOR, item_names.THOR_PROGRESSIVE_HIGH_IMPACT_PAYLOAD), self.player)
            or state.has_all((
                item_names.BULWARK_COMPANY,
                item_names.MICRO_FILTERING,
                item_names.AUTOMATED_REFINERY,
            ), self.player)
            or (
                state.has(item_names.VALKYRIE, self.player)
                and (self.advanced_tactics or state.has(item_names.VALKYRIE_FLECHETTE_MISSILES, self.player))
            )
            or state.has_all((item_names.RAVEN, item_names.RAVEN_HUNTER_SEEKER_WEAPON), self.player)
            or (
                state.has(item_names.WRAITH, self.player)
                and (
                    state.count_from_list_unique((
                        item_names.WRAITH_ADVANCED_LASER_TECHNOLOGY,
                        item_names.WRAITH_RESOURCE_EFFICIENCY,
                    ), self.player)
                    + air_upgrade_level
                ) >= 2
                and self.wa_upgrade_count(VirtualItem.TERRAN_SHIP_ARMOR, state) >= 1
            )
            or (
                (air_upgrade_level + state.has(item_names.BATTLECRUISER_ATX_LASER_BATTERY, self.player)) >= 2
                and state.has(item_names.BATTLECRUISER, self.player)
            )
            or (
                self.advanced_tactics
                and state.has_any((
                    item_names.VIKING,
                    item_names.SKY_FURY,
                    item_names.PRIDE_OF_AUGUSTGRAD,
                ), self.player)
            )
        )

    @series(LogicSeries.Detection, SC2Race.TERRAN, 0)
    def terran_anti_cloak_self_splash(self, state: CollectionState) -> bool:
        return (
            self.terran_anti_cloak_tech(state)
            or state.has_any((
                item_names.PREDATOR,
                item_names.SIEGE_TANK,  # barely works
            ), self.player)
            or state.has_all((item_names.REAPER, item_names.REAPER_G4_CLUSTERBOMB), self.player)
            or state.has_all((item_names.VIKING, item_names.VIKING_SHREDDER_ROUNDS), self.player)
            # Note(mm): Banshee Shockwave Missile Battery doesn't damage invisible
        )

    @series(LogicSeries.Detection, SC2Race.TERRAN, 1)
    def terran_anti_cloak_tech(self, state: CollectionState) -> bool:
        return (
            self.terran_basic_detection(state)
            or state.has(item_names.EMPERORS_SHADOW, self.player)
            or state.has_all((item_names.GHOST, item_names.GHOST_EMP_ROUNDS), self.player)
            # Note(mm): I can't believe sc2 spider mines don't trigger on cloaked units
        )

    @series(LogicSeries.Detection, SC2Race.TERRAN, 2)
    def terran_basic_detection(self, state: CollectionState) -> bool:
        return state.has_any(item_groups.terran_detection, self.player)

    @series(LogicSeries.Detection, SC2Race.TERRAN, 3)
    def terran_mobile_detector(self, state: CollectionState) -> bool:
        return state.has_any(item_groups.terran_mobile_detection, self.player)

    @series(LogicSeries.MacroPower, SC2Race.TERRAN, 0)
    def terran_macro_rating(self, state: CollectionState) -> int:
        """Rating out of 18. Recommend requiring no more than 12."""
        # Passive Score (Economic upgrades and global army upgrades)
        # max 18
        power_score = 0
        terran_passive_ratings = {
            (item_names.AUTOMATED_REFINERY, 4,),
            (item_names.COMMAND_CENTER_MULE, 4,),
            (item_names.ORBITAL_DEPOTS, 2,),
            (item_names.COMMAND_CENTER_COMMAND_CENTER_REACTOR, 2,),
            (item_names.COMMAND_CENTER_EXTRA_SUPPLIES, 2,),
            (item_names.MICRO_FILTERING, 2,),
            (item_names.TECH_REACTOR, 2,),
        }
        for item, rating in terran_passive_ratings:
            if state.has(item, self.player):
                power_score += rating
        return power_score

    @series(LogicSeries.MacroPower, SC2Race.TERRAN, 1)
    def terran_soa_active_power_rating(self, state: CollectionState) -> int:
        return self.terran_macro_rating(state) + self.soa_power_rating(state)

    @series(LogicSeries.MacroPower, SC2Race.TERRAN, 2)
    def terran_soa_passive_power_rating(self, state: CollectionState) -> int:
        return self.terran_macro_rating(state) + self.soa_passive_power_rating(state)

    @series(LogicSeries.MacroPower, SC2Race.TERRAN, 3)
    def terran_soa_power_rating(self, state: CollectionState) -> int:
        return (
            self.terran_macro_rating(state)
            + self.soa_power_rating(state)
            + self.soa_passive_power_rating(state)
        )

    @series(LogicSeries.DefenseRating, SC2Race.TERRAN, 0)
    def terran_defense_rating(self, state: CollectionState) -> int:
        """
        Basic-logic only defensive tools. Siegeable units and buildings only.
        Individual options rate 1~3 points depending on strength and applicability.
        Max possible rating around 20. Reasonable requirement limit around 10.
        """
        rating = 0
        # Good
        for item in (
            item_names.SIEGE_TANK,
            item_names.LIBERATOR,
            item_names.PLANETARY_FORTRESS,
            item_names.PERDITION_TURRET,
            item_names.DEVASTATOR_TURRET,
        ):
            if state.has(item, self.player):
                rating += 3
        if state.has_all((
            item_names.PSI_DISRUPTER,
            item_names.PSI_SCREEN,
            item_names.SONIC_DISRUPTER,
        ), self.player):
            rating += 3
        # Medium
        for item in (
            item_names.WIDOW_MINE,
            item_names.SIEGE_BREAKERS,
        ):
            if state.has(item, self.player):
                rating += 2
        # Situational
        if state.has(item_names.MISSILE_TURRET, self.player):
            rating += 1
        # Manned Bunker
        if state.has(item_names.BUNKER, self.player):
            if (state.has_any((
                item_names.MARINE, item_names.DOMINION_TROOPER, item_names.MARAUDER, item_names.REAPER,
            ), self.player)):
                rating += 3
            elif state.has(item_names.FIREBAT, self.player):
                rating += 1
            elif state.has_all((
                item_names.SPECTRE,
                item_names.SPECTRE_IMPALER_ROUNDS,
                item_names.SPECTRE_RESOURCE_EFFICIENCY,
            ), self.player):
                rating += 1
            elif state.has_all((
                item_names.GHOST,
                item_names.GHOST_OCULAR_IMPLANTS,
                item_names.GHOST_RESOURCE_EFFICIENCY,
            ), self.player):
                rating += 1

        return rating

    def terran_basic_air_comp(self, state: CollectionState) -> bool:
        """Basic logic-only noob-friendly air comp for roaming around the map"""
        return (
            self.wa_upgrade_count(VirtualItem.TERRAN_SHIP_WEAPON, state) >= 1
            and (
                state.has_any((
                    item_names.VIKING, item_names.WRAITH, item_names.BATTLECRUISER,
                ), self.player)
                or state.has_all((item_names.LIBERATOR, item_names.LIBERATOR_RAID_ARTILLERY), self.player)
                or state.has_all((item_names.RAVEN, item_names.RAVEN_HUNTER_SEEKER_WEAPON), self.player)
                or state.has_all((item_names.VALKYRIE, item_names.VALKYRIE_FLECHETTE_MISSILES), self.player)
            )
        )

    def terran_basic_transport(self, state: CollectionState) -> bool:
        return state.has_any((
            item_names.MEDIVAC,
            item_names.HERCULES,
        ), self.player)

    def terran_basic_transport_or_air_comp(self, state: CollectionState) -> bool:
        return self.terran_basic_transport(state) or self.terran_basic_air_comp(state)

    def terran_air_anti_air(self, state: CollectionState) -> bool:
        """
        Air-to-air
        """
        return (
            state.has(item_names.VIKING, self.player)
            or state.has_all((item_names.WRAITH, item_names.WRAITH_ADVANCED_LASER_TECHNOLOGY), self.player)
            or state.has_all((item_names.BATTLECRUISER, item_names.BATTLECRUISER_ATX_LASER_BATTERY), self.player)
            or (
                self.advanced_tactics
                and state.has_any((item_names.WRAITH, item_names.VALKYRIE, item_names.BATTLECRUISER), self.player)
                and self.wa_upgrade_count(VirtualItem.TERRAN_SHIP_WEAPON, state) >= 2
            )
        )

    def terran_early_tech(self, state: CollectionState) -> bool:
        """
        Basic combat unit that can be deployed quickly from mission start
        """
        return (
            state.has_any((
                item_names.MARINE,
                item_names.DOMINION_TROOPER,
                item_names.FIREBAT,
                item_names.MARAUDER,
                item_names.REAPER,
                item_names.HELLION,
            ), self.player)
            or (
                self.advanced_tactics
                and state.has_any((
                    item_names.GOLIATH,
                    item_names.DIAMONDBACK,
                    item_names.VIKING,
                    item_names.BANSHEE,
                ), self.player)
            )
        )

    def terran_air(self, state: CollectionState) -> bool:
        """
        Air units or drops on advanced tactics
        """
        return (
            state.has_any((
                item_names.VIKING,
                item_names.WRAITH,
                item_names.BANSHEE,
                item_names.BATTLECRUISER,
            ), self.player)
            or state.has_all((item_names.VALKYRIE, item_names.VALKYRIE_FLECHETTE_MISSILES), self.player)
            or state.has_all((item_names.LIBERATOR, item_names.LIBERATOR_RAID_ARTILLERY), self.player)
            or (
                self.advanced_tactics
                and (
                    (
                        state.has_any((item_names.HERCULES, item_names.MEDIVAC), self.player)
                        and self.has_terran_advanced_starter_unit(state)
                    )
                    or (state.has_all((item_names.RAVEN, item_names.RAVEN_HUNTER_SEEKER_WEAPON), self.player))
                )
            )
        )

    def terran_mineral_dump(self, state: CollectionState) -> bool:
        """
        Can build something using only minerals
        """
        return (
            state.has_any((
                item_names.MARINE, item_names.VULTURE, item_names.HELLION, item_names.DOMINION_TROOPER
            ), self.player)
            or state.has_all((item_names.REAPER, item_names.REAPER_RESOURCE_EFFICIENCY), self.player)
            or (self.advanced_tactics
                and state.has_any((item_names.PERDITION_TURRET, item_names.DEVASTATOR_TURRET), self.player)
            )
        )

    def marine_medic_upgrade(self, state: CollectionState) -> bool:
        """
        Infantry upgrade to infantry-only no-build segments
        """
        return (
            state.has_any((
                item_names.MARINE_COMBAT_SHIELD,
                item_names.MARINE_STIMPACK,
                item_names.MARINE_MAGRAIL_MUNITIONS,
                item_names.MARINE_MEDPACK,
                item_names.MEDIC_STABILIZER_MEDPACKS,
            ), self.player)
            or (self.advanced_tactics
                and state.has(item_names.MARINE_LASER_TARGETING_SYSTEM, self.player)
            )
        )

    def marine_medic_firebat_upgrade(self, state: CollectionState) -> bool:
        return (
            self.marine_medic_upgrade(state)
            or state.has_all((item_names.FIREBAT_STIMPACK, item_names.FIREBAT_MEDPACK), self.player)
            or state.has_any((item_names.FIREBAT_NANO_PROJECTORS, item_names.FIREBAT_JUGGERNAUT_PLATING), self.player)
        )

    def terran_bio_heal(self, state: CollectionState) -> bool:
        """
        Ability to heal bio units
        """
        return (
            state.has_any((item_names.MEDIC, item_names.MEDIVAC, item_names.FIELD_RESPONSE_THETA), self.player)
            or (self.advanced_tactics
                and state.has_all((item_names.RAVEN, item_names.RAVEN_BIO_MECHANICAL_REPAIR_DRONE), self.player)
            )
        )

    def terran_sustainable_mech_heal(self, state: CollectionState) -> bool:
        """
        Can heal mech units without spending resources
        """
        return (
            state.has(item_names.SCIENCE_VESSEL, self.player)
            or state.has_all((item_names.MEDIC, item_names.MEDIC_ADAPTIVE_MEDPACKS), self.player)
            or state.count(item_names.PROGRESSIVE_REGENERATIVE_BIO_STEEL, self.player) >= 2
            or state.has_all((item_names.RAVEN, item_names.RAVEN_BIO_MECHANICAL_REPAIR_DRONE), self.player)
            or (self.advanced_tactics and state.has(item_names.SCV_RESOURCEFUL, self.player))
        )

    def terran_cliffjumper(self, state: CollectionState) -> bool:
        return (
            state.has(item_names.REAPER, self.player)
            or state.has_all((item_names.GOLIATH, item_names.GOLIATH_JUMP_JETS), self.player)
            or state.has_all((item_names.SIEGE_TANK, item_names.SIEGE_TANK_JUMP_JETS), self.player)
        )

    # endregion Global Terran

    # ###################################################################################################### #
    # region Global Zerg ................................................................................... #
    # ###################################################################################################### #

    @series(LogicSeries.PowerComp, SC2Race.ZERG, 1)
    def zerg_upgraded_unit(self, state: CollectionState, upgrade: int) -> bool:
        return (
            (
                self.wa_upgrade_count(VirtualItem.ZERG_GROUND_ARMOR, state) >= upgrade
                and (
                    (
                        self.wa_upgrade_count(VirtualItem.ZERG_MELEE_ATTACK, state) >= upgrade
                        and (
                            state.has_any(self.upgradeable_zerg_melee_units, self.player)
                            or (self.morphling_enabled
                                and state.has_any(self.upgradeable_zerg_melee_morphs, self.player)
                            )
                        )
                    )
                    or (
                        self.wa_upgrade_count(VirtualItem.ZERG_RANGED_ATTACK, state) >= upgrade
                        and (
                            state.has_any(self.upgradeable_zerg_ranged_units, self.player)
                            or (self.morphling_enabled
                                and state.has_any(self.upgradeable_zerg_ranged_morphs, self.player)
                            )
                        )
                    )
                )
            )
            or (
                self.wa_upgrade_count(VirtualItem.ZERG_AIR_ARMOR, state) >= upgrade
                and self.wa_upgrade_count(VirtualItem.ZERG_AIR_ATTACK, state) >= upgrade
                and (
                    state.has_any(self.upgradeable_zerg_air_units, self.player)
                    or (self.morphling_enabled
                        and state.has_any(self.upgradeable_zerg_air_morphs, self.player)
                    )
                )
            )
        )

    @series(LogicSeries.PowerComp, SC2Race.ZERG, 2)
    def zerg_competent_comp(self, state: CollectionState, upgrade: int = 1) -> bool:
        if self.wa_upgrade_count(VirtualItem.ZERG_GROUND_ARMOR, state) < upgrade:
            # All comps require at least one upgraded ground unit
            return False
        has_melee_attack = self.wa_upgrade_count(VirtualItem.ZERG_MELEE_ATTACK, state) > upgrade
        has_ranged_attack = self.wa_upgrade_count(VirtualItem.ZERG_RANGED_ATTACK, state) > upgrade
        core_unit = (
            (
                has_melee_attack
                and state.has_any((
                    item_names.ZERGLING, item_names.ABERRATION, item_names.PYGALISK,
                ), self.player)
            )
            or (
                has_ranged_attack
                and (
                    state.has_any((
                        item_names.ROACH, item_names.INFESTED_DIAMONDBACK,
                    ), self.player)
                    or self.morph_igniter(state)
                )
            )
        )
        support_unit = (
            state.has_any((item_names.SWARM_QUEEN, item_names.HYDRALISK, item_names.INFESTED_BANSHEE), self.player)
            or self.morph_brood_lord(state)
            or self.morph_guardian(state)
            or (state.has(item_names.MUTALISK, self.player)
                and state.count_from_list_unique((
                    item_names.MUTALISK_VICIOUS_GLAIVE,
                    item_names.MUTALISK_SEVERING_GLAIVE,
                    item_names.MUTALISK_SUNDERING_GLAIVE,
                    VirtualItem.ZERG_AIR_ATTACK.name,
                ), self.player) >= 2
            )
            or (self.advanced_tactics
                and (
                    state.has_any((
                        item_names.INFESTOR, item_names.DEFILER, item_names.HIVE_QUEEN,
                    ), self.player)
                    or self.morph_viper(state)
                )
            )
        )
        if core_unit and support_unit:
            return True
        has_air_attack = self.wa_upgrade_count(VirtualItem.ZERG_AIR_ATTACK, state) >= upgrade
        vespene_unit = (
            (
                state.has_any((item_names.ULTRALISK, item_names.ABERRATION), self.player)
                and has_melee_attack
            )
            or (
                self.morph_guardian(state)
                and has_air_attack
                and state.has_any((
                    item_names.GUARDIAN_SORONAN_ACID,
                    item_names.GUARDIAN_EXPLOSIVE_SPORES,
                    item_names.GUARDIAN_PRIMORDIAL_FURY,
                ), self.player)
            )
            or (
                self.morph_brood_lord(state)
                and has_air_attack
                and has_melee_attack
                and state.has(item_names.BROOD_LORD_POROUS_CARTILAGE, self.player)
            )
            or (self.advanced_tactics
                and self.morph_viper(state)
            )
        )
        return (
            vespene_unit
            and self.zerg_mineral_dump(state)
        )

    @series(LogicSeries.PowerComp, SC2Race.ZERG, 3)
    def zerg_ultimate_comp(self, state: CollectionState, upgrade: int = 2) -> bool:
        """Powerful and sustainable zerg anti-ground for busting big bases; anti-air not included"""
        if not self.zerg_competent_comp(state, upgrade):
            return False
        has_ground_carapace = self.wa_upgrade_count(VirtualItem.ZERG_GROUND_ARMOR, state) >= upgrade
        has_melee_upgrades = (
            self.wa_upgrade_count(VirtualItem.ZERG_MELEE_ATTACK, state) >= upgrade
            and has_ground_carapace
        )
        has_ranged_upgrades = (
            self.wa_upgrade_count(VirtualItem.ZERG_RANGED_ATTACK, state) >= upgrade
            and has_ground_carapace
        )
        has_air_upgrades = (
            self.wa_upgrade_count(VirtualItem.ZERG_AIR_ATTACK, state) >= upgrade
            and self.wa_upgrade_count(VirtualItem.ZERG_AIR_ARMOR, state) >= upgrade
        )
        return (
            (
                has_melee_upgrades
                and (
                    self.morph_tyrannozor(state)
                    or (
                        state.has_all((item_names.ULTRALISK, item_names.ULTRALISK_TORRASQUE_STRAIN), self.player)
                        and state.has_any((
                            item_names.ULTRALISK_MONARCH_BLADES,
                            item_names.ULTRALISK_CHITINOUS_PLATING,
                        ), self.player)
                    )
                    or state.has_all((
                        item_names.ABERRATION,
                        item_names.ABERRATION_RESOURCE_EFFICIENCY,
                        item_names.ABERRATION_BANELING_INCUBATION,
                    ), self.player)
                )
                and state.has(item_names.SWARM_QUEEN, self.player)  # Healing to sustain the frontline
            )
            or (
                has_ranged_upgrades
                and (
                    self.morph_impaler(state)
                    or (self.morph_lurker(state)
                        and state.has_all((item_names.LURKER_SEISMIC_SPINES, item_names.LURKER_ADAPTED_SPINES), self.player)
                    )
                    or state.has_all((
                        item_names.ROACH,
                        item_names.ROACH_CORPSER_STRAIN,
                        item_names.ROACH_ADAPTIVE_PLATING,
                        item_names.ROACH_GLIAL_RECONSTITUTION,
                    ), self.player)
                    or (self.morph_igniter(state)
                        and state.has(item_names.PRIMAL_IGNITER_PRIMAL_TENACITY, self.player)
                    )
                    or state.has_all((item_names.INFESTOR, item_names.INFESTOR_INFESTED_TERRAN), self.player)
                    or (self.spread_creep(state, False)
                        and state.has(item_names.INFESTED_BUNKER, self.player)
                    )
                    or self.zerg_infested_tank_with_ammo(state)
                    # Highly-upgraded swarm hosts may also work, but that would require promoting many upgrades to progression
                )
            )
            or (
                has_air_upgrades
                and (
                    self.morph_brood_lord(state)
                    or (self.morph_guardian(state)
                        and state.has_all((item_names.GUARDIAN_PROPELLANT_SACS, item_names.GUARDIAN_SORONAN_ACID), self.player)
                    )
                    or state.has_all((item_names.INFESTED_BANSHEE, item_names.INFESTED_BANSHEE_FLESHFUSED_TARGETING_OPTICS), self.player)
                    # Highly-upgraded anti-ground devourers would also be good
                )
            )
        )

    @series(LogicSeries.AntiAir, SC2Race.ZERG, 1)
    def zerg_any_anti_air(self, state: CollectionState) -> bool:
        return (
            state.has_any((
                item_names.HYDRALISK,
                item_names.SWARM_QUEEN,
                item_names.HIVE_QUEEN,
                item_names.BROOD_QUEEN,
                item_names.MUTALISK,
                item_names.CORRUPTOR,
                item_names.SCOURGE,
                item_names.INFESTOR,
                item_names.INFESTED_MARINE,
                item_names.INFESTED_LIBERATOR,
                # buildings
                item_names.SPORE_CRAWLER,
                item_names.INFESTED_MISSILE_TURRET,
                item_names.INFESTED_BUNKER,
                # mercs
                item_names.HUNTER_KILLERS,
                item_names.CAUSTIC_HORRORS,
            ), self.player)
            or state.has_all((
                item_names.SWARM_HOST,
                item_names.SWARM_HOST_PRESSURIZED_GLANDS,
            ), self.player)
            or state.has_all((
                item_names.ABERRATION,
                item_names.ABERRATION_PROGRESSIVE_BANELING_LAUNCH,
            ), self.player)
            or state.has_all((
                item_names.INFESTED_DIAMONDBACK,
                item_names.INFESTED_DIAMONDBACK_PROGRESSIVE_FUNGAL_SNARE,
            ), self.player)
            or self.morph_ravager(state)
            or self.morph_viper(state)
            or self.morph_devourer(state)
            or (
                self.morph_guardian(state)
                and state.has(item_names.GUARDIAN_PRIMAL_ADAPTATION, self.player)
            )
            # Note(mm): Noxious Ultralisks excluded for being a little too silly
        )

    @series(LogicSeries.AntiAir, SC2Race.ZERG, 2)
    def zerg_basic_anti_air(self, state: CollectionState) -> bool:
        spread_creep = self.spread_creep(state)
        return (
            state.has_any((
                item_names.HYDRALISK,
                item_names.MUTALISK,
                item_names.SWARM_QUEEN,
                item_names.HIVE_QUEEN,
                item_names.HUNTER_KILLERS,
                item_names.CAUSTIC_HORRORS,
            ), self.player)
            or state.has_all((
                item_names.INFESTED_DIAMONDBACK,
                item_names.INFESTED_DIAMONDBACK_PROGRESSIVE_FUNGAL_SNARE,
            ), self.player)
            or (state.has_all((
                    item_names.INFESTED_MARINE, item_names.INFESTED_MARINE_ENDURING_STRAIN,
                ), self.player)
                and (
                    spread_creep
                    or state.has(item_names.INFESTED_MARINE_LEG_ENHANCEMENTS, self.player)
                )
            )
            or state.has_all((
                item_names.SWARM_HOST,
                item_names.SWARM_HOST_PRESSURIZED_GLANDS,
            ), self.player)
            or (self.morph_guardian(state)
                and state.has(item_names.GUARDIAN_PRIMAL_ADAPTATION, self.player)
            )
            or (self.morph_devourer(state)
                and (
                    # Note: Basic should never require using AA-only units
                    state.has(item_names.DEVOURER_PRESCIENT_SPORES, self.player)
                    or self.advanced_tactics
                )
            )
            or (
                self.advanced_tactics
                and (
                    state.has_any((
                        item_names.CORRUPTOR,
                        item_names.BROOD_QUEEN,
                        item_names.SCOURGE,
                    ), self.player)
                    or state.has_all((item_names.INFESTOR, item_names.INFESTOR_INFESTED_TERRAN), self.player)
                    or state.has_all((item_names.VIPER, item_names.VIPER_PARASITIC_BOMB), self.player)
                    or state.has_all((
                        item_names.INFESTED_LIBERATOR, item_names.INFESTED_LIBERATOR_CLOUD_DISPERSAL,
                    ), self.player)
                    or (
                        self.morph_ravager(state)
                        and state.has_any((
                            item_names.RAVAGER_AERIAL_CORROSIVE_BILE,
                            item_names.RAVAGER_BURROWED_BOMBARDMENT,
                        ), self.player)
                    )
                )
            )
            or (
                spread_creep
                and state.has(item_names.INFESTED_BUNKER, self.player)
            )
            or (self.advanced_tactics
                and spread_creep
                and state.has_any((item_names.SPORE_CRAWLER, item_names.INFESTED_MISSILE_TURRET), self.player)
            )
        )

    @series(LogicSeries.AntiAir, SC2Race.ZERG, 3)
    def zerg_competent_anti_air(self, state: CollectionState) -> bool:
        ranged_attack_upgrades = self.wa_upgrade_count(VirtualItem.ZERG_RANGED_ATTACK, state)
        air_attack_upgrades = self.wa_upgrade_count(VirtualItem.ZERG_AIR_ATTACK, state)
        return (
            (
                state.has(item_names.HYDRALISK, self.player)
                and (
                    ranged_attack_upgrades >= 1
                    or state.has_any((
                        item_names.HYDRALISK_RESOURCE_EFFICIENCY,
                        item_names.HYDRALISK_FRENZY,
                    ), self.player)
                )
            )
            or (
                ranged_attack_upgrades >= 1
                and state.has_all((
                    item_names.SWARM_QUEEN,
                    item_names.SWARM_QUEEN_RESOURCE_EFFICIENCY,
                    item_names.SWARM_QUEEN_BIO_MECHANICAL_TRANSFUSION,
                ), self.player)
            )
            or (
                state.has(item_names.MUTALISK, self.player)
                and air_attack_upgrades >= 1
            )
            or (
                state.has_all((
                    item_names.INFESTED_DIAMONDBACK,
                ), self.player)
                and state.has(item_names.INFESTED_DIAMONDBACK_PROGRESSIVE_FUNGAL_SNARE, self.player, 2)
            )
            or (
                self.advanced_tactics
                and (
                    state.has_any((
                        item_names.CORRUPTOR,
                        item_names.BROOD_QUEEN,
                    ), self.player)
                    or (state.has_all((
                            item_names.INFESTED_MARINE,
                            item_names.INFESTED_MARINE_ENDURING_STRAIN,
                            item_names.INFESTED_MARINE_LEG_ENHANCEMENTS,
                        ), self.player)
                        and ranged_attack_upgrades >= 1
                        and self.spread_creep(state)
                    )
                    or state.has_all((
                        item_names.SCOURGE,
                        item_names.SCOURGE_RESOURCE_EFFICIENCY,
                        item_names.SCOURGE_SWARM_SCOURGE,
                        item_names.VESPENE_EFFICIENCY,
                    ), self.player)
                    or state.has_all((
                        item_names.SWARM_HOST,
                        item_names.SWARM_HOST_PRESSURIZED_GLANDS,
                        item_names.SWARM_HOST_RAPID_INCUBATION,
                    ), self.player)
                    or state.has_all((item_names.INFESTOR, item_names.INFESTOR_INFESTED_TERRAN), self.player)
                    or state.has_all((item_names.VIPER, item_names.VIPER_PARASITIC_BOMB), self.player)
                    or state.has_all((
                        item_names.INFESTED_LIBERATOR, item_names.INFESTED_LIBERATOR_CLOUD_DISPERSAL,
                    ), self.player)
                    or (
                        self.morph_ravager(state)
                        and state.has_all((
                            item_names.RAVAGER_AERIAL_CORROSIVE_BILE,
                            item_names.RAVAGER_BURROWED_BOMBARDMENT,
                        ), self.player)
                    )
                )
            )
        )

    @series(LogicSeries.Detection, SC2Race.ZERG, 1)
    def zerg_anti_cloak_tech(self, state: CollectionState) -> bool:
        return (
            self.zerg_basic_detection(state)
            or self.morph_ravager(state)
            or self.morph_baneling(state)
            or state.has_any((
                item_names.DEFILER,  # Plague
                item_names.INFESTOR,  # Fungal Growth
                item_names.BULLFROG,
            ), self.player)
        )

    @series(LogicSeries.Detection, SC2Race.ZERG, 2)
    def zerg_basic_detection(self, state: CollectionState) -> bool:
        return (
            state.has_any(item_groups.zerg_detection, self.player)
            or self._zerg_mobile_multi_item_detection(state)
        )

    @series(LogicSeries.Detection, SC2Race.ZERG, 3)
    def zerg_mobile_detector(self, state: CollectionState) -> bool:
        return (
            state.has_any(item_groups.zerg_mobile_detection, self.player)
            or self._zerg_mobile_multi_item_detection(state)
        )

    def _zerg_mobile_multi_item_detection(self, state: CollectionState) -> bool:
        return (self.morph_lurker(state) and state.has(item_names.LURKER_SONAR_GLANDS, self.player))

    @series(LogicSeries.MacroPower, SC2Race.ZERG, 0)
    def zerg_macro_rating(self, state: CollectionState) -> int:
        """Rating out of 20. Recommend requiring no more than 12."""
        # Passive Score (Economic upgrades and global army upgrades)
        # Max 20
        power_score = 0
        zerg_passive_ratings = (
            (item_names.TWIN_DRONES, 7,),
            (item_names.AUTOMATED_EXTRACTORS, 4,),
            (item_names.VESPENE_EFFICIENCY, 3,),
            (item_names.OVERLORD_IMPROVED_OVERLORDS, 4,),
            (item_names.MALIGNANT_CREEP, 2,),
        )
        for item, rating in zerg_passive_ratings:
            if state.has(item, self.player):
                power_score += rating
        return power_score

    @series(LogicSeries.MacroPower, SC2Race.ZERG, 1)
    def zerg_soa_active_power_rating(self, state: CollectionState) -> int:
        return self.zerg_macro_rating(state) + self.soa_power_rating(state)

    @series(LogicSeries.MacroPower, SC2Race.ZERG, 2)
    def zerg_soa_passive_power_rating(self, state: CollectionState) -> int:
        return self.zerg_macro_rating(state) + self.soa_passive_power_rating(state)

    @series(LogicSeries.MacroPower, SC2Race.ZERG, 3)
    def zerg_soa_power_rating(self, state: CollectionState) -> int:
        return (
            self.zerg_macro_rating(state)
            + self.soa_power_rating(state)
            + self.soa_passive_power_rating(state)
        )

    @series(LogicSeries.DefenseRating, SC2Race.ZERG, 0)
    def zerg_defense_rating(self, state: CollectionState) -> int:
        """
        Basic-logic only defensive tools. Siegeable units and buildings only.
        Individual options rate 1~3 points depending on strength and applicability.
        Max possible rating around 20. Reasonable requirement limit around 10.
        """

        rating = 0
        # Good
        for item in (
            item_names.SPINE_CRAWLER,
            item_names.INFESTED_BUNKER,
            item_names.BILE_LAUNCHER,
            item_names.SWARM_HOST,
        ):
            if state.has(item, self.player):
                rating += 3
        if self.morph_lurker(state):
            rating += 3
        if self.morph_impaler(state):
            rating += 3
        # Medium
        if state.has_all((item_names.INFESTED_LIBERATOR, item_names.INFESTED_LIBERATOR_DEFENDER_MODE), self.player):
            rating += 2
        # Situational
        for item in (
            item_names.SPORE_CRAWLER,
            item_names.INFESTED_MISSILE_TURRET,
        ):
            if state.has(item, self.player):
                rating += 1
        return rating

    def zerg_basic_transport(self, state: CollectionState) -> bool:
        return state.has_any((
            item_names.YGGDRASIL,
            item_names.OVERLORD_VENTRAL_SACS,
            item_names.NYDUS_WORM,
            item_names.BULLFROG,
        ), self.player)

    def zerg_basic_air_comp(self, state: CollectionState) -> bool:
        """Basic logic-only air comp for roaming the map"""
        has_guardian = self.morph_guardian(state)
        has_devourer = self.morph_devourer(state)
        return (
            self.wa_upgrade_count(VirtualItem.ZERG_AIR_ATTACK, state) >= 1
            and (
                state.has(item_names.MUTALISK, self.player)
                or (
                    has_guardian
                    and state.has_all((
                        item_names.GUARDIAN_PROPELLANT_SACS,
                        item_names.GUARDIAN_PRIMAL_ADAPTATION,
                    ), self.player)
                )
                or (
                    has_devourer
                    and state.has(item_names.DEVOURER_PRESCIENT_SPORES, self.player)
                )
                or (
                    (
                        state.has(item_names.CORRUPTOR, self.player)
                        or state.has_all((
                            item_names.INFESTED_LIBERATOR,
                            item_names.INFESTED_LIBERATOR_CLOUD_DISPERSAL,
                        ), self.player)
                        or has_devourer
                    )
                    and (
                        has_guardian
                        or self.morph_brood_lord(state)
                        or state.has(item_names.INFESTED_BANSHEE, self.player)
                    )
                )
            )
        )

    def zerg_strong_air_comp(self, state: CollectionState) -> bool:
        has_guardian = self.morph_guardian(state)
        has_devourer = self.morph_devourer(state)
        return (
            self.wa_upgrade_count(VirtualItem.ZERG_AIR_ATTACK, state) >= 3
            and (
                (
                    state.has(item_names.MUTALISK, self.player)
                    and state.count_from_list_unique((
                        item_names.MUTALISK_SEVERING_GLAIVE,
                        item_names.MUTALISK_SUNDERING_GLAIVE,
                        item_names.MUTALISK_VICIOUS_GLAIVE,
                        item_names.MUTALISK_RAPID_REGENERATION,
                        item_names.MUTALISK_AERODYNAMIC_GLAIVE_SHAPE,
                    ), self.player) >= 3
                )
                or (
                    state.has_all((
                        item_names.INFESTED_LIBERATOR,
                        item_names.INFESTED_LIBERATOR_DEFENDER_MODE,
                        item_names.INFESTED_LIBERATOR_CLOUD_DISPERSAL,
                    ), self.player)
                )
                or (
                    has_guardian
                    and state.has_all((
                        item_names.GUARDIAN_PROPELLANT_SACS,
                        item_names.GUARDIAN_PRIMAL_ADAPTATION,
                        item_names.GUARDIAN_PROLONGED_DISPERSION,
                    ), self.player)
                )
                or (
                    has_devourer
                    and state.has_all((
                        item_names.DEVOURER_GAPING_MAW,
                        item_names.DEVOURER_PRESCIENT_SPORES,
                    ), self.player)
                )
                or (
                    (
                        state.has_all((
                            item_names.CORRUPTOR,
                            item_names.CORRUPTOR_RESOURCE_EFFICIENCY,
                        ), self.player)
                        or state.has_all((
                            item_names.INFESTED_LIBERATOR,
                            item_names.INFESTED_LIBERATOR_CLOUD_DISPERSAL,
                        ), self.player)
                        or has_devourer
                    )
                    and (
                        has_guardian
                        or self.morph_brood_lord(state)
                        or state.has_all((
                            item_names.INFESTED_BANSHEE,
                            item_names.INFESTED_BANSHEE_FLESHFUSED_TARGETING_OPTICS,
                        ), self.player)
                    )
                )
            )
        )

    def zerg_basic_transport_or_air_comp(self, state: CollectionState) -> bool:
        return self.zerg_basic_transport(state) or self.zerg_basic_transport(state)

    def zerg_can_collect_pickup_across_gap(self, state: CollectionState) -> bool:
        """Any way for zerg to get any ground unit across gaps longer than viper yoink range to collect a pickup."""
        return (
            state.has_any((
                item_names.NYDUS_WORM,
                item_names.ECHIDNA_WORM,
                item_names.OVERLORD_VENTRAL_SACS,
                item_names.YGGDRASIL,
            ), self.player)
            or state.has_all((
                item_names.INFESTED_BANSHEE,
                item_names.INFESTED_BANSHEE_RAPID_HIBERNATION,
            ), self.player)
            or (
                state.has(item_names.OVERLORD_GENERATE_CREEP, self.player)
                and (
                    state.has_all((
                        item_names.INFESTED_SIEGE_TANK,
                        item_names.INFESTED_SIEGE_TANK_DEEP_TUNNEL,
                    ), self.player)
                    or state.has_all((
                        item_names.SWARM_QUEEN,
                        item_names.SWARM_QUEEN_DEEP_TUNNEL,
                    ), self.player)
                    or (self.morph_ravager(state)
                        and state.has(item_names.RAVAGER_DEEP_TUNNEL, self.player)
                    )
                    or (self.morph_impaler(state)
                        and state.has(item_names.IMPALER_DEEP_TUNNEL, self.player)
                    )
                )
            )
        )

    def zerg_has_infested_scv(self, state: CollectionState) -> bool:
        return (
            state.has_any((
                item_names.INFESTED_MARINE,
                item_names.INFESTED_BUNKER,
                item_names.INFESTED_DIAMONDBACK,
                item_names.INFESTED_SIEGE_TANK,
                item_names.INFESTED_BANSHEE,
                item_names.BULLFROG,
                item_names.INFESTED_LIBERATOR,
                item_names.INFESTED_MISSILE_TURRET,
            ), self.player)
        )

    def zerg_infested_tank_with_ammo(self, state: CollectionState) -> bool:
        return state.has(item_names.INFESTED_SIEGE_TANK, self.player) and (
            state.has_all({item_names.INFESTOR, item_names.INFESTOR_INFESTED_TERRAN}, self.player)
            or state.has(item_names.INFESTED_BUNKER, self.player)
            or (self.advanced_tactics and state.has(item_names.INFESTED_MARINE, self.player))
            or (
                state.count(item_names.INFESTED_SIEGE_TANK_PROGRESSIVE_AUTOMATED_MITOSIS, self.player)
                >= (1 if self.advanced_tactics else 2)
            )
        )

    def morph_baneling(self, state: CollectionState) -> bool:
        return (state.has(item_names.ZERGLING, self.player) or self.morphling_enabled) and state.has(item_names.BANELING, self.player)

    def morph_ravager(self, state: CollectionState) -> bool:
        return (state.has(item_names.ROACH, self.player) or self.morphling_enabled) and state.has(item_names.RAVAGER, self.player)

    def morph_brood_lord(self, state: CollectionState) -> bool:
        return (state.has_any({item_names.MUTALISK, item_names.CORRUPTOR}, self.player) or self.morphling_enabled) and state.has(
            item_names.BROOD_LORD, self.player
        )

    def morph_guardian(self, state: CollectionState) -> bool:
        return (state.has_any({item_names.MUTALISK, item_names.CORRUPTOR}, self.player) or self.morphling_enabled) and state.has(
            item_names.GUARDIAN, self.player
        )

    def morph_viper(self, state: CollectionState) -> bool:
        return (state.has_any({item_names.MUTALISK, item_names.CORRUPTOR}, self.player) or self.morphling_enabled) and state.has(
            item_names.VIPER, self.player
        )

    def morph_devourer(self, state: CollectionState) -> bool:
        return (state.has_any({item_names.MUTALISK, item_names.CORRUPTOR}, self.player) or self.morphling_enabled) and state.has(
            item_names.DEVOURER, self.player
        )

    def morph_impaler(self, state: CollectionState) -> bool:
        return (state.has(item_names.HYDRALISK, self.player) or self.morphling_enabled) and state.has(
            item_names.IMPALER, self.player
        )

    def morph_lurker(self, state: CollectionState) -> bool:
        return (state.has(item_names.HYDRALISK, self.player) or self.morphling_enabled) and state.has(item_names.LURKER, self.player)

    def morph_igniter(self, state: CollectionState) -> bool:
        return (state.has(item_names.ROACH, self.player) or self.morphling_enabled) and state.has(item_names.PRIMAL_IGNITER, self.player)

    def morph_tyrannozor(self, state: CollectionState) -> bool:
        return state.has(item_names.TYRANNOZOR, self.player) and (
            state.has(item_names.ULTRALISK, self.player) or self.morphling_enabled
        )

    def spread_creep(self, state: CollectionState, free_creep_tumor: bool = True) -> bool:
        return (
            state.has_any((
                item_names.SWARM_QUEEN, item_names.OVERSEER, item_names.HIVE_QUEEN,
            ), self.player)
            or (self.advanced_tactics
                and (
                    free_creep_tumor
                    or state.has(item_names.ECHIDNA_WORM, self.player)
                )
            )
        )

    def zerg_mineral_dump(self, state: CollectionState) -> bool:
        return (
            state.has_any((
                item_names.ZERGLING, item_names.PYGALISK, item_names.INFESTED_BUNKER, item_names.HIVE_QUEEN,
            ), self.player)
            or (self.advanced_tactics
                and self.spread_creep(state)
                and state.has_any((item_names.SPINE_CRAWLER, item_names.INFESTED_BUNKER), self.player)
            )
        )

    def zerg_big_monsters(self, state: CollectionState) -> bool:
        """
        Durable units with some capacity for damage
        """
        return (
            self.morph_tyrannozor(state)
            or state.has_any((item_names.ABERRATION, item_names.ULTRALISK), self.player)
            or (self.spread_creep(state, False) and state.has(item_names.INFESTED_BUNKER, self.player))
        )

    def zergling_hydra_roach_start(self, state: CollectionState) -> bool:
        """
        Created mainly for engine of destruction start, but works for other missions with no-build starts.
        """
        return state.has_any((
            item_names.ZERGLING_ADRENAL_OVERLOAD,
            item_names.HYDRALISK_FRENZY,
            item_names.ROACH_HYDRIODIC_BILE,
            item_names.ZERGLING_RAPTOR_STRAIN,
            item_names.ROACH_CORPSER_STRAIN,
        ), self.player)

    # endregion Global Zerg

    # ###################################################################################################### #
    # region Heroes ........................................................................................ #
    # ###################################################################################################### #

    def get_hero_flag(self, mission: SC2Mission) -> HeroFlag:
        return self.hero_presence.get(mission, HeroFlag.NONE)

    @series(LogicSeries.Kerrigan, SC2Race.ANY, 1)
    def basic_kerrigan(self, state: CollectionState) -> bool:
        # One active ability that can be used to defeat enemies directly
        if not state.has_any((
            item_names.KERRIGAN_LEAPING_STRIKE,
            item_names.KERRIGAN_KINETIC_BLAST,
            item_names.KERRIGAN_SPAWN_BANELINGS,
            item_names.KERRIGAN_PSIONIC_SHIFT,
            item_names.KERRIGAN_CRUSHING_GRIP,
        ), self.player):
            return False
        return self.kerrigan_levels(state, 5)

    @series(LogicSeries.Kerrigan, SC2Race.ANY, 2)
    def competent_kerrigan(self, state: CollectionState) -> bool:
        return (
            self.basic_kerrigan(state)
            and (
                state.count_from_list_unique(item_groups.kerrigan_logic_active_abilities, self.player) >= 2
                or state.has_any(item_groups.kerrigan_passives, self.player)
            )
        )

    @series(LogicSeries.Kerrigan, SC2Race.ANY, 3)
    def ultra_kerrigan(self, state: CollectionState) -> bool:
        return (
            self.basic_kerrigan(state)
            and state.count_from_list_unique(item_groups.kerrigan_logic_active_abilities, self.player) >= 2
            and state.has_any(item_groups.kerrigan_passives, self.player)
            # Note(mm): Requiring ultimates doesn't play nice with excluding OP items
        )

    @series(LogicSeries.Nova, SC2Race.ANY, 1)
    def nova_any_weapon(self, state: CollectionState) -> bool:
        # 1 item
        return state.has_any((
            item_names.NOVA_C20A_CANISTER_RIFLE,
            item_names.NOVA_HELLFIRE_SHOTGUN,
            item_names.NOVA_PLASMA_RIFLE,
            item_names.NOVA_MONOMOLECULAR_BLADE,
            item_names.NOVA_BLAZEFIRE_GUNBLADE,
        ), self.player)

    @series(LogicSeries.Nova, SC2Race.ANY, 2)
    def competent_nova(self, state: CollectionState) -> bool:
        # 2 items
        return (
            self.nova_any_weapon(state)
            and (
                self.nova_splash(state)
                or self.nova_any_suit(state)
                or self.nova_heal(state)
                or self.nova_dash(state)
            )
        )

    @series(LogicSeries.Nova, SC2Race.ANY, 3)
    def ultra_nova(self, state: CollectionState) -> bool:
        # 3 items
        return (
            self.nova_any_weapon(state)
            and self.nova_splash(state)
            and (
                self.nova_any_suit(state)
                or self.nova_heal(state)
                or self.nova_dash(state)
            )
        )

    @series(LogicSeries.Artanis, SC2Race.ANY, 1)
    def basic_artanis(self, state: CollectionState) -> bool:
        return (
            self.artanis_any_weapon_aspect(state)
            and (
                self.advanced_tactics
                or self.artanis_active_ability_count(state) >= 1
            )
        )

    @series(LogicSeries.Artanis, SC2Race.ANY, 2)
    def competent_artanis(self, state: CollectionState) -> bool:
        return (
            self.artanis_any_weapon_aspect(state)
            and self.artanis_any_defensive_upgrade(state)
            and self.artanis_active_ability_count(state) >= 1
        )

    @series(LogicSeries.Artanis, SC2Race.ANY, 3)
    def ultra_artanis(self, state: CollectionState) -> bool:
        return (
            self.artanis_any_weapon_aspect(state)
            and self.artanis_any_defensive_upgrade(state)
            and self.artanis_active_ability_count(state) >= 2
        )

    def two_kerrigan_solo_actives(self, state: CollectionState) -> bool:
        return state.count_from_list_unique(item_groups.kerrigan_solo_active_abilities, self.player) >= 2

    def two_kerrigan_actives(self, state: CollectionState) -> bool:
        return state.count_from_list_unique(item_groups.kerrigan_logic_active_abilities, self.player) >= 2

    def nova_any_nobuild_damage(self, state: CollectionState) -> bool:
        return state.has_any((
            item_names.NOVA_C20A_CANISTER_RIFLE,
            item_names.NOVA_HELLFIRE_SHOTGUN,
            item_names.NOVA_PLASMA_RIFLE,
            item_names.NOVA_MONOMOLECULAR_BLADE,
            item_names.NOVA_BLAZEFIRE_GUNBLADE,
            item_names.NOVA_PULSE_GRENADES,
            item_names.NOVA_DOMINATION,
        ), self.player)

    def nova_ranged_weapon(self, state: CollectionState) -> bool:
        return state.has_any((
            item_names.NOVA_C20A_CANISTER_RIFLE,
            item_names.NOVA_HELLFIRE_SHOTGUN,
            item_names.NOVA_PLASMA_RIFLE,
        ), self.player)

    def nova_splash(self, state: CollectionState) -> bool:
        return (
            state.has_any((
                item_names.NOVA_HELLFIRE_SHOTGUN,
                item_names.NOVA_PULSE_GRENADES,
            ), self.player)
            or (
                self.advanced_tactics
                and state.has_any((
                    item_names.NOVA_PLASMA_RIFLE,
                    item_names.NOVA_MONOMOLECULAR_BLADE,
                ), self.player)
            )
        )

    def nova_dash(self, state: CollectionState) -> bool:
        return state.has_any((item_names.NOVA_MONOMOLECULAR_BLADE, item_names.NOVA_BLINK), self.player)

    def nova_any_suit(self, state: CollectionState) -> bool:
        return state.has_any(item_groups.nova_suits, self.player)

    def nova_full_stealth(self, state: CollectionState) -> bool:
        return state.count(item_names.NOVA_PROGRESSIVE_STEALTH_SUIT_MODULE, self.player) >= 2

    def nova_heal(self, state: CollectionState) -> bool:
        return state.has_any((item_names.NOVA_ARMORED_SUIT_MODULE, item_names.NOVA_STIM_INFUSION), self.player)

    def nova_escape_assist(self, state: CollectionState) -> bool:
        return state.has_any((item_names.NOVA_BLINK, item_names.NOVA_HOLO_DECOY, item_names.NOVA_IONIC_FORCE_FIELD), self.player)

    # endregion Heroes

    # ###################################################################################################### #
    # region Global Protoss ................................................................................ #
    # ###################################################################################################### #

    @series(LogicSeries.PowerComp, SC2Race.PROTOSS, 1)
    def protoss_upgraded_unit(self, state: CollectionState, upgrade: int) -> bool:
        return (
            (
                self.wa_upgrade_count(VirtualItem.PROTOSS_GROUND_WEAPON, state) >= upgrade
                and self.wa_upgrade_count(VirtualItem.PROTOSS_GROUND_ARMOR, state) >= upgrade
                and state.has_any(self.upgradeable_protoss_ground_units, self.player)
            )
            or (
                self.wa_upgrade_count(VirtualItem.PROTOSS_AIR_WEAPON, state) >= upgrade
                and self.wa_upgrade_count(VirtualItem.PROTOSS_AIR_ARMOR, state) >= upgrade
                and state.has_any(self.upgradeable_protoss_air_units, self.player)
            )
        )

    @series(LogicSeries.PowerComp, SC2Race.PROTOSS, 2)
    def protoss_competent_comp(self, state: CollectionState, upgrade: int = 1) -> bool:
        if self.protoss_fleet(state, upgrade) and self.protoss_mineral_dump(state):
            return True
        has_ground_upgrades = (
            self.wa_upgrade_count(VirtualItem.PROTOSS_GROUND_WEAPON, state) >= upgrade
            and self.wa_upgrade_count(VirtualItem.PROTOSS_GROUND_ARMOR, state) >= upgrade
        )
        core_unit = (
            has_ground_upgrades
            and state.has_any((
                item_names.ZEALOT,
                item_names.CENTURION,
                item_names.SENTINEL,
                item_names.STALKER,
                item_names.INSTIGATOR,
                item_names.SLAYER,
                item_names.ADEPT,
            ), self.player)
        )
        support_unit: bool = (
            state.has_any((
                item_names.SENTRY,
                item_names.ENERGIZER,
                item_names.IMMORTAL,
                item_names.VANGUARD,
                item_names.COLOSSUS,
                item_names.REAVER,
            ), self.player)
            or (
                self.wa_upgrade_count(VirtualItem.PROTOSS_AIR_WEAPON, state) >= upgrade
                and self.wa_upgrade_count(VirtualItem.PROTOSS_AIR_ARMOR, state) >= upgrade
                and (
                    state.has_any((
                        item_names.VOID_RAY,
                        item_names.PHOENIX,
                        item_names.CORSAIR,
                    ), self.player)
                    or state.has_all((item_names.MIRAGE, item_names.MIRAGE_GRAVITON_BEAM), self.player)
                )
            )
            or state.has_all((
                item_names.DARK_TEMPLAR,
                item_names.DARK_TEMPLAR_LESSER_SHADOW_FURY,
                item_names.DARK_TEMPLAR_GREATER_SHADOW_FURY
            ), self.player)
            or (
                self.advanced_tactics
                and (
                    state.has_any((
                        item_names.HIGH_TEMPLAR,
                        item_names.SIGNIFIER,
                        item_names.ASCENDANT,
                        item_names.ANNIHILATOR,
                        item_names.WRATHWALKER,
                        item_names.SKIRMISHER,
                        item_names.ARBITER,
                    ), self.player)
                )
            )
        )
        if core_unit and support_unit:
            return True
        return False

    @series(LogicSeries.PowerComp, SC2Race.PROTOSS, 3)
    def protoss_ultimate_comp(self, state: CollectionState, upgrade: int = 2) -> bool:
        return (
            self.protoss_competent_comp(state, upgrade)
            and self.protoss_hybrid_counter(state, upgrade)
            and self.protoss_basic_splash(state, upgrade)
        )

    @series(LogicSeries.AntiAir, SC2Race.PROTOSS, 1)
    def protoss_any_anti_air_unit(self, state: CollectionState) -> bool:
        return (
            state.has_any((
                # Gateway
                item_names.STALKER,
                item_names.SLAYER,
                item_names.INSTIGATOR,
                item_names.DRAGOON,
                item_names.ADEPT,
                item_names.SENTRY,
                item_names.ENERGIZER,
                item_names.HIGH_TEMPLAR,
                item_names.SIGNIFIER,
                item_names.ASCENDANT,
                item_names.DARK_ARCHON,
                # Robo
                item_names.ANNIHILATOR,
                # Stargate
                item_names.PHOENIX,
                item_names.MIRAGE,
                item_names.CORSAIR,
                item_names.SCOUT,
                item_names.MISTWING,
                item_names.CALADRIUS,
                item_names.OPPRESSOR,
                item_names.ARBITER,
                item_names.VOID_RAY,
                item_names.DESTROYER,
                item_names.PULSAR,
                item_names.CARRIER,
                item_names.TRIREME,
                item_names.SKYLORD,
                item_names.TEMPEST,
                item_names.MOTHERSHIP_TALDARIM,
                # Nexus
                item_names.MOTHERSHIP_AIUR,
                item_names.MOTHERSHIP_PURIFIER,
                # Buildings
                item_names.NEXUS_OVERCHARGE,
                item_names.PHOTON_CANNON,
                item_names.KHAYDARIN_MONOLITH,
            ), self.player)
            or state.has_all((item_names.SUPPLICANT, item_names.SUPPLICANT_ZENITH_PITCH), self.player)
            or state.has_all((item_names.WARP_PRISM, item_names.WARP_PRISM_PHASE_BLASTER), self.player)
            or state.has_all((item_names.WRATHWALKER, item_names.WRATHWALKER_AERIAL_TRACKING), self.player)
            or state.has_all((item_names.DISRUPTOR, item_names.DISRUPTOR_PERFECTED_POWER), self.player)
            or state.has_all((item_names.IMMORTAL, item_names.IMMORTAL_ADVANCED_TARGETING), self.player)
            or state.has_all((item_names.SKIRMISHER, item_names.SKIRMISHER_PEER_CONTEMPT), self.player)
            or (
                state.has(item_names.DARK_TEMPLAR, self.player)
                and state.has_any((item_names.DARK_TEMPLAR_DARK_ARCHON_MELD, item_names.DARK_TEMPLAR_ARCHON_MERGE), self.player)
            )
        )

    @series(LogicSeries.AntiAir, SC2Race.PROTOSS, 2)
    def protoss_basic_anti_air(self, state: CollectionState) -> bool:
        return (
            self.protoss_competent_anti_air(state)
            or state.has_any((
                # Competent
                item_names.STALKER,
                item_names.SLAYER,
                item_names.INSTIGATOR,
                item_names.DRAGOON,
                item_names.ADEPT,
                item_names.PHOENIX,
                item_names.SCOUT,
                item_names.MISTWING,
                item_names.VOID_RAY,
                item_names.DESTROYER,
                item_names.TEMPEST,
                item_names.SKYLORD,
                item_names.CARRIER,
                # Basic
                item_names.TRIREME,
                item_names.OPPRESSOR,
                item_names.MOTHERSHIP_TALDARIM,
                item_names.MOTHERSHIP_PURIFIER,
            ), self.player)
            or state.has_all((item_names.WRATHWALKER, item_names.WRATHWALKER_AERIAL_TRACKING), self.player)
            or state.has_all((item_names.SKIRMISHER, item_names.SKIRMISHER_PEER_CONTEMPT), self.player)
            or state.has_all((item_names.WARP_PRISM, item_names.WARP_PRISM_PHASE_BLASTER), self.player)
            or (state.has(item_names.MIRAGE, self.player)
                and (self.advanced_tactics or state.has(item_names.MIRAGE_GRAVITON_BEAM, self.player))
            )
            or (self.advanced_tactics
                and state.has_any((
                    # Competent
                    item_names.CALADRIUS,
                    item_names.CORSAIR,
                    # Basic
                    item_names.HIGH_TEMPLAR,
                    item_names.SIGNIFIER,
                    item_names.SENTRY,
                    item_names.ENERGIZER,
                    item_names.MOTHERSHIP_AIUR,
                ), self.player)
            )
            or self.protoss_can_merge_archon(state)
            or self.protoss_can_merge_dark_archon(state)
        )

    @series(LogicSeries.AntiAir, SC2Race.PROTOSS, 3)
    def protoss_competent_anti_air(self, state: CollectionState) -> bool:
        return (
            state.has_any((
                item_names.STALKER,
                item_names.SLAYER,
                item_names.INSTIGATOR,
                item_names.DRAGOON,
                item_names.ADEPT,
                item_names.PHOENIX,
                item_names.SCOUT,
                item_names.MISTWING,
                item_names.VOID_RAY,
                item_names.DESTROYER,
                item_names.TEMPEST,
                item_names.SKYLORD,
                item_names.CARRIER,
            ), self.player)
            or state.has_all((item_names.WRATHWALKER, item_names.WRATHWALKER_AERIAL_TRACKING), self.player)
            or state.has_all((item_names.SKIRMISHER, item_names.SKIRMISHER_PEER_CONTEMPT), self.player)
            or (self.advanced_tactics
                and state.has_any((
                    item_names.CALADRIUS,
                    item_names.CORSAIR,
                    item_names.MIRAGE,
                ), self.player)
            )
        )

    @series(LogicSeries.Detection, SC2Race.PROTOSS, 0)
    def protoss_anti_cloak_self_splash(self, state: CollectionState) -> bool:
        return (
            self.protoss_anti_cloak_tech(state)
            or self.protoss_can_merge_archon(state)
            or state.has_any((
                item_names.COLOSSUS,
                item_names.VANGUARD,
            ), self.player)
        )

    @series(LogicSeries.Detection, SC2Race.PROTOSS, 1)
    def protoss_anti_cloak_tech(self, state: CollectionState) -> bool:
        return (
            self.protoss_basic_detection(state)
            or state.has_any((
                item_names.HIGH_TEMPLAR,  # Storm
                item_names.SIGNIFIER,  # Storm
                item_names.ASCENDANT,  # Psi Orb
                item_names.DISRUPTOR,
            ), self.player)
        )

    @series(LogicSeries.Detection, SC2Race.PROTOSS, 2)
    def protoss_basic_detection(self, state: CollectionState) -> bool:
        return (
            state.has_any(item_groups.protoss_detection, self.player)
            or self._protoss_mobile_multi_item_detection(state)
        )

    @series(LogicSeries.Detection, SC2Race.PROTOSS, 3)
    def protoss_mobile_detector(self, state: CollectionState) -> bool:
        return (
            state.has_any(item_groups.protoss_mobile_detection, self.player)
            or self._protoss_mobile_multi_item_detection(state)
        )

    def _protoss_mobile_multi_item_detection(self, state: CollectionState) -> bool:
        return state.has_all((item_names.VANGUARD, item_names.VANGUARD_FLARE), self.player)

    @series(LogicSeries.MacroPower, SC2Race.PROTOSS, 0)
    def protoss_macro_rating(self, state: CollectionState) -> int:
        """
        Rating out of 19. Recommend requiring no more than 12.
        Note 10 cannot be reached with vanilla items only.
        """
        # Max 3 (war council)
        power_score = self.protoss_base_macro_rating
        # Passive Score (Economic upgrades and global army upgrades)
        # Max 16
        protoss_passive_ratings = (
            (item_names.ORBITAL_ASSIMILATORS, 4,),
            (item_names.QUATRO, 3,),
            (item_names.AMPLIFIED_ASSIMILATORS, 3,),
            (item_names.PROBE_WARPIN, 2,),
            (item_names.ELDER_PROBES, 2,),
            (item_names.MATRIX_OVERLOAD, 2,),
        )
        for item, rating in protoss_passive_ratings:
            if state.has(item, self.player):
                power_score += rating
        return power_score

    @series(LogicSeries.MacroPower, SC2Race.PROTOSS, 1)
    def protoss_soa_active_power_rating(self, state: CollectionState) -> int:
        return self.protoss_macro_rating(state) + self.soa_power_rating(state)

    @series(LogicSeries.MacroPower, SC2Race.PROTOSS, 2)
    def protoss_soa_passive_power_rating(self, state: CollectionState) -> int:
        return self.protoss_macro_rating(state) + self.soa_passive_power_rating(state)

    @series(LogicSeries.MacroPower, SC2Race.PROTOSS, 3)
    def protoss_soa_power_rating(self, state: CollectionState) -> int:
        return (
            self.protoss_macro_rating(state)
            + self.soa_power_rating(state)
            + self.soa_passive_power_rating(state)
        )

    @series(LogicSeries.DefenseRating, SC2Race.PROTOSS, 0)
    def protoss_defense_rating(self, state: CollectionState) -> int:
        """
        Basic-logic only defensive tools. Siegeable units and buildings only.
        (Plus elder probes and building buffs because Protoss doesn't have much static D).
        Individual options rate 1~3 points depending on strength and applicability.
        Max possible rating around 20. Reasonable requirement limit around 10.
        """
        rating = 0
        has_attacking_building = False
        for item in (
            item_names.PHOTON_CANNON,
            item_names.KHAYDARIN_MONOLITH,
            item_names.NEXUS_OVERCHARGE,
        ):
            if state.has(item, self.player):
                rating += 3
                has_attacking_building = True
        if state.has(item_names.SHIELD_BATTERY, self.player):
            rating += 3
        for item in (
            item_names.MATRIX_OVERLOAD,
        ):
            if state.has(item, self.player):
                rating += 2
        if state.has_all((item_names.WARP_PRISM, item_names.WARP_PRISM_PHASE_BLASTER), self.player):
            rating += 2
        if has_attacking_building:
            for item in (
                item_names.ELDER_PROBES,
                item_names.KHALAI_INGENUITY,
                item_names.OPTIMIZED_ORDNANCE,
                item_names.ENHANCED_TARGETING,
                item_names.PROTOSS_BUILDING_SHIELDS,
            ):
                rating += 1

        return rating

    def protoss_mineral_dump(self, state: CollectionState) -> bool:
        return (
            state.has_any((item_names.ZEALOT, item_names.SENTINEL, item_names.PHOTON_CANNON), self.player)
            or state.has_all((item_names.CENTURION, item_names.CENTURION_RESOURCE_EFFICIENCY), self.player)
            or (self.advanced_tactics
                and state.has_any((item_names.SUPPLICANT, item_names.SHIELD_BATTERY), self.player)
            )
        )

    def protoss_early_unit(self, state: CollectionState) -> bool:
        return (
            state.has_any((
                item_names.ZEALOT,
                item_names.CENTURION,
                item_names.SENTINEL,
                item_names.STALKER,
                item_names.SLAYER,
                item_names.INSTIGATOR,
                item_names.DRAGOON,
                item_names.ADEPT,
                item_names.STALWART,
            ), self.player)
        )

    def protoss_basic_air_comp(self, state: CollectionState) -> bool:
        """Basic logic-only noob-friendly air comp for roaming around the map"""
        return self.protoss_fleet(state, upgrade=1)

    def protoss_basic_transport(self, state: CollectionState) -> bool:
        return state.has_any((
            item_names.WARP_PRISM,
            item_names.ARBITER,
        ), self.player)

    def protoss_basic_transport_or_air_comp(self, state: CollectionState) -> bool:
        return self.protoss_basic_transport(state) or self.protoss_basic_air_comp(state)

    def protoss_has_blink(self, state: CollectionState) -> bool:
        return (
            state.has_any((item_names.STALKER, item_names.INSTIGATOR), self.player)
            or state.has_all((item_names.SLAYER, item_names.SLAYER_PHASE_BLINK), self.player)
            or (
                state.has(item_names.DARK_TEMPLAR_BLINK, self.player)
                and state.has(item_names.DARK_TEMPLAR, self.player)
            )
        )

    def protoss_fleet(self, state: CollectionState, upgrade: int = 2) -> bool:
        return (
            self.wa_upgrade_count(VirtualItem.PROTOSS_AIR_ARMOR, state) >= upgrade
            and self.wa_upgrade_count(VirtualItem.PROTOSS_AIR_WEAPON, state) >= upgrade
            and (
                (
                    state.has_any((
                        item_names.CARRIER,
                        item_names.SKYLORD,
                        item_names.TEMPEST,
                        item_names.VOID_RAY,
                        item_names.DESTROYER,
                    ), self.player)
                )
                or (
                    state.has(item_names.TRIREME, self.player)
                    and (
                        state.has_any((item_names.PHOENIX, item_names.MIRAGE, item_names.CORSAIR), self.player)
                        or state.has_all((item_names.SKIRMISHER, item_names.SKIRMISHER_PEER_CONTEMPT), self.player)
                        or state.has_all((
                            item_names.SCOUT,
                            item_names.SCOUT_RESOURCE_EFFICIENCY,
                            item_names.SCOUT_ADVANCED_PHOTON_BLASTERS,
                        ), self.player)
                        or (self.advanced_tactics
                            and state.has_any((item_names.SCOUT, item_names.MISTWING, item_names.OPPRESSOR), self.player)
                        )
                    )
                )
            )
        )

    def protoss_hybrid_counter(self, state: CollectionState, upgrade: int = 0) -> bool:
        """
        Ground Hybrids
        """
        has_air_upgrades = (
            self.wa_upgrade_count(VirtualItem.PROTOSS_AIR_ARMOR, state) >= upgrade
            and self.wa_upgrade_count(VirtualItem.PROTOSS_AIR_WEAPON, state) >= upgrade
        )
        air_comp = (
            has_air_upgrades
            and (
                state.has_any((
                    item_names.TEMPEST,
                    item_names.CARRIER,
                    item_names.TRIREME,
                    item_names.VOID_RAY,
                ), self.player)
                or (
                    self.advanced_tactics
                    and state.has_all((
                        item_names.OPPRESSOR,
                        item_names.OPPRESSOR_VULCAN_BLASTER
                    ), self.player)
                    and has_air_upgrades
                )
            )
        )
        if air_comp:
            return True
        has_ground_upgrades = (
            self.wa_upgrade_count(VirtualItem.PROTOSS_GROUND_ARMOR, state) >= upgrade
            and self.wa_upgrade_count(VirtualItem.PROTOSS_GROUND_WEAPON, state) >= upgrade
        )
        if not has_ground_upgrades:
            return False
        return (
            state.has_any((
                item_names.ANNIHILATOR,
                item_names.ASCENDANT,
                item_names.WRATHWALKER,
            ), self.player)
            or state.has_all((item_names.VANGUARD, item_names.VANGUARD_FUSION_MORTARS), self.player)
            or (
                (state.has(item_names.IMMORTAL, self.player) or self.advanced_tactics)
                and (
                    state.has_any((
                        item_names.STALKER,
                        item_names.DRAGOON,
                        item_names.INSTIGATOR,
                        item_names.SLAYER,
                    ), self.player)
                    or state.has_all((item_names.ADEPT, item_names.ADEPT_DISRUPTIVE_TRANSFER), self.player)
                )
            )
        )

    def protoss_basic_splash(self, state: CollectionState, upgrade: int = 0) -> bool:
        has_air_upgrades = (
            self.wa_upgrade_count(VirtualItem.PROTOSS_AIR_ARMOR, state) >= upgrade
            and self.wa_upgrade_count(VirtualItem.PROTOSS_AIR_WEAPON, state) >= upgrade
        )
        has_ground_upgrades = (
            self.wa_upgrade_count(VirtualItem.PROTOSS_GROUND_ARMOR, state) >= upgrade
            and self.wa_upgrade_count(VirtualItem.PROTOSS_GROUND_WEAPON, state) >= upgrade
        )
        air_comp = (
            has_air_upgrades
            and (
                state.has_any((
                    item_names.DAWNBRINGER,
                ), self.player)
                or (
                    state.has(item_names.DESTROYER, self.player)
                    and (
                        state.has_any((
                            item_names.DESTROYER_REFORGED_BLOODSHARD_CORE,
                            item_names.DESTROYER_RESOURCE_EFFICIENCY,
                        ), self.player)
                    )
                )
            )
        )
        if air_comp:
            return True
        if not has_ground_upgrades:
            return False
        return (
            state.has_any((
                item_names.COLOSSUS,
                item_names.VANGUARD,
                item_names.HIGH_TEMPLAR,
                item_names.SIGNIFIER,
                item_names.REAVER,
                item_names.ASCENDANT,
            ), self.player)
            or state.has_all((item_names.ZEALOT, item_names.ZEALOT_WHIRLWIND), self.player)
            or (
                state.has_all((
                    item_names.DARK_TEMPLAR,
                    item_names.DARK_TEMPLAR_LESSER_SHADOW_FURY,
                    item_names.DARK_TEMPLAR_GREATER_SHADOW_FURY,
                ), self.player)
            )
        )

    def protoss_can_merge_archon(self, state: CollectionState) -> bool:
        return (
            state.has_any({item_names.HIGH_TEMPLAR, item_names.SIGNIFIER}, self.player)
            or state.has_all({item_names.ASCENDANT, item_names.ASCENDANT_ARCHON_MERGE}, self.player)
            or state.has_all({item_names.DARK_TEMPLAR, item_names.DARK_TEMPLAR_ARCHON_MERGE}, self.player)
        )

    def protoss_can_merge_dark_archon(self, state: CollectionState) -> bool:
        return (
            state.has(item_names.DARK_ARCHON, self.player)
            or state.has_all((
                item_names.DARK_TEMPLAR,
                item_names.DARK_TEMPLAR_DARK_ARCHON_MELD
            ), self.player)
        )

    def protoss_heal(self, state: CollectionState) -> bool:
        return (
            state.has_any((
                item_names.SENTRY,
                item_names.SHIELD_BATTERY,
                item_names.RECONSTRUCTION_BEAM,
            ), self.player)
            or state.has_all((
                item_names.CARRIER,
                item_names.CARRIER_REPAIR_DRONES,
            ), self.player)
        )

    def zealot_sentry_slayer_start(self, state: CollectionState) -> bool:
        """
        Created mainly for engine of destruction start, but works for other missions with no-build starts.
        """
        return state.has_any((
            item_names.ZEALOT_WHIRLWIND,
            item_names.SENTRY_DOUBLE_SHIELD_RECHARGE,
            item_names.SLAYER_PHASE_BLINK,
            item_names.STALKER_DISINTEGRATING_PARTICLES,
            item_names.STALKER_PARTICLE_REFLECTION,
        ), self.player)

    def artanis_aspect_damage_boost(self, state: CollectionState) -> bool:
        return state.has_any((
            item_names.ARTANIS_EXTERMINATE,
            item_names.ARTANIS_BLADE_WALTZ,
            item_names.ARTANIS_SHADOW_SLICE,
            item_names.ARTANIS_CLEANSING_SMITE,
            item_names.ARTANIS_TASSADARS_TEACHINGS,  # make sure to pair with active ability in logic
            item_names.ARTANIS_RASZAGALS_RHYTHM,  # make sure to pair with active ability in logic
            item_names.ARTANIS_CLOLARIONS_CONFIDENCE,
            item_names.ARTANIS_MALASHS_MALEVOLENCE,
        ), self.player)

    def artanis_any_weapon_aspect(self, state: CollectionState) -> bool:
        return state.has_any(
            item_groups.artanis_weapon_aspect_active + item_groups.artanis_weapon_aspect_passive,
            self.player,
        )

    def artanis_active_ability_count(self, state: CollectionState) -> int:
        return state.count_from_list_unique(
            item_groups.artanis_active_abilities + item_groups.artanis_weapon_aspect_active,
            self.player,
        )

    def artanis_any_damage_item(self, state: CollectionState) -> bool:
        return (
            state.has_any((
                item_names.ARTANIS_VOLTAIC_SHOCK,
                item_names.ARTANIS_LIGHTNING_DASH,
            ), self.player)
            or (self.advanced_tactics and state.has(item_names.ARTANIS_TEMPERED_IN_TWILIGHT, self.player))
            or self.artanis_aspect_damage_boost(state)
        )

    def artanis_any_defensive_upgrade(self, state: CollectionState) -> bool:
        return (
            state.has_any((
                item_names.ARTANIS_VALOR_OF_THE_FIRSTBORN,
                item_names.ARTANIS_FORCE_OF_WILL,
                item_names.ARTANIS_SHIELD_OVERLOAD,
            ), self.player)
            or (
                self.advanced_tactics
                and state.has_any((
                    item_names.ARTANIS_RESURGENCE,  # need to actively use revive to get value out of this
                ), self.player)
            )
        )

    # endregion Global Protoss

    # ###################################################################################################### #
    # region WoL Missions .................................................................................. #
    # ###################################################################################################### #

    def zerg_outbreak_requirement(self, state: CollectionState) -> bool:
        """
        Outbreak mission requirement.
        Made to exclude melee-based comps like Zergling, Aberration, or Pygalisk
        """
        return (
            (
                state.has_any((
                    item_names.SWARM_QUEEN,
                    item_names.HIVE_QUEEN,
                    item_names.HYDRALISK,
                    item_names.ROACH,
                    item_names.MUTALISK,
                    item_names.INFESTED_BANSHEE,
                    item_names.INFESTED_BUNKER,
                ), self.player)
                or self.morph_lurker(state)
                or self.morph_brood_lord(state)
                or (
                    self.advanced_tactics
                    and (
                        self.morph_impaler(state)
                        or self.morph_igniter(state)
                        or state.has_any((item_names.INFESTED_DIAMONDBACK, item_names.INFESTED_SIEGE_TANK), self.player)
                    )
                )
            )
        )

    def protoss_outbreak_requirement(self, state: CollectionState) -> bool:
        """
        Outbreak mission requirement
        Something other than Zealot-based comp is required.
        """
        return (
            (
                state.has_any((
                    item_names.STALKER,
                    item_names.SLAYER,
                    item_names.INSTIGATOR,
                    item_names.DRAGOON,
                    item_names.ADEPT,
                    item_names.COLOSSUS,
                    item_names.VANGUARD,
                    item_names.SKIRMISHER,
                    item_names.OPPRESSOR,
                    item_names.CARRIER,
                    item_names.SKYLORD,
                    item_names.TRIREME,
                    item_names.DAWNBRINGER,
                    item_names.DARK_TEMPLAR,
                    item_names.BLOOD_HUNTER,
                ), self.player)
                or state.has_all((item_names.AVENGER, item_names.AVENGER_KRYHAS_CLOAK), self.player)
                or (
                    self.advanced_tactics
                    and (
                        state.has_any((item_names.VOID_RAY, item_names.DESTROYER), self.player)
                        or self.protoss_can_merge_archon(state)
                    )
                )
            )
            and (
                self.advanced_tactics
                or self.protoss_basic_splash(state)
            )
        )

    def zerg_havens_fall_gas_pickups(self, state: CollectionState) -> bool:
        return (
            state.has_any((
                item_names.OVERLORD_VENTRAL_SACS,
                item_names.YGGDRASIL,
            ), self.player)
            or state.has_all((
                item_names.INFESTED_BANSHEE,
                item_names.INFESTED_BANSHEE_RAPID_HIBERNATION
            ), self.player)
        )

    def protoss_havens_fall_gas_pickups(self, state: CollectionState) -> bool:
        return (
            self.protoss_basic_transport(state)
            or state.has_all((item_names.MISTWING, item_names.MISTWING_PILOT), self.player)
            or state.has_all((item_names.ORACLE, item_names.ORACLE_SURFACE_STABILIZER), self.player)
        )

    def terran_great_train_robbery_train_stopper(self, state: CollectionState) -> bool:
        """
        Ability to deal with trains (moving target with a lot of HP)
        """
        return (
            state.has_any((
                item_names.SIEGE_TANK,
                item_names.DIAMONDBACK,
                item_names.MARAUDER,
                item_names.CYCLONE,
                item_names.BANSHEE,
            ), self.player)
            or (
                self.advanced_tactics
                and (
                    state.has_all((item_names.REAPER, item_names.REAPER_G4_CLUSTERBOMB), self.player)
                    or state.has_all((item_names.SPECTRE, item_names.SPECTRE_PSIONIC_LASH), self.player)
                    or state.has_any((item_names.VULTURE, item_names.LIBERATOR), self.player)
                )
            )
        )

    def zerg_great_train_robbery_train_stopper(self, state: CollectionState) -> bool:
        """
        Ability to deal with trains (moving target with a lot of HP)
        """
        return (
            state.has_any((
                item_names.ABERRATION,
                item_names.INFESTED_DIAMONDBACK,
                item_names.INFESTED_BANSHEE,
            ), self.player)
            or state.has_all((item_names.MUTALISK, item_names.MUTALISK_SUNDERING_GLAIVE), self.player)
            or state.has_all((item_names.HYDRALISK, item_names.HYDRALISK_MUSCULAR_AUGMENTS), self.player)
            # Note: Zerglings were tested by Snarky, and it was found they'd need >= 3 upgrades to be viable,
            # so they are not included in this logic.
            # Raptor + 2 of (Shredding, Adrenal, +2 attack upgrade)
            or self.zerg_infested_tank_with_ammo(state)
            or (self.advanced_tactics and (self.morph_tyrannozor(state)))
        )

    def protoss_great_train_robbery_train_stopper(self, state: CollectionState) -> bool:
        """
        Ability to deal with trains (moving target with a lot of HP)
        """
        return (
            state.has_any((
                item_names.ANNIHILATOR,
                item_names.IMMORTAL,
                item_names.STALKER,
                item_names.ADEPT,  # Tested by Snarky, "An easy 1-item solve"
                item_names.WRATHWALKER,
                item_names.VOID_RAY,
                item_names.DESTROYER,
            ), self.player)
            or state.has_all((item_names.SLAYER, item_names.SLAYER_PHASE_BLINK), self.player)
            or state.has_all((item_names.REAVER, item_names.REAVER_KHALAI_REPLICATORS), self.player)
            or state.has_all((item_names.VANGUARD, item_names.VANGUARD_FUSION_MORTARS), self.player)
            or (
                state.has(item_names.INSTIGATOR, self.player)
                and state.has_any((item_names.INSTIGATOR_BLINK_OVERDRIVE, item_names.INSTIGATOR_MODERNIZED_SERVOS), self.player)
            )
            or (state.has_all((item_names.OPPRESSOR, item_names.SCOUT_GRAVITIC_THRUSTERS, item_names.SCOUT_ADVANCED_PHOTON_BLASTERS), self.player))
            or state.has_all((item_names.ORACLE, item_names.ORACLE_TEMPORAL_ACCELERATION_BEAM), self.player)
            or (
                self.advanced_tactics
                and (
                    state.has(item_names.TEMPEST, self.player)
                    or state.has_all((item_names.VANGUARD, item_names.VANGUARD_RAPIDFIRE_CANNON), self.player)
                    or state.has_all((item_names.OPPRESSOR, item_names.SCOUT_GRAVITIC_THRUSTERS, item_names.OPPRESSOR_VULCAN_BLASTER), self.player)
                    or state.has_all((item_names.ASCENDANT, item_names.ASCENDANT_POWER_OVERWHELMING, item_names.SUPPLICANT), self.player)
                    or state.has_all((
                        item_names.DARK_TEMPLAR,
                        item_names.DARK_TEMPLAR_LESSER_SHADOW_FURY,
                        item_names.DARK_TEMPLAR_GREATER_SHADOW_FURY,
                    ), self.player)
                    or self.protoss_has_blink(state)
                )
            )
        )

    def terran_moebius_factor_can_rescue(self, state: CollectionState) -> bool:
        """
        Rescuing in The Moebius Factor
        """
        return state.has_any((
            item_names.MEDIVAC, item_names.HERCULES, item_names.RAVEN, item_names.VIKING
        ), self.player)

    def zerg_moebius_factor_can_rescue(self, state: CollectionState) -> bool:
        return state.has_any((
            item_names.YGGDRASIL,
            item_names.OVERLORD_VENTRAL_SACS,
            item_names.NYDUS_WORM,
            item_names.BULLFROG,
        ), self.player)

    def protoss_moebius_factor_can_rescue(self, state: CollectionState) -> bool:
        return state.has_any((
            item_names.WARP_PRISM, item_names.COLOSSUS, item_names.WRATHWALKER,
        ), self.player)

    def zerg_supernova_basic_requirement(self, state: CollectionState) -> bool:
        return state.has(item_names.YGGDRASIL, self.player)

    def protoss_supernova_basic_requirement(self, state: CollectionState) -> bool:
        return state.has(item_names.PROGRESSIVE_WARP_RELOCATE, self.player, 2)

    def protoss_supernova_advanced_requirement(self, state: CollectionState) -> bool:
        return state.has(item_names.PROGRESSIVE_WARP_RELOCATE, self.player)

    def terran_maw_requirement(self, state: CollectionState) -> bool:
        """
        Ability to deal with large areas with environment damage
        """
        return (
            state.has(item_names.BATTLECRUISER, self.player)
            and (
                self.wa_upgrade_count(VirtualItem.TERRAN_SHIP_WEAPON, state) >= 2
                or state.has(item_names.BATTLECRUISER_ATX_LASER_BATTERY, self.player)
            )
        ) or (
            self.terran_air(state)
            and (
                # Avoid dropping Troopers or units that do barely damage
                state.has_any((
                    item_names.GOLIATH,
                    item_names.THOR,
                    item_names.WARHOUND,
                    item_names.VIKING,
                    item_names.BANSHEE,
                    item_names.WRAITH,
                    item_names.BATTLECRUISER,
                ), self.player)
                or state.has_all((item_names.LIBERATOR, item_names.LIBERATOR_RAID_ARTILLERY), self.player)
                or state.has_all((item_names.VALKYRIE, item_names.VALKYRIE_FLECHETTE_MISSILES), self.player)
                or (state.has(item_names.MARAUDER, self.player) and self.terran_bio_heal(state))
            )
            and (
                # Can deal damage to air units inside rip fields
                state.has_any((item_names.GOLIATH, item_names.CYCLONE, item_names.VIKING), self.player)
                or (
                    state.has_any((item_names.WRAITH, item_names.VALKYRIE, item_names.BATTLECRUISER), self.player)
                    and self.wa_upgrade_count(VirtualItem.TERRAN_SHIP_WEAPON, state) >= 2
                )
                or state.has_all((item_names.THOR, item_names.THOR_PROGRESSIVE_HIGH_IMPACT_PAYLOAD), self.player)
            )
            and self.terran_sustainable_mech_heal(state)
        )

    def zerg_maw_requirement(self, state: CollectionState) -> bool:
        """
        Ability to cross defended gaps, deal with skytoss, and avoid costly losses.
        """
        usable_muta = (
            state.has_all((item_names.MUTALISK, item_names.MUTALISK_RAPID_REGENERATION), self.player)
            and state.count_from_list_unique((
                item_names.MUTALISK_SEVERING_GLAIVE,
                item_names.MUTALISK_SUNDERING_GLAIVE,
                item_names.MUTALISK_VICIOUS_GLAIVE,
            ), self.player) >= 2
        )
        return (
            # Heal
            (
                state.has(item_names.SWARM_QUEEN, self.player)
                or (self.advanced_tactics
                    and (
                        (
                            self.morph_tyrannozor(state)
                            and state.has(item_names.TYRANNOZOR_HEALING_ADAPTATION, self.player)
                        )
                        or usable_muta
                    )
                )
            )
            # Cross the gap
            and (
                state.has_any((item_names.NYDUS_WORM, item_names.OVERLORD_VENTRAL_SACS), self.player)
                or (self.advanced_tactics and state.has(item_names.YGGDRASIL, self.player))
            )
            # Air to ground
            and (self.morph_brood_lord(state) or self.morph_guardian(state) or usable_muta)
            # Ground to air
            and (
                state.has(item_names.INFESTOR, self.player)
                or self.morph_tyrannozor(state)
                or state.has_all((
                    item_names.SWARM_HOST,
                    item_names.SWARM_HOST_RESOURCE_EFFICIENCY,
                    item_names.SWARM_HOST_PRESSURIZED_GLANDS
                ), self.player)
                or state.has_all((item_names.HYDRALISK, item_names.HYDRALISK_RESOURCE_EFFICIENCY), self.player)
                or state.has_all((
                    item_names.INFESTED_DIAMONDBACK,
                    item_names.INFESTED_DIAMONDBACK_PROGRESSIVE_FUNGAL_SNARE,
                ), self.player)
            )
            # Survives rip-field
            and (
                state.has_any((item_names.ABERRATION, item_names.ROACH, item_names.ULTRALISK), self.player)
                or self.morph_tyrannozor(state)
                or (self.advanced_tactics and usable_muta)
            )
            # Air-to-air
            and (state.has_any((
                item_names.MUTALISK,
                item_names.CORRUPTOR,
                item_names.INFESTED_LIBERATOR,
                item_names.BROOD_QUEEN,
            ), self.player))
        )

    def protoss_maw_advanced_requirement(self, state: CollectionState) -> bool:
        """
        Ability to cross defended gaps
        """
        return (
            state.has_any((item_names.WARP_PRISM, item_names.ARBITER), self.player)
            or state.has_all((item_names.MISTWING, item_names.MISTWING_PILOT), self.player)
        )

    def protoss_maw_basic_requirement(self, state: CollectionState) -> bool:
        return (
            self.protoss_basic_air_comp(state)
            and state.has_any((item_names.WARP_PRISM, item_names.ARBITER), self.player)
        )

    def terran_engine_of_destruction_requirement(self, state: CollectionState) -> bool:
        power_rating = self.terran_macro_rating(state)
        if power_rating < 3 or not self.marine_medic_upgrade(state):
            return False
        if power_rating >= 7 and self.terran_competent_comp(state):
            return True
        else:
            return (
                state.has_any((item_names.WRAITH, item_names.BATTLECRUISER), self.player)
                or (self.terran_air_anti_air(state)
                    and state.has_any((item_names.BANSHEE, item_names.LIBERATOR), self.player)
                )
            )

    def zerg_engine_of_destruction_requirement(self, state: CollectionState) -> bool:
        return (
            self.zergling_hydra_roach_start(state)
            and self.zerg_repair_odin(state)
        )

    def protoss_engine_of_destruction_requirement(self, state: CollectionState) -> bool:
        return (
            self.zealot_sentry_slayer_start(state)
            and self.protoss_repair_odin(state)
        )

    def zerg_repair_odin(self, state: CollectionState) -> bool:
        return (
            self.zerg_has_infested_scv(state)
            or state.has_all({item_names.SWARM_QUEEN_BIO_MECHANICAL_TRANSFUSION, item_names.SWARM_QUEEN}, self.player)
            or (self.advanced_tactics and state.has(item_names.SWARM_QUEEN, self.player))
        )

    def protoss_repair_odin(self, state: CollectionState) -> bool:
        return (
            state.has(item_names.SENTRY, self.player)
            or state.has_all((item_names.CARRIER, item_names.CARRIER_REPAIR_DRONES), self.player)
            or (
                self.spear_of_adun_passive_presence in (
                    SpearOfAdunPassiveAbilityPresence.option_protoss,
                    SpearOfAdunPassiveAbilityPresence.option_everywhere,
                )
                and state.has(item_names.RECONSTRUCTION_BEAM, self.player)
            )
            or (self.advanced_tactics
                and state.has_all((item_names.SHIELD_BATTERY, item_names.KHALAI_INGENUITY), self.player)
            )
        )

    def terran_all_in_requirement(self, state: CollectionState) -> bool:
        """
        All-in
        """
        beats_kerrigan = (
            state.has_any((item_names.MARINE, item_names.DOMINION_TROOPER, item_names.BANSHEE), self.player)
            or state.has_all((item_names.REAPER, item_names.REAPER_RESOURCE_EFFICIENCY), self.player)
            or (self.all_in_map == AllInMap.option_air and state.has_all((item_names.VALKYRIE, item_names.VALKYRIE_FLECHETTE_MISSILES), self.player))
            or (self.advanced_tactics and state.has_all((item_names.GHOST, item_names.GHOST_EMP_ROUNDS), self.player))
        )
        if not beats_kerrigan:
            return False
        if self.all_in_map == AllInMap.option_ground:
            # Beats worms
            return (
                state.has_any((item_names.BATTLECRUISER, item_names.BANSHEE,), self.player)
                or state.has_all((item_names.VALKYRIE, item_names.VALKYRIE_FLECHETTE_MISSILES,), self.player)
                or state.has_all((item_names.RAVEN, item_names.RAVEN_HUNTER_SEEKER_WEAPON,), self.player)
                or state.has_all((
                    item_names.WRAITH,
                    item_names.WRAITH_RESOURCE_EFFICIENCY,
                    item_names.WRAITH_ADVANCED_LASER_TECHNOLOGY,
                ), self.player)
                or state.has_all((
                    item_names.PREDATOR,
                    item_names.PREDATOR_RESOURCE_EFFICIENCY,
                    item_names.PREDATOR_ADAPTIVE_DEFENSES,
                ), self.player)
            )
        else:
            # Air
            return (
                self.terran_competent_anti_air(state)
                and state.has_any((item_names.VIKING, item_names.BATTLECRUISER, item_names.VALKYRIE), self.player)
                and state.has_any((item_names.HIVE_MIND_EMULATOR, item_names.PSI_DISRUPTER, item_names.MISSILE_TURRET), self.player)
            )

    def zerg_all_in_requirement(self, state: CollectionState) -> bool:
        """
        All-in (Zerg)
        """
        beats_kerrigan = (
            state.has_any((
                item_names.INFESTED_MARINE,
                item_names.INFESTED_BANSHEE,
                item_names.INFESTED_BUNKER,
            ), self.player)
            or state.has_all((item_names.SWARM_HOST, item_names.SWARM_HOST_RESOURCE_EFFICIENCY), self.player)
            or self.morph_brood_lord(state)
        )
        if not beats_kerrigan:
            return False
        if self.all_in_map == AllInMap.option_ground:
            # Beats Worms
            return (
                state.has_any((item_names.MUTALISK, item_names.INFESTED_BANSHEE), self.player)
                or self.morph_brood_lord(state)
                or self.morph_guardian(state)
            )
        else:
            # Air
            return (
                self.zerg_competent_anti_air(state)
                # Beats leviathan
                and state.has_any((item_names.MUTALISK, item_names.CORRUPTOR), self.player)
                and state.has_any((item_names.SPORE_CRAWLER, item_names.INFESTED_MISSILE_TURRET), self.player)
            )

    def protoss_all_in_requirement(self, state: CollectionState) -> bool:
        """
        All-in (Protoss)
        """
        beats_kerrigan = (
            # cheap units with multiple small attacks, or anything with Feedback
            state.has_any((item_names.ZEALOT, item_names.SENTINEL, item_names.SKIRMISHER, item_names.HIGH_TEMPLAR), self.player)
            or state.has_all((item_names.CENTURION, item_names.CENTURION_RESOURCE_EFFICIENCY), self.player)
            or state.has_all((item_names.SIGNIFIER, item_names.SIGNIFIER_FEEDBACK), self.player)
            or (self.protoss_can_merge_archon(state) and state.has(item_names.ARCHON_HIGH_ARCHON, self.player))
            or (self.protoss_can_merge_dark_archon(state) and state.has(item_names.DARK_ARCHON_FEEDBACK, self.player))
        )
        if not beats_kerrigan:
            return False
        if self.all_in_map == AllInMap.option_ground:
            # Beats Worms
            return (
                state.has_any((
                    item_names.SKIRMISHER,
                    item_names.DARK_TEMPLAR,
                    item_names.TEMPEST,
                    item_names.TRIREME,
                ), self.player)
                or state.has_all((item_names.BLOOD_HUNTER, item_names.BLOOD_HUNTER_BRUTAL_EFFICIENCY), self.player)
                or state.has_all((item_names.AVENGER, item_names.AVENGER_KRYHAS_CLOAK), self.player)
            )
        else:
            # Air
            return (
                # Beats leviathan
                state.has_any((item_names.TEMPEST, item_names.SKYLORD, item_names.VOID_RAY), self.player)
                or state.has_all((item_names.SCOUT, item_names.SCOUT_RESOURCE_EFFICIENCY), self.player)
            )

    # endregion WoL Missions

    # ###################################################################################################### #
    # region HotS Missions ................................................................................. #
    # ###################################################################################################### #

    def zerg_any_units_back_in_the_saddle_requirement(self, state: CollectionState) -> bool:
        return (
            # Note(mm): This check isn't necessary as self.kerrigan_levels cover it,
            # and it's not fully desirable in future when we support non-grant story tech + kerriganless.
            SC2Mission.BACK_IN_THE_SADDLE in self.grant_hero_items
            or state.has_any((
                # Cases tested by Snarky
                item_names.KERRIGAN_KINETIC_BLAST,
                item_names.KERRIGAN_LEAPING_STRIKE,
                item_names.KERRIGAN_CRUSHING_GRIP,
                item_names.KERRIGAN_PSIONIC_SHIFT,
                item_names.KERRIGAN_SPAWN_BANELINGS,
                item_names.KERRIGAN_FURY,
                item_names.KERRIGAN_APOCALYPSE,
                item_names.KERRIGAN_DROP_PODS,
                item_names.KERRIGAN_SPAWN_LEVIATHAN,
                item_names.KERRIGAN_IMMOBILIZATION_WAVE,  # Involves a 1-minute cooldown wait before the ultra
                item_names.KERRIGAN_MEND,  # See note from THE EV below
            ), self.player)
            or self.kerrigan_levels(state, 20)
            or (self.kerrigan_levels(state, 10) and state.has(item_names.KERRIGAN_CHAIN_REACTION, self.player))
            # Tested by THE EV, "facetank with Kerrigan and stutter step to the end with >10s left"
            # > have to lure the first group of Zerg in the 2nd timed section into the first room of the second area
            # > (with the heal box) so you can kill them before the timer starts.
            #
            # phaneros: Technically possible without the levels, but adding them in for safety margin and to hopefully
            # make generation force this branch less often
            or (state.has_any((item_names.KERRIGAN_HEROIC_FORTITUDE, item_names.KERRIGAN_INFEST_BROODLINGS), self.player)
                and self.kerrigan_levels(state, 5)
            )
            # Insufficient: Wild Mutation, Assimilation Aura
        )

    def zerg_enemy_within_advanced_tactics_requirement(self, state: CollectionState) -> bool:
        return (
            state.has(item_names.INFESTOR, self.player)
            or (self.morphling_enabled
                and state.has_any(item_groups.ENEMY_WITHIN_ZERG_MORPHLING_UNITS, self.player)
            )
        )

    def zerg_enemy_within_pass_vents(self, state: CollectionState) -> bool:
        return (
            self.grant_story_tech == GrantStoryTech.option_grant
            or state.has_any(item_groups.ENEMY_WITHIN_ZERG_STANDARD_UNITS, self.player)
            or (self.advanced_tactics
                and self.zerg_enemy_within_advanced_tactics_requirement(state)
            )
        )

    def zerg_enemy_within_victory_requirement(self, state: CollectionState) -> bool:
        return (
            self.grant_story_tech == GrantStoryTech.option_grant
            or state.has_any(item_groups.ENEMY_WITHIN_ZERG_STANDARD_UNITS[1:], self.player)
            or state.has_all((item_names.ZERGLING, item_names.ZERGLING_RAPTOR_STRAIN), self.player)
            or (self.advanced_tactics
                and self.zerg_enemy_within_advanced_tactics_requirement(state)
            )
        )

    def terran_enemy_within_requirement(self, state: CollectionState) -> bool:
        return (
            self.grant_story_tech == GrantStoryTech.option_grant
            or state.has_any(item_groups.ENEMY_WITHIN_TERRAN_UNITS, self.player)
            or (self.advanced_tactics
                and state.has_any(item_groups.ENEMY_WITHIN_TERRAN_ADVANCED_UNITS, self.player)
            )
        )

    def protoss_enemy_within_requirement(self, state: CollectionState) -> bool:
        return (
            self.grant_story_tech == GrantStoryTech.option_grant
            or state.has_any(item_groups.ENEMY_WITHIN_PROTOSS_STANDARD_UNITS, self.player)
            or (self.advanced_tactics
                and state.has_any(item_groups.ENEMY_WITHIN_PROTOSS_ADVANCED_UNITS, self.player)
            )
        )

    def terran_waking_the_ancient_flawless(self, state: CollectionState) -> bool:
        return (
            # Fast unit
            state.has_any((
                item_names.DOMINION_TROOPER,
                item_names.BANSHEE,
                item_names.VULTURE,
                item_names.HELLION,
                item_names.DIAMONDBACK,
                item_names.WARHOUND,
                item_names.CYCLONE,
            ), self.player)
            or state.has_all((
                item_names.VALKYRIE, item_names.VALKYRIE_FLECHETTE_MISSILES,
            ), self.player)
            or (
                state.has(item_names.WRAITH, self.player)
                and state.has_any((
                    item_names.WRAITH_ADVANCED_LASER_TECHNOLOGY,
                    item_names.WRAITH_RESOURCE_EFFICIENCY,
                ), self.player)
            )
        )

    def supreme_requirement(self, state: CollectionState) -> bool:
        return (
            SC2Mission.SUPREME in self.grant_hero_items
            or (self.grant_story_tech == GrantStoryTech.option_allow_substitutes
                and state.has_any((
                    item_names.KERRIGAN_LEAPING_STRIKE,
                    item_names.OVERLORD_VENTRAL_SACS,
                    item_names.YGGDRASIL,
                    item_names.VIPER,
                    item_names.NYDUS_WORM,
                    item_names.BULLFROG,
                ), self.player)
                and state.has_any((
                    item_names.KERRIGAN_MEND,
                    item_names.SWARM_QUEEN,
                    item_names.INFESTED_MEDICS,
                ), self.player)
                and self.kerrigan_levels(state, 35)
            )
            or (state.has_all((item_names.KERRIGAN_LEAPING_STRIKE, item_names.KERRIGAN_MEND), self.player) and self.kerrigan_levels(state, 35))
        )

    def terran_infested_garrison_claimer(self, state: CollectionState) -> bool:
        return state.has_any((item_names.GHOST, item_names.SPECTRE, item_names.EMPERORS_SHADOW), self.player)

    def zerg_infested_garrison_claimer(self, state: CollectionState) -> bool:
        return state.has_any((item_names.INFESTOR, item_names.DEFILER, item_names.HIVE_QUEEN), self.player)

    def protoss_infested_garrison_claimer(self, state: CollectionState) -> bool:
        return (
            state.has_any((
                item_names.HIGH_TEMPLAR, item_names.SIGNIFIER, item_names.ASCENDANT,
            ), self.player)
            or self.protoss_can_merge_dark_archon(state)
        )

    def zerg_conviction_requirement(self, state: CollectionState) -> bool:
        return (
            SC2Mission.CONVICTION in self.grant_hero_items
            or (
                self.two_kerrigan_actives(state)
                and self.kerrigan_levels(state, 25)
            )
        )

    def the_reckoning_ally_requirement(self, state: CollectionState) -> bool:
        if not self.take_over_ai_allies:
            return True
        return self.terran_competent_comp(state, 2)

    # endregion HotS Missions

    # ###################################################################################################### #
    # region LotV Missions ................................................................................. #
    # ###################################################################################################### #

    def protoss_can_grab_ghosts_in_the_fog_east_rock_formation(self, state: CollectionState) -> bool:
        return (
            state.has_any((
                item_names.SCOUT,
                item_names.SKIRMISHER,
                item_names.TEMPEST,
                item_names.CARRIER,
                item_names.SKYLORD,
                item_names.TRIREME,
                item_names.VOID_RAY,
                item_names.DESTROYER,
                item_names.PULSAR,
                item_names.DAWNBRINGER,
                item_names.MOTHERSHIP_TALDARIM,
                item_names.MOTHERSHIP_PURIFIER,
                item_names.MOTHERSHIP_AIUR,
            ), self.player)
            or self.protoss_has_blink(state)
            or state.has(item_names.WARP_PRISM, self.player)
            or (self.advanced_tactics and state.has_any((item_names.ORACLE, item_names.ARBITER), self.player))
        )

    def terran_can_grab_ghosts_in_the_fog_fast_rock_formations(self, state: CollectionState) -> bool:
        """
        Able to shoot by a long range or from air to claim the rock formation separated by a chasm
        """
        # East rock formation
        return (
            state.has_any((
                item_names.MEDIVAC,
                item_names.HERCULES,
                item_names.VIKING,
                item_names.BANSHEE,
                item_names.WRAITH,
                item_names.SIEGE_TANK,
                item_names.BATTLECRUISER,
                item_names.NIGHT_HAWK,
                item_names.NIGHT_WOLF,
                item_names.SHOCK_DIVISION,
                item_names.SKY_FURY,
            ), self.player)
            or state.has_all((item_names.VALKYRIE, item_names.VALKYRIE_FLECHETTE_MISSILES), self.player)
            or state.has_all((item_names.RAVEN, item_names.RAVEN_HUNTER_SEEKER_WEAPON), self.player)
            or (
                state.has_any((item_names.LIBERATOR, item_names.EMPERORS_GUARDIAN), self.player)
                and state.has(item_names.LIBERATOR_RAID_ARTILLERY, self.player)
            )
            or state.has_all((item_names.REAPER, item_names.REAPER_JET_PACK_OVERDRIVE), self.player)
            or state.has_all((item_names.WARHOUND, item_names.WARHOUND_JUMP_JETS), self.player)
            or (
                self.advanced_tactics
                and (
                    state.has_any((
                        item_names.HELS_ANGELS,
                        item_names.DUSK_WINGS,
                        item_names.WINGED_NIGHTMARES,
                        item_names.SIEGE_BREAKERS,
                        item_names.BRYNHILDS,
                        item_names.JACKSONS_REVENGE,
                    ), self.player)
                    or state.has_all((
                        item_names.MIDNIGHT_RIDERS, item_names.LIBERATOR_RAID_ARTILLERY,
                    ), self.player)
                )
            )
        )

    def zerg_can_grab_ghosts_in_the_fog_east_rock_formation(self, state: CollectionState) -> bool:
        return (
            state.has_any((
                item_names.MUTALISK,
                item_names.INFESTED_BANSHEE,
                item_names.OVERLORD_VENTRAL_SACS,
                item_names.YGGDRASIL,
                item_names.BULLFROG,
            ), self.player)
            or (self.morph_devourer(state) and state.has(item_names.DEVOURER_PRESCIENT_SPORES, self.player))
            or self.morph_guardian(state)
            or self.morph_brood_lord(state)
            or (
                self.advanced_tactics
                and (
                    state.has_any((item_names.INFESTED_SIEGE_BREAKERS, item_names.INFESTED_DUSK_WINGS), self.player)
                    or state.has(item_names.HUNTERLING, self.player)
                    or state.has_all((item_names.INFESTOR, item_names.INFESTOR_INFESTED_TERRAN), self.player)
                )
            )
        )

    def protoss_evil_awoken_requirement(self, state: CollectionState) -> bool:
        return state.has_any((
            item_names.STALKER_PHASE_REACTOR,
            item_names.STALKER_DISINTEGRATING_PARTICLES,
            item_names.STALKER_PARTICLE_REFLECTION,
        ), self.player)

    def protoss_unsealing_the_past_basic_ledge_requirement(self, state: CollectionState) -> bool:
        return (
            state.has_any((item_names.COLOSSUS, item_names.WRATHWALKER), self.player)
            or self.protoss_can_grab_ghosts_in_the_fog_east_rock_formation(state)
        )

    def terran_unsealing_the_past_basic_ledge_requirement(self, state: CollectionState) -> bool:
        return (
            self.terran_air(state)
            or state.has_all((item_names.REAPER, item_names.REAPER_RESOURCE_EFFICIENCY), self.player)
            or state.has_all((item_names.GOLIATH, item_names.GOLIATH_JUMP_JETS), self.player)
        )

    def zerg_unsealing_the_past_basic_ledge_requirement(self, state: CollectionState) -> bool:
        return (
            state.has_any((item_names.MUTALISK, item_names.INFESTED_BANSHEE), self.player)
            or self.morph_brood_lord(state)
            or self.morph_guardian(state)
            or state.has_all((
                item_names.ZERGLING,
                item_names.ZERGLING_RAPTOR_STRAIN,
                item_names.ZERGLING_ADRENAL_OVERLOAD,
            ), self.player)
            or (
                self.morph_devourer(state)
                and state.has(item_names.DEVOURER_PRESCIENT_SPORES, self.player)
            )
        )

    def the_infinite_cycle_requirement(self, state: CollectionState) -> bool:
        return (
            SC2Mission.THE_INFINITE_CYCLE in self.grant_hero_items
            or (
                self.kerrigan_levels(state, 70)
                and state.has_any((
                    item_names.KERRIGAN_KINETIC_BLAST,
                    item_names.KERRIGAN_SPAWN_BANELINGS,
                    item_names.KERRIGAN_LEAPING_STRIKE,
                    item_names.KERRIGAN_SPAWN_LEVIATHAN,
                ), self.player)
                and self.basic_kerrigan(state)
            )
        )

    def protoss_templars_charge_basic_requirement(self, state: CollectionState) -> bool:
        return self.protoss_heal(state) and self.protoss_fleet(state, 3)

    def protoss_templars_charge_advanced_requirement(self, state: CollectionState) -> bool:
        return (
            self.protoss_heal(state)
            and (
                self.protoss_fleet(state, 2)
                or state.has_any((item_names.STALKER, item_names.INSTIGATOR), self.player)
                or state.has_all((item_names.SLAYER, item_names.SLAYER_PHASE_BLINK), self.player)
                or (
                    # Air supporter + ground muscle
                    (
                        state.has_any((item_names.CORSAIR, item_names.ARBITER, item_names.PHOENIX), self.player)
                        or state.has_all((item_names.MIRAGE, item_names.MIRAGE_GRAVITON_BEAM), self.player)
                    )
                    and (
                        state.has_any((
                            item_names.COLOSSUS,
                            item_names.WRATHWALKER,
                            item_names.IMMORTAL,
                            item_names.ANNIHILATOR,
                            item_names.VANGUARD,
                            item_names.AVENGER,
                        ), self.player)
                        or state.has_all((
                            item_names.DARK_TEMPLAR,
                            item_names.DARK_TEMPLAR_LESSER_SHADOW_FURY,
                            item_names.DARK_TEMPLAR_GREATER_SHADOW_FURY,
                        ), self.player)
                    )
                )
            )
        )

    def terran_templars_charge_requirement(self, state: CollectionState) -> bool:
        return (
            (
                state.has_all((item_names.BATTLECRUISER, item_names.BATTLECRUISER_ATX_LASER_BATTERY), self.player)
                and state.count(item_names.BATTLECRUISER_PROGRESSIVE_DEFENSIVE_MATRIX, self.player) >= 2
            )
            or (
                self.terran_air_anti_air(state)
                and self.terran_sustainable_mech_heal(state)
                and (
                    state.has_any((item_names.BANSHEE, item_names.BATTLECRUISER), self.player)
                    or state.has_all((item_names.LIBERATOR, item_names.LIBERATOR_RAID_ARTILLERY), self.player)
                    or state.has_all((item_names.VALKYRIE, item_names.VALKYRIE_FLECHETTE_MISSILES), self.player)
                    or (self.advanced_tactics
                        and (state.has_all((item_names.WRAITH, item_names.WRAITH_ADVANCED_LASER_TECHNOLOGY), self.player))
                    )
                )
            )
        )

    def templars_return_phase_2_basic_requirement(self, state: CollectionState) -> bool:
        return (
            self.grant_story_tech == GrantStoryTech.option_grant
            or state.has_any(item_groups.TEMPLARS_RETURN_PROTOSS_UNITS, self.player)
        )

    def templars_return_phase_3_reach_colossus_basic_requirement(self, state: CollectionState) -> bool:
        return (
            self.grant_story_tech == GrantStoryTech.option_grant
            or (
                self.templars_return_phase_2_basic_requirement(state)
                and state.has_all((
                    item_names.ZEALOT_WHIRLWIND, item_names.VANGUARD_RAPIDFIRE_CANNON
                ), self.player)
            )
        )

    def templars_return_phase_3_reach_colossus_advanced_requirement(self, state: CollectionState) -> bool:
        return (
            self.grant_story_tech == GrantStoryTech.option_grant
            or state.has_any((
                item_names.ZEALOT_WHIRLWIND, item_names.VANGUARD_RAPIDFIRE_CANNON,
            ), self.player)
        )

    def templars_return_phase_3_reach_dts_basic_requirement(self, state: CollectionState) -> bool:
        return (
            self.grant_story_tech == GrantStoryTech.option_grant
            or (
                self.templars_return_phase_3_reach_colossus_basic_requirement(state)
                and state.has(item_names.ENERGIZER_MOBILE_CHRONO_BEAM, self.player)
                and state.has_any((
                    item_names.COLOSSUS_PACIFICATION_PROTOCOL,
                    item_names.COLOSSUS_FIRE_LANCE,
                ), self.player)
            )
        )

    def templars_return_phase_3_reach_dts_advanced_requirement(self, state: CollectionState) -> bool:
        return (
            self.grant_story_tech == GrantStoryTech.option_grant
            or (
                self.templars_return_phase_3_reach_colossus_advanced_requirement(state)
                and (
                    state.has_all((
                        item_names.COLOSSUS_PACIFICATION_PROTOCOL,
                        item_names.ENERGIZER_MOBILE_CHRONO_BEAM,
                    ), self.player)
                    or state.has(item_names.COLOSSUS_FIRE_LANCE, self.player)
                )
            )
        )

    def epilogue_ally_requirement(self, state: CollectionState) -> bool:
        return (
            not self.take_over_ai_allies
            or (
                self.terran_competent_comp(state, 2)
                and self.zerg_competent_comp(state, 2)
                and self.protoss_competent_comp(state, 2)
            )
        )

    def zerg_amons_fall_requirement(self, state: CollectionState) -> bool:
        return (
            self.epilogue_ally_requirement(state)
            and self.spread_creep(state)
        )

    # endregion LotV Missions

    # ###################################################################################################### #
    # region NCO Missions .................................................................................. #
    # ###################################################################################################### #

    def the_escape_first_stage_requirement(self, state: CollectionState) -> bool:
        return (
            SC2Mission.THE_ESCAPE in self.grant_hero_items
            or (self.nova_ranged_weapon(state)
                and (self.nova_full_stealth(state)
                    or self.nova_heal(state)
                )
            )
        )

    def the_escape_requirement(self, state: CollectionState) -> bool:
        return (
            self.the_escape_first_stage_requirement(state)
            and (
                SC2Mission.THE_ESCAPE in self.grant_hero_items
                or self.nova_splash(state)
            )
        )

    def the_escape_hard_rule(self, state: CollectionState) -> bool:
        return (
            SC2Mission.THE_ESCAPE in self.grant_hero_items
            or self.nova_any_nobuild_damage(state)
        )

    def hero_handle_defiler(self, state: CollectionState, presence: HeroFlag) -> bool:
        if presence == HeroFlag.NONE:
            return False
        return (
            (
                HeroFlag.NOVA in presence
                and state.has(item_names.NOVA_JUMP_SUIT_MODULE, self.player)
                and state.has_any((
                    item_names.NOVA_DOMINATION,
                    item_names.NOVA_C20A_CANISTER_RIFLE,
                    item_names.NOVA_PULSE_GRENADES,
                ), self.player)
            )
            or (
                HeroFlag.KERRIGAN in presence
                and state.has_any((
                    item_names.KERRIGAN_KINETIC_BLAST,
                    item_names.KERRIGAN_SPAWN_BANELINGS,
                    item_names.KERRIGAN_CRUSHING_GRIP,
                    # item_names.KERRIGAN_LEAPING_STRIKE,
                ), self.player)
            )
            or (
                HeroFlag.ARTANIS in presence
                and True # TODO (Snarky): Revisit once Artanis is implemented
            )
        )

    def terran_able_to_snipe_defiler(self, state: CollectionState, presence: HeroFlag = HeroFlag.NONE) -> bool:
        return (
            state.has(item_names.BANSHEE, self.player)
            or (state.has_all((
                item_names.SIEGE_TANK,
                item_names.SIEGE_TANK_MAELSTROM_ROUNDS,
                item_names.SIEGE_TANK_JUMP_JETS,
            ), self.player))
            or self.hero_handle_defiler(state, presence)
        )

    def zerg_handle_defiler(self, state: CollectionState, presence: HeroFlag = HeroFlag.NONE) -> bool:
        return (
            state.has(item_names.ABERRATION, self.player)
            or state.has(item_names.ULTRALISK, self.player)
            or self.morph_tyrannozor(state)
            or (self.advanced_tactics
                and (
                    state.has_any((item_names.INFESTOR, item_names.BROOD_QUEEN), self.player)
                    or self.morph_viper(state)
                )
            )
            or self.hero_handle_defiler(state, presence)
        )

    def protoss_handle_defiler(self, state: CollectionState, presence: HeroFlag = HeroFlag.NONE) -> bool:
        return (
            state.has_all({item_names.COLOSSUS,item_names.COLOSSUS_FIRE_LANCE}, self.player)
            or (self.advanced_tactics and state.has_any({item_names.HIGH_TEMPLAR, item_names.ASCENDANT, item_names.DISRUPTOR}, self.player))
            or self.hero_handle_defiler(state, presence)
        )

    def sudden_strike_artanis(self, state: CollectionState) -> bool:
        return self.basic_artanis(state)

    def sudden_strike_nova(self, state: CollectionState) -> bool:
        return (
            self.nova_splash(state)
            and (self.advanced_tactics
                or state.has(item_names.NOVA_JUMP_SUIT_MODULE, self.player)
            )
        )

    def sudden_strike_kerrigan(self, state: CollectionState) -> bool:
        return (
            self.two_kerrigan_actives(state)
            and state.has_any((
                # one non-ultimate way to deal splash damage
                item_names.KERRIGAN_PSIONIC_SHIFT,
                item_names.KERRIGAN_SPAWN_BANELINGS,
                item_names.KERRIGAN_CRUSHING_GRIP,
            ), self.player)
        )

    def sudden_strike_hero(self, state: CollectionState, presence: HeroFlag, mission: SC2Mission) -> bool:
        return (
            presence == HeroFlag.NONE
            or mission in self.grant_hero_items
            or (HeroFlag.NOVA in presence and self.sudden_strike_nova(state))
            or (HeroFlag.KERRIGAN in presence and self.sudden_strike_kerrigan(state))
            or (HeroFlag.ARTANIS in presence and self.sudden_strike_artanis(state))
        )

    def terran_sudden_strike_requirement(self, state: CollectionState) -> bool:
        presence = self.get_hero_flag(SC2Mission.SUDDEN_STRIKE)
        return (
            self.sudden_strike_hero(state, presence, SC2Mission.SUDDEN_STRIKE)
            and self.terran_able_to_snipe_defiler(state, presence)
            and (self.terran_cliffjumper(state) or state.has(item_names.BANSHEE, self.player))
        )

    def zerg_sudden_strike_requirement(self, state: CollectionState) -> bool:
        presence = self.get_hero_flag(SC2Mission.SUDDEN_STRIKE_Z)
        return (
            self.sudden_strike_hero(state, presence, SC2Mission.SUDDEN_STRIKE_Z)
            and self.zerg_handle_defiler(state, presence)
        )

    def protoss_sudden_strike_requirement(self, state: CollectionState) -> bool:
        presence = self.get_hero_flag(SC2Mission.SUDDEN_STRIKE_P)
        return (
            self.sudden_strike_hero(state, presence, SC2Mission.SUDDEN_STRIKE_Z)
            and self.protoss_handle_defiler(state, presence)
        )

    def terran_enemy_intelligence_garrisonable_unit(self, state: CollectionState) -> bool:
        """
        Has unit usable as a Garrison in Enemy Intelligence
        """
        return (
            state.has_any((
                item_names.MARINE,
                item_names.SON_OF_KORHAL,
                item_names.REAPER,
                item_names.MARAUDER,
                item_names.GHOST,
                item_names.SPECTRE,
                item_names.HELLION,
                item_names.GOLIATH,
                item_names.WARHOUND,
                item_names.DIAMONDBACK,
                item_names.VIKING,
                item_names.DOMINION_TROOPER,
                item_names.SIEGE_TANK,
                item_names.WIDOW_MINE,
                item_names.THOR,
                item_names.VULTURE,
                item_names.CYCLONE,
            ), self.player)
            or (self.advanced_tactics
                and state.has(item_names.ROGUE_FORCES, self.player)
                and state.count_from_list_unique((
                    item_names.WAR_PIGS,
                    item_names.HAMMER_SECURITIES,
                    item_names.DEATH_HEADS,
                    item_names.SPARTAN_COMPANY,
                    item_names.HELS_ANGELS,
                    item_names.BRYNHILDS,
                    item_names.SIEGE_BREAKERS,
                    item_names.JOTUN,
                ), self.player) >= 3
            )
        )

    def zerg_enemy_intelligence_garrisonable_unit(self, state: CollectionState) -> bool:
        """
        Has zerg unit usable as a Garrison in Enemy Intelligence
        """
        return (
            state.has_any((
                item_names.ROACH,
                item_names.HYDRALISK,
                item_names.SWARM_QUEEN,
                item_names.INFESTED_DIAMONDBACK,
                item_names.INFESTED_SIEGE_TANK,
            ), self.player)
            or state.has_all({item_names.SWARM_HOST, item_names.SWARM_HOST_CARRION_STRAIN}, self.player)
            or self.morph_lurker(state)
            or self.morph_impaler(state)
            or (self.advanced_tactics
                and state.has(item_names.UNRESTRICTED_MUTATION, self.player)
                and state.count_from_list_unique((
                    item_names.HUNTER_KILLERS,
                    item_names.INFESTED_SIEGE_BREAKERS,
                    item_names.CAUSTIC_HORRORS,
                ), self.player) >= 3
            )
        )

    def protoss_enemy_intelligence_garrisonable_unit(self, state: CollectionState) -> bool:
        """
        Has a garrisonable protoss unit in Enemy Intelligence
        """
        return (
            state.has_any((
                item_names.ADEPT,
                item_names.SENTRY,
                item_names.ENERGIZER,
                item_names.HIGH_TEMPLAR,
                item_names.SIGNIFIER,
                item_names.ASCENDANT,
                item_names.STALKER,
                item_names.SLAYER,
                item_names.INSTIGATOR,
                item_names.DRAGOON,
                item_names.IMMORTAL,
                item_names.ANNIHILATOR,
                item_names.VANGUARD,
                item_names.COLOSSUS,
                item_names.WRATHWALKER,
                item_names.REAVER,
            ), self.player)
        )

    def terran_enemy_intelligence_cliff_garrison(self, state: CollectionState) -> bool:
        return (
            state.has_any((item_names.REAPER, item_names.VIKING), self.player)
            or (state.has_any((item_names.MEDIVAC, item_names.HERCULES), self.player)
                and self.terran_enemy_intelligence_garrisonable_unit(state)
            )
            or state.has_all((item_names.GOLIATH, item_names.GOLIATH_JUMP_JETS), self.player)
            or (self.advanced_tactics
                and state.has_any((item_names.HELS_ANGELS, item_names.BRYNHILDS), self.player)
            )
        )

    def zerg_enemy_intelligence_cliff_garrison(self, state: CollectionState) -> bool:
        return (
            (
                state.has_any((
                    item_names.YGGDRASIL,
                    item_names.OVERLORD_VENTRAL_SACS,
                    item_names.BULLFROG,
                ), self.player)
                or self.morph_viper(state)
            )
            # consider Creep Teleport + Overlord creep?
            and self.zerg_enemy_intelligence_garrisonable_unit(state)
        )

    def protoss_enemy_intelligence_cliff_garrison(self, state: CollectionState) -> bool:
        return (
            state.has_any((
                item_names.STALKER,
                item_names.INSTIGATOR,
                item_names.COLOSSUS,
                item_names.WRATHWALKER,
            ), self.player)
            or state.has_all((item_names.SLAYER, item_names.SLAYER_PHASE_BLINK), self.player)
            or (
                state.has(item_names.WARP_PRISM, self.player)
                # consider SoA pylon + warpable unit/reinforcements?
                and self.protoss_enemy_intelligence_garrisonable_unit(state)
            )
        )

    def enemy_intelligence_nova(self, state: CollectionState) -> bool:
        return (
            self.nova_any_weapon(state)
            and (
                self.nova_full_stealth(state)
                or (
                    self.nova_heal(state)
                    and self.nova_splash(state)
                    and self.nova_ranged_weapon(state)
                    and self.nova_dash(state)
                )
            )
        )

    def enemy_intelligence_kerrigan(self, state: CollectionState) -> bool:
        return self.two_kerrigan_solo_actives(state)

    def enemy_intelligence_artanis(self, state: CollectionState) -> bool:
        return True  # TODO (Snarky): Revisit once Artanis is implemented

    def enemy_intelligence_hero(self, state: CollectionState, mission: SC2Mission) -> bool:
        presence = self.get_hero_flag(mission)
        return (
            presence == HeroFlag.NONE  # no hero active formission, 2nd stage is skipped
            or mission in self.grant_hero_items
            or (HeroFlag.NOVA in presence and self.enemy_intelligence_nova(state))
            or (HeroFlag.KERRIGAN in presence and self.enemy_intelligence_kerrigan(state))
            or (HeroFlag.ARTANIS in presence and self.enemy_intelligence_artanis(state))
        )

    def terran_enemy_intelligence_second_stage_requirement(self, state: CollectionState) -> bool:
        return (
            self.terran_enemy_intelligence_cliff_garrison(state)
            and self.enemy_intelligence_hero(state, SC2Mission.ENEMY_INTELLIGENCE)
        )

    def zerg_enemy_intelligence_second_stage_requirement(self, state: CollectionState) -> bool:
        return (
            self.zerg_enemy_intelligence_cliff_garrison(state)
            and self.enemy_intelligence_hero(state, SC2Mission.ENEMY_INTELLIGENCE_Z)
        )

    def protoss_enemy_intelligence_second_stage_requirement(self, state: CollectionState) -> bool:
        return (
            self.protoss_enemy_intelligence_cliff_garrison(state)
            and self.enemy_intelligence_hero(state, SC2Mission.ENEMY_INTELLIGENCE_P)
        )

    def terran_enemy_intelligence_hard_rule(self, state: CollectionState) -> bool:
        return (
            self.terran_enemy_intelligence_cliff_garrison(state)
            and self.enemy_intelligence_hero(state, SC2Mission.ENEMY_INTELLIGENCE)
        )

    def zerg_enemy_intelligence_hard_rule(self, state: CollectionState) -> bool:
        return (
            self.zerg_enemy_intelligence_cliff_garrison(state)
            and self.enemy_intelligence_hero(state, SC2Mission.ENEMY_INTELLIGENCE_Z)
        )

    def protoss_enemy_intelligence_hard_rule(self, state: CollectionState) -> bool:
        return (
            self.protoss_enemy_intelligence_cliff_garrison(state)
            and self.enemy_intelligence_hero(state, SC2Mission.ENEMY_INTELLIGENCE_P)
        )

    def enemy_shadow_tripwires_tool(self, state: CollectionState) -> bool:
        return (
            SC2Mission.IN_THE_ENEMY_S_SHADOW in self.grant_hero_items
            or state.has_any({item_names.NOVA_FLASHBANG_GRENADES, item_names.NOVA_BLINK, item_names.NOVA_DOMINATION}, self.player)
        )

    def enemy_shadow_door_unlocks_tool(self, state: CollectionState) -> bool:
        return (
            SC2Mission.IN_THE_ENEMY_S_SHADOW in self.grant_hero_items
            or state.has_any((item_names.NOVA_DOMINATION, item_names.NOVA_BLINK, item_names.NOVA_JUMP_SUIT_MODULE), self.player)
        )

    def enemy_shadow_blazefire_unlock(self, state: CollectionState) -> bool:
        return (
            self.enemy_shadow_second_stage(state)
            and (
                SC2Mission.IN_THE_ENEMY_S_SHADOW in self.grant_hero_items
                or state.has(item_names.NOVA_BLINK, self.player)
                or (
                    self.advanced_tactics
                    and state.has_all((
                        item_names.NOVA_DOMINATION,
                        item_names.NOVA_HOLO_DECOY,
                        item_names.NOVA_JUMP_SUIT_MODULE,
                    ), self.player)
                )
            )
        )

    def enemy_shadow_nova_damage_and_blazefire_unlock(self, state: CollectionState) -> bool:
        return (
            SC2Mission.IN_THE_ENEMY_S_SHADOW in self.grant_hero_items
            or (
                self.nova_any_nobuild_damage(state)
                and (
                    state.has(item_names.NOVA_BLINK, self.player)
                    or state.has_all((item_names.NOVA_HOLO_DECOY, item_names.NOVA_DOMINATION), self.player)
                )
            )
        )

    def enemy_shadow_domination(self, state: CollectionState) -> bool:
        return (
            SC2Mission.IN_THE_ENEMY_S_SHADOW in self.grant_hero_items
            or (
                self.nova_ranged_weapon(state)
                and (
                    self.nova_full_stealth(state)
                    or state.has(item_names.NOVA_JUMP_SUIT_MODULE, self.player)
                    or (self.nova_heal(state) and self.nova_splash(state))
                )
            )
        )

    def enemy_shadow_first_stage(self, state: CollectionState) -> bool:
        return (
            self.enemy_shadow_domination(state)
            and (
                SC2Mission.IN_THE_ENEMY_S_SHADOW in self.grant_hero_items
                or (
                    self.nova_full_stealth(state) and self.enemy_shadow_tripwires_tool(state)
                    or (self.nova_heal(state) and self.nova_splash(state))
                )
            )
        )

    def enemy_shadow_second_stage(self, state: CollectionState) -> bool:
        return (
            self.enemy_shadow_first_stage(state)
            and (
                SC2Mission.IN_THE_ENEMY_S_SHADOW in self.grant_hero_items
                or (
                    (
                        self.nova_splash(state) or self.nova_heal(state) or self.nova_escape_assist(state)
                    )
                    and (self.advanced_tactics or state.has(item_names.NOVA_GHOST_VISOR, self.player))
                )
            )
        )

    def enemy_shadow_can_reach_stone(self, state: CollectionState) -> bool:
        return (
            self.enemy_shadow_second_stage(state)
            and (
                SC2Mission.IN_THE_ENEMY_S_SHADOW in self.grant_hero_items
                or self.enemy_shadow_door_unlocks_tool(state)
            )
        )

    def nova_beat_stone(self, state: CollectionState) -> bool:
        """
        Used for any units logic for beating Stone. Shotgun may not be possible; may need feedback.
        """
        return (
            SC2Mission.IN_THE_ENEMY_S_SHADOW in self.grant_hero_items
            or state.has_any((
                item_names.NOVA_DOMINATION,
                item_names.NOVA_BLAZEFIRE_GUNBLADE,
                item_names.NOVA_C20A_CANISTER_RIFLE,
            ), self.player)
            or ((
                    state.has_any((
                        item_names.NOVA_PLASMA_RIFLE,
                        item_names.NOVA_MONOMOLECULAR_BLADE,
                    ), self.player)
                    or state.has_all((
                        item_names.NOVA_HELLFIRE_SHOTGUN,
                        item_names.NOVA_STIM_INFUSION
                    ), self.player)
                )
                and state.has_any((
                    item_names.NOVA_JUMP_SUIT_MODULE,
                    item_names.NOVA_ARMORED_SUIT_MODULE,
                    item_names.NOVA_ENERGY_SUIT_MODULE,
                ), self.player)
                and state.has_any((
                    item_names.NOVA_FLASHBANG_GRENADES,
                    item_names.NOVA_STIM_INFUSION,
                    item_names.NOVA_BLINK,
                    item_names.NOVA_IONIC_FORCE_FIELD,
                ), self.player)
            )
        )

    def enemy_shadow_victory(self, state: CollectionState) -> bool:
        return (
            self.enemy_shadow_can_reach_stone(state)
            and (
                SC2Mission.IN_THE_ENEMY_S_SHADOW in self.grant_hero_items
                or (self.nova_heal(state) and self.nova_beat_stone(state))
            )
        )

    def enemy_shadow_hard_rule(self, state: CollectionState) -> bool:
        return (
            SC2Mission.IN_THE_ENEMY_S_SHADOW in self.grant_hero_items
            or self.nova_any_nobuild_damage(state)
        )

    def enemy_shadow_can_reach_stone_hard_rule(self, state: CollectionState) -> bool:
        return self.enemy_shadow_hard_rule(state) and self.enemy_shadow_door_unlocks_tool(state)

    def enemy_shadow_victory_hard_rule(self, state: CollectionState) -> bool:
        return (
            SC2Mission.IN_THE_ENEMY_S_SHADOW in self.grant_hero_items
            or (
                self.nova_beat_stone(state)
                and self.enemy_shadow_door_unlocks_tool(state)
            )
        )

    def terran_end_game_requirement(self, state: CollectionState) -> bool:
        return (
            # Xanthos
            state.has_any((item_names.BATTLECRUISER, item_names.VIKING, item_names.WARHOUND), self.player)
            or state.has_all((item_names.LIBERATOR, item_names.LIBERATOR_SMART_SERVOS), self.player)
            or state.has_all((item_names.THOR, item_names.THOR_PROGRESSIVE_HIGH_IMPACT_PAYLOAD), self.player)
            or (
                state.has(item_names.VALKYRIE, self.player)
                and state.has_any((item_names.VALKYRIE_AFTERBURNERS, item_names.VALKYRIE_SHAPED_HULL), self.player)
                and state.has_any((
                    item_names.VALKYRIE_FLECHETTE_MISSILES,
                    item_names.VALKYRIE_ENHANCED_CLUSTER_LAUNCHERS,
                ), self.player)
            )
            or (
                state.has(item_names.BANSHEE, self.player)
                and (self.advanced_tactics
                    or state.has(item_names.BANSHEE_SHAPED_HULL, self.player)
                )
            )
            or (
                self.advanced_tactics
                and (
                    (
                        state.has_all((item_names.MARINE, item_names.MARINE_STIMPACK), self.player)
                        and (
                            self.terran_bio_heal(state)
                            or state.has(item_names.MARINE_MEDPACK, self.player)
                        )
                    )
                    or (state.has(item_names.DOMINION_TROOPER, self.player)
                        and self.terran_bio_heal(state)
                    )
                    or state.has_all((
                        item_names.PREDATOR,
                        item_names.PREDATOR_RESOURCE_EFFICIENCY,
                        item_names.PREDATOR_ADAPTIVE_DEFENSES,
                    ), self.player)
                    or state.has_all((item_names.CYCLONE, item_names.CYCLONE_TARGETING_OPTICS), self.player)
                )
            )
        )

    # endregion NCO Missions

    # ###################################################################################################### #
    # region Core Units .................................................................................... #
    # ###################################################################################################### #

    def has_terran_basic_starter_unit(self, state: CollectionState) -> bool:
        return state.has_any(item_groups.terran_basic_starter_units, self.player)

    def has_terran_advanced_starter_unit(self, state: CollectionState) -> bool:
        return state.has_any(item_groups.terran_advanced_starter_units, self.player)

    def has_terran_chaos_starter_unit(self, state: CollectionState) -> bool:
        # Anything that can hit buildings
        return (
            state.has_any(item_groups.terran_chaos_starter_units, self.player)
            or state.has_all((item_names.LIBERATOR, item_names.LIBERATOR_RAID_ARTILLERY), self.player)
            or state.has_all((item_names.EMPERORS_GUARDIAN, item_names.LIBERATOR_RAID_ARTILLERY), self.player)
            or state.has_all((item_names.VALKYRIE, item_names.VALKYRIE_FLECHETTE_MISSILES), self.player)
            or state.has_all((item_names.WIDOW_MINE, item_names.WIDOW_MINE_DEMOLITION_PAYLOAD), self.player)
            or (
                state.has_any((
                    # Mercs with shortest initial cooldown (300s)
                    item_names.WAR_PIGS,
                    item_names.DEATH_HEADS,
                    item_names.HELS_ANGELS,
                    item_names.WINGED_NIGHTMARES,
                ), self.player)
                # + 2 upgrades that allow getting faster/earlier mercs
                and state.count_from_list_unique((
                    item_names.RAPID_REINFORCEMENT,
                    item_names.PROGRESSIVE_FAST_DELIVERY,
                    item_names.ROGUE_FORCES,
                    # item_names.SIGNAL_BEACON,  # Probably doesn't help too much on the first unit
                ), self.player) >= 2
            )
        )

    @series(LogicSeries.CoreUnit, SC2Race.TERRAN, 0)
    def has_terran_units(self, target: int, logic_level: int) -> Callable[["CollectionState"], bool]:
        if logic_level == RequiredTactics.option_basic:
            if target == 1:
                return self.has_terran_basic_starter_unit
            def _has_terran_basic_units(state: CollectionState) -> bool:
                return (
                    self.has_terran_basic_starter_unit(state)
                    and state.count_from_list_unique(item_groups.terran_basic_units, self.player) >= target
                )
            return _has_terran_basic_units

        if logic_level == RequiredTactics.option_advanced:
            if target == 1:
                return self.has_terran_advanced_starter_unit
            def _has_terran_advanced_units(state: CollectionState) -> bool:
                return (
                    self.has_terran_advanced_starter_unit(state)
                    and state.count_from_list_unique(item_groups.terran_advanced_units, self.player) >= target
                )
            return _has_terran_advanced_units

        def _has_terran_units(state: CollectionState) -> bool:
            return (
                state.count_from_list_unique(
                    item_groups.terran_units + item_groups.terran_buildings, self.player
                ) >= target
                and (
                    target < 5
                    or self.terran_any_anti_air(state)
                )
                and self.has_terran_chaos_starter_unit(state)
            )

        return _has_terran_units

    def has_zerg_basic_starter_unit(self, state: CollectionState) -> bool:
        return state.has_any(item_groups.zerg_basic_starter_units, self.player)

    def has_zerg_advanced_starter_unit(self, state: CollectionState) -> bool:
        return (
            state.has_any(item_groups.zerg_advanced_starter_units, self.player)
            or self.morph_ravager(state)
            or self.morph_igniter(state)
            or self.morph_lurker(state)
            or self.morph_impaler(state)
        )

    def has_zerg_chaos_starter_unit(self, state: CollectionState) -> bool:
        return (
            # Anything that can hit buildings
            state.has_any(item_groups.zerg_chaos_starter_units, self.player)
            or state.has_all((item_names.INFESTOR, item_names.INFESTOR_INFESTED_TERRAN), self.player)
            or self.morph_baneling(state)
            or self.morph_lurker(state)
            or self.morph_impaler(state)
            or self.morph_brood_lord(state)
            or self.morph_guardian(state)
            or self.morph_ravager(state)
            or self.morph_igniter(state)
            or self.morph_tyrannozor(state)
            or (self.morph_devourer(state)
                and state.has(item_names.DEVOURER_PRESCIENT_SPORES, self.player)
            )
            or (
                state.has_any((
                    # Mercs with <= 300s first drop time
                    item_names.DEVOURING_ONES,
                    item_names.HUNTER_KILLERS,
                    item_names.CAUSTIC_HORRORS,
                    item_names.HUNTERLING,
                ), self.player)
                # + 2 upgrades that allow getting faster/earlier mercs
                and state.count_from_list_unique((
                    item_names.UNRESTRICTED_MUTATION,
                    item_names.EVOLUTIONARY_LEAP,
                    item_names.CELL_DIVISION,
                    item_names.SELF_SUFFICIENT,
                ), self.player) >= 2
            )
        )

    @series(LogicSeries.CoreUnit, SC2Race.ZERG, 0)
    def has_zerg_units(self, target: int, logic_level: int) -> Callable[["CollectionState"], bool]:
        if logic_level == RequiredTactics.option_basic:
            if target == 1:
                return self.has_zerg_basic_starter_unit
            def _has_zerg_basic_units(state: CollectionState) -> bool:
                num_units = (
                    state.count_from_list_unique(item_groups.zerg_basic_units, self.player)
                    + self.morph_igniter(state)
                    + self.morph_brood_lord(state)
                    + self.morph_guardian(state)
                    + self.morph_tyrannozor(state)
                    + self.morph_lurker(state)
                    + self.morph_impaler(state)
                )
                return (
                    self.has_zerg_basic_starter_unit(state)
                    and num_units >= target
                )
            return _has_zerg_basic_units

        if logic_level == RequiredTactics.option_advanced:
            if target == 1:
                return self.has_zerg_advanced_starter_unit
            def _has_zerg_advanced_units(state: CollectionState) -> bool:
                num_units = (
                    state.count_from_list_unique(item_groups.zerg_advanced_units, self.player)
                    + self.morph_ravager(state)
                    + self.morph_igniter(state)
                    + self.morph_lurker(state)
                    + self.morph_impaler(state)
                    + self.morph_viper(state)
                    + self.morph_devourer(state)
                    + self.morph_brood_lord(state)
                    + self.morph_guardian(state)
                    + self.morph_tyrannozor(state)
                )
                return (
                    self.has_zerg_advanced_starter_unit(state)
                    and num_units >= target
                )
            return _has_zerg_advanced_units

        def _has_zerg_units(state: CollectionState) -> bool:
            num_units = (
                state.count_from_list_unique(
                    item_groups.zerg_nonmorph_units + item_groups.zerg_buildings + [item_names.OVERSEER],
                    self.player
                )
                + self.morph_baneling(state)
                + self.morph_ravager(state)
                + self.morph_igniter(state)
                + self.morph_lurker(state)
                + self.morph_impaler(state)
                + self.morph_viper(state)
                + self.morph_devourer(state)
                + self.morph_brood_lord(state)
                + self.morph_guardian(state)
                + self.morph_tyrannozor(state)
            )
            return (
                num_units >= target
                and (
                    target < 5
                    or self.zerg_any_anti_air(state)
                )
                and self.has_zerg_chaos_starter_unit(state)
            )

        return _has_zerg_units

    def has_protoss_basic_starter_unit(self, state: CollectionState) -> bool:
        return state.has_any(item_groups.protoss_basic_starter_units, self.player)

    def has_protoss_advanced_starter_unit(self, state: CollectionState) -> bool:
        return state.has_any(item_groups.protoss_advanced_starter_units, self.player)

    def has_protoss_chaos_starter_unit(self, state: CollectionState) -> bool:
        return (
            # Anything that can hit buildings
            state.has_any(item_groups.protoss_chaos_starter_units, self.player)
            or state.has_all((item_names.WARP_PRISM, item_names.WARP_PRISM_PHASE_BLASTER), self.player)
            or state.has_all((item_names.CALADRIUS, item_names.CALADRIUS_CORONA_BEAM), self.player)
            or state.has_all((item_names.PHOTON_CANNON, item_names.KHALAI_INGENUITY), self.player)
            or state.has_all((item_names.KHAYDARIN_MONOLITH, item_names.KHALAI_INGENUITY), self.player)
        )

    @series(LogicSeries.CoreUnit, SC2Race.PROTOSS, 0)
    def has_protoss_units(self, target: int, logic_level: int) -> Callable[["CollectionState"], bool]:
        if logic_level == RequiredTactics.option_basic:
            if target == 1:
                return self.has_protoss_basic_starter_unit
            def _has_protoss_basic_units(state: CollectionState) -> bool:
                return (
                    self.has_protoss_basic_starter_unit(state)
                    and state.count_from_list_unique(item_groups.protoss_basic_units, self.player) >= target
                )
            return _has_protoss_basic_units

        if logic_level == RequiredTactics.option_advanced:
            if target == 1:
                return self.has_protoss_advanced_starter_unit
            def _has_protoss_advanced_units(state: CollectionState) -> bool:
                return (
                    self.has_protoss_advanced_starter_unit(state)
                    and state.count_from_list_unique(item_groups.protoss_advanced_units, self.player) >= target
                )
            return _has_protoss_advanced_units

        def _has_protoss_units(state: CollectionState) -> bool:
            return (
                state.count_from_list_unique(item_groups.protoss_units + item_groups.protoss_buildings + [item_names.NEXUS_OVERCHARGE], self.player)
                >= target
            ) and (
                target < 5
                or self.protoss_any_anti_air_unit(state)
            ) and self.has_protoss_chaos_starter_unit(state)

        return _has_protoss_units

    # endregion Core Units

    def has_race_units(
        self, target: int, race: SC2Race, logic_level: int = RequiredTactics.option_chaos
    ) -> Callable[[CollectionState], bool]:
        if target == 0 or race == SC2Race.ANY:
            return Location.access_rule
        result = self.unit_count_functions.get((race, target, logic_level))
        if result is not None:
            return result
        result = self.series_functions[LogicSeries.CoreUnit, race, 0](target, logic_level)
        assert result is not None
        self.unit_count_functions[(race, target, logic_level)] = result
        return result

    def has_power_comp(self, race: SC2Race, upgrade: int, tier: int) -> Callable[[CollectionState], bool]:
        if upgrade == 0 or race == SC2Race.ANY:
            return Location.access_rule
        if tier < 1:
            # If upgrade is specified but tier is 0, use upgraded_unit
            tier = 1
        result = self.power_comp_functions.get((race, upgrade, tier))
        if result is not None:
            return result
        parent = self.series_functions[LogicSeries.PowerComp, race, tier]
        def power_comp(state: CollectionState) -> bool:
            return parent(state, upgrade)
        self.power_comp_functions[race, upgrade, tier] = power_comp
        return power_comp

    def get_rating_function(
        self, race: SC2Race, series: LogicSeries, rating: int, series_modifier: int = 0
    ) -> Callable[[CollectionState], bool]:
        if rating == 0 or race == SC2Race.ANY:
            return Location.access_rule
        result = self.rating_functions.get((race, series, rating))
        if result is not None:
            return result
        parent = self.series_functions[series, race, series_modifier]
        def has_rating(state: CollectionState) -> bool:
            return parent(state) >= rating
        self.rating_functions[race, series, rating] = has_rating
        return has_rating


def get_required_kerrigan_levels(missions: list[SC2Mission]) -> int:
    result = 0
    if SC2Mission.BACK_IN_THE_SADDLE in missions:
        result = 10
    if SC2Mission.CONVICTION in missions:
        result = 25
    if SC2Mission.SUPREME in missions:
        result = 35
    if SC2Mission.THE_INFINITE_CYCLE in missions:
        result = 70
    return result

