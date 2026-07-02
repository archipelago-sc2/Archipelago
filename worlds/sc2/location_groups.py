"""
Location group definitions
"""

from . import locations
from .mission_tables import MissionFlag

def get_location_groups() -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}

    for location_name, location_id in locations.LOCATION_NAME_TO_ID.items():
        if location_id is None:
            # Beat events
            continue
        mission = locations.location_id_to_mission(location_id)

        if (MissionFlag.HasRaceSwap|MissionFlag.RaceSwap) & mission.flags:
            # Location group including race-swapped variants of a location
            agnostic_location_name = (
                location_name
                .replace(' (Terran)', '')
                .replace(' (Protoss)', '')
                .replace(' (Zerg)', '')
            )
            result.setdefault(agnostic_location_name, set()).add(location_name)

            # Location group including all locations in all raceswaps
            result.setdefault(mission.mission_name[:mission.mission_name.find(' (')], set()).add(location_name)

        # Location group including all locations in a mission
        result.setdefault(mission.mission_name, set()).add(location_name)

        # Location group by location category
        location_type = locations.location_id_to_type(location_id)
        result.setdefault(location_type.name.title(), set()).add(location_name)

    return result
