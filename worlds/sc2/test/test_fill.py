"""
Tests of the actual fill stage, not just sc2-specific functionality.
"""
import logging
import logging.handlers
import io

from Fill import FillError
from . import test_base
from .. import options, mission_tables


class TestFill(test_base.Sc2SetupTestBase):
    NUM_FILLS = 5
    BASE_OPTIONS = {
        options.OPTION_NAME[options.RequiredTactics]: options.RequiredTactics.option_basic,
        options.OPTION_NAME[options.HeroPresence]: options.HeroPresence.option_anywhere,
        options.OPTION_NAME[options.EnabledCampaigns]: options.EnabledCampaigns.valid_keys,
        options.OPTION_NAME[options.SelectedRaces]: set(),
        options.OPTION_NAME[options.ShuffleNoBuild]: False,
    }

    @classmethod
    def setUpClass(cls) -> None:
        # Set up the logger to buffer log messages
        logger = logging.getLogger()
        cls.removed_handlers = logger.handlers[:]
        for handler in cls.removed_handlers:
            logger.removeHandler(handler)
        cls.formatted_logs = io.StringIO()
        subhandler = logging.StreamHandler(cls.formatted_logs)
        cls.handler = logging.handlers.MemoryHandler(capacity=100_000, target=subhandler, flushOnClose=False)
        formatter = logging.Formatter('%(asctime)s %(levelname)s | %(message)s')
        subhandler.formatter = formatter
        logger.addHandler(cls.handler)
        cls.old_level = logger.level
        logger.setLevel(logging.DEBUG)

    @classmethod
    def tearDownClass(cls) -> None:
        logger = logging.getLogger()
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        for handler in cls.removed_handlers:
            logger.addHandler(handler)
        cls.formatted_logs.close()
        logger.setLevel(cls.old_level)

    def _get_formatted_logs(self) -> str:
        result = self.formatted_logs.getvalue()
        self.formatted_logs.truncate(0)
        self.formatted_logs.seek(0)
        return result

    @staticmethod
    def _plando_first_mission(mission: mission_tables.SC2Mission) -> dict:
        return {
            "Test Campaign": {
                "Test Layout": {
                    "type": "column",
                    "size": 5,
                    "mission_pool": f"{mission.race.get_title()} Missions",
                    "missions": [
                        {"index": 0, "mission_pool": mission.mission_name},
                    ]
                }
            }
        }

    def test_stress_fill_one_build_starter_mission_with_3_heroes(self) -> None:
        world_options = {
            **self.BASE_OPTIONS,
            options.OPTION_NAME[options.MissionOrder]: options.MissionOrder.option_gauntlet,
            options.OPTION_NAME[options.MaximumCampaignSize]: 10,
        }
        logger = logging.getLogger()
        try:
            for attempt in range(self.NUM_FILLS):
                logger.info(f"Fill attempt {attempt+1} / {self.NUM_FILLS}")
                self.generate_world(world_options)
                self.fill_after_generation()
                self.handler.buffer.clear()
        except FillError as ex:
            self.handler.flush()
            ex.add_note(self._get_formatted_logs())
            raise ex

    def test_fill_terran_outbreak_first(self) -> None:
        world_options = {
            **self.BASE_OPTIONS,
            options.OPTION_NAME[options.MissionOrder]: options.MissionOrder.option_custom,
            options.OPTION_NAME[options.CustomMissionOrder]: self._plando_first_mission(
                mission_tables.SC2Mission.OUTBREAK
            ),
        }
        try:
            self.generate_world(world_options)
            self.fill_after_generation()
            self.handler.buffer.clear()
        except FillError as ex:
            self.handler.flush()
            ex.add_note(self._get_formatted_logs())
            raise ex
        self.handler.buffer.clear()

    def test_fill_protoss_outbreak_first(self) -> None:
        world_options = {
            **self.BASE_OPTIONS,
            options.OPTION_NAME[options.MissionOrder]: options.MissionOrder.option_custom,
            options.OPTION_NAME[options.CustomMissionOrder]: self._plando_first_mission(
                mission_tables.SC2Mission.OUTBREAK_P
            ),
        }
        try:
            self.generate_world(world_options)
            self.fill_after_generation()
            self.handler.buffer.clear()
        except FillError as ex:
            self.handler.flush()
            ex.add_note(self._get_formatted_logs())
            raise ex
        self.handler.buffer.clear()

    def test_fill_zerg_outbreak_first(self) -> None:
        world_options = {
            **self.BASE_OPTIONS,
            options.OPTION_NAME[options.MissionOrder]: options.MissionOrder.option_custom,
            options.OPTION_NAME[options.CustomMissionOrder]: self._plando_first_mission(
                mission_tables.SC2Mission.OUTBREAK_Z
            ),
        }
        try:
            self.generate_world(world_options)
            self.fill_after_generation()
            self.handler.buffer.clear()
        except FillError as ex:
            self.handler.flush()
            ex.add_note(self._get_formatted_logs())
            raise ex
        self.handler.buffer.clear()

    def _test_100_times(self, race: str, function) -> None:
        NUM_ATTEMPTS = 100
        num_failures = 0
        raised_ex = None
        for x in range(NUM_ATTEMPTS):
            print(f"Attempt: {x}")
            try:
                function()
            except Exception as ex:
                num_failures += 1
                print(f"==== Failure on attempt {x} (failure #{num_failures})")
                raised_ex = ex
        print(f"{num_failures}/{NUM_ATTEMPTS} failed for {race}")
        if raised_ex:
            raised_ex.add_note(f"{num_failures}/{NUM_ATTEMPTS} failed for {race}")
            raise raised_ex
