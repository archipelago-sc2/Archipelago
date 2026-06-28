"""
Helper functions for combining rules.
"""
from typing import TypeVar, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from BaseClasses import CollectionState


T = TypeVar('T')


def identity(x: T) -> T:
    return x


def and_2_rules(
    rule_1: Callable[["CollectionState"], bool],
    rule_2: Callable[["CollectionState"], bool],
) -> Callable[["CollectionState"], bool]:
    def and_2(state: "CollectionState") -> bool:
        return rule_1(state) and rule_2(state)
    return and_2


def and_3_rules(
    rule_1: Callable[["CollectionState"], bool],
    rule_2: Callable[["CollectionState"], bool],
    rule_3: Callable[["CollectionState"], bool],
) -> Callable[["CollectionState"], bool]:
    def and_3(state: "CollectionState") -> bool:
        return rule_1(state) and rule_2(state) and rule_3(state)
    return and_3


def and_4_rules(
    rule_1: Callable[["CollectionState"], bool],
    rule_2: Callable[["CollectionState"], bool],
    rule_3: Callable[["CollectionState"], bool],
    rule_4: Callable[["CollectionState"], bool],
) -> Callable[["CollectionState"], bool]:
    def and_4(state: "CollectionState") -> bool:
        return rule_1(state) and rule_2(state) and rule_3(state) and rule_4(state)
    return and_4


def and_5_rules(
    rule_1: Callable[["CollectionState"], bool],
    rule_2: Callable[["CollectionState"], bool],
    rule_3: Callable[["CollectionState"], bool],
    rule_4: Callable[["CollectionState"], bool],
    rule_5: Callable[["CollectionState"], bool],
) -> Callable[["CollectionState"], bool]:
    def and_5(state: "CollectionState") -> bool:
        return (
            rule_1(state)
            and rule_2(state)
            and rule_3(state)
            and rule_4(state)
            and rule_5(state)
        )
    return and_5


def and_6_rules(
    rule_1: Callable[["CollectionState"], bool],
    rule_2: Callable[["CollectionState"], bool],
    rule_3: Callable[["CollectionState"], bool],
    rule_4: Callable[["CollectionState"], bool],
    rule_5: Callable[["CollectionState"], bool],
    rule_6: Callable[["CollectionState"], bool],
) -> Callable[["CollectionState"], bool]:
    def and_6(state: "CollectionState") -> bool:
        return (
            rule_1(state)
            and rule_2(state)
            and rule_3(state)
            and rule_4(state)
            and rule_5(state)
            and rule_6(state)
        )
    return and_6


def and_7_rules(
    rule_1: Callable[["CollectionState"], bool],
    rule_2: Callable[["CollectionState"], bool],
    rule_3: Callable[["CollectionState"], bool],
    rule_4: Callable[["CollectionState"], bool],
    rule_5: Callable[["CollectionState"], bool],
    rule_6: Callable[["CollectionState"], bool],
    rule_7: Callable[["CollectionState"], bool],
) -> Callable[["CollectionState"], bool]:
    def and_7(state: "CollectionState") -> bool:
        return (
            rule_1(state)
            and rule_2(state)
            and rule_3(state)
            and rule_4(state)
            and rule_5(state)
            and rule_6(state)
            and rule_7(state)
        )
    return and_7


def and_8_rules(
    rule_1: Callable[["CollectionState"], bool],
    rule_2: Callable[["CollectionState"], bool],
    rule_3: Callable[["CollectionState"], bool],
    rule_4: Callable[["CollectionState"], bool],
    rule_5: Callable[["CollectionState"], bool],
    rule_6: Callable[["CollectionState"], bool],
    rule_7: Callable[["CollectionState"], bool],
    rule_8: Callable[["CollectionState"], bool],
) -> Callable[["CollectionState"], bool]:
    def and_8(state: "CollectionState") -> bool:
        return (
            rule_1(state)
            and rule_2(state)
            and rule_3(state)
            and rule_4(state)
            and rule_5(state)
            and rule_6(state)
            and rule_7(state)
            and rule_8(state)
        )
    return and_8


def and_9_rules(
    rule_1: Callable[["CollectionState"], bool],
    rule_2: Callable[["CollectionState"], bool],
    rule_3: Callable[["CollectionState"], bool],
    rule_4: Callable[["CollectionState"], bool],
    rule_5: Callable[["CollectionState"], bool],
    rule_6: Callable[["CollectionState"], bool],
    rule_7: Callable[["CollectionState"], bool],
    rule_8: Callable[["CollectionState"], bool],
    rule_9: Callable[["CollectionState"], bool],
) -> Callable[["CollectionState"], bool]:
    def and_9(state: "CollectionState") -> bool:
        return (
            rule_1(state)
            and rule_2(state)
            and rule_3(state)
            and rule_4(state)
            and rule_5(state)
            and rule_6(state)
            and rule_7(state)
            and rule_8(state)
            and rule_9(state)
        )
    return and_9


def and_10_rules(
    rule_1: Callable[["CollectionState"], bool],
    rule_2: Callable[["CollectionState"], bool],
    rule_3: Callable[["CollectionState"], bool],
    rule_4: Callable[["CollectionState"], bool],
    rule_5: Callable[["CollectionState"], bool],
    rule_6: Callable[["CollectionState"], bool],
    rule_7: Callable[["CollectionState"], bool],
    rule_8: Callable[["CollectionState"], bool],
    rule_9: Callable[["CollectionState"], bool],
    rule_10: Callable[["CollectionState"], bool],
) -> Callable[["CollectionState"], bool]:
    def and_10(state: "CollectionState") -> bool:
        return (
            rule_1(state)
            and rule_2(state)
            and rule_3(state)
            and rule_4(state)
            and rule_5(state)
            and rule_6(state)
            and rule_7(state)
            and rule_8(state)
            and rule_9(state)
            and rule_10(state)
        )
    return and_10


COUNT_TO_AND_FUNCTION: dict[int, Callable] = {
    1: identity,
    2: and_2_rules,
    3: and_3_rules,
    4: and_4_rules,
    5: and_5_rules,
    6: and_6_rules,
    7: and_7_rules,
    8: and_8_rules,
    9: and_9_rules,
    10: and_10_rules,
}
