"""
Tests of the actual fill stage, not just sc2-specific functionality.
"""
import logging
import logging.handlers
import io

from . import test_base
from .. import options, mission_tables


class TestFill(test_base.Sc2SetupTestBase):
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
    def _plando_first_missions(*missions: mission_tables.SC2Mission) -> dict:
        missions = [
            {"index": index, "mission_pool": mission.mission_name}
            for index, mission in enumerate(missions)
        ]
        while len(missions) < 5:
            missions.append({"index": len(missions), "difficulty": "easy"})
        return {
            "Test Campaign": {
                "Test Layout": {
                    "type": "column",
                    "size": 5,
                    "max_difficulty": "medium",
                    "missions": missions,
                }
            }
        }

    def test_stress_fill_one_build_starter_mission_with_2_heroes(self) -> None:
        NUM_FILLS = 5
        world_options = {
            **self.BASE_OPTIONS,
            options.OPTION_NAME[options.SelectedRaces]: {mission_tables.SC2Race.TERRAN.get_title()},
            options.OPTION_NAME[options.MissionOrder]: options.MissionOrder.option_gauntlet,
            # Note(mm): Fill errors can still happen if hard missions appear early, but after the 3rd mission
            # Relative difficulty puts hard missions in proportion to the size of the order, so longer
            # gauntlets mean later hard missions and more stability. This is worsened by having more heroes.
            options.OPTION_NAME[options.MaximumCampaignSize]: 20,
        }
        logger = logging.getLogger()
        try:
            for attempt in range(NUM_FILLS):
                logger.info(f"Fill attempt {attempt+1} / {NUM_FILLS}")
                self.generate_world(world_options)
                self.fill_after_generation()
                self.handler.buffer.clear()
        except Exception as ex:
            self.handler.flush()
            ex.add_note(self._get_formatted_logs())
            raise ex

    def test_fill_all_races_outbreak(self) -> None:
        world_options = {
            **self.BASE_OPTIONS,
            options.OPTION_NAME[options.MissionOrder]: options.MissionOrder.option_custom,
            options.OPTION_NAME[options.CustomMissionOrder]: self._plando_first_missions(
                mission_tables.SC2Mission.OUTBREAK,
                mission_tables.SC2Mission.OUTBREAK_P,
                mission_tables.SC2Mission.OUTBREAK_Z,
                mission_tables.SC2Mission.THE_GREAT_TRAIN_ROBBERY,
                # Give an extra mission before the third Outbreak
                # The extra unit requirement puts outbreak 3rd as over the starter location cap
                # This is fair to leave unsupported on basic logic
                mission_tables.SC2Mission.THE_GREAT_TRAIN_ROBBERY_P,
            ),
        }
        try:
            self.generate_world(world_options)
            self.fill_after_generation()
            self.handler.buffer.clear()
        except Exception as ex:
            self.handler.flush()
            ex.add_note(self._get_formatted_logs())
            raise ex
        self.handler.buffer.clear()

    def test_fill_gauntlet_with_keys(self) -> None:
        world_options = {
            **self.BASE_OPTIONS,
            options.OPTION_NAME[options.MissionOrder]: options.MissionOrder.option_gauntlet,
            options.OPTION_NAME[options.SelectedRaces]: {mission_tables.SC2Race.TERRAN.get_title()},
            options.OPTION_NAME[options.EnabledCampaigns]: {mission_tables.SC2Campaign.WOL.campaign_name},
            options.OPTION_NAME[options.KeyMode]: options.KeyMode.option_missions,
            options.OPTION_NAME[options.MasteryLocations]: options.LocationInclusion.option_disabled,
            options.OPTION_NAME[options.MaximumCampaignSize]: 8,
            options.OPTION_NAME[options.ExcludedMissions]: [
                # Exclude the hard missions that might appear after depth 3 with high item requirements
                mission_tables.SC2Mission.ALL_IN.mission_name,
                mission_tables.SC2Mission.SHATTER_THE_SKY.mission_name,
                mission_tables.SC2Mission.GATES_OF_HELL.mission_name,
                mission_tables.SC2Mission.MAW_OF_THE_VOID.mission_name,
                mission_tables.SC2Mission.SUPERNOVA.mission_name,
                mission_tables.SC2Mission.ENGINE_OF_DESTRUCTION.mission_name,
                # Exclude the loot pinata to put more pressure on the starter location system
                mission_tables.SC2Mission.THE_GREAT_TRAIN_ROBBERY.mission_name,
            ]
        }
        try:
            self.generate_world(world_options)
            self.fill_after_generation()
            self.handler.buffer.clear()
        except Exception as ex:
            self.handler.flush()
            ex.add_note(self._get_formatted_logs())
            raise ex
        self.handler.buffer.clear()

    def test_fill_cmo_with_keys(self) -> None:
        world_options = {
            **self.BASE_OPTIONS,
            options.OPTION_NAME[options.SelectedRaces]: {mission_tables.SC2Race.TERRAN.get_title()},
            options.OPTION_NAME[options.EnabledHeroes]: set(),
            options.OPTION_NAME[options.MissionOrder]: options.MissionOrder.option_custom,
            options.OPTION_NAME[options.CustomMissionOrder]: {
                "Test Campaign": {
                    "Test Layout": {
                        "type": "column",
                        "size": 5,
                        "max_difficulty": "medium",
                        "missions": [
                            {"index": 0, "mission_pool": mission_tables.SC2Mission.OUTBREAK.mission_name},
                            {"index": 1, "entry_rules": [{"items": {"Key": 1}}]},
                            {"index": 2, "entry_rules": [{"items": {"Key": 1}}]},
                        ]
                    }
                }
            }
        }
        try:
            self.generate_world(world_options)
            self.fill_after_generation()
            self.handler.buffer.clear()
        except Exception as ex:
            self.handler.flush()
            ex.add_note(self._get_formatted_logs())
            raise ex
        self.handler.buffer.clear()

    def test_fill_terran_outbreak_first(self) -> None:
        world_options = {
            **self.BASE_OPTIONS,
            options.OPTION_NAME[options.SelectedRaces]: {mission_tables.SC2Race.TERRAN.get_title()},
            options.OPTION_NAME[options.MissionOrder]: options.MissionOrder.option_custom,
            options.OPTION_NAME[options.CustomMissionOrder]: self._plando_first_missions(
                mission_tables.SC2Mission.OUTBREAK
            ),
        }
        try:
            self.generate_world(world_options)
            self.fill_after_generation()
            self.handler.buffer.clear()
        except Exception as ex:
            self.handler.flush()
            ex.add_note(self._get_formatted_logs())
            raise ex
        self.handler.buffer.clear()

    def test_fill_protoss_outbreak_first(self) -> None:
        world_options = {
            **self.BASE_OPTIONS,
            options.OPTION_NAME[options.SelectedRaces]: {mission_tables.SC2Race.PROTOSS.get_title()},
            options.OPTION_NAME[options.MissionOrder]: options.MissionOrder.option_custom,
            options.OPTION_NAME[options.CustomMissionOrder]: self._plando_first_missions(
                mission_tables.SC2Mission.OUTBREAK_P
            ),
        }
        try:
            self.generate_world(world_options)
            self.fill_after_generation()
            self.handler.buffer.clear()
        except Exception as ex:
            self.handler.flush()
            ex.add_note(self._get_formatted_logs())
            raise ex
        self.handler.buffer.clear()

    def test_fill_zerg_outbreak_first(self) -> None:
        world_options = {
            **self.BASE_OPTIONS,
            options.OPTION_NAME[options.SelectedRaces]: {mission_tables.SC2Race.ZERG.get_title()},
            options.OPTION_NAME[options.MissionOrder]: options.MissionOrder.option_custom,
            options.OPTION_NAME[options.CustomMissionOrder]: self._plando_first_missions(
                mission_tables.SC2Mission.OUTBREAK_Z
            ),
        }
        try:
            self.generate_world(world_options)
            self.fill_after_generation()
            self.handler.buffer.clear()
        except Exception as ex:
            self.handler.flush()
            ex.add_note(self._get_formatted_logs())
            raise ex
        self.handler.buffer.clear()

    def test_fill_with_vanilla_and_extra_locations_excluded(self) -> None:
        world_options = {
            **self.BASE_OPTIONS,
            options.OPTION_NAME[options.SelectedRaces]: {mission_tables.SC2Race.TERRAN.get_title()},
            options.OPTION_NAME[options.ExtraLocations]: options.LocationInclusion.option_disabled,
            options.OPTION_NAME[options.VanillaLocations]: options.LocationInclusion.option_disabled,
            options.OPTION_NAME[options.VictoryCache]: 3,
            options.OPTION_NAME[options.MissionOrder]: options.MissionOrder.option_custom,
            options.OPTION_NAME[options.CustomMissionOrder]: self._plando_first_missions(
                mission_tables.SC2Mission.THE_OUTLAWS,
                mission_tables.SC2Mission.OUTBREAK,
                mission_tables.SC2Mission.THE_GREAT_TRAIN_ROBBERY,
                mission_tables.SC2Mission.HAVENS_FALL,
                mission_tables.SC2Mission.SHATTER_THE_SKY,
            ),
        }
        try:
            self.generate_world(world_options)
            self.fill_after_generation()
            self.handler.buffer.clear()
        except Exception as ex:
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
