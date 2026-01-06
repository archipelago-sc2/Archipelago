class NovaPresenceOptions():
    # Currently, if Nova is disabled in all available campaigns, Nova can still appear in no-builds
    # In this case, all Nova items are removed from the pool and her no-builds effectively grant story tech
    # TODO: Add an option here for Nova presence in no-builds, allowing players to exclude Nova for build missions
    # while still requiring them to find equipment to solve the no-builds
    NCO_TERRAN = "Nova Covert Ops (Terran)"
    NCO_ZERG = "Nova Covert Ops (Zerg)"
    NCO_PROTOSS = "Nova Covert Ops (Protoss)"
    GHOST_OF_A_CHANCE = "Ghost of a Chance"
    GHOST_OF_A_CHANCE_AUTO = "Ghost of a Chance (Auto)" # Use NCO Nova only if Nova is enabled in any build missions
