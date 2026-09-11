import enum
from dataclasses import dataclass
from typing import Optional, Union, Dict, Type, NamedTuple

from BaseClasses import Item, ItemClassification
from ..mission_tables import SC2Race


class ItemFilterFlags(enum.IntFlag):
    """Removed > Start Inventory > Locked > Excluded > Requested > Culled"""
    Available = 0
    StartInventory = enum.auto()
    Locked = enum.auto()
    """Used to flag items that are never allowed to be culled."""
    LogicLocked = enum.auto()
    """Locked by item cull logic checks; logic-locked w/a upgrades may be removed if all parents are removed"""
    Requested = enum.auto()
    """Soft-locked items by item count checks during item culling; may be re-added"""
    Removed = enum.auto()
    """Marked for immediate removal"""
    UserExcluded = enum.auto()
    """Excluded by the user; display an error message if failing to exclude"""
    FilterExcluded = enum.auto()
    """Excluded by item filtering"""
    Culled = enum.auto()
    """Soft-removed by the item culling"""
    NonLocal = enum.auto()
    Plando = enum.auto()
    AllowedOrphan = enum.auto()
    """Used to flag items that shouldn't be filtered out with their parents"""
    ForceProgression = enum.auto()
    """Used to flag items that aren't classified as progression by default"""

    Unexcludable = StartInventory|Plando|Locked|LogicLocked
    UnexcludableUpgrade = StartInventory|Plando|Locked
    Uncullable = StartInventory|Plando|Locked|LogicLocked|Requested
    Excluded = UserExcluded|FilterExcluded
    RequestedOrBetter = StartInventory|Locked|LogicLocked|Requested
    CulledOrBetter = Removed|Excluded|Culled


class StarcraftItem(Item):
    game: str = "Starcraft 2"
    filter_flags: ItemFilterFlags = ItemFilterFlags.Available

    def __init__(self, name: str, classification: ItemClassification, code: Optional[int], player: int, filter_flags: ItemFilterFlags = ItemFilterFlags.Available):
        super().__init__(name, classification, code, player)
        self.filter_flags = filter_flags

class ItemTypeEnum(enum.Enum):
    def __new__(cls, *args, **kwargs):
        value = len(cls.__members__) + 1
        obj = object.__new__(cls)
        obj._value_ = value
        return obj

    def __init__(self, name: str, flag_word: int):
        self.display_name = name
        self.flag_word = flag_word


class TerranItemType(ItemTypeEnum):
    Unit = "Unit", 0
    Item = "Item", 1
    Upgrade = "Upgrade", 2
    Progressive = "Progressive Upgrade", 3


class ZergItemType(ItemTypeEnum):
    Unit = "Unit", 0
    Item = "Item", 1
    Upgrade = "Upgrade", 2
    Progressive = "Progressive Upgrade", 3

class ProtossItemType(ItemTypeEnum):
    Unit = "Unit", 0
    Item = "Item", 1
    Upgrade = "Upgrade", 2
    Progressive = "Progressive Upgrade", 3


class FactionlessItemType(ItemTypeEnum):
    Minerals = "Minerals", 0
    Vespene = "Vespene", 1
    Supply = "Supply", 2
    MaxSupply = "Max Supply", 3
    BuildingSpeed = "Building Speed", 4
    Nothing = "Nothing Group", 5
    Deprecated = "Deprecated", 6
    MaxSupplyTrap = "Max Supply Trap", 7
    ResearchSpeed = "Research Speed", 8
    ResearchCost = "Research Cost", 9
    Level = "Level", 10
    ShieldRegeneration = "Shield Regeneration Group", 11
    GhostSpawnTrap = "Ghost Spawn Trap", 12
    VoidDuplicateTrap = "Void Duplicate Trap", 13
    Keys = "Keys", -1


ItemType = Union[TerranItemType, ZergItemType, ProtossItemType, FactionlessItemType]
race_to_item_type: Dict[SC2Race, Type[ItemTypeEnum]] = {
    SC2Race.ANY: FactionlessItemType,
    SC2Race.TERRAN: TerranItemType,
    SC2Race.ZERG: ZergItemType,
    SC2Race.PROTOSS: ProtossItemType,
}


class ItemData(NamedTuple):
    code: int
    type: ItemType
    number: int  # Important for bot commands to send the item into the game
    race: SC2Race
    classification: ItemClassification = ItemClassification.useful
    quantity: int = 1
    parent: str | None = None
    important_for_filtering: bool = False

    def is_important_for_filtering(self):
        return (
                self.important_for_filtering
                or self.classification == ItemClassification.progression
                or self.classification == ItemClassification.progression_skip_balancing
        )

@dataclass
class FilterItem:
    name: str
    data: ItemData
    index: int = 0
    flags: ItemFilterFlags = ItemFilterFlags.Available
