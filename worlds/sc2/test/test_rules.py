import itertools
from dataclasses import fields
import inspect
from random import Random
import unittest
from typing import Iterable, Callable

from BaseClasses import ItemClassification, MultiWorld
import Options as CoreOptions
from .. import options, rules_mapping, mission_tables, locations
from ..item import item_tables, virtual_items
from ..rules import SC2Logic
from . import test_base


def function_requires_one_argument(function: Callable) -> bool:
    required_args = [
        x
        for x in inspect.signature(function).parameters.values()
        if x.default is inspect.Parameter.empty
    ]
    return len(required_args) == 1


class TestInventory:
    """
    Runs checks against inventory with validation if all target items are progression and returns a random result
    """
    def __init__(self) -> None:
        self.random: Random = Random()
        self.progression_types: set[ItemClassification] = {
            ItemClassification.progression, ItemClassification.progression_skip_balancing,
        }

    def is_item_progression(self, item: str) -> bool:
        return (
            item in virtual_items.VirtualItem._member_names_
            or item_tables.item_table[item].classification in self.progression_types
        )

    def random_boolean(self):
        return self.random.choice([True, False])

    def has(self, item: str, player: int, count: int = 1):
        if not self.is_item_progression(item):
            raise AssertionError("Logic item {} is not a progression item".format(item))
        return self.random_boolean()

    def has_any(self, items: set[str], player: int):
        non_progression_items = [item for item in items if not self.is_item_progression(item)]
        if len(non_progression_items) > 0:
            raise AssertionError("Logic items {} are not progression items".format(non_progression_items))
        return self.random_boolean()

    def has_all(self, items: set[str], player: int):
        return self.has_any(items, player)

    def has_group(self, item_group: str, player: int, count: int = 1):
        return self.random_boolean()

    def count_group(self, item_name_group: str, player: int) -> int:
        return self.random.randrange(0, 20)

    def count(self, item: str, player: int) -> int:
        if not self.is_item_progression(item):
            raise AssertionError("Item {} is not a progression item".format(item))
        random_value: int = self.random.randrange(0, 5)
        if random_value == 4:  # 0-3 has a higher chance due to logic rules
            return self.random.randrange(4, 100)
        else:
            return random_value

    def count_from_list(self, items: Iterable[str], player: int) -> int:
        return sum(self.count(item_name, player) for item_name in items)

    def count_from_list_unique(self, items: Iterable[str], player: int) -> int:
        return sum(self.count(item_name, player) for item_name in items)


class TestWorld:
    """
    Mock world to simulate different player options for logic rules
    """
    def __init__(self) -> None:
        defaults = dict()
        for field in fields(options.Starcraft2Options):
            field_class = field.type
            option_name = field.name
            if isinstance(field_class, str):
                if field_class in globals():
                    field_class = globals()[field_class]
                else:
                    field_class = CoreOptions.__dict__[field.type]
            defaults[option_name] = field_class(options.get_option_value(None, option_name))
        self.options: options.Starcraft2Options = options.Starcraft2Options(**defaults)

        self.options.mission_order.value = options.MissionOrder.option_vanilla_shuffled

        self.player = 1
        self.multiworld = MultiWorld(1)


class StaticInventory:
    def __init__(self, *items: str) -> None:
        self.items = set(items)

    def has(self, item: str, player: int, count: int = 1) -> bool:
        return item in self.items

    def has_any(self, items: Iterable[str], player: int) -> bool:
        return any(item in self.items for item in items)

    def has_all(self, items: Iterable[str], player: int) -> bool:
        return all(item in self.items for item in items)

    def count(self, item: str, player: int) -> int:
        return int(item in self.items)

    def count_from_list(self, items: Iterable[str], player: int) -> int:
        return sum(item in self.items for item in items)

    def count_from_list_unique(self, items: Iterable[str], player: int) -> int:
        return self.count_from_list(items, player)


class TestRules(unittest.TestCase):
    def setUp(self) -> None:
        self.required_tactics_values: list[int] = [
            options.RequiredTactics.option_basic,
            options.RequiredTactics.option_advanced,
            options.RequiredTactics.option_chaos,
        ]
        self.all_in_map_values: list[int] = [
            options.AllInMap.option_ground, options.AllInMap.option_air
        ]
        self.NUM_TEST_RUNS = 150

    @staticmethod
    def _get_world(
        required_tactics: int = options.RequiredTactics.default,
        all_in_map: int = options.AllInMap.default,
        take_over_ai_allies: int = options.TakeOverAIAllies.default,
        # setting this to everywhere catches one extra logic check for Amon's Fall without missing any
        spear_of_adun_passive_presence: int = options.SpearOfAdunPassiveAbilityPresence.option_everywhere,
    ) -> TestWorld:
        test_world = TestWorld()
        test_world.options.required_tactics.value = required_tactics
        test_world.options.all_in_map.value = all_in_map
        test_world.options.take_over_ai_allies.value = take_over_ai_allies
        test_world.options.spear_of_adun_passive_ability_presence.value = spear_of_adun_passive_presence
        test_world.options.enabled_campaigns.value = set(options.EnabledCampaigns.valid_keys)
        test_world.logic = SC2Logic(test_world)
        return test_world

    def test_items_in_rules_are_progression(self):
        test_inventory = TestInventory()
        for option in self.required_tactics_values:
            test_world = self._get_world(required_tactics=option)
            for name, function in test_world.logic.name_to_function.items():
                if not function_requires_one_argument(function):
                    continue
                for _ in range(self.NUM_TEST_RUNS):
                    function(test_inventory)

    def test_items_in_all_in_are_progression(self):
        test_inventory = TestInventory()
        for test_options in itertools.product(self.required_tactics_values, self.all_in_map_values):
            test_world = self._get_world(required_tactics=test_options[0], all_in_map=test_options[1])
            for name, function in test_world.logic.name_to_function.items():
                if not function_requires_one_argument(function):
                    continue
                if 'all_in' not in name:
                    continue
                for _ in range(self.NUM_TEST_RUNS):
                    function(test_inventory)

    # # TODO (Snarky): Make work with Hero Presence
    # def test_items_in_kerriganless_missions_are_progression(self):
    #     test_inventory = TestInventory()
    #     for test_options in itertools.product(self.required_tactics_values, self.kerrigan_presence_values):
    #         test_world = self._get_world(required_tactics=test_options[0], kerrigan_presence=test_options[1])
    #         for location in locations.get_locations(test_world):
    #             mission = lookup_name_to_mission[location.region]
    #             if MissionFlag.Kerrigan not in mission.flags:
    #                 continue
    #             for _ in range(self.NUM_TEST_RUNS):
    #                 location.rule(test_inventory)


class TestRuleGeneration(test_base.Sc2SetupTestBase):
    def test_hero_rules_are_ignored_when_not_present(self) -> None:
        player_options = {
            options.OPTION_NAME[options.KerriganPresence]: set(),
            options.OPTION_NAME[options.NovaPresence]: set(),
            options.OPTION_NAME[options.ArtanisPresence]: set(),
        }
        self.generate_world(player_options)
        rule = rules_mapping.ProtoRule(hero_min=rules_mapping.HERO_COMPETENT)
        signature = rule.to_signature(
            self.world,
            mission_tables.SC2Mission.ZERO_HOUR,
            locations.Sc2Location.ZERO_HOUR_VICTORY,
            depth=3,
            order=5,
            hero_presence={},
        )
        self.assertEqual(signature.kerrigan, 0)
        self.assertEqual(signature.nova, 0)
        self.assertEqual(signature.artanis, 0)
