from glob import glob
from pathlib import Path
import logging
import os
import queue
import re
from urllib.parse import quote, unquote
from . import user_paths
from .failable import Error

# Banks are XML files used to communicate with Starcraft 2
# file names, section names and key names have to match the SC2 trigger implementation
#
# Client -> SC2
# Core Options
BANK_CORE_OPTIONS_FILE_NAME = "ArchipelagoCoreOptions" # .SC2Bank
BANK_CORE_OPTIONS_SECTION_CORE_OPTIONS = "CoreOptions"
BANK_CORE_OPTIONS_KEY_STARTING_RESOURCES = "StartingResources"
BANK_CORE_OPTIONS_KEY_FACTION_COLORS = "FactionColors"
BANK_CORE_OPTIONS_KEY_UNCOLLECTED_LOCATIONS = "UncollectedLocations"
BANK_CORE_OPTIONS_KEY_LOAD_FINISHED = "LoadFinished"
BANK_CORE_OPTIONS_KEY_SLOT_NAME = "SlotName"
BANK_CORE_OPTIONS_KEY_WORLD_ID = "WorldID"
BANK_CORE_OPTIONS_KEY_SAVE_WARNING = "SaveWarning"

# Options
# 2 types of options because they are handled in different mod files by SC2
BANK_OPTIONS_FILE_NAME = "ArchipelagoOptions" # .SC2Bank
BANK_OPTIONS_SECTION_OPTIONS = "GameOptions"
BANK_OPTIONS_KEY_OPTIONS = "Options"

# Items
BANK_ITEMS_FILE_NAME = "ArchipelagoItems" # .SC2Bank
BANK_ITEMS_SECTION_ITEMS = "Items"
BANK_ITEMS_KEY_TERRAN_ITEMS = "TerranItems"
BANK_ITEMS_KEY_ZERG_ITEMS = "ZergItems"
BANK_ITEMS_KEY_PROTOSS_ITEMS = "ProtossItems"
BANK_ITEMS_KEY_MISC_ITEMS = "MiscItems"
BANK_ITEMS_KEY_TRAP_ITEMS = "TrapItems"

# Messages
BANK_MESSAGES_FILE_NAME = "ArchipelagoMessages" # .SC2Bank
BANK_MESSAGES_SECTION_MESSAGES = "Messages"
BANK_MESSAGES_KEY_MESSAGE = "Message" # Appends message number 'Message1' 'Message2' ...
BANK_MESSAGES_KEY_LIMIT = 50 # Limit for messages per bank

# Void Trade Receive (messages received by SC2)
BANK_TRADE_RECEIVE_FILE_NAME = "ArchipelagoVoidTradeReceive" # .SC2Bank
BANK_TRADE_RECEIVE_SECTION_TRADE = "VoidTrade"
BANK_TRADE_RECEIVE_KEY_TRADE_RESPONSE = "TradeResponse"

# SC2 -> Client
# Locations
BANK_LOCATIONS_FILE_NAME = "ArchipelagoLocations" # .SC2Bank
BANK_LOCATIONS_SECTION_LOCATIONS = "Locations"
BANK_LOCATIONS_KEY_GAME_STATE = "GameState"
BANK_LOCATIONS_KEY_MISSION_MAP = "MissionMap"
BANK_LOCATIONS_KEY_MISSION_RACE = "MissionRace"
BANK_LOCATIONS_KEY_SLOT_NAME = "SlotName"
BANK_LOCATIONS_KEY_WORLD_ID = "WorldID"
BANK_LOCATIONS_KEY_SAVE_LOADED = "SaveLoaded"
BANK_LOCATIONS_KEY_CHECKS_OVERRIDE = "ChecksOverride"

# Update
# Doesn't need sections or keys. The existence of the file is used as an update prompt for now
BANK_UPDATE_FILE_NAME = "ArchipelagoUpdate" #.SC2Bank

# Void Trade Send (messages sent by SC2)
BANK_TRADE_SEND_FILE_NAME = "ArchipelagoVoidTradeSend"
BANK_TRADE_SEND_SECTION_UNITS = "VoidTradeUnits"
BANK_TRADE_SEND_KEY_UNIT_TYPES = "UnitTypes"
BANK_TRADE_SEND_SECTION_RECEIVE_REQUEST = "VoidTradeReceiveRequest"
BANK_TRADE_SEND_KEY_RECEIVE_COUNT = "Count"

# Limit for how many backup banks are saved per bank file
BANK_BACKUP_FILE_LIMIT = 100

logger = logging.getLogger("Starcraft2")


def encode_bank_identity(value: str) -> str:
    """Encode arbitrary AP names as XML-safe ASCII for round-tripping through Galaxy banks."""
    return quote(value, safe="")


def decode_bank_identity(value: str) -> str:
    return unquote(value)


class SC2Bank:
    # Has the same structure as bank files provided by SC2
    def __init__(self, name: str) -> None:
        self.file_name: str = name
        self.sections: dict[str, dict[str, str]] = {}

    def __str__(self) -> str:
        result: list[str] = []
        result.append(f'{self.file_name}.SC2Bank:')
        for name, section in self.sections.items():
            result.append(f'Section {name}:')
            for key, value in section.items():
                result.append(f'  Key {key}:')
                result.append(f'    Value: {value}')
        return ('\n'.join(result))

    def add_section(self, section: str) -> None:
        self.sections[section] = {}

    def add_entry(self, section: str, key: str, value: str) -> None:
        if section not in self.sections:
            self.add_section(section)
        self.sections[section][key] = value

    def get_value(self, section: str, key: str) -> str:
        result = ""
        if section in self.sections:
            if key in self.sections[section]:
                result = self.sections[section][key]
        return result

    def read_file(self, path: str = "") -> None | Error[str]:
        """
        Reads a bank file provided by SC2 and converts it into an SC2Bank object.
        Assumes bank files follow the structure provided by the game.
        Asserts catch malformed files, which should never happen unless the player manually edits the files.
        """
        if not path:
            bank_folder = user_paths.get_bank_folder()
            if isinstance(bank_folder, Error):
                return bank_folder
            path = f"{bank_folder}/{self.file_name}.SC2Bank"
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            SECTION_PATTERN = re.compile(r'<Section name="(\w+)">')
            KEY_PATTERN = re.compile(r'<Key name="(\w+)">')
            VALUE_PATTERN = re.compile(r'<Value string="([^"]+)"/>')
            END_KEY_PATTERN = '</Key>'
            END_SECTION_PATTERN = '</Section>'
            section = '' # Use the presence of a section/key as the state variable
            key = ''     # empty string is not present
            lines = f.readlines()
            for line in lines:
                line_content = line.strip()
                if (m := SECTION_PATTERN.match(line_content)):
                    assert not section, f"Encountered section {m.group(1)} while already inside section {section}"
                    section = m.group(1)
                    assert section not in self.sections, f"Duplicate section definition for section {section}"
                    self.add_section(section)
                elif (m := KEY_PATTERN.match(line_content)):
                    assert section, "Encountered a key while not in a section"
                    assert not key, f"Encountered key {m.group(1)} while already inside key {key}"
                    key = m.group(1)
                    assert key not in self.sections[section], f"Duplicate key definition for key {key}"
                elif (m := VALUE_PATTERN.match(line_content)):
                    assert section, "Encountered a value while not in a section"
                    assert key, "Encountered a value while not in a key"
                    value = m.group(1)
                    self.add_entry(section, key, value)
                elif line_content == END_KEY_PATTERN:
                    assert key, "Closing a key while not already in a key"
                    key = ''
                elif line_content == END_SECTION_PATTERN:
                    assert section, "Closing a section while not already in a section"
                    section = ''
                else:
                    pass
        return None

    def write_file(self) -> None | Error[str]:
        # Write a bank file with the formatting expected from SC2
        # SC2 reads data by restoring a bank from a backup
        # so we write the new backup file here
        bank_folder = user_paths.get_bank_folder()
        if isinstance(bank_folder, Error):
            return bank_folder
        dir = f"{bank_folder}/{user_paths.BACKUP_DIRNAME}"
        lines: list[str] = []
        lines.append(         f'<?xml version="1.0" encoding="utf-8"?>')
        lines.append(         f'<Bank version="1">')
        for name, section in self.sections.items():
            lines.append(     f'    <Section name="{name}">')
            for key, value in section.items():
                lines.append( f'        <Key name="{key}">')
                lines.append( f'            <Value string="{value}"/>')
                lines.append( f'        </Key>')
            lines.append(     f'    </Section>')
        lines.append(         f'</Bank>')
        Path(dir).mkdir(parents=True, exist_ok=True)
        # The game deletes a backup after reading. If a backup exists already, the game didn't read it yet
        # In that case, just make a second backup, the game will read them in sequence
        for i in range (1, BANK_BACKUP_FILE_LIMIT + 1):
            # start at 1, makes handling in SC2 easier
            path = f"{dir}/{self.file_name}_backup_{i}.SC2Bank"
            if not os.path.isfile(path):
                with open(path, "w", encoding="utf-8") as f:
                    f.write('\n'.join(lines))
                return None
        # only the messages bank has any chance to hit this
        # at current limits, this would be attempting to send 5000 messages in a single iteration
        return Error(f"Too many bank backups, cannot write {self.file_name}; will retry.")

    def remove_entry_from_file(self, key: str) -> None | Error[str]:
        """Remove one Key/Value pair from a bank file"""

        bank_folder = user_paths.get_bank_folder()
        if isinstance(bank_folder, Error):
            return bank_folder
        path = f"{bank_folder}/{self.file_name}.SC2Bank"
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        with open(path, "w", encoding="utf-8") as f:
            deleting = False
            for line in lines:
                line_content = line.strip()
                # Just find the key tag
                if line_content == f'<Key name="{key}">':
                    deleting = True
                # and delete all lines until finding the closing tag
                elif line_content == '</Key>':
                    deleting = False
                elif not deleting:
                    f.write(line)
        return None


def file_cleanup() -> None | Error[str]:
    # Use at the start of a mission to delete old bank files
    # Locations needs cleanup, others are optional
    bank_folder = user_paths.get_bank_folder()
    if isinstance(bank_folder, Error):
        return bank_folder
    # clean up game -> client banks to prevent sending unintended locations
    Path(f"{bank_folder}/{BANK_CORE_OPTIONS_FILE_NAME}.SC2Bank").unlink(missing_ok=True)
    Path(f"{bank_folder}/{BANK_LOCATIONS_FILE_NAME}.SC2Bank").unlink(missing_ok=True)
    Path(f"{bank_folder}/{BANK_TRADE_RECEIVE_FILE_NAME}.SC2Bank").unlink(missing_ok=True)
    Path(f"{bank_folder}/{BANK_MESSAGES_FILE_NAME}.SC2Bank").unlink(missing_ok=True)
    bank_backup_folder = f"{bank_folder}/{user_paths.BACKUP_DIRNAME}"
    for i in range (1, BANK_BACKUP_FILE_LIMIT + 1):
        # clean up client -> game banks to prevent sending the wrong info to the game
        # we need to clean up all backups that could exist here, but leave backups of other SC2maps untouched
        path = f"{bank_backup_folder}/{BANK_CORE_OPTIONS_FILE_NAME}_backup_{i}.SC2Bank"
        Path(path).unlink(missing_ok=True)
        path = f"{bank_backup_folder}/{BANK_OPTIONS_FILE_NAME}_backup_{i}.SC2Bank"
        Path(path).unlink(missing_ok=True)
        path = f"{bank_backup_folder}/{BANK_ITEMS_FILE_NAME}_backup_{i}.SC2Bank"
        Path(path).unlink(missing_ok=True)
        # Keep stored AP messages
        # path = f"{bank_backup_folder}/{BANK_MESSAGES_FILE_NAME}_backup_{i}.SC2Bank"
        # Path(path).unlink(missing_ok=True)
    return None


def send_options(msg: str) -> None | Error[str]:
    bank = SC2Bank(BANK_OPTIONS_FILE_NAME)
    bank.add_entry(
        BANK_OPTIONS_SECTION_OPTIONS,
        BANK_OPTIONS_KEY_OPTIONS,
        msg
    )
    return bank.write_file()


def send_core_options(
    start_resources: str,
    colors: str,
    uncollected_objectives: str | None = None,
    finished_loading: str | None = None,
    slot_name: str | None = None,
    world_id: str | None = None,
    save_warning: str | None = None,
) -> None | Error[str]:
    bank = SC2Bank(BANK_CORE_OPTIONS_FILE_NAME)
    bank.add_entry(
        BANK_CORE_OPTIONS_SECTION_CORE_OPTIONS,
        BANK_CORE_OPTIONS_KEY_STARTING_RESOURCES,
        start_resources
    )
    bank.add_entry(
        BANK_CORE_OPTIONS_SECTION_CORE_OPTIONS,
        BANK_CORE_OPTIONS_KEY_FACTION_COLORS,
        colors
    )
    if uncollected_objectives:
        bank.add_entry(
            BANK_CORE_OPTIONS_SECTION_CORE_OPTIONS,
            BANK_CORE_OPTIONS_KEY_UNCOLLECTED_LOCATIONS,
            uncollected_objectives
        )
    if finished_loading:
        bank.add_entry(
            BANK_CORE_OPTIONS_SECTION_CORE_OPTIONS,
            BANK_CORE_OPTIONS_KEY_LOAD_FINISHED,
            finished_loading
        )
    if slot_name:
        bank.add_entry(
            BANK_CORE_OPTIONS_SECTION_CORE_OPTIONS,
            BANK_CORE_OPTIONS_KEY_SLOT_NAME,
            encode_bank_identity(slot_name),
        )
    if world_id:
        bank.add_entry(
            BANK_CORE_OPTIONS_SECTION_CORE_OPTIONS,
            BANK_CORE_OPTIONS_KEY_WORLD_ID,
            encode_bank_identity(world_id),
        )
    if save_warning:
        bank.add_entry(
            BANK_CORE_OPTIONS_SECTION_CORE_OPTIONS,
            BANK_CORE_OPTIONS_KEY_SAVE_WARNING,
            save_warning,
        )
    return bank.write_file()


def send_items(
    terran_items: str,
    zerg_items: str,
    protoss_items: str,
    misc_items: str,
    trap_items: str,
    ) -> None | Error[str]:
    bank = SC2Bank(BANK_ITEMS_FILE_NAME)
    bank.add_entry(
        BANK_ITEMS_SECTION_ITEMS,
        BANK_ITEMS_KEY_TERRAN_ITEMS,
        terran_items
    )
    bank.add_entry(
        BANK_ITEMS_SECTION_ITEMS,
        BANK_ITEMS_KEY_ZERG_ITEMS,
        zerg_items
    )
    bank.add_entry(
        BANK_ITEMS_SECTION_ITEMS,
        BANK_ITEMS_KEY_PROTOSS_ITEMS,
        protoss_items
    )
    bank.add_entry(
        BANK_ITEMS_SECTION_ITEMS,
        BANK_ITEMS_KEY_MISC_ITEMS,
        misc_items
    )
    bank.add_entry(
        BANK_ITEMS_SECTION_ITEMS,
        BANK_ITEMS_KEY_TRAP_ITEMS,
        trap_items
    )
    return bank.write_file()


def escape_ap_message(message: str) -> str:
    return message.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def send_ap_messages_from_queue(message_queue: queue.Queue) -> None | Error[str]:
    messages = []
    for i in range(BANK_MESSAGES_KEY_LIMIT):
        # send up to KEY_LIMIT messages in a single bank file
        if not message_queue.empty():
            messages.append(message_queue.get_nowait())
            message_queue.task_done()
        else:
            break
    if messages:
        return send_ap_message(messages)
    return None


def send_ap_message(messages: list[str]) -> None | Error[str]:
    # message list is expected to not contain more than KEY_LIMIT messages
    bank = SC2Bank(BANK_MESSAGES_FILE_NAME)
    if messages:
        i = 0
        for msg in messages:
            if msg and i < BANK_MESSAGES_KEY_LIMIT:
                i += 1
                bank.add_entry(
                    BANK_MESSAGES_SECTION_MESSAGES,
                    f"{BANK_MESSAGES_KEY_MESSAGE}{str(i)}",
                    escape_ap_message(msg)
                )
        if i > 0:
            return bank.write_file()
    return None


def update_prompt() -> bool:
    """Checks to see if the game has requested an update by writing the ArchipelagoUpdate file"""
    bank_folder = user_paths.get_bank_folder()
    if isinstance(bank_folder, Error):
        return False
    result = False
    path = f"{user_paths.get_bank_folder()}/{BANK_UPDATE_FILE_NAME}.SC2Bank"
    if os.path.isfile(path):
        # if bank exists, we want an update prompt. No need to check the values
        os.remove(path)
        result = True
    return result


def read_location_info() -> tuple[str, str, str, str, str, str, str] | Error[str]:
    bank = SC2Bank(BANK_LOCATIONS_FILE_NAME)
    if error := bank.read_file():
        return error
    return (
        bank.get_value(BANK_LOCATIONS_SECTION_LOCATIONS, BANK_LOCATIONS_KEY_GAME_STATE),
        bank.get_value(BANK_LOCATIONS_SECTION_LOCATIONS, BANK_LOCATIONS_KEY_MISSION_MAP),
        bank.get_value(BANK_LOCATIONS_SECTION_LOCATIONS, BANK_LOCATIONS_KEY_MISSION_RACE),
        bank.get_value(BANK_LOCATIONS_SECTION_LOCATIONS, BANK_LOCATIONS_KEY_SLOT_NAME),
        bank.get_value(BANK_LOCATIONS_SECTION_LOCATIONS, BANK_LOCATIONS_KEY_WORLD_ID),
        bank.get_value(BANK_LOCATIONS_SECTION_LOCATIONS, BANK_LOCATIONS_KEY_SAVE_LOADED),
        bank.get_value(BANK_LOCATIONS_SECTION_LOCATIONS, BANK_LOCATIONS_KEY_CHECKS_OVERRIDE),
    )


# Void Trade
def send_trade_received(msg: str) -> None | Error[str]:
    bank = SC2Bank(BANK_TRADE_RECEIVE_FILE_NAME)
    bank.add_entry(
        BANK_TRADE_RECEIVE_SECTION_TRADE,
        BANK_TRADE_RECEIVE_KEY_TRADE_RESPONSE,
        msg
    )
    return bank.write_file()


def read_trade_units() -> str | Error[str]:
    bank = SC2Bank(BANK_TRADE_SEND_FILE_NAME)
    if error := bank.read_file():
        return error
    result = bank.get_value(
        BANK_TRADE_SEND_SECTION_UNITS,
        BANK_TRADE_SEND_KEY_UNIT_TYPES
    )
    if result:
        error = bank.remove_entry_from_file(BANK_TRADE_SEND_KEY_UNIT_TYPES)
        if isinstance(error, Error):
            return error
    return result


def read_trade_receive_request() -> str | Error[str]:
    bank = SC2Bank(BANK_TRADE_SEND_FILE_NAME)
    if error := bank.read_file():
        return error
    result = bank.get_value(
        BANK_TRADE_SEND_SECTION_RECEIVE_REQUEST,
        BANK_TRADE_SEND_KEY_RECEIVE_COUNT
    )
    if result:
        error = bank.remove_entry_from_file(BANK_TRADE_SEND_KEY_RECEIVE_COUNT)
        if isinstance(error, Error):
            return error
    return result
