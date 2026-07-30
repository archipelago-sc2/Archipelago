# AP SC2 Design Notes
The AP sc2 client is split into two repositories: the apworld and the mod files.
This document deals primarily with the apworld repository.

The apworld repository is further split into two main components: the generation code and the client.
These parts share two interfaces:
* Statically, they share data via sharing code for things such as items, locations, missions, and rules
* Per-world information is shared via slot data

## Generator
The generator is primarily responsible for reporting 4 kinds of data to core:
* a list of items
* a list of locations (organized into regions)
* logic rules associated with each location/region
* slot data to be passed to the client at connection time

Currently, we process these roughly in the order of:
1. locations and regions
2. rules
3. items
4. slot data

## Client
The client is responsible for launching missions, communicating with the game while it is running,
and forwarding messages between the game and Archipelago server.
