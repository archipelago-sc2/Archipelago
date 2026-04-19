from __future__ import annotations

import asyncio
import collections
import copy
import glob
import shutil
import enum
import inspect
import logging
import multiprocessing
import os.path
import tempfile
import queue
import zipfile
import random
import concurrent.futures
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING, NamedTuple, Type, Sequence, Iterable

# CommonClient import first to trigger ModuleUpdater
from CommonClient import CommonContext, server_loop, ClientCommandProcessor, gui_enabled, get_base_parser, handle_url_arg
from Utils import init_logging, async_start
import Options as coreoptions
from .item import item_parents
from .item.item_annotations import ITEM_NAME_ANNOTATIONS
from .item.item_groups import item_name_groups, unlisted_item_name_groups
from . import options
from .options import (
    MissionOrder, KerriganPrimalStatus, EnableMorphling, GameDifficulty,
    GameSpeed, GenericUpgradeItems, GenericUpgradeResearch, ColorChoice, GenericUpgradeMissions, MaxUpgradeLevel,
    LocationInclusion, ExtraLocations, MasteryLocations, SpeedrunLocations, PreventativeLocations, ChallengeLocations,
    VanillaLocations, EnabledHeroes, HeroPresence,
    GrantStoryTech, GrantStoryLevels, TakeOverAIAllies, RequiredTactics,
    SpearOfAdunPresence, SpearOfAdunPresentInNoBuild, SpearOfAdunPassiveAbilityPresence,
    SpearOfAdunPassivesPresentInNoBuild, EnableVoidTrade, VoidTradeAgeLimit, void_trade_age_limits_ms, VoidTradeWorkers,
    DifficultyDamageModifier, MissionOrderScouting, GenericUpgradeResearchSpeedup, MercenaryHighlanders, WarCouncilNerfs,
)
from .mission_order.slot_data import CampaignSlotData, LayoutSlotData, MissionSlotData, MissionOrderObjectSlotData
from .mission_order.entry_rules import SubRuleRuleData, CountMissionsRuleData, MissionEntryRules
from .tables import HeroOptions, HeroFlag
from .apclient.transfer_data import worker_units
from . import SC2World
from .apclient import banks, user_paths, game_client
from .apclient.failable import Error
import settings as coresettings
from .settings import Starcraft2Settings

import nest_asyncio
from .item import item_tables
from .locations import (
    SC2WOL_LOC_ID_OFFSET, LocationType, LocationFlag, SC2HOTS_LOC_ID_OFFSET, get_location_id, VICTORY_MODULO
)
from .mission_tables import (
    lookup_id_to_mission, SC2Campaign, MissionInfo,
    lookup_id_to_campaign, SC2Mission, campaign_mission_table,
    lookup_id_to_race, SC2Race,
)
import colorama
from NetUtils import (
    NetworkItem, JSONtoTextParser, JSONMessagePart, add_json_item, add_json_location, add_json_text, JSONTypes
)
from MultiServer import mark_raw


sc2_logger = logging.getLogger("Starcraft2")

pool = concurrent.futures.ThreadPoolExecutor(1)
loop = asyncio.get_event_loop_policy().new_event_loop()
nest_asyncio.apply(loop)

# GitHub repo where the Map/mod data is hosted for /download_data command
DATA_REPO_OWNER = "archipelago-sc2"
DATA_REPO_NAME = "Archipelago-SC2-data"
DATA_API_VERSION = "API5"

# Void Trade
TRADE_DATASTORAGE_TEAM = "SC2_VoidTrade_" # + Team
TRADE_DATASTORAGE_SLOT = "slot_" # + Slot
TRADE_DATASTORAGE_LOCK = "_lock"
TRADE_LOCK_TIME = 5 # Time in seconds that the DataStorage may be considered safe to edit
TRADE_LOCK_WAIT_LIMIT = 540000 / 1.4 # Time in ms that the client may spend trying to get a lock (540000 = 9 minutes, 1.4 is 'faster' game speed's time scale)

# Games
STARCRAFT2 = "Starcraft 2"
STARCRAFT2_WOL = "Starcraft 2 Wings of Liberty"

# Data version file path.
# This file is used to tell if the downloaded data are outdated
# Associated with /download_data command
def get_metadata_file() -> str:
    sc2_install_dir = user_paths.get_sc2_install_dir()
    if isinstance(sc2_install_dir, Error):
        sc2_logger.error(sc2_install_dir.message)
        return ""
    return os.path.join(sc2_install_dir, "ArchipelagoSC2Metadata.txt")

def _remap_color_option(slot_data_version: int, color: int) -> int:
    """Remap colour options for backwards compatibility with older slot data"""
    if slot_data_version < 4 and color == ColorChoice.option_mengsk:
        return ColorChoice.option_default
    return color


class ConfigurableOptionType(enum.Enum):
    INTEGER = enum.auto()
    ENUM = enum.auto()
    SETTING = enum.auto()


class ConfigurableOptionInfo(NamedTuple):
    variable_name: str
    option_class: Type[coreoptions.Option]
    option_type: ConfigurableOptionType = ConfigurableOptionType.ENUM
    can_break_logic: bool = False


@dataclass
class ConfigurableSettingInfo:
    setting_name: str
    option_class: Type[coresettings.Bool] | Type[str] | Type[int]


class ColouredMessage:
    def __init__(self, text: str = '', *, keep_markup: bool = False) -> None:
        self.parts: list[dict[str, Any]] = []
        if text:
            self(text, keep_markup=keep_markup)
    def __call__(self, text: str, *, keep_markup: bool = False) -> 'ColouredMessage':
        add_json_text(self.parts, text, keep_markup=keep_markup)
        return self
    def coloured(self, text: str, colour: str, *, keep_markup: bool = False) -> 'ColouredMessage':
        add_json_text(self.parts, text, type="color", color=colour, keep_markup=keep_markup)
        return self
    def location(self, location_id: int, player_id: int) -> 'ColouredMessage':
        add_json_location(self.parts, location_id, player_id)
        return self
    def item(self, item_id: int, player_id: int, flags: int = 0) -> 'ColouredMessage':
        add_json_item(self.parts, item_id, player_id, flags)
        return self
    def player(self, player_id: int) -> 'ColouredMessage':
        add_json_text(self.parts, str(player_id), type=JSONTypes.player_id)
        return self
    def send(self, ctx: SC2Context) -> None:
        ctx.on_print_json({"data": self.parts, "cmd": "PrintJSON"})


class StarcraftClientProcessor(ClientCommandProcessor):
    ctx: SC2Context

    def formatted_print(self, text: str) -> None:
        """Prints with kivy formatting to the GUI, and also prints to command-line and to all logs"""
        # Note(mm): Bold/underline can help readability, but unfortunately the CommonClient does not filter bold tags from command-line output.
        # Regardless, using `on_print_json` to get formatted text in the GUI and output in the command-line and in the logs,
        # without having to branch code from CommonClient
        self.ctx.on_print_json({"data": [{"text": text, "keep_markup": True}]})

    @mark_raw
    def _cmd_difficulty(self, difficulty: str = "") -> bool:
        """Overrides the current difficulty set for the world.  Takes the argument casual, normal, hard, or brutal"""
        arguments = difficulty.split()
        num_arguments = len(arguments)

        if num_arguments > 0:
            difficulty_choice = arguments[0].lower()
            if difficulty_choice == "casual":
                self.ctx.difficulty_override = 0
            elif difficulty_choice == "normal":
                self.ctx.difficulty_override = 1
            elif difficulty_choice == "hard":
                self.ctx.difficulty_override = 2
            elif difficulty_choice == "brutal":
                self.ctx.difficulty_override = 3
            else:
                self.output("Unable to parse difficulty '" + arguments[0] + "'")
                return False

            self.output("Difficulty set to " + arguments[0])
            return True

        else:
            if self.ctx.difficulty == -1:
                self.output("Please connect to a seed before checking difficulty.")
            else:
                current_difficulty = self.ctx.difficulty
                if self.ctx.difficulty_override >= 0:
                    current_difficulty = self.ctx.difficulty_override
                self.output("Current difficulty: " + ["Casual", "Normal", "Hard", "Brutal"][current_difficulty])
            self.output("To change the difficulty, add the name of the difficulty after the command.")
            return False

    @mark_raw
    def _cmd_game_speed(self, game_speed: str = "") -> bool:
        """Overrides the current game speed for the world.
         Takes the arguments default, slower, slow, normal, fast, faster"""
        arguments = game_speed.split()
        num_arguments = len(arguments)

        if num_arguments > 0:
            speed_choice = arguments[0].lower()
            if speed_choice == "default":
                self.ctx.game_speed_override = 0
            elif speed_choice == "slower":
                self.ctx.game_speed_override = 1
            elif speed_choice == "slow":
                self.ctx.game_speed_override = 2
            elif speed_choice == "normal":
                self.ctx.game_speed_override = 3
            elif speed_choice == "fast":
                self.ctx.game_speed_override = 4
            elif speed_choice == "faster":
                self.ctx.game_speed_override = 5
            else:
                self.output("Unable to parse game speed '" + arguments[0] + "'")
                return False

            self.output("Game speed set to " + arguments[0])
            return True

        else:
            if self.ctx.game_speed == -1:
                self.output("Please connect to a seed before checking game speed.")
            else:
                current_speed = self.ctx.game_speed
                if self.ctx.game_speed_override >= 0:
                    current_speed = self.ctx.game_speed_override
                self.output("Current game speed: "
                            + ["Default", "Slower", "Slow", "Normal", "Fast", "Faster"][current_speed])
            self.output("To change the game speed, add the name of the speed after the command,"
                        " or Default to select based on difficulty.")
            return False

    @mark_raw
    def _cmd_received(self, filter_search: str = "") -> bool:
        """List received items.
        Pass in a parameter to filter the search by partial item name or exact item group.
        Use '/received recent <number>' to list the last 'number' items received (default 20)."""
        if self.ctx.slot is None:
            self.formatted_print("Connect to a slot to view what items are received.")
            return True
        if filter_search.casefold().startswith('recent'):
            return self._received_recent(filter_search[len('recent'):].strip())
        # Groups must be matched case-sensitively, so we properly capitalize the search term
        # eg. "Spear of Adun" over "Spear Of Adun" or "spear of adun"
        # This fails a lot of item name matches, but those should be found by partial name match
        group_filter = ''
        for group_name in item_name_groups:
            if group_name in unlisted_item_name_groups:
                continue
            if filter_search.casefold() == group_name.casefold():
                group_filter = group_name
                break

        def item_matches_filter(item_name: str) -> bool:
            # The filter can be an exact group name or a partial item name
            # Partial item name can be matched case-insensitively
            if filter_search.casefold() in item_name.casefold():
                return True
            # The search term should already be formatted as a group name
            if group_filter and item_name in item_name_groups[group_filter]:
                return True
            return False

        items = item_tables.item_table
        categorized_items: dict[SC2Race, list[int | str]] = {}
        parent_to_child: dict[int | str, list[int]] = {}
        items_received: dict[int, list[NetworkItem]] = {}
        for item in self.ctx.items_received:
            items_received.setdefault(item.item, []).append(item)
        items_received_set = set(items_received)
        for item_data in items.values():
            if item_data.parent:
                parent_rule = item_parents.parent_present[item_data.parent]
                if parent_rule.constraint_group is not None and parent_rule.constraint_group in items:
                    parent_to_child.setdefault(items[parent_rule.constraint_group].code, []).append(item_data.code)
                    continue
                race = items[parent_rule.parent_items()[0]].race
                categorized_items.setdefault(race, [])
                if parent_rule.display_string not in categorized_items[race]:
                    categorized_items[race].append(parent_rule.display_string)
                parent_to_child.setdefault(parent_rule.display_string, []).append(item_data.code)
            else:
                categorized_items.setdefault(item_data.race, []).append(item_data.code)

        def display_info(element: SC2Race | str | int) -> tuple:
            """Return (should display, name, type, children, sum(obtained), sum(matching filter))"""
            have_item = isinstance(element, int) and element in items_received_set
            if isinstance(element, SC2Race):
                children: Sequence[str | int] = categorized_items[faction]
                name = element.name
            elif isinstance(element, int):
                children = parent_to_child.get(element, [])
                name = self.ctx.item_names.lookup_in_game(element)
            else:
                assert isinstance(element, str)
                children = parent_to_child[element]
                name = element
            matches_filter = item_matches_filter(name)
            child_states = [display_info(child) for child in children]
            return (
                (have_item and matches_filter) or any(child_state[0] for child_state in child_states),
                name,
                element,
                child_states,
                sum(child_state[4] for child_state in child_states) + have_item,
                sum(child_state[5] for child_state in child_states) + (have_item and matches_filter),
            )

        def display_tree(
            should_display: bool, name: str, element: SC2Race | str | int, child_states: tuple, indent: int = 0
        ) -> None:
            if not should_display:
                return
            assert self.ctx.slot is not None
            indent_str = " " * indent
            if isinstance(element, SC2Race):
                self.formatted_print(f" [u]{name}[/u] ")
                for child in child_states:
                    display_tree(*child[:4])
            elif isinstance(element, str):
                ColouredMessage(indent_str)("- ").coloured(name, "white").send(self.ctx)
                for child in child_states:
                    display_tree(*child[:4], indent=indent+2)  # type: ignore
            elif isinstance(element, int):
                items = items_received.get(element, [])
                if not items:
                    ColouredMessage(indent_str)("- ").coloured(name, "red")(" - not obtained").send(self.ctx)
                for item in items:
                    (ColouredMessage(indent_str)('- ')
                        .item(item.item, self.ctx.slot, flags=item.flags)
                        (" from ").location(item.location, item.player)
                        (" by ").player(item.player)
                    ).send(self.ctx)
                for child in child_states:
                    display_tree(*child[:4], indent=indent+2)  # type: ignore
            non_matching_descendents = sum(child[5] - child[4] for child in children)
            if non_matching_descendents > 0:
                self.formatted_print(f"{indent_str}  + {non_matching_descendents} child items that don't match the filter")


        item_types_obtained = 0
        items_obtained_matching_filter = 0
        for faction in SC2Race:
            should_display, name, element, children, faction_items_obtained, faction_items_matching_filter = display_info(faction)
            item_types_obtained += faction_items_obtained
            items_obtained_matching_filter += faction_items_matching_filter
            display_tree(should_display, name, element, children)
        if filter_search == "":
            self.formatted_print(f"[b]Obtained: {len(self.ctx.items_received)} items ({item_types_obtained} types)[/b]")
        else:
            self.formatted_print(f"[b]Filter \"{filter_search}\" found {items_obtained_matching_filter} out of {item_types_obtained} obtained item types[/b]")
        return True

    def _received_recent(self, amount: str) -> bool:
        assert self.ctx.slot is not None
        try:
            display_amount = int(amount)
        except ValueError:
            display_amount = 20
        display_amount = min(display_amount, len(self.ctx.items_received))
        self.formatted_print(f"Last {display_amount} of {len(self.ctx.items_received)} items received (most recent last):")
        for item in self.ctx.items_received[-display_amount:]:
            (
                ColouredMessage()
                .item(item.item, self.ctx.slot, item.flags)
                (" from ").location(item.location, item.player)
                (" by ").player(item.player)
            ).send(self.ctx)
        return True

    @mark_raw
    def _cmd_option(self, option_name: str = "", option_value: str = "") -> None:
        """Sets a Starcraft game option that can be changed after generation. Use "/option list" to see all options."""

        # Manually parse arguments so the user doesn't see a stack trace if they provide too many arguments
        arguments = parse_client_cmd_args(option_name, 2, "/option")
        if isinstance(arguments, Error):
            self.output(arguments.message)
            return
        option_name, option_value = arguments

        LOGIC_WARNING = "  *Note changing this may result in logically unbeatable games*\n"

        configurable_options: dict[str, ConfigurableOptionInfo | ConfigurableSettingInfo] = {
            # Kerrigan
            'kerrigan_level_cap': ConfigurableOptionInfo('kerrigan_total_level_cap', options.KerriganTotalLevelCap, ConfigurableOptionType.INTEGER, can_break_logic=True),
            'kerrigan_mission_level_cap': ConfigurableOptionInfo('kerrigan_levels_per_mission_completed_cap', options.KerriganLevelsPerMissionCompletedCap, ConfigurableOptionType.INTEGER),
            'kerrigan_levels_per_mission': ConfigurableOptionInfo('kerrigan_levels_per_mission_completed', options.KerriganLevelsPerMissionCompleted, ConfigurableOptionType.INTEGER),
            'grant_story_levels': ConfigurableOptionInfo('grant_story_levels', options.GrantStoryLevels, can_break_logic=True),

            'grant_story_tech': ConfigurableOptionInfo('grant_story_tech', options.GrantStoryTech, can_break_logic=True),
            'control_ally': ConfigurableOptionInfo('take_over_ai_allies', options.TakeOverAIAllies, can_break_logic=True),
            # SoA
            'soa_presence': ConfigurableOptionInfo('spear_of_adun_presence', options.SpearOfAdunPresence, can_break_logic=True),
            'soa_in_nobuilds': ConfigurableOptionInfo('spear_of_adun_present_in_no_build', options.SpearOfAdunPresentInNoBuild, can_break_logic=True),
            'soa_passive_presence': ConfigurableOptionInfo('spear_of_adun_passive_ability_presence', options.SpearOfAdunPassiveAbilityPresence, can_break_logic=True),
            'soa_passives_in_nobuilds': ConfigurableOptionInfo('spear_of_adun_passive_present_in_no_build', options.SpearOfAdunPassivesPresentInNoBuild),
            # Fillers
            'minerals_per_item': ConfigurableOptionInfo('minerals_per_item', options.MineralsPerItem, ConfigurableOptionType.INTEGER),
            'gas_per_item': ConfigurableOptionInfo('vespene_per_item', options.VespenePerItem, ConfigurableOptionType.INTEGER),
            'supply_per_item': ConfigurableOptionInfo('starting_supply_per_item', options.StartingSupplyPerItem, ConfigurableOptionType.INTEGER),
            'max_supply_per_item': ConfigurableOptionInfo('maximum_supply_per_item', options.MaximumSupplyPerItem, ConfigurableOptionType.INTEGER),
            'reduced_supply_per_item': ConfigurableOptionInfo('maximum_supply_reduction_per_item', options.MaximumSupplyReductionPerItem, ConfigurableOptionType.INTEGER),
            'lowest_max_supply': ConfigurableOptionInfo('lowest_maximum_supply', options.LowestMaximumSupply, ConfigurableOptionType.INTEGER),
            'research_cost_per_item': ConfigurableOptionInfo('research_cost_reduction_per_item', options.ResearchCostReductionPerItem, ConfigurableOptionType.INTEGER),
            # settings / adjustments
            'speed': ConfigurableOptionInfo('game_speed', options.GameSpeed),
            'difficulty': ConfigurableOptionInfo('game_difficulty', options.GameDifficulty),
            'no_forced_camera': ConfigurableSettingInfo('game_disable_forced_camera', Starcraft2Settings.GameDisableForcedCamera),
            'skip_cutscenes': ConfigurableSettingInfo('game_skip_cutscenes', Starcraft2Settings.GameSkipCutscenes),
            'scouting': ConfigurableOptionInfo('mission_order_scouting', options.MissionOrderScouting),
            'scouting_show_traps': ConfigurableSettingInfo('scouting_show_traps', Starcraft2Settings.ScoutingShowTraps),
            'enable_morphling': ConfigurableOptionInfo('enable_morphling', options.EnableMorphling, can_break_logic=True),
            'difficulty_damage_modifier': ConfigurableOptionInfo('difficulty_damage_modifier', options.DifficultyDamageModifier),
            'void_trade_age_limit': ConfigurableOptionInfo('trade_age_limit', options.VoidTradeAgeLimit),
            'void_trade_workers': ConfigurableOptionInfo('trade_workers_allowed', options.VoidTradeWorkers),
            'mercenary_highlanders': ConfigurableOptionInfo('mercenary_highlanders', options.MercenaryHighlanders),
            # Misc
            'max_upgrade_level': ConfigurableOptionInfo('max_upgrade_level', options.MaxUpgradeLevel, ConfigurableOptionType.INTEGER),
            'generic_upgrade_research': ConfigurableOptionInfo('generic_upgrade_research', options.GenericUpgradeResearch, can_break_logic=True),
            'generic_upgrade_research_speedup': ConfigurableOptionInfo('generic_upgrade_research_speedup', options.GenericUpgradeResearchSpeedup),
        }

        WARNING_COLOUR = "salmon"
        CMD_COLOUR = "slateblue"
        LOGIC_WARNING = "**"
        boolean_option_map = {
            'true': 'true', 'y': 'true', 'yes': 'true', '+': 'true',
            'false': 'false', 'n': 'false', 'no': 'false', '-': 'false',
        }

        # Construct help text
        help_message = (ColouredMessage(inspect.cleandoc("""
            Options
        --------------------
        """))
            ("\n * Options marked with a ")
            .coloured(LOGIC_WARNING, WARNING_COLOUR)
            (" may break logic if changed.\n")
        )
        for this_option_name, option in configurable_options.items():
            option_help_text = inspect.cleandoc(option.option_class.__doc__ or "No description provided.").split('\n', 1)[0]
            if not option_help_text.endswith("."):
                option_help_text += "."
            help_message.coloured(this_option_name, CMD_COLOUR)
            if isinstance(option, ConfigurableOptionInfo):
                if option.can_break_logic:
                    help_message.coloured(LOGIC_WARNING, WARNING_COLOUR)
                help_message(": " + " | ".join(option.option_class.options) + f" -- {option_help_text}\n")
            else:
                if issubclass(option.option_class, int):
                    help_message(f": integer -- {option_help_text}\n")
                elif issubclass(option.option_class, coresettings.Bool):
                    # Note(mm): Copying display order of choices in coreoptions.Toggle
                    help_message(f": false | true -- {option_help_text}\n")
                else:
                    help_message(f": {option_help_text}\n")
        help_message("--------------------\nEnter an option without arguments to see its current value.\n")

        # Display help text
        if not option_name or option_name == 'list' or option_name == 'help':
            help_message.send(self.ctx)
            return
        option = configurable_options.get(option_name)
        if not option:
            help_message.send(self.ctx)
            self.output(f"Unknown option '{option_name}")
            return

        option_value = boolean_option_map.get(option_value.lower(), option_value)
        if not option_value:
            pass
        elif isinstance(option, ConfigurableSettingInfo):
            if issubclass(option.option_class, coresettings.Bool):
                if option_value == 'true':
                    SC2World.settings.__dict__[option.setting_name] = True
                elif option_value == 'false':
                    SC2World.settings.__dict__[option.setting_name] = False
                else:
                    self.output(f"{option_value} is not a valid true/false value")
            elif issubclass(option.option_class, int):
                try:
                    int_value = int(option_value, base=0)
                    SC2World.settings.__dict__[option.setting_name] = int_value
                except ValueError:
                    self.output(f"{option_value} is not a valid integer")
            else:
                SC2World.settings.__dict__[option.setting_name] = option_value
            force_settings_save_on_close()
        elif option.option_type == ConfigurableOptionType.ENUM and option_value in option.option_class.options:
            self.ctx.__dict__[option.variable_name] = option.option_class.options[option_value]
        elif option.option_type == ConfigurableOptionType.INTEGER:
            try:
                self.ctx.__dict__[option.variable_name] = int(option_value, base=0)
            except:
                self.output(f"{option_value} is not a valid integer")
        else:
            self.output(f"Unknown option value '{option_value}'")
        if isinstance(option, ConfigurableSettingInfo):
            presentable_value = str(SC2World.settings.__dict__.get(
                option.setting_name,
                Starcraft2Settings.__dict__[option.setting_name])
            ).lower()
        elif issubclass(option.option_class, coreoptions.Toggle):
            # get_option_name() will return 'yes' and 'no' for Toggles, which looks wrong in the UI
            presentable_value = 'true' if self.ctx.__dict__[option.variable_name] else 'false'
        else:
            presentable_value = option.option_class.get_option_name(self.ctx.__dict__[option.variable_name])
        ColouredMessage(f"{option_name} is '{presentable_value}'").send(self.ctx)
        if "scouting" in option_name and self.ctx.ui is not None:
            # Some options, particularly those affecting scouting, require a redraw
            self.ctx.ui.pending_redraw = True

    @mark_raw
    def _cmd_color(self, faction: str = "", color: str = "") -> None:
        """takes faction, color. Changes the player color for a given faction."""
        arguments = parse_client_cmd_args(faction, 2, "/color")
        if isinstance(arguments, Error):
            self.output(arguments.message)
            return
        faction, color = arguments
        player_colors = [
            "White", "Red", "Blue", "Teal",
            "Purple", "Yellow", "Orange", "Green",
            "LightPink", "Violet", "LightGrey", "DarkGreen",
            "Brown", "LightGreen", "DarkGrey", "Pink",
            "Rainbow", "Mengsk", "BrightLime", "Arcane", "Ember", "HotPink",
            "Random", "Default"
        ]
        var_names = {
            'raynor': 'player_color_raynor',
            'kerrigan': 'player_color_zerg',
            'primal': 'player_color_zerg_primal',
            'protoss': 'player_color_protoss',
            'nova': 'player_color_nova',
        }
        faction = faction.lower()
        if not faction:
            for faction_name, key in var_names.items():
                self.output(f"Current player color for {faction_name}: {player_colors[self.ctx.__dict__[key]]}")
            self.output("To change your color, add the faction name and color after the command.")
            self.output("Available factions: " + ', '.join(var_names))
            self.output("Available colors: " + ', '.join(player_colors))
            return
        elif faction not in var_names:
            self.output(f"Unknown faction '{faction}'.")
            self.output("Available factions: " + ', '.join(var_names))
            return
        match_colors = [player_color.lower() for player_color in player_colors]
        if not color:
            self.output(f"Current player color for {faction}: {player_colors[self.ctx.__dict__[var_names[faction]]]}")
            self.output("To change this faction's colors, add the name of the color after the command.")
            self.output("Available colors: " + ', '.join(player_colors))
        else:
            if color.lower() not in match_colors:
                self.output(color + " is not a valid color.  Available colors: " + ', '.join(player_colors))
                return
            if color.lower() == "random":
                color = random.choice(player_colors[:-2])
            self.ctx.__dict__[var_names[faction]] = match_colors.index(color.lower())
            self.ctx.pending_color_update = True
            self.output(f"Color for {faction} set to " + player_colors[self.ctx.__dict__[var_names[faction]]])

    @mark_raw
    def _cmd_windowed_mode(self, true_or_false: str = "") -> None:
        """Controls whether sc2 will launch in Windowed mode. Persists across sessions."""
        if not true_or_false:
            sc2_logger.info("Use `/windowed_mode [true|false]` to set the windowed mode")
        elif true_or_false.casefold() in ('t', 'true', 'yes', 'y', '+'):
            SC2World.settings.game_windowed_mode = True
            force_settings_save_on_close()
        else:
            SC2World.settings.game_windowed_mode = False
            force_settings_save_on_close()
        sc2_logger.info(f"Windowed mode is: {SC2World.settings.game_windowed_mode}")

    @mark_raw
    def _cmd_mission_check(self, enable_or_disable: str = "") -> bool:
        """
        If disabled, allows playing missions even if they are not unlocked.
        """
        if enable_or_disable.casefold() in ("n", "no", "f", "false", "-", "disable", "disabled"):
            if (not self.ctx.missions_unlocked) and self.ctx.ui:
                self.ctx.ui.pending_redraw = True
            self.ctx.missions_unlocked = True
            sc2_logger.info("Mission check has been disabled")
        else:
            if self.ctx.missions_unlocked and self.ctx.ui:
                self.ctx.ui.pending_redraw = True
            self.ctx.missions_unlocked = False
            sc2_logger.info("Mission check has been enabled")
        return True

    @mark_raw
    def _cmd_set_path(self, path: str = "") -> bool:
        """Manually set the SC2 install directory (if the automatic detection fails)."""
        if path:
            SC2World.settings.sc2_install_path = SC2World.settings.Sc2InstallPath(path)
            force_settings_save_on_close()
            is_mod_installed_correctly()
            return True
        else:
            sc2_logger.warning("When using set_path, you must type the path to your SC2 install directory.")
        user_paths.reset_cache()
        return False

    def _cmd_download_data(self) -> bool:
        """Download the most recent release of the necessary files for playing SC2 with
        Archipelago. Will overwrite existing files."""
        pool.submit(self._download_data, self.ctx)
        return True

    @staticmethod
    def _download_data(ctx: SC2Context) -> bool:
        sc2_install_dir = user_paths.get_sc2_install_dir()
        if isinstance(sc2_install_dir, Error):
            sc2_logger.warning(sc2_install_dir.message)
            return False
        if os.path.exists(get_metadata_file()):
            with open(get_metadata_file(), "r") as f:
                metadata = f.read()
        else:
            metadata = None

        tempzip, metadata = download_latest_release_zip(
            DATA_REPO_OWNER, DATA_REPO_NAME, DATA_API_VERSION,
            ctx,
            metadata=metadata,
            force_download=True,
        )

        if not tempzip:
            sc2_logger.warning("Download aborted/failed. Read the log for more information.")
            return False

        ap_map_folders = glob.glob(os.path.join(sc2_install_dir, "Maps", "ArchipelagoCampaign", "*"))
        for folder in ap_map_folders:
            if folder.endswith(".bak"):
                continue
            backup_folder = folder + ".backup"
            if os.path.exists(backup_folder):
                shutil.rmtree(backup_folder)
            shutil.move(folder, backup_folder)

        try:
            zipfile.ZipFile(tempzip).extractall(path=sc2_install_dir)
            sc2_logger.info("Download complete. Package installed.")
            if metadata is not None:
                with open(get_metadata_file(), "w") as f:
                    f.write(metadata)
            for folder in ap_map_folders:
                shutil.rmtree(folder + ".backup")
            ctx.data_out_of_date = False
        except Exception as ex:
            sc2_logger.error(f"An error occurred while trying to unzip the archive: {ex}")
            for folder in ap_map_folders:
                if os.path.exists(folder):
                    shutil.rmtree(folder)
                backup_folder = folder + ".backup"
                shutil.move(backup_folder, folder)
        finally:
            os.remove(tempzip)

        return True


def parse_client_cmd_args(args: str, num_args: int, command_name: str) -> Error[str] | list[str]:
    """
    Split arguments by spaces and return as a list.
    Pads the list with empty strings if too few arguments are given.
    Returns an error if too many arguments are given.
    Use this with @mark_raw to make sure the user doesn't see a stack trace if they provide too many args.
    """
    result = [t for t in args.split(" ") if t]
    if len(result) > num_args:
        return Error(
            f"Too many arguments provided to {command_name}. Expected {num_args}, got {len(result)}"
        )
    while len(result) < num_args:
        result.append("")
    return result


class SC2JSONtoTextParser(JSONtoTextParser):
    def __init__(self, ctx: SC2Context) -> None:
        self.handlers = {
            "ItemSend": self._handle_color,
            "ItemCheat": self._handle_color,
            "Hint": self._handle_color,
        }
        super().__init__(ctx)

    def _handle_color(self, node: JSONMessagePart) -> str:
        codes = node["color"].split(";")
        buffer = "".join(self.color_code(code) for code in codes if code in self.color_codes)
        return buffer + self._handle_text(node) + '</c>'

    def _handle_item_name(self, node: JSONMessagePart) -> str:
        if self.ctx.slot_info[node["player"]].game == STARCRAFT2:
            annotation = ITEM_NAME_ANNOTATIONS.get(node["text"])
            if annotation is not None:
                node["text"] += f" {annotation}"
        return super()._handle_item_name(node)

    def color_code(self, code: str) -> str:
        return '<c val="' + self.color_codes[code] + '">'


class SC2Context(CommonContext):
    command_processor = StarcraftClientProcessor
    game = STARCRAFT2
    items_handling = 0b111

    def __init__(self, *args, **kwargs) -> None:
        super(SC2Context, self).__init__(*args, **kwargs)
        self.raw_text_parser = SC2JSONtoTextParser(self)  # type: ignore

        self.data_out_of_date: bool = False
        self.difficulty = -1
        self.game_speed = -1
        self.all_in_choice = 0
        self.mission_order = 0
        self.player_color_raynor = ColorChoice.option_blue
        self.player_color_zerg = ColorChoice.option_orange
        self.player_color_zerg_primal = ColorChoice.option_purple
        self.player_color_protoss = ColorChoice.option_blue
        self.player_color_nova = ColorChoice.option_dark_grey
        self.pending_color_update = False
        self.kerrigan_primal_status = 0
        self.enable_morphling = EnableMorphling.default
        self.custom_mission_order: list[CampaignSlotData] = []
        self.mission_id_to_entry_rules: dict[int, MissionEntryRules]
        self.final_mission_ids: list[int] = [29]
        self.final_locations: list[int] = []
        self.announcements: queue.Queue = queue.Queue()
        self.missions_unlocked: bool = False  # allow launching missions ignoring requirements
        self.max_upgrade_level: int = MaxUpgradeLevel.default
        self.generic_upgrade_missions = 0
        self.generic_upgrade_research = 0
        self.generic_upgrade_research_speedup: int = GenericUpgradeResearchSpeedup.default
        self.generic_upgrade_items = 0
        self.location_inclusions: dict[LocationType, int] = {}
        self.location_inclusions_by_flag: dict[LocationFlag, int] = {}
        self.plando_locations: list[str] = []
        self.difficulty_override = -1
        self.game_speed_override = -1
        self.mission_id_to_location_ids: dict[int, list[int]] = {}
        self.mission_client: game_client.MissionClient | None = None
        self.slot_data_version = 2
        self.required_tactics: int = RequiredTactics.default
        self.grant_story_tech: int = GrantStoryTech.default
        self.grant_story_levels: int = GrantStoryLevels.default
        self.take_over_ai_allies: int = TakeOverAIAllies.default
        self.spear_of_adun_presence = SpearOfAdunPresence.option_not_present
        self.spear_of_adun_present_in_no_build = SpearOfAdunPresentInNoBuild.option_false
        self.spear_of_adun_passive_ability_presence = SpearOfAdunPassiveAbilityPresence.option_not_present
        self.spear_of_adun_passive_present_in_no_build = SpearOfAdunPassivesPresentInNoBuild.option_false
        self.minerals_per_item: int = 15  # For backwards compat with games generated pre-0.4.5
        self.vespene_per_item: int =  15  # For backwards compat with games generated pre-0.4.5
        self.starting_supply_per_item: int = 2  # For backwards compat with games generated pre-0.4.5
        self.maximum_supply_per_item: int = 2
        self.maximum_supply_reduction_per_item: int = options.MaximumSupplyReductionPerItem.default
        self.lowest_maximum_supply: int = options.LowestMaximumSupply.default
        self.research_cost_reduction_per_item: int = options.ResearchCostReductionPerItem.default
        self.enabled_heroes: frozenset[str] = EnabledHeroes.default
        self.hero_presence: dict[SC2Campaign, dict[SC2Race], int] = HeroPresence.default
        self.mercenary_highlanders: bool = False
        self.kerrigan_levels_per_mission_completed = 0
        self.trade_enabled: int = EnableVoidTrade.default
        self.trade_age_limit: int = VoidTradeAgeLimit.default
        self.trade_workers_allowed: int = VoidTradeWorkers.default
        self.trade_underway: bool = False
        self.trade_latest_reply: dict[str, Any] | None = None
        self.trade_reply_event = asyncio.Event()
        self.trade_lock_wait: float = 0.0
        self.trade_lock_start: float | None = None
        self.trade_response: str | None = None
        self.difficulty_damage_modifier: int = DifficultyDamageModifier.default
        self.mission_order_scouting = MissionOrderScouting.option_none
        self.mission_item_classification: dict[str, int] | None = None
        self.show_war_council_nerfs: bool = False

    async def server_auth(self, password_requested: bool = False) -> None:
        self.game = STARCRAFT2
        if password_requested and not self.password:
            await super(SC2Context, self).server_auth(password_requested)
        await self.get_username()
        await self.send_connect()
        if self.ui:
            self.ui.first_check = True

    def is_legacy_game(self):
        return self.game == STARCRAFT2_WOL

    def event_invalid_game(self):
        if self.is_legacy_game():
            self.game = STARCRAFT2
            super().event_invalid_game()
        else:
            self.game = STARCRAFT2_WOL
            async_start(self.send_connect())

    def trade_storage_team(self) -> str:
        return f"{TRADE_DATASTORAGE_TEAM}{self.team}"

    def trade_storage_slot(self) -> str:
        return f"{TRADE_DATASTORAGE_SLOT}{self.slot}"

    def _apply_host_settings_to_options(self) -> None:
        if str(SC2World.settings.game_difficulty).casefold() == 'casual':
            self.difficulty = GameDifficulty.option_casual
        elif str(SC2World.settings.game_difficulty).casefold() == 'normal':
            self.difficulty = GameDifficulty.option_normal
        elif str(SC2World.settings.game_difficulty).casefold() == 'hard':
            self.difficulty = GameDifficulty.option_hard
        elif str(SC2World.settings.game_difficulty).casefold() == 'brutal':
            self.difficulty = GameDifficulty.option_brutal

        if str(SC2World.settings.game_speed).casefold() == 'slower':
            self.game_speed = GameSpeed.option_slower
        elif str(SC2World.settings.game_speed).casefold() == 'slow':
            self.game_speed = GameSpeed.option_slow
        elif str(SC2World.settings.game_speed).casefold() == 'normal':
            self.game_speed = GameSpeed.option_normal
        elif str(SC2World.settings.game_speed).casefold() == 'fast':
            self.game_speed = GameSpeed.option_fast
        elif str(SC2World.settings.game_speed).casefold() == 'faster':
            self.game_speed = GameSpeed.option_faster

    def unpack_hero_presence(self, slot_data: dict[str, str]) -> dict[SC2Campaign, dict[SC2Race, int]]:
        campaigns = [campaign for campaign in SC2Campaign if campaign != SC2Campaign.GLOBAL]
        result: dict[SC2Campaign, dict[SC2Race, int]] = {campaign: {} for campaign in campaigns}
        for key, value in slot_data.items():
            campaign, race, = key.split(".")
            result[lookup_id_to_campaign[int(campaign)]][lookup_id_to_race[int(race)]] = int(value)
        return result

    def default_hero_presence(self, kerrigan_present: bool = True) -> dict[SC2Campaign, dict[SC2Race, int]]:
        if kerrigan_present:
            return {
                SC2Campaign.HOTS: {SC2Race.ZERG: HeroFlag.KERRIGAN.value},
                SC2Campaign.NCO: {SC2Race.TERRAN: HeroFlag.NOVA.value},
            }
        else:
            return {
                # only used by compat code
                SC2Campaign.NCO: {SC2Race.TERRAN: HeroFlag.NOVA.value},
            }


    def on_package(self, cmd: str, args: dict) -> None:
        if cmd == "Connected":
            # Set up the trade storage
            async_start(self.send_msgs([
                { # We want to know about other clients' Set commands for locking
                    "cmd": "SetNotify",
                    "keys": [self.trade_storage_team()],
                },
                {
                    "cmd": "Set",
                    "key": self.trade_storage_team(),
                    "default": { TRADE_DATASTORAGE_LOCK: 0 },
                    "operations": [{"operation": "default", "value": None}]  # value is ignored
                }
            ]))

            self.difficulty = args["slot_data"]["game_difficulty"]
            self.game_speed = args["slot_data"].get("game_speed", GameSpeed.option_default)
            self.all_in_choice = args["slot_data"]["all_in_map"]
            self.slot_data_version = args["slot_data"].get("version", 2)

            self._apply_host_settings_to_options()

            if self.slot_data_version < 4:
                # Maintaining backwards compatibility with older slot data
                slot_req_table: dict = args["slot_data"]["mission_req"]

                first_item = list(slot_req_table.keys())[0]
                if first_item in [str(campaign.id) for campaign in SC2Campaign]:
                    # Multi-campaign
                    mission_req_table = {}
                    for campaign_id in slot_req_table:
                        campaign = lookup_id_to_campaign[int(campaign_id)]
                        mission_req_table[campaign] = {
                            mission: self.parse_mission_info(mission_info)
                            for mission, mission_info in slot_req_table[campaign_id].items()
                        }
                else:
                    # Old format
                    mission_req_table = {SC2Campaign.GLOBAL: {
                            mission: self.parse_mission_info(mission_info)
                            for mission, mission_info in slot_req_table.items()
                        }
                    }

                self.custom_mission_order = self.parse_mission_req_table(mission_req_table)

            if self.slot_data_version >= 4:
                self.custom_mission_order = [
                    CampaignSlotData(
                        **{field:value for field, value in campaign_data.items() if field not in ["layouts", "entry_rule"]},
                        entry_rule = SubRuleRuleData.parse_from_dict(campaign_data["entry_rule"]),
                        layouts = [
                            LayoutSlotData(
                                **{field:value for field, value in layout_data.items() if field not in ["missions", "entry_rule"]},
                                entry_rule = SubRuleRuleData.parse_from_dict(layout_data["entry_rule"]),
                                missions = [
                                    [
                                        MissionSlotData(
                                            **{field:value for field, value in mission_data.items() if field != "entry_rule"},
                                            entry_rule = SubRuleRuleData.parse_from_dict(mission_data["entry_rule"])
                                        ) for mission_data in column
                                    ] for column in layout_data["missions"]
                                ]
                            ) for layout_data in campaign_data["layouts"]
                        ]
                    ) for campaign_data in args["slot_data"]["custom_mission_order"]
                ]
            self.mission_id_to_entry_rules = {
                mission.mission_id: MissionEntryRules(mission.entry_rule, layout.entry_rule, campaign.entry_rule)
                for campaign in self.custom_mission_order for layout in campaign.layouts
                for column in layout.missions for mission in column
            }

            self.mission_order = args["slot_data"].get("mission_order", MissionOrder.option_vanilla)
            if self.slot_data_version < 4:
                self.final_mission_ids = [args["slot_data"].get("final_mission", SC2Mission.ALL_IN.id)]
            else:
                self.final_mission_ids = args["slot_data"].get("final_mission_ids", [SC2Mission.ALL_IN.id])
                self.final_locations = [get_location_id(mission_id, 0) for mission_id in self.final_mission_ids]

            self.player_color_raynor = _remap_color_option(
                self.slot_data_version,
                args["slot_data"].get("player_color_terran_raynor", ColorChoice.option_blue)
            )
            self.player_color_zerg = _remap_color_option(
                self.slot_data_version,
                args["slot_data"].get("player_color_zerg", ColorChoice.option_orange)
            )
            self.player_color_zerg_primal = _remap_color_option(
                self.slot_data_version,
                args["slot_data"].get("player_color_zerg_primal", ColorChoice.option_purple)
            )
            self.player_color_protoss = _remap_color_option(
                self.slot_data_version,
                args["slot_data"].get("player_color_protoss", ColorChoice.option_blue)
            )
            self.player_color_nova = _remap_color_option(
                self.slot_data_version,
                args["slot_data"].get("player_color_nova", ColorChoice.option_dark_grey)
            )
            self.show_war_council_nerfs = args["slot_data"].get("war_council_nerfs", WarCouncilNerfs.option_false)
            self.mercenary_highlanders = args["slot_data"].get("mercenary_highlanders", MercenaryHighlanders.option_false)
            self.generic_upgrade_missions = args["slot_data"].get("generic_upgrade_missions", GenericUpgradeMissions.default)
            self.max_upgrade_level = args["slot_data"].get("max_upgrade_level", MaxUpgradeLevel.default)
            self.generic_upgrade_items = args["slot_data"].get("generic_upgrade_items", GenericUpgradeItems.option_individual_items)
            self.generic_upgrade_research = args["slot_data"].get("generic_upgrade_research", GenericUpgradeResearch.option_vanilla)
            self.generic_upgrade_research_speedup = args["slot_data"].get("generic_upgrade_research_speedup", GenericUpgradeResearchSpeedup.default)
            self.kerrigan_primal_status = args["slot_data"].get("kerrigan_primal_status", KerriganPrimalStatus.option_vanilla)
            self.kerrigan_levels_per_mission_completed = args["slot_data"].get("kerrigan_levels_per_mission_completed", 0)
            self.kerrigan_levels_per_mission_completed_cap = args["slot_data"].get("kerrigan_levels_per_mission_completed_cap", -1)
            self.kerrigan_total_level_cap = args["slot_data"].get("kerrigan_total_level_cap", -1)
            self.enable_morphling = args["slot_data"].get("enable_morphling", EnableMorphling.option_false)
            self.grant_story_tech = args["slot_data"].get("grant_story_tech", GrantStoryTech.option_no_grant)
            self.grant_story_levels = args["slot_data"].get("grant_story_levels", GrantStoryLevels.option_additive)
            self.required_tactics = args["slot_data"].get("required_tactics", RequiredTactics.option_standard)
            self.take_over_ai_allies = args["slot_data"].get("take_over_ai_allies", TakeOverAIAllies.option_false)
            self.spear_of_adun_presence = args["slot_data"].get("spear_of_adun_presence", SpearOfAdunPresence.option_not_present)
            self.spear_of_adun_present_in_no_build = args["slot_data"].get("spear_of_adun_present_in_no_build", SpearOfAdunPresentInNoBuild.option_false)
            if self.slot_data_version < 4:
                self.spear_of_adun_passive_ability_presence = args["slot_data"].get("spear_of_adun_autonomously_cast_ability_presence", SpearOfAdunPassiveAbilityPresence.option_not_present)
                self.spear_of_adun_passive_present_in_no_build = args["slot_data"].get("spear_of_adun_autonomously_cast_present_in_no_build", SpearOfAdunPassivesPresentInNoBuild.option_false)
            else:
                self.spear_of_adun_passive_ability_presence = args["slot_data"].get("spear_of_adun_passive_ability_presence", SpearOfAdunPassiveAbilityPresence.option_not_present)
                self.spear_of_adun_passive_present_in_no_build = args["slot_data"].get("spear_of_adun_passive_present_in_no_build", SpearOfAdunPassivesPresentInNoBuild.option_false)
            self.minerals_per_item = args["slot_data"].get("minerals_per_item", 15)
            self.vespene_per_item = args["slot_data"].get("vespene_per_item", 15)
            self.starting_supply_per_item = args["slot_data"].get("starting_supply_per_item", 2)
            self.maximum_supply_per_item = args["slot_data"].get("maximum_supply_per_item", options.MaximumSupplyPerItem.default)
            self.maximum_supply_reduction_per_item = args["slot_data"].get("maximum_supply_reduction_per_item", options.MaximumSupplyReductionPerItem.default)
            self.lowest_maximum_supply = args["slot_data"].get("lowest_maximum_supply", options.LowestMaximumSupply.default)
            self.research_cost_reduction_per_item = args["slot_data"].get("research_cost_reduction_per_item", options.ResearchCostReductionPerItem.default)
            self.nova_items_granted = args["slot_data"].get("nova_items_granted", False)
            hero_presence_args = args["slot_data"].get("hero_presence","0")
            if hero_presence_args != "0":
                self.hero_presence = self.unpack_hero_presence(hero_presence_args)
            else:
                self.hero_presence = self.default_hero_presence(True)
            # # TODO (Snarky): NCO Nova is currently disabled. Revisit if enabled.
            # # Generic Nova presence never made it to live, so it doesn't need compat code
            # if self.slot_data_version < 4:
            #     if args["slot_data"].get("nova_covert_ops_only", True):
            #     else:
            # if self.slot_data_version < 5:
            #     if args["slot_data"].get("use_nova_wol_fallback", True):
            #     else:
            if self.slot_data_version < 5:
                if args["slot_data"].get("kerrigan_presence", True):
                    self.hero_presence = self.default_hero_presence(True)
                else:
                    self.hero_presence = self.default_hero_presence(False)
            self.trade_enabled = args["slot_data"].get("enable_void_trade", EnableVoidTrade.option_false)
            self.trade_age_limit = args["slot_data"].get("void_trade_age_limit", VoidTradeAgeLimit.default)
            self.trade_workers_allowed = args["slot_data"].get("void_trade_workers", VoidTradeWorkers.default)
            self.difficulty_damage_modifier = args["slot_data"].get("difficulty_damage_modifier", DifficultyDamageModifier.option_true)
            self.mission_order_scouting = args["slot_data"].get("mission_order_scouting", MissionOrderScouting.option_none)
            self.mission_item_classification = args["slot_data"].get("mission_item_classification")

            if self.required_tactics == RequiredTactics.option_no_logic:
                # Locking Grant Story Tech/Levels if no logic
                self.grant_story_tech = GrantStoryTech.option_grant
                self.grant_story_levels = GrantStoryLevels.option_minimum

            self.location_inclusions = {
                LocationType.VICTORY: LocationInclusion.option_enabled, # Victory checks are always enabled
                LocationType.VICTORY_CACHE: LocationInclusion.option_enabled, # Victory checks are always enabled
                LocationType.VANILLA: args["slot_data"].get("vanilla_locations", VanillaLocations.default),
                LocationType.EXTRA: args["slot_data"].get("extra_locations", ExtraLocations.default),
                LocationType.CHALLENGE: args["slot_data"].get("challenge_locations", ChallengeLocations.default),
                LocationType.MASTERY: args["slot_data"].get("mastery_locations", MasteryLocations.default),
            }
            self.location_inclusions_by_flag = {
                LocationFlag.SPEEDRUN: args["slot_data"].get("speedrun_locations", SpeedrunLocations.default),
                LocationFlag.PREVENTATIVE: args["slot_data"].get("preventative_locations", PreventativeLocations.default),
            }
            self.plando_locations = args["slot_data"].get("plando_locations", [])

            self.build_location_to_mission_mapping()

            # Looks for the required maps and mods for SC2.
            maps_present = is_mod_installed_correctly()
            if os.path.exists(get_metadata_file()):
                with open(get_metadata_file(), "r") as f:
                    current_ver = f.read()
                    sc2_logger.debug(f"Current version: {current_ver}")
                if is_mod_update_available(DATA_REPO_OWNER, DATA_REPO_NAME, DATA_API_VERSION, current_ver):
                    (
                        ColouredMessage().coloured("NOTICE: Update for required files found. ", colour="red")
                        ("Run ").coloured("/download_data", colour="slateblue")
                        (" to install.")
                    ).send(self)
                    self.data_out_of_date = True
            elif maps_present:
                (
                    ColouredMessage()
                    .coloured("NOTICE: Your map files may be outdated (version number not found). ", colour="red")
                    ("Run ").coloured("/download_data", colour="slateblue")
                    (" to install.")
                ).send(self)
                self.data_out_of_date = True

            ColouredMessage("[b]Check the Launcher tab to start playing.[/b]", keep_markup=True).send(self)

        elif cmd == "SetReply":
            # Currently can only be Void Trade reply
            self.trade_latest_reply = args
            self.trade_reply_event.set()

    @staticmethod
    def parse_mission_info(mission_info: dict[str, Any]) -> MissionInfo:
        if mission_info.get("id") is not None:
            mission_info["mission"] = lookup_id_to_mission[mission_info["id"]]
        elif isinstance(mission_info["mission"], int):
            mission_info["mission"] = lookup_id_to_mission[mission_info["mission"]]

        return MissionInfo(
            **{field: value for field, value in mission_info.items() if field in MissionInfo._fields}
        )

    @staticmethod
    def parse_mission_req_table(mission_req_table: dict[SC2Campaign, dict[Any, MissionInfo]]) -> list[CampaignSlotData]:
        campaigns: list[tuple[int, CampaignSlotData]] = []
        rolling_rule_id = 0
        for (campaign, campaign_data) in mission_req_table.items():
            if campaign.campaign_name == "Global":
                campaign_name = ""
            else:
                campaign_name = campaign.campaign_name
            categories: dict[str, list[MissionSlotData]] = {}
            for mission in campaign_data.values():
                if mission.category not in categories:
                    categories[mission.category] = []
                mission_id = mission.mission.id
                sub_rules: list[CountMissionsRuleData] = []
                missions: list[int]
                if mission.number:
                    amount = mission.number
                    missions = [
                        mission.mission.id
                        for mission in mission_req_table[campaign].values()
                    ]
                    sub_rules.append(CountMissionsRuleData(missions, amount, [campaign_name]))
                prev_missions: list[int] = []
                if len(mission.required_world) > 0:
                    missions = []
                    for connection in mission.required_world:
                        if isinstance(connection, dict):
                            required_campaign = {}
                            for camp, camp_data in mission_req_table.items():
                                if camp.id == connection["campaign"]:
                                    required_campaign = camp_data
                                    break
                            required_mission_id = connection["connect_to"]
                        else:
                            required_campaign = mission_req_table[connection.campaign]
                            required_mission_id = connection.connect_to
                        required_mission = list(required_campaign.values())[required_mission_id - 1]
                        missions.append(required_mission.mission.id)
                        if required_mission.category == mission.category:
                            prev_missions.append(required_mission.mission.id)
                    if mission.or_requirements:
                        amount = 1
                    else:
                        amount = len(missions)
                    sub_rules.append(CountMissionsRuleData(missions, amount, missions))
                entry_rule = SubRuleRuleData(rolling_rule_id, sub_rules, len(sub_rules))
                rolling_rule_id += 1
                categories[mission.category].append(MissionSlotData.legacy(mission_id, prev_missions, entry_rule))

            layouts: list[LayoutSlotData] = []
            for (layout, mission_slots) in categories.items():
                if layout.startswith("_"):
                    layout_name = ""
                else:
                    layout_name = layout
                layouts.append(LayoutSlotData.legacy(layout_name, [mission_slots]))
            campaigns.append((campaign.id, CampaignSlotData.legacy(campaign_name, layouts)))
        return [data for (_, data) in sorted(campaigns)]


    def on_print_json(self, args: dict) -> None:
        # goes to this world
        if "receiving" in args and self.slot_concerns_self(args["receiving"]):
            relevant = True
        # found in this world
        elif "item" in args and self.slot_concerns_self(args["item"].player):
            relevant = True
        # not related
        else:
            relevant = False

        if relevant:
            self.announcements.put(self.raw_text_parser(copy.deepcopy(args["data"])))

        super(SC2Context, self).on_print_json(args)

    def run_gui(self) -> None:
        from .client_gui import start_gui
        start_gui(self)

    async def shutdown(self) -> None:
        await super(SC2Context, self).shutdown()
        if self.mission_client:
            self.mission_client.close()

    async def disconnect(self, allow_autoreconnect: bool = False) -> None:
        self.finished_game = False
        await super(SC2Context, self).disconnect(allow_autoreconnect=allow_autoreconnect)

    def play_mission(self, mission_id: int) -> bool:
        if self.missions_unlocked or is_mission_available(self, mission_id):
            if self.mission_client and self.mission_client.check_game_running():
                sc2_logger.info("Cannot start a mission while the game is still running")
                return False
            mission_client = game_client.launch_game_client(self, mission_id)
            if isinstance(mission_client, Error):
                sc2_logger.error(mission_client.message)
                return False
            self.mission_client = mission_client
            return True
        else:
            sc2_logger.info(f"{lookup_id_to_mission[mission_id].mission_name} is not currently unlocked.")
            return False

    def build_location_to_mission_mapping(self) -> None:
        mission_id_to_location_ids: dict[int, set[int]] = {
            mission.mission_id: set()
            for campaign in self.custom_mission_order for layout in campaign.layouts
            for column in layout.missions for mission in column
        }

        for loc in self.server_locations:
            offset = (
                SC2WOL_LOC_ID_OFFSET
                if loc < SC2HOTS_LOC_ID_OFFSET
                else (SC2HOTS_LOC_ID_OFFSET - SC2Mission.ALL_IN.id * VICTORY_MODULO)
            )
            mission_id, objective = divmod(loc - offset, VICTORY_MODULO)
            mission_id_to_location_ids[mission_id].add(objective)
        self.mission_id_to_location_ids = {
            mission_id: sorted(objectives)
            for mission_id, objectives in mission_id_to_location_ids.items()
        }

    def locations_for_mission(self, mission: SC2Mission) -> Iterable[int]:
        mission_id: int = mission.id
        objectives = self.mission_id_to_location_ids[mission_id]
        for objective in objectives:
            yield get_location_id(mission_id, objective)

    def locations_for_mission_id(self, mission_id: int) -> Iterable[int]:
        objectives = self.mission_id_to_location_ids[mission_id]
        for objective in objectives:
            yield get_location_id(mission_id, objective)

    def uncollected_locations_in_mission(self, mission: SC2Mission) -> Iterable[int]:
        for location_id in self.locations_for_mission(mission):
            if location_id in self.missing_locations:
                yield location_id

    def is_mission_completed(self, mission_id: int) -> bool:
        return get_location_id(mission_id, 0) in self.checked_locations


    async def trade_acquire_storage(self, keep_trying: bool = False) -> dict | None:
        # This function was largely taken from the Pokemon Emerald client
        """
        Acquires a lock on the Void Trade DataStorage.
        Locking the key means you have exclusive access
        to modifying the value until you unlock it or the key expires (5 seconds).

        If `keep_trying` is `True`, it will keep trying to acquire the lock
        until successful. Otherwise it will return `None` if it fails to
        acquire the lock.
        """
        while not self.exit_event.is_set() and self.mission_client and self.mission_client.check_game_running():
            lock = int(time.time_ns() / 1000000000) # in seconds

            # Make sure we're not past the waiting limit
            # SC2 needs to be notified within 10 minutes of game time (training time of the dummy units)
            mission_time_seconds = self.mission_client.game_time_seconds()
            if self.trade_lock_start is not None:
                if mission_time_seconds - self.trade_lock_start >= TRADE_LOCK_WAIT_LIMIT:
                    self.trade_lock_wait = 0
                    self.trade_lock_start = None
                    return None
            elif keep_trying:
                self.trade_lock_start = mission_time_seconds

            message_uuid = str(uuid.uuid4())
            await self.send_msgs([{
                "cmd": "Set",
                "key": self.trade_storage_team(),
                "default": { TRADE_DATASTORAGE_LOCK: 0 },
                "want_reply": True,
                "operations": [{ "operation": "update", "value": { TRADE_DATASTORAGE_LOCK: lock } }],
                "uuid": message_uuid,
            }])

            self.trade_reply_event.clear()
            try:
                await asyncio.wait_for(self.trade_reply_event.wait(), 5)
            except asyncio.TimeoutError:
                if not keep_trying:
                    return None
                continue

            assert self.trade_latest_reply is not None
            reply = copy.deepcopy(self.trade_latest_reply)

            # Make sure the most recently received update was triggered by our lock attempt
            if reply.get("uuid", None) != message_uuid:
                if not keep_trying:
                    return None
                await asyncio.sleep(TRADE_LOCK_TIME)
                continue

            # Make sure the current value of the lock is what we set it to
            # (I think this should theoretically never run)
            if reply["value"][TRADE_DATASTORAGE_LOCK] != lock:
                if not keep_trying:
                    return None
                await asyncio.sleep(TRADE_LOCK_TIME)
                continue

            # Make sure that the lock value we replaced is at least 5 seconds old
            # If it was unlocked before our change, its value was 0 and it will look decades old
            if lock - reply["original_value"][TRADE_DATASTORAGE_LOCK] < TRADE_LOCK_TIME:
                if not keep_trying:
                    return None

                # Multiple clients trying to lock the key may get stuck in a loop of checking the lock
                # by trying to set it, which will extend its expiration. So if we see that the lock was
                # too new when we replaced it, we should wait for increasingly longer periods so that
                # eventually the lock will expire and a client will acquire it.
                self.trade_lock_wait += TRADE_LOCK_TIME
                self.trade_lock_wait += random.randrange(100, 500) / 1000

                await asyncio.sleep(self.trade_lock_wait)
                continue

            # We have the lock, reset the waiting period and return
            self.trade_lock_wait = 0
            self.trade_lock_start = None
            return reply
        return None


    async def trade_receive(self, amount: int = 1):
        """
        Tries to pop `amount` units out of the trade storage.
        """
        reply = await self.trade_acquire_storage(True)

        if reply is None:
            banks.send_trade_received("FailConnection")
            return None

        # Find available units
        # Ignore units we sent ourselves
        allowed_slots: list[str] = [
            slot for slot in reply["value"]
            if slot != TRADE_DATASTORAGE_LOCK
                and slot != self.trade_storage_slot()
        ]
        # Filter out trades that are too old
        if self.trade_age_limit != VoidTradeAgeLimit.option_disabled:
            trade_time = reply["value"][TRADE_DATASTORAGE_LOCK]
            allowed_age = void_trade_age_limits_ms[self.trade_age_limit]
            is_young_enough = lambda send_time: trade_time - send_time <= allowed_age
        else:
            is_young_enough = lambda _: True
        # Filter out banned units
        if self.trade_workers_allowed == VoidTradeWorkers.option_false:
            is_unit_allowed = lambda unit: unit not in worker_units
        else:
            is_unit_allowed = lambda _: True

        available_units: list[tuple[str, str, int]] = []
        available_counts: list[int] = []
        for slot in allowed_slots:
            for (send_time, units) in reply["value"][slot].items():
                if is_young_enough(int(send_time)):
                    for (unit, count) in units.items():
                        if is_unit_allowed(str(unit)):
                            available_units.append((unit, slot, send_time))
                            available_counts.append(count)

        # Pick units to receive
        # If there's not enough units in total, just pick as many as possible
        # SC2 should handle the refund
        available = sum(available_counts)
        refunds = 0
        if available < amount:
            refunds = amount - available
            amount = available
        if available == 0:
            # random.sample crashes if counts is an empty list
            units = []
        else:
            units = random.sample(available_units, amount, counts = available_counts)
        # Build response data
        unit_counts: dict[str, int] = {}
        slots_to_update: dict[str, dict[int, dict[str, int]]] = {}
        for (unit, slot, send_time) in units:
            unit_counts[unit] = unit_counts.get(unit, 0) + 1
            if slot not in slots_to_update:
                slots_to_update[slot] = copy.deepcopy(reply["value"][slot])
            slots_to_update[slot][send_time][unit] -= 1
            # Clean up units that were removed completely
            if slots_to_update[slot][send_time][unit] == 0:
                slots_to_update[slot][send_time].pop(unit)
            # Clean up trades that were completely exhausted
            if len(slots_to_update[slot][send_time]) == 0:
                slots_to_update[slot].pop(send_time)
        await self.send_msgs([
            {   # Update server storage
                "cmd": "Set",
                "key": self.trade_storage_team(),
                "operations": [{ "operation": "update", "value": slots_to_update }]
            },
            {   # Release the lock
                "cmd": "Set",
                "key": self.trade_storage_team(),
                "operations": [{ "operation": "update", "value": { TRADE_DATASTORAGE_LOCK: 0 } }]
            }
        ])
        # Write units to bank
        value = f"ReceiveUnits {refunds} " + " ".join(f"{unit} {count}" for (unit, count) in unit_counts.items())
        banks.send_trade_received(value)
        self.trade_response = None
        self.trade_underway = False


    async def trade_send(self, units: list[str]):
        """
        Tries to upload `units` to the trade DataStorage.
        """
        reply = await self.trade_acquire_storage(True)

        if reply is None:
            banks.send_trade_received("FailConnection")
            return None

        # Create a storage entry for the time the trade was confirmed
        trade_time = reply["value"][TRADE_DATASTORAGE_LOCK]
        storage_entry: dict[str, int] = {}
        for unit in units:
            storage_entry[unit] = storage_entry.get(unit, 0) + 1

        # Update the storage with the new units
        data: dict[int, dict[str, int]] = copy.deepcopy(reply["value"].get(self.trade_storage_slot(), {}))
        data[trade_time] = storage_entry

        await self.send_msgs([
            {   # Send the updated data
                "cmd": "Set",
                "key": self.trade_storage_team(),
                "operations": [{ "operation": "update", "value": { self.trade_storage_slot(): data } }]
            },
            {   # Release the lock
                "cmd": "Set",
                "key": self.trade_storage_team(),
                "operations": [{ "operation": "update", "value": { TRADE_DATASTORAGE_LOCK: 0 } }]
            }
        ])

        # Notify the game
        banks.send_trade_received("Success")
        self.trade_response = None
        self.trade_underway = False


async def main(arguments: Sequence[str] | None):
    multiprocessing.freeze_support()
    parser = get_base_parser()
    parser.add_argument('--name', default=None, help="Slot Name to connect as.")
    args, uri = parser.parse_known_args(arguments)

    if uri and uri[0].startswith('archipelago://'):
        args.url = uri[0]
        handle_url_arg(args, parser)

    ctx = SC2Context(args.connect, args.password)
    ctx.auth = args.name
    if ctx.server_task is None:
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="ServerLoop")

    if gui_enabled:
        ctx.run_gui()
    ctx.run_cli()

    await ctx.exit_event.wait()

    await ctx.shutdown()


def calc_unfinished_nodes(
    ctx: SC2Context
) -> tuple[list[int], dict[int, list[int]], list[int], set[int]]:
    unfinished_missions: set[int] = set()

    available_missions, available_layouts, available_campaigns = calc_available_nodes(ctx)

    for mission_id in available_missions:
        objectives = set(ctx.locations_for_mission_id(mission_id))
        if objectives:
            objectives_completed = ctx.checked_locations & objectives
            if len(objectives_completed) < len(objectives):
                unfinished_missions.add(mission_id)

    return available_missions, available_layouts, available_campaigns, unfinished_missions

def is_mission_available(ctx: SC2Context, mission_id_to_check: int) -> bool:
    available_missions, _, _ = calc_available_nodes(ctx)

    return mission_id_to_check in available_missions

def calc_available_nodes(ctx: SC2Context) -> tuple[list[int], dict[int, list[int]], list[int]]:
    beaten_missions: set[int] = {mission_id for mission_id in ctx.mission_id_to_entry_rules if ctx.is_mission_completed(mission_id)}
    received_items = compute_received_items(ctx)

    mission_order_objects: list[MissionOrderObjectSlotData] = []
    parent_objects: list[list[MissionOrderObjectSlotData]] = []
    for campaign in ctx.custom_mission_order:
        mission_order_objects.append(campaign)
        parent_objects.append([])
        for layout in campaign.layouts:
            mission_order_objects.append(layout)
            parent_objects.append([campaign])
            for column in layout.missions:
                for mission in column:
                    if mission.mission_id == -1:
                        continue
                    mission_order_objects.append(mission)
                    parent_objects.append([campaign, layout])

    candidate_accessible_objects: list[MissionOrderObjectSlotData] = [
        mission_order_object for mission_order_object in mission_order_objects
        if mission_order_object.entry_rule.is_accessible(beaten_missions, received_items)
    ]

    accessible_objects: list[MissionOrderObjectSlotData] = []

    while len(candidate_accessible_objects) > 0:
        accessible_missions: list[MissionSlotData] = [mission_order_object for mission_order_object in accessible_objects if isinstance(mission_order_object, MissionSlotData)]
        beaten_accessible_missions: set[int] = {mission.mission_id for mission in accessible_missions if mission.mission_id in beaten_missions}
        accessible_objects_to_add: list[MissionOrderObjectSlotData] = []
        for mission_order_object in candidate_accessible_objects:
            if (
                mission_order_object.entry_rule.is_accessible(beaten_accessible_missions, received_items)
                and all([
                    parent_object.entry_rule.is_accessible(beaten_accessible_missions, received_items)
                    for parent_object in parent_objects[mission_order_objects.index(mission_order_object)]
                ])
            ):
                accessible_objects_to_add.append(mission_order_object)
        if len(accessible_objects_to_add) > 0:
            accessible_objects.extend(accessible_objects_to_add)
            candidate_accessible_objects = [
                mission_order_object for mission_order_object in candidate_accessible_objects
                if mission_order_object not in accessible_objects_to_add
            ]
        else:
            break

    accessible_missions = [
        mission_order_object
        for mission_order_object in accessible_objects
        if isinstance(mission_order_object, MissionSlotData)
    ]
    beaten_accessible_missions = {
        mission.mission_id for mission in accessible_missions if mission.mission_id in beaten_missions
    }
    for mission_order_object in mission_order_objects:
        # re-generate tooltip accessibility
        for sub_rule in mission_order_object.entry_rule.sub_rules:
            sub_rule.was_accessible = False
        mission_order_object.entry_rule.is_accessible(beaten_accessible_missions, received_items)

    available_missions: list[int] = [
        mission_order_object.mission_id for mission_order_object in accessible_objects
        if isinstance(mission_order_object, MissionSlotData)
    ]
    available_campaign_objects: list[CampaignSlotData] = [
        mission_order_object for mission_order_object in accessible_objects
        if isinstance(mission_order_object, CampaignSlotData)
    ]
    available_campaigns: list[int] = [
        campaign_idx for campaign_idx, campaign in enumerate(ctx.custom_mission_order)
        if campaign in available_campaign_objects
    ]
    available_layout_objects: list[LayoutSlotData] = [
        mission_order_object for mission_order_object in accessible_objects
        if isinstance(mission_order_object, LayoutSlotData)
    ]
    available_layouts: dict[int, list[int]] = {
        campaign_idx: [
            layout_idx for layout_idx, layout in enumerate(campaign.layouts) if layout in available_layout_objects
        ]
        for campaign_idx, campaign in enumerate(ctx.custom_mission_order)
    }

    return available_missions, available_layouts, available_campaigns


def compute_received_items(ctx: SC2Context) -> collections.Counter[int]:
    received_items: collections.Counter[int] = collections.Counter()
    for network_item in ctx.items_received:
        received_items[network_item.item] += 1
    return received_items


def is_mod_installed_correctly() -> bool:
    """Searches for all required files."""
    sc2_path = user_paths.get_sc2_install_dir()
    if isinstance(sc2_path, Error):
        sc2_logger.warning(sc2_path.message)
        return False
    mapdir = Path(sc2_path) / Path('Maps/ArchipelagoCampaign')
    mods = ["ArchipelagoCore", "ArchipelagoPlayer", "ArchipelagoPlayerSuper", "ArchipelagoPatches",
            "ArchipelagoTriggers", "ArchipelagoPlayerWoL", "ArchipelagoPlayerHotS",
            "ArchipelagoPlayerLotV", "ArchipelagoPlayerLotVPrologue", "ArchipelagoPlayerNCO"]
    modfiles = [sc2_path / Path("Mods/" + mod + ".SC2Mod") for mod in mods]
    wol_required_maps: list[str] = ["WoL" + os.sep + mission.map_file + ".SC2Map" for mission in SC2Mission
                         if mission.campaign in (SC2Campaign.WOL, SC2Campaign.PROPHECY)]
    hots_required_maps: list[str] = ["HotS" + os.sep + mission.map_file + ".SC2Map" for mission in campaign_mission_table[SC2Campaign.HOTS]]
    lotv_required_maps: list[str] = ["LotV" + os.sep + mission.map_file + ".SC2Map" for mission in SC2Mission
                                            if mission.campaign in (SC2Campaign.LOTV, SC2Campaign.PROLOGUE, SC2Campaign.EPILOGUE)]
    nco_required_maps: list[str] = ["NCO" + os.sep + mission.map_file + ".SC2Map" for mission in campaign_mission_table[SC2Campaign.NCO]]
    required_maps = wol_required_maps + hots_required_maps + lotv_required_maps + nco_required_maps
    needs_files = False

    # Check for maps.
    missing_maps: list[str] = []
    for mapfile in required_maps:
        if not os.path.isfile(mapdir / mapfile):
            missing_maps.append(mapfile)
    if len(missing_maps) >= 19:
        sc2_logger.warning(f"All map files missing from {mapdir}.")
        needs_files = True
    elif len(missing_maps) > 0:
        for map in missing_maps:
            sc2_logger.debug(f"Missing {map} from {mapdir}.")
        sc2_logger.warning(f"Missing {len(missing_maps)} map files.")
        needs_files = True
    else:  # Must be no maps missing
        sc2_logger.debug(f"All maps found in {mapdir}.")

    # Check for mods.
    for modfile in modfiles:
        if os.path.isfile(modfile) or os.path.isdir(modfile):
            sc2_logger.debug(f"Archipelago mod found at {modfile}.")
        else:
            sc2_logger.warning(f"Archipelago mod could not be found at {modfile}.")
            needs_files = True

    # Final verdict.
    if needs_files:
        sc2_logger.warning("Required files are missing. Run /download_data to acquire them.")
        return False
    else:
        sc2_logger.debug("All map/mod files are properly installed.")
        return True


def download_latest_release_zip(
    owner: str,
    repo: str,
    api_version: str,
    ctx: SC2Context,
    metadata: str | None = None,
    force_download: bool = False,
) -> tuple[str, str | None]:
    """Downloads the latest release of a GitHub repo to the current directory as a .zip file."""
    import requests

    headers = {"Accept": "application/vnd.github.v3+json"}
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{api_version}"
    user_facing_url = f"https://github.com/{owner}/{repo}/releases/tag/{api_version}"

    MB_SCALE = 20
    CHUNK_SCALE = 22  # 4 MiB
    CHUNK_SIZE = 1 << CHUNK_SCALE
    PROGRESS_FRACTION = 10

    r2: requests.Response | None = None
    try:
        r1 = requests.get(url, headers=headers, timeout=15.0)
        if r1.status_code == 200:
            latest_metadata = r1.json()
            cleanup_downloaded_metadata(latest_metadata)
            latest_metadata = str(latest_metadata)
        else:
            sc2_logger.warning(f"Status code: {r1.status_code}")
            sc2_logger.warning("Failed to reach GitHub. Could not find download link.")
            sc2_logger.warning(f"text: {r1.text}")
            return "", metadata

        if not force_download and (metadata == latest_metadata):
            sc2_logger.info("Latest version already installed.")
            return "", metadata

        sc2_logger.info(f"Attempting to download latest {api_version} release of {repo}.")
        download_url = r1.json()["assets"][0]["browser_download_url"]

        tempdir = tempfile.gettempdir()
        file = tempdir + os.sep + f"{repo}.zip"
        r2 = requests.get(download_url, headers=headers, timeout=(12.5, 60.0), stream=True)
        if r2.status_code != 200:
            r2.close()
            sc2_logger.warning(f"Download failed with status code {r2.status_code}.")
            return "", metadata

        def print_progress_bar(progress: int, mb_written: int, mb_total: int) -> None:
            # In Roboto, `|` and ` ` are very similar widths, so this displays nicely everywhere
            (
                ColouredMessage('Progress: [ ')
                .coloured("|||" * progress, colour="orange")
                (("   " * (PROGRESS_FRACTION - progress)) + f" ] {mb_written} / {mb_total} MiB")
            ).send(ctx)

        with open(file, "wb") as fp:
            total_length = r2.headers.get("content-length")
            if total_length is None:
                fp.write(r2.content)
            else:
                bytes_written = 0
                bytes_total = int(total_length)
                total_length_megabytes = bytes_total >> MB_SCALE
                last_progress = -1
                for chunk in r2.iter_content(chunk_size=CHUNK_SIZE):
                    bytes_written += len(chunk)
                    fp.write(chunk)
                    progress = bytes_written * PROGRESS_FRACTION // bytes_total
                    if progress > last_progress:
                        print_progress_bar(progress, bytes_written >> MB_SCALE, total_length_megabytes)
                        last_progress = progress
                if bytes_written < bytes_total:
                    sc2_logger.warning(
                        f"Could not download the file. Written {bytes_written}/{bytes_total} bytes. "
                        f"(status {r2.status_code})"
                    )
                    return "", metadata
            if r2.status_code != 200:
                r2.close()
                sc2_logger.warning(f"Download failed with status code {r2.status_code}.")
                return "", metadata
        sc2_logger.info(f"Successfully downloaded {repo}.zip. Installing...")
        return file, latest_metadata
    except requests.ConnectionError:
        sc2_logger.warning("Failed to reach GitHub. Could not find download link.")
        return "", metadata
    except requests.Timeout:
        sc2_logger.warning(f"Download request timed out. Try again or check connection to {user_facing_url}")
        return "", metadata
    except Exception as ex:
        sc2_logger.warning(f"An unknown exception occurred: {type(ex)}: {ex}")
        return "", metadata
    finally:
        r1.close()
        if r2 is not None:
            r2.close()


def cleanup_downloaded_metadata(medatada_json: dict) -> None:
    for asset in medatada_json['assets']:
        del asset['download_count']


def is_mod_update_available(owner: str, repo: str, api_version: str, metadata: str) -> bool:
    import requests

    headers = {"Accept": 'application/vnd.github.v3+json'}
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{api_version}"
    r1: requests.Response | None = None
    try:
        r1 = requests.get(url, headers=headers)
        if r1.status_code == 200:
            latest_metadata = r1.json()
            cleanup_downloaded_metadata(latest_metadata)
            latest_metadata = str(latest_metadata)
            if metadata != latest_metadata:
                return True
            else:
                return False

        else:
            sc2_logger.warning("Failed to reach GitHub while checking for updates.")
            sc2_logger.warning(f"Status code: {r1.status_code}")
            sc2_logger.warning(f"text: {r1.text}")
            return False
    except Exception as ex:
        sc2_logger.warning(f"Failed to reach GitHub while checking for updates.")
        sc2_logger.debug(ex)
        return False
    finally:
        if r1:
            r1.close()


_has_forced_save = False
def force_settings_save_on_close() -> None:
    """
    Settings has an existing auto-save feature, but it only triggers if a new key was introduced.
    Force it to mark things as changed by introducing a new key and then cleaning up.
    """
    global _has_forced_save
    if _has_forced_save:
        return
    SC2World.settings.update({'invalid_attribute': True})
    del SC2World.settings.invalid_attribute
    _has_forced_save = True


def launch(*args: str):
    colorama.just_fix_windows_console()
    init_logging("SC2Client", exception_logger="Client")
    asyncio.run(main(args))
    colorama.deinit()
