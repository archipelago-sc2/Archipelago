"""
Utilities for interaction between apclient and game.
"""
from typing import TYPE_CHECKING, NamedTuple, Literal
import logging
import os
import subprocess
import inspect
import asyncio
import time

import Utils
from Utils import async_start
from NetUtils import ClientStatus, NetworkItem

from . import banks, user_paths
from .failable import Error
from .transfer_data import normalized_unit_types
from .. import options, locations, item, rules
from .. import SC2World
from ..item import item_tables, item_names, item_groups
from ..item import ZergItemType
from ..mission_tables import (
    lookup_id_to_mission,
    SC2Mission,
    SC2Race,
    MissionFlag,
)

if TYPE_CHECKING:
    from ..client import SC2Context


MAX_BONUS: int = 28
logger = logging.getLogger("Starcraft2")


class MissionClient:
    __slots__ = [
        'update_number',
        'mission_completed',
        'task',
        'running',
        'ctx',
        'mission_id',
        'switcher_process',
        'sc2_pid',
        'bonuses',
        'trade_reply_cooldown',
        'last_received_update',
        'last_trade_cargo',
        'update_period_seconds',
        'start_time',
    ]

    def __init__(self, ctx: 'SC2Context', mission_id: int, process: subprocess.Popen) -> None:
        self.update_number: int = -1
        self.mission_completed = False
        self.task: asyncio.Task | None = None
        self.running = True
        self.ctx = ctx
        self.mission_id = mission_id
        self.switcher_process = process
        self.sc2_pid: int | None = None
        self.bonuses = [False for _ in range(MAX_BONUS)]
        self.trade_reply_cooldown: int = 0
        self.last_received_update: int = 0
        self.last_trade_cargo: set = set()
        self.update_period_seconds = 0.5
        self.start_time = time.time_ns()

    def check_game_running(self) -> bool:
        if not self.running:
            return False
        if self.sc2_pid is None:
            return True
        self.running = is_pid_running(self.sc2_pid)
        return self.running

    def is_switcher_process_closed(self) -> bool:
        return self.switcher_process.poll() is not None

    def game_time_seconds(self) -> float:
        """
        How long the mission has been running in realtime.
        Does not account for menu time/pause time.
        """
        return (time.time_ns() - self.start_time) / 1_000_000_000

    def close(self) -> None:
        if self.switcher_process.poll() is None:
            self.switcher_process.kill()
        if self.running and self.sc2_pid is not None:
            kill_pid(self.sc2_pid)
        self.running = False

    def do_setup(self) -> None:
        mission = lookup_id_to_mission[self.mission_id]
        start_items = calculate_items(self.ctx, self.mission_id)
        missions_beaten = self.missions_beaten_count()
        kerrigan_level = get_kerrigan_level(self.ctx, start_items, missions_beaten, self.mission_id)
        kerrigan_options = calculate_kerrigan_options(self.ctx)
        hero_presence = self.ctx.hero_presence.get(mission, 0)
        logger.debug(f"Hero settings for current mission: {hero_presence}") # TODO (Snarky): Disable on release
        grant_story_tech = calculate_story_tech(self.ctx, mission)
        soa_options = calculate_soa_options(self.ctx, mission)
        generic_upgrade_options = calculate_generic_upgrade_options(self.ctx)
        trade_options = calculate_trade_options(self.ctx)
        mission_variant = get_mission_variant(self.mission_id)  # 0/1/2/3 for unchanged/Terran/Zerg/Protoss
        uncollected_objectives: list[int] = self.get_uncollected_objectives()
        if self.ctx.difficulty_override >= 0:
            difficulty = calc_difficulty(self.ctx.difficulty_override)
        else:
            difficulty = calc_difficulty(self.ctx.difficulty)
        if self.ctx.game_speed_override >= 0:
            game_speed = self.ctx.game_speed_override
        else:
            game_speed = self.ctx.game_speed
        skip_cutscenes = 1 if SC2World.settings.game_skip_cutscenes else 0
        disable_forced_camera = 1 if SC2World.settings.game_disable_forced_camera else 0
        nova_presence = 0  # unused for now
        error = banks.send_options(
            f" {difficulty}"
            f" {generic_upgrade_options}"
            f" {self.ctx.all_in_choice}"
            f" {game_speed}"
            f" {disable_forced_camera}"
            f" {skip_cutscenes}"
            f" {kerrigan_options}"
            f" {grant_story_tech}"
            f" {self.ctx.take_over_ai_allies}"
            f" {soa_options}"
            f" {self.ctx.mission_order}"
            f" {nova_presence}"
            f" {self.ctx.grant_story_levels}"
            f" {self.ctx.enable_morphling}"
            f" {mission_variant}"
            f" {trade_options}"
            f" {self.ctx.difficulty_damage_modifier}"
            f" {self.ctx.mercenary_highlanders}" # TODO: Possibly rework into unit options
            f" {self.ctx.show_war_council_nerfs}"
            f" {hero_presence}"
        )
        if isinstance(error, Error):
            logger.error(error.message)
            return
        self.update_tech(start_items, kerrigan_level)
        objectives = ""
        if uncollected_objectives:
            objectives = " ".join(f"{str(objective)}" for objective in uncollected_objectives)
        error = banks.send_core_options(
            self.get_resources(start_items),
            self.get_colors(),
            objectives,
            "1"
        )
        if isinstance(error, Error):
            logger.error(error.message)
            return
        self.last_received_update = len(self.ctx.items_received)

    async def client_loop(self) -> None:
        while self.running:
            await asyncio.sleep(self.update_period_seconds)
            try:
                await self.on_step()
            except Exception as ex:
                logger.error(ex)

    async def on_step(self) -> None:
        # @assume setup is done
        if self.sc2_pid is None:
            if not self.is_switcher_process_closed():
                # Still starting up
                return
            self.sc2_pid = get_sc2_pid()
            logger.debug(f"sc2 process ID is {self.sc2_pid}")
            return
        elif self.update_number % 10 == 0:
            if not self.check_game_running():
                logger.debug("sc2 process exited")
        game_state = 0
        error = banks.send_ap_messages_from_queue(self.ctx.announcements)
        if isinstance(error, Error):
            logger.error(error.message)
            return
        trade_send_string = self.get_trade_units_sent()
        # Message format:
        # <unit1> <unit2> <unit3>...
        if len(trade_send_string) > 0:
            units_to_send: list[str] = []
            non_ap_units: set[str] = set()
            for unit_id in trade_send_string.split():
                if unit_id.startswith("AP_"):
                    units_to_send.append(normalized_unit_types.get(unit_id, unit_id))
                else:
                    non_ap_units.add(unit_id)
            if len(non_ap_units) > 0:
                logger.info(f"Void Trade tried to send non-AP units: {', '.join(non_ap_units)}")
                banks.send_trade_received("FailNonAPUnits")
                self.ctx.trade_underway = True
            else:
                self.ctx.trade_response = None
                self.ctx.trade_underway = True
                async_start(self.ctx.trade_send(units_to_send))

        trade_receive_string = self.get_trade_receive_request()
        # Message format:
        # <count>
        if len(trade_receive_string) > 0:
            if int(trade_receive_string) == 1:
                self.ctx.trade_underway = True
                self.ctx.trade_response = None
                async_start(self.ctx.trade_receive(1))
                # TODO (snarky): handle supply, self.ctx.trade_response = "?TradeFail Void Trade rejected: Not enough supply."
            elif int(trade_receive_string) == 5:
                self.ctx.trade_underway = True
                self.ctx.trade_response = None
                async_start(self.ctx.trade_receive(5))

        game_state = self.get_locations()

        if game_state & 1:
            self.update_number += 1
            if self.update_number == 0:
                error = banks.send_ap_message(["Archipelago Connected"])
                if isinstance(error, Error):
                    logger.error(error.message)
                    return

        if banks.update_prompt():
            self.last_received_update = 0

        if self.last_received_update < len(self.ctx.items_received):
            current_items = calculate_items(self.ctx, self.mission_id)
            missions_beaten = self.missions_beaten_count()
            kerrigan_level = get_kerrigan_level(self.ctx, current_items, missions_beaten, self.mission_id)
            if (error := self.update_core_options(current_items)):
                logger.error(error.message)
                return
            if (error := self.update_tech(current_items, kerrigan_level)):
                logger.error(error.message)
                return
            self.last_received_update = len(self.ctx.items_received)

        if game_state & 1:
            if game_state & (1 << 1) and not self.mission_completed:
                victory_locations = [locations.get_location_id(self.mission_id, 0)]
                send_victory = (
                    self.mission_id in self.ctx.final_mission_ids
                    and (
                        len(self.ctx.final_locations)
                        == len(
                            self.ctx.checked_locations
                            .union(victory_locations)
                            .intersection(self.ctx.final_locations)
                        )
                    )
                )

                # Old slots don't have locations on goal
                if not send_victory or self.ctx.slot_data_version >= 4:
                    logger.info("Mission Completed")
                    location_ids = self.ctx.mission_id_to_location_ids[self.mission_id]
                    victory_locations += sorted([
                        locations.get_location_id(self.mission_id, location_id)
                        for location_id in location_ids
                        if (location_id % locations.VICTORY_MODULO) >= locations.VICTORY_CACHE_OFFSET
                    ])
                    await self.ctx.send_msgs(
                        [{"cmd": 'LocationChecks',
                            "locations": victory_locations}])
                    self.mission_completed = True

                if send_victory:
                    print("Game Complete")
                    await self.ctx.send_msgs([{"cmd": 'StatusUpdate', "status": ClientStatus.CLIENT_GOAL}])
                    self.mission_completed = True
                    self.ctx.finished_game = True

            for x, completed in enumerate(self.bonuses):
                if not completed and game_state & (1 << (x + 2)):
                    await self.ctx.send_msgs(
                        [{"cmd": 'LocationChecks',
                            "locations": [locations.get_location_id(self.mission_id, x + 1)]}])
                    self.bonuses[x] = True

            # Send Void Trade results
            if self.ctx.trade_response is not None and self.trade_reply_cooldown == 0:
                error = banks.send_ap_message([self.ctx.trade_response])
                if isinstance(error, Error):
                    logger.error(error.message)
                    return
                # Wait an arbitrary amount of frames before trying again
                self.trade_reply_cooldown = 60

    def get_locations(self) -> int:
        result = banks.read_locations()
        if isinstance(result, Error):
            return 0
        if (result.strip()):  # may be "" or " "
            return int(result)
        return 0

    def get_trade_units_sent(self) -> str:
        result = banks.read_trade_units()
        if isinstance(result, Error):
            return ""
        return result

    def get_trade_receive_request(self) -> str:
        result = banks.read_trade_receive_request()
        if isinstance(result, Error):
            return ""
        return result

    def get_uncollected_objectives(self) -> list[int]:
        result = [
            location % locations.VICTORY_MODULO
            for location in self.ctx.uncollected_locations_in_mission(lookup_id_to_mission[self.mission_id])
            if (location % locations.VICTORY_MODULO) < locations.VICTORY_CACHE_OFFSET
        ]
        return result

    def missions_beaten_count(self) -> int:
        return len([
            location for location in self.ctx.checked_locations if location % locations.VICTORY_MODULO == 0
        ])

    def get_colors(self) -> str:
        self.ctx.pending_color_update = False
        result = [
            str(self.ctx.player_color_raynor),
            str(self.ctx.player_color_zerg),
            str(self.ctx.player_color_zerg_primal),
            str(self.ctx.player_color_protoss),
            str(self.ctx.player_color_nova),
        ]
        return ' '.join(result)

    def get_resources(self, current_items: dict[SC2Race, list[int]]) -> str:
        DEFAULT_MAX_SUPPLY = 200
        max_supply_amount = max(
            DEFAULT_MAX_SUPPLY
            + (
                current_items[SC2Race.ANY][get_item_flag_word(item_names.MAX_SUPPLY)]
                * self.ctx.maximum_supply_per_item
            )
            - (
                current_items[SC2Race.ANY][get_item_flag_word(item_names.REDUCED_MAX_SUPPLY)]
                * self.ctx.maximum_supply_reduction_per_item
            ),
            self.ctx.lowest_maximum_supply,
        )
        return ("{} {} {} {}".format(
            current_items[SC2Race.ANY][get_item_flag_word(item_names.STARTING_MINERALS)],
            current_items[SC2Race.ANY][get_item_flag_word(item_names.STARTING_VESPENE)],
            current_items[SC2Race.ANY][get_item_flag_word(item_names.STARTING_SUPPLY)],
            max_supply_amount - DEFAULT_MAX_SUPPLY,
        ))

    def get_terran_tech(self, current_items: dict[SC2Race, list[int]]) -> str:
        terran_items = current_items[SC2Race.TERRAN]
        return (" ".join(map(str, terran_items)))

    def get_zerg_tech(self, current_items: dict[SC2Race, list[int]], kerrigan_level: int) -> str:
        zerg_items = current_items[SC2Race.ZERG]
        zerg_items = [
            value
            for index, value in enumerate(zerg_items)
            if index not in (ZergItemType.Level.flag_word, ZergItemType.Primal_Form.flag_word)
        ]
        kerrigan_primal_by_items = is_kerrigan_primal(self.ctx, kerrigan_level)
        kerrigan_primal_bot_value = 1 if kerrigan_primal_by_items else 0
        return(f"{kerrigan_level} {kerrigan_primal_bot_value} " + ' '.join(map(str, zerg_items)))

    def get_protoss_tech(self, current_items: dict[SC2Race, list[int]]) -> str:
        protoss_items = current_items[SC2Race.PROTOSS]
        return (" ".join(map(str, protoss_items)))

    def get_misc_tech(self, current_items: dict[SC2Race, list[int]]) -> str:
        return ("{} {} {}".format(
            current_items[SC2Race.ANY][get_item_flag_word(item_names.BUILDING_CONSTRUCTION_SPEED)],
            current_items[SC2Race.ANY][get_item_flag_word(item_names.UPGRADE_RESEARCH_SPEED)],
            current_items[SC2Race.ANY][get_item_flag_word(item_names.UPGRADE_RESEARCH_COST)],
        ))

    def get_trap_items(self, current_items: dict[SC2Race, list[int]]) -> str:
        return ("{}".format(
            current_items[SC2Race.ANY][get_item_flag_word(item_names.TRAP_GHOST_SPAWN)],
        ))

    def update_tech(self, current_items: dict[SC2Race, list[int]], kerrigan_level: int) -> None | Error[str]:
        return banks.send_items(
            self.get_terran_tech(current_items),
            self.get_zerg_tech(current_items, kerrigan_level),
            self.get_protoss_tech(current_items),
            self.get_misc_tech(current_items),
            self.get_trap_items(current_items),
        )

    def update_core_options(self, current_items: dict[SC2Race, list[int]]) -> None | Error[str]:
        return banks.send_core_options(
            self.get_resources(current_items),
            self.get_colors()
        )


# ################################################################################################ #
#     Startup
# ################################################################################################ #


def launch_game_client(ctx: 'SC2Context', mission_id: int) -> MissionClient | Error[str]:
    error = banks.file_cleanup()
    if isinstance(error, Error):
        return error
    if ctx.slot is None:
        logger.warning(
            "Launching Mission without Archipelago authentication, "
            "checks will not be registered to server."
        )
    process = launch_mission(ctx, mission_id)
    if isinstance(process, Error):
        return process
    client = MissionClient(ctx, mission_id, process)
    client.do_setup()
    client.task = asyncio.create_task(client.client_loop())
    return client


def launch_mission(ctx: 'SC2Context', mission_id: int) -> subprocess.Popen | Error[str]:
    logger.info(f"Launching {lookup_id_to_mission[mission_id].mission_name}.")
    sc2_install_dir = user_paths.get_sc2_install_dir()
    if isinstance(sc2_install_dir, Error):
        return sc2_install_dir
    sc2_switcher_exe = os.path.join(sc2_install_dir, "Support64", "SC2Switcher_x64.exe")
    difficulty = ctx.difficulty if ctx.difficulty_override < 0 else ctx.difficulty_override
    # Note(mm): SC2Switcher accepts difficulty on a scale of 1~4, the Archipelago option is 0~3, though
    difficulty = min(4, difficulty + 1)
    speed = ctx.game_speed if ctx.game_speed_override < 0 else ctx.game_speed_override
    TRIGDEBUG = False
    mission = lookup_id_to_mission[mission_id]
    map_path = os.path.join("ArchipelagoCampaign", mission.campaign.folder, mission.map_file + ".SC2Map")
    command_line = [
        sc2_switcher_exe,
        "-run", map_path,
        # Note(mm): displaymode 2 is available for true fullscreen
        "-displaymode", ("0" if SC2World.settings.game_windowed_mode else "1"),
        "-difficulty", str(difficulty),
    ]

    # Unused but kept around in case we want to take another stab at starting SC2.exe directly
    # sc2_exe = user_paths.get_sc2_exe_path()
    # if isinstance(sc2_exe, Error):
    #     return sc2_exe
    # temp_dir = tempfile.mkdtemp(prefix="SC2_")
    # command_line = [
    #     sc2_exe,
    #     "-listen", "127.0.0.1",
    #     "-port", "44063",
    #     "-dataDir", sc2_install_dir,
    #     "-tempDir", temp_dir,
    #     "-run", map_path,
    #     # Note(mm): displaymode 2 is available for true fullscreen
    #     "-displaymode", ("0" if SC2World.settings.game_windowed_mode else "1"),
    #     "-difficulty", str(difficulty),
    #     '-verbose',
    # ]

    if TRIGDEBUG:
        command_line.append("-trigdebug")
    working_directory = os.path.join(sc2_install_dir, "Support64")
    if speed != options.GameSpeed.option_default:
        # Note(mm): SC2Switcher accepts speed on a scale of 0~5, the Archipelago option 0 is "default" though
        speed = max(0, speed - 1)
        command_line.extend(("-speed", str(speed)))
    if Utils.is_windows:
        with DllDirectory(None):
            logger.debug(command_line)
            return subprocess.Popen(command_line, cwd=working_directory)

    # Linux
    wine = user_paths.get_wine_path()
    if isinstance(wine, Error):
        return wine
    wine_prefix = user_paths.get_wine_prefix()
    if isinstance(wine_prefix, Error):
        return wine_prefix
    command_line = [wine] + command_line
    logger.debug(f"WINEPREFIX: {wine_prefix}")
    logger.debug(command_line)
    return subprocess.Popen(
        command_line,
        env=os.environ | {"WINEPREFIX": wine_prefix},
        stderr=subprocess.DEVNULL,
        cwd=working_directory,
    )


# ################################################################################################ #
#     Platform
# ################################################################################################ #


class DllDirectory:
    """
    Context manager that sets the DLL search path on Windows and restores it on exit.
    Setting the new path to `None` restores the default search order.
    See https://docs.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setdlldirectoryw
    """
    # Credit to Black Sliver for this code.
    _old: str | None = None
    _new: str | None = None

    def __init__(self, new: str | None) -> None:
        self._new = new

    def __enter__(self) -> None:
        old = self.get()
        if self.set(self._new):
            self._old = old

    def __exit__(self, *args) -> None:
        if self._old is not None:
            self.set(self._old)

    @staticmethod
    def get() -> str | None:
        if Utils.is_windows:
            import ctypes
            n = ctypes.windll.kernel32.GetDllDirectoryW(0, None)
            buf = ctypes.create_unicode_buffer(n)
            ctypes.windll.kernel32.GetDllDirectoryW(n, buf)
            return buf.value
        # NOTE: other OS may support os.environ["LD_LIBRARY_PATH"], but this fix is windows-specific
        return None

    @staticmethod
    def set(s: str | None) -> bool:
        if Utils.is_windows:
            import ctypes
            return ctypes.windll.kernel32.SetDllDirectoryW(s) != 0
        # NOTE: other OS may support os.environ["LD_LIBRARY_PATH"], but this fix is windows-specific
        return False


def get_sc2_pid() -> int | None:
    if Utils.is_windows:
        return windows_get_sc2_pid()
    return linux_get_sc2_pid()


def linux_get_sc2_pid() -> int | None:
    result_bytes = subprocess.run(["ps", "-ef"], stdout=subprocess.PIPE).stdout
    lines = result_bytes.decode("utf-8").split("\n")
    for line in lines:
        if "SC2_x64.exe" not in line:
            continue
        parts = [p for p in line.split() if p]
        # Format: UID, PID, PPID, C, STIME, TTY, TIME, CMD
        if len(parts) < 2:
            continue
        pid_part = parts[1]
        if not pid_part.isnumeric():
            continue
        return int(pid_part)
    return None


def try_decode(line: bytes, encoding: str) -> str | None:
    try:
        return line.decode(encoding)
    except UnicodeDecodeError:
        return None


def windows_get_sc2_pid() -> int | None:
    result_bytes = subprocess.check_output(["tasklist"])
    lines = result_bytes.split(b"\r\n")
    for line_bytes in lines:
        if b"SC2_x64.exe" not in line_bytes:
            continue
        line = try_decode(line_bytes, "utf-8")
        if line is None:
            line = try_decode(line_bytes, "cp437")  # Windows why?
        if line is None:
            logger.warning(f"Unable to decode PID line {line_bytes!r}")
            continue

        parts = [p for p in line.split() if p]
        # Format: Image Name, PID, Session Name, Session#, Mem Usage
        if len(parts) < 2:
            continue
        pid_part = parts[1]
        if not pid_part.isnumeric():
            continue
        return int(pid_part)
    return None


def is_pid_running(pid: int | None) -> bool:
    if pid is None:
        return False
    if Utils.is_windows:
        return windows_is_pid_running(pid)
    return linux_is_pid_running(pid)


def windows_is_pid_running(pid: int) -> bool:
    result_bytes = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}"])
    return b"SC2_x64.exe" in result_bytes


def linux_is_pid_running(pid: int) -> bool:
    # Note(mm): ps -q has nonzero returncode if there are no matches
    proc = subprocess.run(["ps", "-q", str(pid), "-f"], stdout=subprocess.PIPE)
    result_bytes = proc.stdout
    return b"SC2_x64.exe" in result_bytes


def kill_pid(pid: int | None) -> None:
    if pid is None:
        return
    if Utils.is_windows:
        windows_kill_pid(pid)
        return
    linux_kill_pid(pid)


def windows_kill_pid(pid: int) -> None:
    result = subprocess.run(["taskkill", "/PID", str(pid), "/F"])
    if result.returncode != 0:
        logger.warning(f"Could not close sc2 process (PID {pid}). Reason: {result.stdout.decode('utf-8')}")


def linux_kill_pid(pid: int) -> None:
    import signal
    os.kill(pid, signal.SIGKILL)


# ################################################################################################ #
#     Compatibility
# ################################################################################################ #

class CompatItemHolder(NamedTuple):
    name: str
    quantity: int = 1


# These items must be given to the player if the game is generated on older versions
API2_TO_API3_COMPAT_ITEMS: set[CompatItemHolder] = {
    CompatItemHolder(item_names.PHOTON_CANNON),
    CompatItemHolder(item_names.OBSERVER),
    CompatItemHolder(item_names.WARP_HARMONIZATION),
    CompatItemHolder(item_names.PROGRESSIVE_PROTOSS_WEAPON_ARMOR_UPGRADE, 3)
}
API3_TO_API4_COMPAT_ITEMS: set[CompatItemHolder] = {
    # War Council
    CompatItemHolder(item_names.ZEALOT_WHIRLWIND),
    CompatItemHolder(item_names.CENTURION_RESOURCE_EFFICIENCY),
    CompatItemHolder(item_names.SENTINEL_RESOURCE_EFFICIENCY),
    CompatItemHolder(item_names.STALKER_PHASE_REACTOR),
    CompatItemHolder(item_names.DRAGOON_PHALANX_SUIT),
    CompatItemHolder(item_names.INSTIGATOR_MODERNIZED_SERVOS),
    CompatItemHolder(item_names.ADEPT_DISRUPTIVE_TRANSFER),
    CompatItemHolder(item_names.SLAYER_PHASE_BLINK),
    CompatItemHolder(item_names.AVENGER_KRYHAS_CLOAK),
    CompatItemHolder(item_names.DARK_TEMPLAR_LESSER_SHADOW_FURY),
    CompatItemHolder(item_names.DARK_TEMPLAR_GREATER_SHADOW_FURY),
    CompatItemHolder(item_names.BLOOD_HUNTER_BRUTAL_EFFICIENCY),
    CompatItemHolder(item_names.SENTRY_DOUBLE_SHIELD_RECHARGE),
    CompatItemHolder(item_names.ENERGIZER_MOBILE_CHRONO_BEAM),
    CompatItemHolder(item_names.HAVOC_ENDURING_SIGHT),
    CompatItemHolder(item_names.HIGH_TEMPLAR_PLASMA_SURGE),
    CompatItemHolder(item_names.SIGNIFIER_FEEDBACK),
    CompatItemHolder(item_names.ASCENDANT_BREATH_OF_CREATION),
    CompatItemHolder(item_names.DARK_ARCHON_INDOMITABLE_WILL),
    CompatItemHolder(item_names.IMMORTAL_IMPROVED_BARRIER),
    CompatItemHolder(item_names.VANGUARD_RAPIDFIRE_CANNON),
    CompatItemHolder(item_names.VANGUARD_FUSION_MORTARS),
    CompatItemHolder(item_names.ANNIHILATOR_TWILIGHT_CHASSIS),
    CompatItemHolder(item_names.COLOSSUS_FIRE_LANCE),
    CompatItemHolder(item_names.WRATHWALKER_AERIAL_TRACKING),
    CompatItemHolder(item_names.REAVER_KHALAI_REPLICATORS),
    CompatItemHolder(item_names.PHOENIX_DOUBLE_GRAVITON_BEAM),
    CompatItemHolder(item_names.CORSAIR_NETWORK_DISRUPTION),
    CompatItemHolder(item_names.MIRAGE_GRAVITON_BEAM),
    CompatItemHolder(item_names.VOID_RAY_PRISMATIC_RANGE),
    CompatItemHolder(item_names.CARRIER_REPAIR_DRONES),
    CompatItemHolder(item_names.TEMPEST_DISINTEGRATION),
    CompatItemHolder(item_names.ARBITER_VESSEL_OF_THE_CONCLAVE),
    CompatItemHolder(item_names.MOTHERSHIP_TALDARIM_INTEGRATED_POWER),
    # Other items
    CompatItemHolder(item_names.ASCENDANT_ARCHON_MERGE),
    CompatItemHolder(item_names.DARK_TEMPLAR_ARCHON_MERGE),
    CompatItemHolder(item_names.SPORE_CRAWLER_BIO_BONUS),
}


def compat_item_to_network_items(compat_item: CompatItemHolder) -> list[NetworkItem]:
    item_id = item_tables.item_table[compat_item.name].code
    network_item = NetworkItem(item_id, 0, 0, 0)
    return compat_item.quantity * [network_item]

compat_stimpack_to_medpack: dict[str, str] = {
    item_names.MARINE_STIMPACK: item_names.MARINE_MEDPACK,
    item_names.MARAUDER_STIMPACK: item_names.MARAUDER_MEDPACK,
    item_names.FIREBAT_STIMPACK: item_names.FIREBAT_MEDPACK,
    item_names.REAPER_STIMPACK: item_names.REAPER_MEDPACK,
    item_names.HELLION_STIMPACK: item_names.HELLION_MEDPACK,
}


# ################################################################################################ #
#     Calculation helpers
# ################################################################################################ #


def calculate_items(ctx: 'SC2Context', mission_id: int) -> dict[SC2Race, list[int]]:
    items = ctx.items_received.copy()
    item_list = item_tables.item_table
    def create_network_item(item_name: str) -> NetworkItem:
        return NetworkItem(item_list[item_name].code, 0, 0, 0)

    # Items unlocked in earlier generator versions by default (Prophecy defaults, war council, rebalances)
    if ctx.slot_data_version < 3:
        for compat_item in API2_TO_API3_COMPAT_ITEMS:
            items.extend(compat_item_to_network_items(compat_item))
    if ctx.slot_data_version < 4:
        for compat_item in API3_TO_API4_COMPAT_ITEMS:
            items.extend(compat_item_to_network_items(compat_item))
        received_item_ids = set(item.item for item in ctx.items_received)
        if item_list[item_names.GHOST_RESOURCE_EFFICIENCY].code in received_item_ids:
            items.append(create_network_item(item_names.GHOST_BARGAIN_BIN_PRICES))
        if item_list[item_names.SPECTRE_RESOURCE_EFFICIENCY].code in received_item_ids:
            items.append(create_network_item(item_names.SPECTRE_BARGAIN_BIN_PRICES))
        if item_list[item_names.ROGUE_FORCES].code in received_item_ids:
            items.append(create_network_item(item_names.UNRESTRICTED_MUTATION))
        if item_list[item_names.SCOUT_RESOURCE_EFFICIENCY].code in received_item_ids:
            items.append(create_network_item(item_names.SCOUT_SUPPLY_EFFICIENCY))
        if item_list[item_names.REAVER_RESOURCE_EFFICIENCY].code in received_item_ids:
            items.append(create_network_item(item_names.REAVER_BARGAIN_BIN_PRICES))

    # API < 4 Orbital Command Count (Deprecated item)
    orbital_command_count: int = 0
    # API < 5 Stimpack Count (split into non-progressive)
    stimpack_count: dict[str, int] = {}

    # Keep track of items that impact automated grant story tech
    nova_weapon_count = 0

    network_item: NetworkItem
    accumulators: dict[SC2Race, list[int]] = {
        race: [0 for element in item_type_enum_class if element.flag_word >= 0]
        for race, item_type_enum_class in item.race_to_item_type.items()
    }

    # Protoss Shield grouped item specific logic
    shields_from_ground_upgrade: int = 0
    shields_from_air_upgrade: int = 0

    for network_item in items:
        name = item_tables.lookup_id_to_name.get(network_item.item)
        if name is None:
            continue
        item_data: item.ItemData = item_list[name]

        if item_data.type.flag_word < 0:
            continue

        if ctx.slot_data_version < 5:
            if name in item_groups.item_name_groups[item_groups.ItemGroupNames.TERRAN_STIMPACKS]:
                stimpack_count[name] = stimpack_count.get(name, 0) + 1
            elif name in item_groups.nova_weapons:
                nova_weapon_count += 1

        # exists exactly once
        if item_data.quantity == 1 or name in item_groups.item_name_groups[item_groups.ItemGroupNames.UNRELEASED_ITEMS]:
            accumulators[item_data.race][item_data.type.flag_word] |= 1 << item_data.number

        # exists multiple times
        elif item_data.quantity > 1:
            flaggroup = item_data.type.flag_word

            # Generic upgrades apply only to Weapon / Armor upgrades
            if item_data.number >= 0:
                accumulators[item_data.race][flaggroup] += 1 << item_data.number
            else:
                if name == item_names.PROGRESSIVE_PROTOSS_GROUND_UPGRADE:
                    shields_from_ground_upgrade += 1
                if name == item_names.PROGRESSIVE_PROTOSS_AIR_UPGRADE:
                    shields_from_air_upgrade += 1
                for bundled_number in get_bundle_upgrade_member_numbers(name):
                    accumulators[item_data.race][flaggroup] += 1 << bundled_number

            # Regen bio-steel nerf with API3 - undo for older games
            if ctx.slot_data_version < 3 and name == item_names.PROGRESSIVE_REGENERATIVE_BIO_STEEL:
                current_level = (accumulators[item_data.race][flaggroup] >> item_data.number) % 4
                if current_level == 2:
                    # Switch from level 2 to level 3 for compatibility
                    accumulators[item_data.race][flaggroup] += 1 << item_data.number
        # sum
        # Fillers, deprecated items
        else:
            if name == item_names.PROGRESSIVE_ORBITAL_COMMAND:
                orbital_command_count += 1
            elif item_data.type == ZergItemType.Level:
                accumulators[item_data.race][item_data.type.flag_word] += item_data.number
            elif name == item_names.STARTING_MINERALS:
                accumulators[item_data.race][item_data.type.flag_word] += ctx.minerals_per_item
            elif name == item_names.STARTING_VESPENE:
                accumulators[item_data.race][item_data.type.flag_word] += ctx.vespene_per_item
            elif name == item_names.STARTING_SUPPLY:
                accumulators[item_data.race][item_data.type.flag_word] += ctx.starting_supply_per_item
            elif name == item_names.UPGRADE_RESEARCH_COST:
                accumulators[item_data.race][item_data.type.flag_word] += ctx.research_cost_reduction_per_item
            else:
                accumulators[item_data.race][item_data.type.flag_word] += 1

    if mission_id in ctx.grant_hero_items:
        if nova_weapon_count == 0:
            # todo(mm): Replace this with some other in-game buff when the mod can be updated
            # Grant rifle
            item_data = item_tables.item_table[item_names.NOVA_C20A_CANISTER_RIFLE]
            accumulators[item_data.race][item_data.type.flag_word] |= 1 << item_data.number

    # Fix Shields from generic upgrades by unit class (Maximum of ground/air upgrades)
    if shields_from_ground_upgrade > 0 or shields_from_air_upgrade > 0:
        shield_upgrade_level = max(shields_from_ground_upgrade, shields_from_air_upgrade)
        shield_upgrade_item = item_list[item_names.PROGRESSIVE_PROTOSS_SHIELDS]
        for _ in range(0, shield_upgrade_level):
            accumulators[shield_upgrade_item.race][shield_upgrade_item.type.flag_word] += 1 << shield_upgrade_item.number

    # Deprecated Orbital Command handling (Backwards compatibility):
    if orbital_command_count > 0:
        orbital_command_replacement_items: list[str] = [
            item_names.COMMAND_CENTER_SCANNER_SWEEP,
            item_names.COMMAND_CENTER_MULE,
            item_names.COMMAND_CENTER_EXTRA_SUPPLIES,
            item_names.PLANETARY_FORTRESS_ORBITAL_MODULE
        ]
        replacement_item_ids = [item_tables.item_table[item_name].code for item_name in orbital_command_replacement_items]
        if sum(item_id in replacement_item_ids for item_id in items) > 0:
            logger.warning(inspect.cleandoc("""
                Both old Orbital Command and its replacements are present in the world. Skipping compatibility handling.
            """))
        else:
            # None of replacement items are present
            # L1: MULE and Scanner Sweep
            scanner_sweep_data = item_tables.item_table[item_names.COMMAND_CENTER_SCANNER_SWEEP]
            mule_data = item_tables.item_table[item_names.COMMAND_CENTER_MULE]
            accumulators[scanner_sweep_data.race][scanner_sweep_data.type.flag_word] += 1 << scanner_sweep_data.number
            accumulators[mule_data.race][mule_data.type.flag_word] += 1 << mule_data.number
            if orbital_command_count >= 2:
                # L2 MULE and Scanner Sweep usable even in Planetary Fortress Mode
                planetary_orbital_module_data = item_tables.item_table[item_names.PLANETARY_FORTRESS_ORBITAL_MODULE]
                accumulators[planetary_orbital_module_data.race][planetary_orbital_module_data.type.flag_word] += \
                    1 << planetary_orbital_module_data.number

    # Progressive Stimpack handling (Backwards compatibility):
    if ctx.slot_data_version < 5:
        for name, count in stimpack_count.items():
            if count > 1:
                # stimpack level 2, grant medpack to upgrade to super stim
                medpack_item_data: item.ItemData = item_list[compat_stimpack_to_medpack[name]]
                accumulators[medpack_item_data.race][medpack_item_data.type.flag_word] |= (
                    1 << medpack_item_data.number
                )


    # Upgrades from completed missions
    if ctx.generic_upgrade_missions > 0:
        total_missions = sum(len(column) for campaign in ctx.custom_mission_order for layout in campaign.layouts for column in layout.missions)
        num_missions = int((ctx.generic_upgrade_missions / 100) * total_missions)
        completed = len([mission_id for mission_id in ctx.mission_id_to_location_ids if ctx.is_mission_completed(mission_id)])
        upgrade_count = min(completed // num_missions, ctx.max_upgrade_level) if num_missions > 0 else ctx.max_upgrade_level
        upgrade_count = min(upgrade_count, item_tables.WEAPON_ARMOR_UPGRADE_MAX_LEVEL)

        # Equivalent to "Progressive Weapon/Armor Upgrade" item
        global_upgrades: set[str] = options.upgrade_included_names[options.GenericUpgradeItems.option_bundle_all]
        for global_upgrade in global_upgrades:
            race = item_tables.item_table[global_upgrade].race
            upgrade_flaggroup = item.race_to_item_type[race]["Upgrade"].flag_word
            for bundled_number in get_bundle_upgrade_member_numbers(global_upgrade):
                accumulators[race][upgrade_flaggroup] += upgrade_count << bundled_number

    return accumulators


def get_bundle_upgrade_member_numbers(bundled_item: str) -> list[int]:
    upgrade_elements: list[str] = item_tables.upgrade_bundles[bundled_item]
    if bundled_item in (item_names.PROGRESSIVE_PROTOSS_GROUND_UPGRADE, item_names.PROGRESSIVE_PROTOSS_AIR_UPGRADE):
        # Shields are handled as a maximum of those two
        upgrade_elements = [item_name for item_name in upgrade_elements if item_name != item_names.PROGRESSIVE_PROTOSS_SHIELDS]
    return [item_tables.item_table[item_name].number for item_name in upgrade_elements]


def calc_difficulty(difficulty: int) -> Literal['C', 'N', 'H', 'B', 'X']:
    if difficulty == 0:
        return 'C'
    elif difficulty == 1:
        return 'N'
    elif difficulty == 2:
        return 'H'
    elif difficulty == 3:
        return 'B'

    return 'X'


def get_kerrigan_level(
    ctx: 'SC2Context', items: dict[SC2Race, list[int]], missions_beaten: int, mission_id: int
) -> int:
    item_value = items[SC2Race.ZERG][ZergItemType.Level.flag_word]
    mission_value = missions_beaten * ctx.kerrigan_levels_per_mission_completed
    if ctx.kerrigan_levels_per_mission_completed_cap != -1:
        mission_value = min(mission_value, ctx.kerrigan_levels_per_mission_completed_cap)
    total_value = item_value + mission_value
    if ctx.kerrigan_total_level_cap != -1:
        total_value = min(total_value, ctx.kerrigan_total_level_cap)
    if mission_id in ctx.grant_hero_items:
        KERRIGAN_DEFAULT_LEVELS_GRANTED = 3
        required_levels = rules.get_required_kerrigan_levels([lookup_id_to_mission[mission_id]])
        required_levels = required_levels or KERRIGAN_DEFAULT_LEVELS_GRANTED
        if total_value < required_levels:
            total_value = required_levels
    return total_value


def calculate_kerrigan_options(ctx: 'SC2Context') -> int:
    result = 0

    # # Bits 0, 1
    # # Kerrigan unit available
    # if ctx.kerrigan_presence in options.kerrigan_unit_available:
    #     result |= 1 << 0

    # Bit 2
    # Kerrigan primal status by map
    if ctx.kerrigan_primal_status == options.KerriganPrimalStatus.option_vanilla:
        result |= 1 << 2

    return result


def calculate_story_tech(ctx: 'SC2Context', mission: SC2Mission) -> int:
    if (
        (MissionFlag.Nova|MissionFlag.Kerrigan) & mission.flags
        and MissionFlag.NoBuild in mission.flags
        and mission.id in ctx.grant_hero_items
    ):
        result = options.GrantStoryTech.option_grant
    else:
        result = ctx.grant_story_tech
    return result


def calculate_soa_options(ctx: 'SC2Context', mission: SC2Mission) -> int:
    """
    Pack SOA options into a single integer with bitflags.
    0b000011 = SOA presence
    0b000100 = SOA in no-builds
    0b011000 = Passives presence
    0b100000 = PAssives in no-builds
    """
    result = 0

    # Bits 0, 1
    # SoA Calldowns available
    soa_presence_value = 0
    if options.is_mission_in_soa_presence(ctx.spear_of_adun_presence, mission):
        soa_presence_value = 3
    result |= soa_presence_value << 0

    # Bit 2
    # SoA Calldowns for no-builds
    if ctx.spear_of_adun_present_in_no_build == options.SpearOfAdunPresentInNoBuild.option_true:
        result |= 1 << 2

    # Bits 3,4
    # Autocasts
    soa_autocasts_presence_value = 0
    if options.is_mission_in_soa_presence(
        ctx.spear_of_adun_passive_ability_presence, mission, options.SpearOfAdunPassiveAbilityPresence
    ):
        soa_autocasts_presence_value = 3
    # Guardian Shell breaks without SoA on version 4+, but can be generated without SoA on version 3
    if ctx.slot_data_version < 4 and MissionFlag.Protoss in mission.flags:
        soa_autocasts_presence_value = 3
    result |= soa_autocasts_presence_value << 3

    # Bit 5
    # Autocasts in no-builds
    if (ctx.spear_of_adun_passive_present_in_no_build
        == options.SpearOfAdunPassivesPresentInNoBuild.option_true
    ):
        result |= 1 << 5

    return result


def calculate_generic_upgrade_options(ctx: 'SC2Context') -> int:
    result = 0

    # Bits 0,1
    # Research mode
    research_mode_value = 0
    if ctx.generic_upgrade_research == options.GenericUpgradeResearch.option_vanilla:
        research_mode_value = 0
    elif ctx.generic_upgrade_research == options.GenericUpgradeResearch.option_auto_in_no_build:
        research_mode_value = 1
    elif ctx.generic_upgrade_research == options.GenericUpgradeResearch.option_auto_in_build:
        research_mode_value = 2
    elif ctx.generic_upgrade_research == options.GenericUpgradeResearch.option_always_auto:
        research_mode_value = 3
    result |= research_mode_value << 0

    # Bit 2
    # Speedup
    if ctx.generic_upgrade_research_speedup == options.GenericUpgradeResearchSpeedup.option_true:
        result |= 1 << 2

    return result


def calculate_trade_options(ctx: 'SC2Context') -> int:
    result = 0

    # Bit 0
    # Trade enabled
    if ctx.trade_enabled:
        result |= 1 << 0

    # Bit 1
    # Workers allowed
    if ctx.trade_workers_allowed == options.VoidTradeWorkers.option_true:
        result |= 1 << 1

    return result


def is_kerrigan_primal(ctx: 'SC2Context', kerrigan_level: int) -> bool:
    if ctx.kerrigan_primal_status == options.KerriganPrimalStatus.option_always_zerg:
        return True
    elif ctx.kerrigan_primal_status == options.KerriganPrimalStatus.option_always_human:
        return False
    elif ctx.kerrigan_primal_status == options.KerriganPrimalStatus.option_level_35:
        return kerrigan_level >= 35
    elif ctx.kerrigan_primal_status == options.KerriganPrimalStatus.option_half_completion:
        total_missions = len(ctx.mission_id_to_location_ids)
        completed = sum(ctx.is_mission_completed(mission_id)
                         for mission_id in ctx.mission_id_to_location_ids)
        return completed >= (total_missions / 2)
    elif ctx.kerrigan_primal_status == options.KerriganPrimalStatus.option_item:
        codes = [item.item for item in ctx.items_received]
        return item_tables.item_table[item_names.KERRIGAN_PRIMAL_FORM].code in codes
    return False


def get_mission_variant(mission_id: int) -> int:
    mission_flags = lookup_id_to_mission[mission_id].flags
    if MissionFlag.RaceSwap not in mission_flags:
        return 0
    if MissionFlag.Terran in mission_flags:
        return 1
    elif MissionFlag.Zerg in mission_flags:
        return 2
    elif MissionFlag.Protoss in mission_flags:
        return 3
    return 0


def get_item_flag_word(item_name: str) -> int:
    return item_tables.item_table[item_name].type.flag_word
