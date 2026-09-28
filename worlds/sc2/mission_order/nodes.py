"""
Contains the data structures that make up a mission order.
Data in these structures is validated in .options.py and manipulated by .generation.py.
"""

from typing import Callable, Any, TYPE_CHECKING, overload, Literal, cast, Protocol, Sequence
from dataclasses import asdict

from Options import OptionError
from BaseClasses import Region, CollectionState
from ..mission_tables import SC2Mission
from ..item import item_names
from .layout_types import LayoutType
from .entry_rules import SubRuleEntryRule, ItemEntryRule, EntryRule
from .mission_pools import Difficulty
from .slot_data import CampaignSlotData, LayoutSlotData, MissionSlotData

if TYPE_CHECKING:
    from .. import SC2World
    from .types import CampaignDict, LayoutDict, MissionSlotDict, EntryRuleDict


def parent_id(base_id: tuple[int, ...]) -> tuple[int, ...]:
    if not base_id:
        return ()
    return base_id[:-1]


class MissionOrderNode(Protocol):
    id: tuple[int, ...]
    important_beat_event: bool
    """Signals container types should export their exits to slot data for use in entry rules"""

    def children(self) -> Sequence['MissionOrderNode']: ...

    def search(
        self,
        term: str,
        search_info: tuple['SC2MOGenMission', 'SC2MOGenLayout'] | tuple[()],
    ) -> list['MissionOrderNode']: ...

    def type_name(self) -> str: ...

    def get_missions(self) -> list['SC2MOGenMission']: ...

    def get_exits(self) -> list['SC2MOGenMission']: ...

    def get_visual_requirement(self, start_node: 'MissionOrderNode') -> 'str | SC2MOGenMission': ...

    def get_visual_name(self) -> str: ...

    def get_key_name(self, id_to_node: dict[tuple[int, ...], 'MissionOrderNode']) -> str: ...

    def get_min_depth(self) -> int: ...

    def get_address_to_node(self, id_to_node: dict[tuple[int, ...], 'MissionOrderNode']) -> str: ...



class SC2MOGenMissionOrder:
    """
    The top-level data structure for mission orders.
    """
    campaigns: list['SC2MOGenCampaign']
    sorted_missions: dict[Difficulty | int, list['SC2MOGenMission']]
    """All mission slots in the mission order sorted by their difficulty, but not their depth."""
    fixed_missions: list['SC2MOGenMission']
    """All mission slots that have a plando'd mission."""
    items_to_lock: dict[str, int]
    keys_to_resolve: dict[MissionOrderNode, list[ItemEntryRule]]
    goal_missions: list['SC2MOGenMission']
    max_depth: int

    def __init__(self, world: 'SC2World', data: dict[str, 'CampaignDict']) -> None:
        self.id: tuple[int, ...] = ()
        self.important_beat_event = False
        self.campaigns = []
        self.sorted_missions = {diff: [] for diff in Difficulty if diff != Difficulty.RELATIVE}
        self.fixed_missions = []
        self.items_to_lock = {}
        self.keys_to_resolve = {}
        self.goal_missions = []
        self.parent = None
        self._id_to_child_nodes: dict[tuple[int, ...], MissionOrderNode] = {}

        for index, (campaign_name, campaign_data) in enumerate(data.items()):
            campaign = SC2MOGenCampaign(world, (index,), campaign_name, campaign_data)
            self.campaigns.append(campaign)

        # Check that the mission order actually has a goal
        for campaign in self.campaigns:
            if campaign.option_goal:
                self.goal_missions.extend(mission for mission in campaign.exits)
            for layout in campaign.layouts:
                if layout.option_goal:
                    self.goal_missions.extend(layout.exits)
                for mission in layout.missions:
                    if mission.option_goal and not mission.option_empty:
                        self.goal_missions.append(mission)
        # Remove duplicates
        for goal in self.goal_missions:
            while self.goal_missions.count(goal) > 1:
                self.goal_missions.remove(goal)

        # If not, set the last defined campaign as goal
        if len(self.goal_missions) == 0:
            self.campaigns[-1].option_goal = True
            self.goal_missions.extend(mission for mission in self.campaigns[-1].exits)

        # Apply victory cache option wherever the value has not yet been defined; must happen after goal missions are decided
        for mission in self.get_missions():
            if mission.option_victory_cache != -1:
                # Already set
                continue
            if mission in self.goal_missions:
                mission.option_victory_cache = 0
            else:
                mission.option_victory_cache = world.options.victory_cache.value

        # Resolve names
        used_names: set[str] = set()
        for campaign in self.campaigns:
            names = [campaign.option_name] if len(campaign.option_display_name) == 0 else campaign.option_display_name
            if campaign.option_unique_name:
                names = [name for name in names if name not in used_names]
            campaign.display_name = world.random.choice(names)
            used_names.add(campaign.display_name)
            for layout in campaign.layouts:
                names = [layout.option_name] if len(layout.option_display_name) == 0 else layout.option_display_name
                if layout.option_unique_name:
                    names = [name for name in names if name not in used_names]
                layout.display_name = world.random.choice(names)
                used_names.add(layout.display_name)

    def children(self) -> Sequence['MissionOrderNode']:
        return self.campaigns

    def get_id_to_node(self) -> dict[tuple[int, ...], MissionOrderNode]:
        if not self._id_to_child_nodes:
            for campaign in self.campaigns:
                self._id_to_child_nodes[campaign.id] = campaign
                for layout in campaign.layouts:
                    self._id_to_child_nodes[layout.id] = layout
                    for mission in layout.missions:
                        if not mission.option_empty:
                            self._id_to_child_nodes[mission.id] = mission
        # Store self id separately to avoid the circular reference
        return self._id_to_child_nodes | {self.id: self}

    def get_slot_data(self) -> list[dict[str, Any]]:
        # [(campaign data, [(layout data, [[(mission data)]] )] )]
        return [campaign.get_slot_data() for campaign in self.campaigns]

    def search(
        self,
        term: str,
        search_info: tuple['SC2MOGenMission', 'SC2MOGenLayout'] | tuple[()],
    ) -> list[MissionOrderNode]:
        return [
            campaign.layouts[0] if campaign.option_single_layout_campaign else campaign
            for campaign in self.campaigns
            if campaign.option_name.casefold() == term.casefold()
        ]

    def type_name(self) -> str:
        return "Mission Order"

    def get_missions(self) -> list['SC2MOGenMission']:
        return [mission for campaign in self.campaigns for layout in campaign.layouts for mission in layout.missions]

    def get_exits(self) -> list['SC2MOGenMission']:
        return []

    def get_visual_requirement(self, start_node: MissionOrderNode) -> 'str | SC2MOGenMission':
        return "All Missions"

    def get_visual_name(self) -> str:
        return "Everything"

    def get_key_name(self, id_to_node: dict[tuple[int, ...], MissionOrderNode]) -> str:
        raise NotImplementedError

    def get_min_depth(self) -> int:
        return 0

    def get_address_to_node(self, id_to_node: dict[tuple[int, ...], MissionOrderNode]) -> str:
        return "/"


class SC2MOGenCampaign:
    option_name: str # name of this campaign
    option_display_name: list[str]
    option_unique_name: bool
    option_entry_rules: list['EntryRuleDict']
    option_unique_progression_track: int # progressive keys under this campaign and on this track will be changed to a unique track
    option_goal: bool # whether this campaign is required to beat the game
    # minimum difficulty of this campaign
    # 'relative': based on the median distance of the first mission
    option_min_difficulty: Difficulty
    # maximum difficulty of this campaign
    # 'relative': based on the median distance of the last mission
    option_max_difficulty: Difficulty
    option_single_layout_campaign: bool

    # layouts of this campaign in correct order
    layouts: list['SC2MOGenLayout']
    exits: list['SC2MOGenMission'] # missions required to beat this campaign (missions marked "exit" in layouts marked "exit")
    entry_rule: SubRuleEntryRule
    display_name: str

    min_depth: int
    max_depth: int

    def __init__(
        self,
        world: 'SC2World',
        id: tuple[int, ...],
        name: str,
        data: 'CampaignDict',
    ) -> None:
        self.id = id
        self.important_beat_event = False
        self.option_name = name
        self.option_display_name = data["display_name"]
        self.option_unique_name = data["unique_name"]
        self.option_goal = data["goal"]
        self.option_entry_rules = data["entry_rules"]
        self.option_unique_progression_track = data["unique_progression_track"]
        self.option_min_difficulty = Difficulty(data["min_difficulty"])
        self.option_max_difficulty = Difficulty(data["max_difficulty"])
        self.option_single_layout_campaign = data["single_layout_campaign"]
        self.layouts = []
        self.exits = []

        if self.option_single_layout_campaign:
            assert len(data["layouts"]) == 1
        for index, (layout_name, layout_data) in enumerate(data["layouts"].items()):
            if self.option_single_layout_campaign:
                layout_id = self.id
            else:
                layout_id = (*self.id, index)
            layout = SC2MOGenLayout(world, layout_id, layout_name, layout_data)
            self.layouts.append(layout)

            # Collect required missions (marked layouts' exits)
            if layout.option_exit:
                self.exits.extend(layout.exits)

        # If no exits are set, use the last defined layout
        if len(self.exits) == 0:
            self.layouts[-1].option_exit = True
            self.exits.extend(self.layouts[-1].exits)

    def is_beaten(self, beaten_missions: set['SC2MOGenMission']) -> bool:
        return beaten_missions.issuperset(self.exits)

    def is_always_unlocked(self, in_region_creation = False) -> bool:
        return self.entry_rule.is_always_fulfilled(in_region_creation)

    def is_unlocked(self, beaten_missions: set['SC2MOGenMission'], in_region_creation = False) -> bool:
        return self.entry_rule.is_fulfilled(beaten_missions, in_region_creation)

    def children(self) -> Sequence['MissionOrderNode']:
        return self.layouts

    def search(
        self,
        term: str,
        search_info: tuple['SC2MOGenMission', 'SC2MOGenLayout'] | tuple[()],
    ) -> list[MissionOrderNode]:
        return [
            layout
            for layout in self.layouts
            if layout.option_name.casefold() == term.casefold()
        ]

    def type_name(self) -> str:
        return "Campaign"

    def get_missions(self) -> list['SC2MOGenMission']:
        return [mission for layout in self.layouts for mission in layout.missions]

    def get_exits(self) -> list['SC2MOGenMission']:
        return self.exits

    def get_visual_requirement(self, start_node: MissionOrderNode) -> 'str | SC2MOGenMission':
        visual_name = self.get_visual_name()
        if start_node.id[:len(self.id)] == self.id:
            # This campaign is a parent of the node getting a requirement printout
            if not visual_name:
                return "this campaign"
        return visual_name

    def get_visual_name(self) -> str:
        return self.display_name

    def get_key_name(self, id_to_node: dict[tuple[int, ...], MissionOrderNode]) -> str:
        return item_names._TEMPLATE_NAMED_CAMPAIGN_KEY.format(self.get_visual_name())

    def get_min_depth(self) -> int:
        return self.min_depth

    def get_address_to_node(self, id_to_node: dict[tuple[int, ...], MissionOrderNode]) -> str:
        return f"{self.option_name}"

    def get_slot_data(self) -> dict[str, Any]:
        if self.important_beat_event:
            exits = [slot.mission.id for slot in self.exits]
        else:
            exits = []

        return asdict(CampaignSlotData(
            self.get_visual_name(),
            self.entry_rule.to_slot_data(),
            exits,
            [layout.get_slot_data() for layout in self.layouts]
        ))


class SC2MOGenLayout:
    option_name: str  # name of this layout
    option_display_name: list[str]  # visual name of this layout
    option_unique_name: bool
    option_type: str  # type of this layout
    option_size: int  # amount of missions in this layout
    option_goal: bool  # whether this layout is required to beat the game
    option_exit: bool  # whether this layout is required to beat its parent campaign
    option_mission_pool: set[int]  # IDs of valid missions for this layout
    option_missions: list['MissionSlotDict']

    option_entry_rules: list['EntryRuleDict']
    option_unique_progression_track: int  # progressive keys under this layout and on this track will be changed to a unique track

    # minimum difficulty of this layout
    # 'relative': based on the median distance of the first mission
    option_min_difficulty: Difficulty
    # maximum difficulty of this layout
    # 'relative': based on the median distance of the last mission
    option_max_difficulty: Difficulty

    missions: list['SC2MOGenMission']
    layout_type: LayoutType
    entrances: list['SC2MOGenMission']
    exits: list['SC2MOGenMission']
    entry_rule: SubRuleEntryRule
    display_name: str

    min_depth: int
    max_depth: int

    def __init__(
        self,
        world: 'SC2World',
        id: tuple[int, ...],
        name: str,
        data: 'LayoutDict'
    ) -> None:
        self.id = id
        self.important_beat_event = False
        self.option_name = name
        self.option_display_name = data["display_name"]
        self.option_unique_name = data["unique_name"]
        self.option_type = data["type"]
        self.option_size = data.get("size")
        self.option_goal = data["goal"]
        self.option_exit = data["exit"]
        self.option_mission_pool = data["mission_pool"]
        self.option_missions = data["missions"]
        self.option_entry_rules = data["entry_rules"]
        self.option_unique_progression_track = data.get("unique_progression_track")
        self.option_min_difficulty = Difficulty(data["min_difficulty"])
        self.option_max_difficulty = Difficulty(data["max_difficulty"])
        self.missions = []
        self.entrances = []
        self.exits = []

        # Check for positive size now instead of during YAML validation to actively error with default size
        if self.option_size == 0:
            raise ValueError(f"Layout \"{self.option_name}\" has a size of 0.")

        # Build base layout
        from . import layout_types
        self.layout_type: LayoutType = layout_types.LAYOUT_TYPE_NAME_TO_CLASS[self.option_type](self.option_size)
        self.layout_type.set_options(data)

        def mission_factory(index: int) -> SC2MOGenMission:
            return SC2MOGenMission((*self.id, index,), set(self.option_mission_pool))
        self.missions = self.layout_type.make_slots(mission_factory)

        # Update missions with user data
        for mission_data in self.option_missions:
            indices: set[int] = set()
            index_terms: list[int | str] = mission_data["index"]
            for term in index_terms:
                result = self.resolve_index_term(term, "specifying mission indices")
                indices.update(result)
            for idx in indices:
                self.missions[idx].update_with_data(mission_data)

        # Let layout respond to user changes
        self.layout_type.final_setup(self.missions)

        for mission in self.missions:
            if mission.option_entrance:
                self.entrances.append(mission)
            if mission.option_exit:
                self.exits.append(mission)
            if mission.option_next is not None:
                mission.next = [
                    self.missions[idx]
                    for term in mission.option_next
                    for idx in sorted(self.resolve_index_term(
                        term, "specifying next mission", search_info=(mission, self)
                    ))
                ]

        # Set up missions' prev data
        for mission in self.missions:
            for next_mission in mission.next:
                next_mission.prev.append(mission)

        # Remove empty missions from access data
        for mission in self.missions:
            if mission.option_empty:
                for next_mission in mission.next:
                    next_mission.prev.remove(mission)
                mission.next.clear()
                for prev_mission in mission.prev:
                    prev_mission.next.remove(mission)
                mission.prev.clear()

        # Clean up data and options
        all_empty = True
        for mission in self.missions:
            if mission.option_empty:
                # Empty missions cannot be entrances, exits, or required
                # This is done now instead of earlier to make "set all default entrances to empty" not fail
                if mission in self.entrances:
                    self.entrances.remove(mission)
                mission.option_entrance = False
                if mission in self.exits:
                    self.exits.remove(mission)
                mission.option_exit = False
                mission.option_goal = False
                # Empty missions are also not allowed to cause secondary effects via entry rules (eg. create key items)
                mission.option_entry_rules = []
            else:
                all_empty = False
                # Establish the following invariant:
                # A non-empty mission has no prev missions <=> A non-empty mission is an entrance
                # This is mandatory to guarantee the entire layout is accessible via consecutive .nexts
                # Note that the opposite is not enforced for exits to allow fully optional layouts
                if len(mission.prev) == 0:
                    mission.option_entrance = True
                    self.entrances.append(mission)
                elif mission.option_entrance:
                    for prev_mission in mission.prev:
                        prev_mission.next.remove(mission)
                    mission.prev.clear()
        if all_empty:
            raise OptionError(f"Layout \"{self.option_name}\" only contains empty mission slots.")

    def is_beaten(self, beaten_missions: set['SC2MOGenMission']) -> bool:
        return beaten_missions.issuperset(self.exits)

    def is_always_unlocked(self, in_region_creation = False) -> bool:
        return self.entry_rule.is_always_fulfilled(in_region_creation)

    def is_unlocked(self, beaten_missions: set['SC2MOGenMission'], in_region_creation = False) -> bool:
        return self.entry_rule.is_fulfilled(beaten_missions, in_region_creation)

    def resolve_index_term(
        self,
        term: str | int,
        context: str,
        *,
        reject_none: bool = True,
        search_info: tuple['SC2MOGenMission', 'SC2MOGenLayout'] | tuple[()] = (),
    ) -> set[int]:
        result: set[int]
        try:
            int_term = int(term)
            if int_term < 0:
                int_term += len(self.missions)
            result = {int_term}
        except ValueError:
            assert isinstance(term, str)
            if term == "entrances":
                result = {idx for idx in range(len(self.missions)) if self.missions[idx].option_entrance}
            elif term == "exits":
                result = {idx for idx in range(len(self.missions)) if self.missions[idx].option_exit}
            elif term == "all":
                result = {idx for idx in range(len(self.missions))}
            else:
                result = self.layout_type.parse_index(term, search_info, len(self.missions), context)
                if not result and reject_none:
                    raise OptionError(f"Layout \"{self.option_name}\" could not resolve mission index term \"{term}\".")
        # Ignore out-of-bounds
        result = {index for index in result if index >= 0 and index < len(self.missions)}
        return result

    def children(self) -> Sequence['MissionOrderNode']:
        return self.missions

    def search(
        self,
        term: str,
        search_info: tuple['SC2MOGenMission', 'SC2MOGenLayout'] | tuple[()],
    ) -> list[MissionOrderNode]:
        indices = self.resolve_index_term(term, "defining entry rule mission requirements", reject_none=False, search_info=search_info)
        if indices is None:
            # Let the caller handle the fail case
            return []
        return [self.missions[index] for index in sorted(indices)]

    def type_name(self) -> str:
        return "Questline"

    def get_missions(self) -> list['SC2MOGenMission']:
        return [mission for mission in self.missions]

    def get_exits(self) -> list['SC2MOGenMission']:
        return self.exits

    def get_visual_requirement(self, start_node: MissionOrderNode) -> 'str | SC2MOGenMission':
        visual_name = self.get_visual_name()
        if start_node.id[:len(self.id)] == self.id:
            # This layout is a parent of the node getting a requirement printout
            if not visual_name:
                return "this questline"
        return visual_name

    def get_visual_name(self) -> str:
        return self.display_name

    def get_key_name(self, id_to_node: dict[tuple[int, ...], MissionOrderNode]) -> str:
        parent_node = id_to_node[parent_id(self.id)]
        return item_names._TEMPLATE_NAMED_LAYOUT_KEY.format(self.get_visual_name(), parent_node.get_visual_name())

    def get_min_depth(self) -> int:
        return self.min_depth

    def get_address_to_node(self, id_to_node: dict[tuple[int, ...], MissionOrderNode]) -> str:
        campaign = cast(SC2MOGenCampaign, id_to_node[parent_id(self.id)])
        if campaign.option_single_layout_campaign:
            return f"{self.option_name}"
        return campaign.get_address_to_node(id_to_node) + f"/{self.option_name}"

    def get_slot_data(self) -> dict[str, Any]:
        mission_slots: list[list[MissionSlotData]] = [
            [
                self.missions[idx].get_slot_data()
                if (idx >= 0 and not self.missions[idx].option_empty)
                else MissionSlotData.empty_slot_data()
                for idx in column
            ]
            for column in self.layout_type.get_visual_layout()
        ]
        if self.important_beat_event:
            exits = [slot.mission.id for slot in self.exits]
        else:
            exits = []

        return asdict(LayoutSlotData(
            self.get_visual_name(),
            self.entry_rule.to_slot_data(),
            exits,
            mission_slots
        ))


class SC2MOGenMission:
    option_goal: bool  # whether this mission is required to beat the game
    option_entrance: bool  # whether this mission is unlocked when the layout is unlocked
    option_exit: bool  # whether this mission is required to beat its parent layout
    option_empty: bool  # whether this slot contains a mission at all
    option_next: list[int | str] | None  # indices of internally connected missions
    option_entry_rules: list['EntryRuleDict']
    option_difficulty: Difficulty | int  # difficulty pool this mission pulls from
    option_mission_pool: set[int]  # Allowed mission IDs for this slot
    option_victory_cache: int  # Number of victory cache locations tied to the mission name
    option_heroes: list[str] | None  # Exact heroes assigned to this slot, or None to use normal hero presence

    entry_rule: SubRuleEntryRule
    min_depth: int # Smallest amount of missions to beat before this slot is accessible

    mission: SC2Mission
    region: Region

    next: list['SC2MOGenMission']
    prev: list['SC2MOGenMission']

    def __init__(self, id: tuple[int, ...], parent_mission_pool: set[int]) -> None:
        self.id = id
        self.important_beat_event = False
        self.option_mission_pool = parent_mission_pool
        self.option_goal = False
        self.option_entrance = False
        self.option_exit = False
        self.option_empty = False
        self.option_next = None
        self.option_entry_rules = []
        self.option_difficulty = Difficulty.RELATIVE
        self.next = []
        self.prev = []
        self.min_depth = -1
        self.option_victory_cache = -1
        self.option_heroes = None

    def update_with_data(self, data: 'MissionSlotDict') -> None:
        self.option_goal = data.get("goal", self.option_goal)
        self.option_entrance = data.get("entrance", self.option_entrance)
        self.option_exit = data.get("exit", self.option_exit)
        self.option_empty = data.get("empty", self.option_empty)
        self.option_next = data.get("next", self.option_next)
        self.option_entry_rules = data.get("entry_rules", self.option_entry_rules)
        self.option_difficulty = data.get("difficulty", self.option_difficulty)
        self.option_mission_pool = data.get("mission_pool", self.option_mission_pool)
        self.option_victory_cache = data.get("victory_cache", -1)
        self.option_heroes = data.get("heroes", self.option_heroes)

    def is_always_unlocked(self, in_region_creation = False) -> bool:
        return self.entry_rule.is_always_fulfilled(in_region_creation)

    def is_unlocked(self, beaten_missions: set['SC2MOGenMission'], in_region_creation = False) -> bool:
        return self.entry_rule.is_fulfilled(beaten_missions, in_region_creation)

    def beat_item(self) -> str:
        return f"Beat {self.mission.mission_name}"

    def beat_rule(self, player) -> Callable[[CollectionState], bool]:
        return lambda state: state.has(self.beat_item(), player)

    def children(self) -> Sequence['MissionOrderNode']:
        return []

    def search(
        self,
        term: str,
        search_info: tuple['SC2MOGenMission', 'SC2MOGenLayout'] | tuple[()],
    ) -> list[MissionOrderNode]:
        return []

    def type_name(self) -> str:
        return "Mission"

    def get_missions(self) -> list['SC2MOGenMission']:
        return [self]

    def get_exits(self) -> list['SC2MOGenMission']:
        return [self]

    def get_visual_requirement(self, _start_node: MissionOrderNode) -> 'str | SC2MOGenMission':
        return self

    def get_visual_name(self) -> str:
        return f"Mission_{'.'.join(map(str, self.id))}"

    def get_key_name(self, id_to_node: dict[tuple[int, ...], MissionOrderNode]) -> str:
        return item_names._TEMPLATE_MISSION_KEY.format(self.mission.mission_name)

    def get_min_depth(self) -> int:
        return self.min_depth

    def get_address_to_node(self, id_to_node: dict[tuple[int, ...], MissionOrderNode]) -> str:
        layout = cast(SC2MOGenLayout, id_to_node[parent_id(self.id)])
        index = layout.missions.index(self)
        return layout.get_address_to_node(id_to_node) + f"/{index}"

    def get_slot_data(self) -> dict[str, Any]:
        return asdict(MissionSlotData(
            self.mission.id,
            [mission.mission.id for mission in self.prev],
            self.entry_rule.to_slot_data(),
            self.option_victory_cache,
            self.min_depth,
        ))

    def __str__(self) -> str:
        terms = [f"id={self.id}", f"mission={self.mission}"]
        if self.option_empty:
            terms.append(f"empty=True")
        if self.option_goal:
            terms.append(f"goal=True")
        return f"MissionSlot({', '.join(terms)})"

    def __repr__(self) -> str:
        return self.__str__()
