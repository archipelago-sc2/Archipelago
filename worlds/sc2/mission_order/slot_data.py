"""
Houses the data structures representing a mission order in slot data.
Creating these is handled by the nodes they represent in .nodes.py.
"""

from __future__ import annotations
from typing import List, Protocol, Any, TypedDict, NotRequired
from dataclasses import dataclass, field

from .entry_rules import SubRuleRuleData, SubRuleRuleDataDict

class MissionOrderObjectSlotData(Protocol):
    entry_rule: SubRuleRuleData


@dataclass
class CampaignSlotData:
    name: str
    entry_rule: SubRuleRuleData
    exits: list[int]
    layouts: list[LayoutSlotData]

    @staticmethod
    def legacy(name: str, layouts: List[LayoutSlotData]) -> CampaignSlotData:
        return CampaignSlotData(name, SubRuleRuleData.empty(), [], layouts)


class CampaignSlotDataDict(TypedDict):
    name: str
    entry_rule: SubRuleRuleDataDict
    exits: list[int]
    layouts: list['LayoutSlotDataDict']


@dataclass
class LayoutSlotData:
    name: str
    entry_rule: SubRuleRuleData
    exits: list[int]
    missions: list[list[MissionSlotData]]

    @staticmethod
    def legacy(name: str, missions: list[list[MissionSlotData]]) -> LayoutSlotData:
        return LayoutSlotData(name, SubRuleRuleData.empty(), [], missions)


class LayoutSlotDataDict(TypedDict):
    name: str
    entry_rule: SubRuleRuleDataDict
    exits: list[int]
    missions: list[list['MissionSlotDataDict']]


@dataclass
class MissionSlotData:
    mission_id: int = -1
    prev_mission_ids: list[int] = field(default_factory=list)
    entry_rule: SubRuleRuleData = field(default_factory=SubRuleRuleData.empty)
    victory_cache_size: int = 0
    min_depth: int = 0

    @staticmethod
    def empty_slot_data() -> dict[str, Any]:
        return {}

    @staticmethod
    def legacy(mission_id: int, prev_mission_ids: List[int], entry_rule: SubRuleRuleData) -> MissionSlotData:
        return MissionSlotData(mission_id, prev_mission_ids, entry_rule)


class MissionSlotDataDict(TypedDict):
    mission_id: NotRequired[int]
    prev_mission_ids: NotRequired[list[int]]
    entry_rule: NotRequired[SubRuleRuleDataDict]
    victory_cache_size: NotRequired[int]
    min_depth: NotRequired[int]
