from typing import Union
import settings


class Starcraft2Settings(settings.Group):
    class Sc2InstallPath(str):
        """The path to your sc2 install folder; normally in C:/Program Files (x86)/StarCraft II"""

    class Sc2DocumentsPath(str):
        """The path to your sc2 documents folder; normally ~/Documents/StarCraft II"""

    class WinePath(str):
        """Non-Windows. The path to your preferred wine executable; defaults to WINE environment variable if not set"""

    class WinePrefix(str):
        """Non-Windows. The path to your preferred wine executable; defaults to WINEPREFIX environment variable if not set"""

    class WindowWidth(int):
        """The starting width the client window in pixels"""

    class WindowHeight(int):
        """The starting height the client window in pixels"""

    class TerranButtonColor(list):
        """Defines the colour of terran mission buttons in the launcher in rgb format (3 elements ranging from 0 to 1)"""

    class ZergButtonColor(list):
        """Defines the colour of zerg mission buttons in the launcher in rgb format (3 elements ranging from 0 to 1)"""

    class ProtossButtonColor(list):
        """Defines the colour of protoss mission buttons in the launcher in rgb format (3 elements ranging from 0 to 1)"""

    class GameWindowedMode(settings.Bool):
        """Controls whether the game should start in windowed mode"""

    class GameDisableForcedCamera(settings.Bool):
        """Stops the game from ever taking control over the player's camera"""

    class GameSkipCutscenes(settings.Bool):
        """Automatically skips all cutscenes except mission end cutscenes. Stops dialogue from halting progress"""

    class GameDifficulty(str):
        """Overrides the slot's difficulty setting. Possible values: `casual`, `normal`, `hard`, `brutal`, `default`. Default uses slot value"""

    class GameSpeed(str):
        """Overrides the slot's gamespeed setting. Possible values: `slower`, `slow`, `normal`, `fast`, `faster`, `default`. Default uses slot value"""

    class ScoutingShowTraps(settings.Bool):
        """If set to true, in-client scouting will show traps as distinct from filler"""

    # Client options
    sc2_install_path: Sc2InstallPath = Sc2InstallPath("")
    sc2_documents_path: Sc2InstallPath = Sc2InstallPath("")
    wine_path: WinePath = WinePath("")
    wine_prefix: WinePrefix = WinePrefix("")
    window_width: WindowWidth = WindowWidth(1080)
    window_height: WindowHeight = WindowHeight(720)
    scouting_show_traps: ScoutingShowTraps | bool = False

    terran_button_color: TerranButtonColor = TerranButtonColor([0.0838, 0.2898, 0.2346])
    zerg_button_color: ZergButtonColor = ZergButtonColor([0.345, 0.22425, 0.12765])
    protoss_button_color: ProtossButtonColor = ProtossButtonColor([0.18975, 0.2415, 0.345])

    # Game options
    game_windowed_mode: GameWindowedMode | bool = False
    game_disable_forced_camera: GameDisableForcedCamera | bool = True
    game_skip_cutscenes: GameSkipCutscenes | bool = True

    # Options overrides
    game_difficulty: GameDifficulty = GameDifficulty("default")
    game_speed: GameSpeed = GameSpeed("default")
