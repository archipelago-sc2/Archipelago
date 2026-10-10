
from typing import TYPE_CHECKING, TypedDict, NotRequired, Required, Any, Literal
from dataclasses import fields
from . import options, mission_tables, tables, locations


if TYPE_CHECKING:
    from . import SC2World


class Sc2SlotDataDict(TypedDict, total=False):
    version: Required[Literal[5]]
    game_difficulty: Required[int]
    custom_mission_order: Required[list[dict[str, Any]]]
    all_in_map: Required[int]
    final_mission_ids: list[int]

    game_speed: int
    mission_order: int
    war_council_nerfs: int
    mercenary_highlanders: int
    generic_upgrade_missions: int
    max_upgrade_level: int
    generic_upgrade_research: int
    generic_upgrade_research_speedup: int
    kerrigan_primal_status: int
    kerrigan_levels_per_mission_completed: int
    kerrigan_levels_per_mission_completed_cap: int
    kerrigan_total_level_cap: int
    enable_morphling: int
    grant_story_tech: int
    grant_story_levels: int
    required_tactics: int
    take_over_ai_allies: int
    spear_of_adun_presence: int
    spear_of_adun_present_in_no_build: int
    spear_of_adun_passive_ability_presence: int
    spear_of_adun_passive_present_in_no_build: int
    hero_presence: dict[str, int]
    grant_hero_items: list[int]
    difficulty_damage_modifier: int

    # Scouting
    mission_order_scouting: int
    mission_item_classification: dict[str, int]
    vanilla_locations: int
    extra_locations: int
    challenge_locations: int
    mastery_locations: int
    basebust_locations: int
    speedrun_locations: int
    preventative_locations: int
    plando_locations: list[str]

    # Filler
    minerals_per_item: int
    vespene_per_item: int
    starting_supply_per_item: int
    maximum_supply_per_item: int
    maximum_supply_reduction_per_item: int
    lowest_maximum_supply: int
    research_cost_reduction_per_item: int

    # Mutators
    mutation_rate_source: int
    mutation_rate_limit: int
    mutation_rate_endpoint: int
    mutation_rate_order: list[str]
    detector_items: int

    # Void Trade
    enable_void_trade: int
    void_trade_age_limit: int
    void_trade_workers: int

    # Cosmetic
    player_color_terran_raynor: int
    player_color_zerg: int
    player_color_zerg_primal: int
    player_color_protoss: int
    player_color_nova: int


class Sc2SlotDataDictV4(TypedDict):
    """Slot data members that were removed from v4 -> v5"""
    version: Literal[4]
    use_nova_wol_fallback: NotRequired[int]


class Sc2SlotDataDictV3(TypedDict):
    """Slot data members that were removed from v3 -> v4"""
    version: Literal[3]
    mission_req: dict[str, dict]
    final_mission: int
    spear_of_adun_autonomously_cast_ability_presence: NotRequired[int]
    spear_of_adun_autonomously_cast_present_in_no_build: NotRequired[int]
    nova_covert_ops_only: NotRequired[int]


def pack_hero_presence(presence: dict[mission_tables.SC2Mission, tables.HeroFlag]) -> dict[str, int]:
    result: dict[str, int] = {}
    for mission, hero_flag in presence.items():
        if hero_flag != tables.HeroFlag.NONE:
            result[str(mission.id)] = hero_flag.value
    return result


def fill_slot_data(world: 'SC2World') -> Sc2SlotDataDict:
    assert world.logic
    slot_data: Sc2SlotDataDict = {
        "version": 5,
        "game_difficulty": int(world.options.game_difficulty),
        "all_in_map": int(world.options.all_in_map),
        "mission_order": int(world.options.mission_order),

        "plando_locations": locations.get_plando_locations(world),
        "hero_presence": pack_hero_presence(world.hero_presence),
        "grant_hero_items": [mission.id for mission in world.logic.grant_hero_items],
        "final_mission_ids": world.custom_mission_order.get_final_mission_ids(),
        "custom_mission_order": world.custom_mission_order.get_slot_data(),
    }
    if world.options.game_speed != options.GameSpeed.option_default:
        slot_data["game_speed"] = int(world.options.game_speed)
    if world.options.war_council_nerfs != options.WarCouncilNerfs.option_false:
        slot_data["war_council_nerfs"] = int(world.options.war_council_nerfs)
    if world.options.mercenary_highlanders != options.MercenaryHighlanders.option_false:
        slot_data["mercenary_highlanders"] = int(world.options.mercenary_highlanders)
    if world.options.generic_upgrade_missions != options.GenericUpgradeMissions.default:
        slot_data["generic_upgrade_missions"] = int(world.options.generic_upgrade_missions)

    slot_data["max_upgrade_level"] = int(world.options.max_upgrade_level)
    slot_data["generic_upgrade_research"] = int(world.options.generic_upgrade_research)
    slot_data["generic_upgrade_research_speedup"] = int(world.options.generic_upgrade_research_speedup)
    slot_data["kerrigan_primal_status"] = int(world.options.kerrigan_primal_status)
    slot_data["kerrigan_levels_per_mission_completed"] = int(world.options.kerrigan_levels_per_mission_completed)
    slot_data["kerrigan_levels_per_mission_completed_cap"] = int(world.options.kerrigan_levels_per_mission_completed_cap)
    slot_data["kerrigan_total_level_cap"] = int(world.options.kerrigan_total_level_cap)
    slot_data["enable_morphling"] = int(world.options.enable_morphling)
    slot_data["grant_story_tech"] = int(world.options.grant_story_tech)
    slot_data["grant_story_levels"] = int(world.options.grant_story_levels)
    slot_data["required_tactics"] = int(world.options.required_tactics)
    slot_data["take_over_ai_allies"] = int(world.options.take_over_ai_allies)
    slot_data["spear_of_adun_presence"] = int(world.options.spear_of_adun_presence)
    slot_data["spear_of_adun_present_in_no_build"] = int(world.options.spear_of_adun_present_in_no_build)
    slot_data["spear_of_adun_passive_ability_presence"] = int(world.options.spear_of_adun_passive_ability_presence)
    slot_data["spear_of_adun_passive_present_in_no_build"] = int(world.options.spear_of_adun_passive_present_in_no_build)

    slot_data["mission_order_scouting"] = int(world.options.mission_order_scouting)
    slot_data["vanilla_locations"] = int(world.options.vanilla_locations)
    slot_data["extra_locations"] = int(world.options.extra_locations)
    slot_data["challenge_locations"] = int(world.options.challenge_locations)
    slot_data["mastery_locations"] = int(world.options.mastery_locations)
    slot_data["basebust_locations"] = int(world.options.basebust_locations)
    slot_data["speedrun_locations"] = int(world.options.speedrun_locations)
    slot_data["preventative_locations"] = int(world.options.preventative_locations)

    slot_data["minerals_per_item"] = int(world.options.minerals_per_item)
    slot_data["vespene_per_item"] = int(world.options.vespene_per_item)
    slot_data["starting_supply_per_item"] = int(world.options.starting_supply_per_item)
    slot_data["maximum_supply_per_item"] = int(world.options.maximum_supply_per_item)
    slot_data["maximum_supply_reduction_per_item"] = int(world.options.maximum_supply_reduction_per_item)
    slot_data["lowest_maximum_supply"] = int(world.options.lowest_maximum_supply)
    slot_data["research_cost_reduction_per_item"] = int(world.options.research_cost_reduction_per_item)
    slot_data["difficulty_damage_modifier"] = int(world.options.difficulty_damage_modifier)

    slot_data["mutation_rate_source"] = int(world.options.mutation_rate_source)
    slot_data["mutation_rate_limit"] = int(world.options.mutation_rate_limit)
    slot_data["mutation_rate_endpoint"] = int(world.options.mutation_rate_endpoint)
    slot_data["mutation_rate_order"] = world.mutation_rate_order
    slot_data["detector_items"] = int(world.options.detector_items)

    if world.options.enable_void_trade != options.EnableVoidTrade.option_false:
        slot_data["enable_void_trade"] = int(world.options.enable_void_trade)
        slot_data["void_trade_age_limit"] = int(world.options.void_trade_age_limit)
        slot_data["void_trade_workers"] = int(world.options.void_trade_workers)

    if world.options.player_color_terran_raynor != options.PlayerColorTerranRaynor.option_blue:
        slot_data["player_color_terran_raynor"] = int(world.options.player_color_terran_raynor)
    if world.options.player_color_zerg != options.PlayerColorZerg.option_orange:
        slot_data["player_color_zerg"] = int(world.options.player_color_zerg)
    if world.options.player_color_zerg_primal != options.PlayerColorZerg.option_purple:
        slot_data["player_color_zerg_primal"] = int(world.options.player_color_zerg_primal)
    if world.options.player_color_protoss != options.PlayerColorZerg.option_blue:
        slot_data["player_color_protoss"] = int(world.options.player_color_protoss)
    if world.options.player_color_nova != options.PlayerColorZerg.option_dark_grey:
        slot_data["player_color_nova"] = int(world.options.player_color_nova)

    if world.options.mission_order_scouting != options.MissionOrderScouting.option_none:
        mission_item_classification: dict[str, int] = {}
        for location in world.multiworld.get_locations(world.player):
            # Event do not hold items
            if not location.is_event:
                assert location.address is not None
                assert location.item is not None
                if locations.is_victory_cache(location.address):
                    # Ensure that if there are multiple items given for finishing a mission and that at least
                    # one is progressive, the flag kept is progressive.
                    location_id = (location.address // locations.VICTORY_MODULO) * locations.VICTORY_MODULO
                    location_name = world.location_id_to_name[location_id]
                    old_classification = mission_item_classification.get(location_name, 0)
                    mission_item_classification[location_name] = old_classification | location.item.classification.as_flag()
                else:
                    mission_item_classification[location.name] = location.item.classification.as_flag()
        slot_data["mission_item_classification"] = mission_item_classification

    # Disable trade if there is no trade partner
    traders = [
        _world
        for _world in world.multiworld.worlds.values()
        if _world.game == world.game
        and _world.options.enable_void_trade == options.EnableVoidTrade.option_true  # type: ignore
    ]
    if len(traders) < 2:
        slot_data["enable_void_trade"] = options.EnableVoidTrade.option_false

    return slot_data
