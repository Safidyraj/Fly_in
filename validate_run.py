"""Run a map through the simulator and verify no capacity is exceeded."""

import sys
from collections import defaultdict

from algo import (
    Connection,
    Graph,
    PathNotFoundError,
    Pathfinder,
    Zone as AlgoZone,
)
from colorama import Fore, Style, init
from models import Zone
from parser import Parser


def main(path: str) -> None:
    """Run the map at `path` and report any capacity violation."""
    zones, nb_drones = Parser().file_parser(path)
    start_zone = next(z for z in zones.values() if z.role == "start_hub")
    end_zone = next(z for z in zones.values() if z.role == "end_hub")

    graph = Graph()
    for zone in zones.values():
        graph.add_zone(
            AlgoZone(
                zone.name,
                zone.x,
                zone.y,
                zone.zone_type.value,
                zone.max_drones,
            )
        )
    for zone in zones.values():
        for connection in zone.connections:
            graph.add_connection(
                Connection(
                    connection.zone_a.name,
                    connection.zone_b.name,
                    connection.max_link_capacity,
                )
            )

    pathfinder = Pathfinder(graph)
    agenda: dict[tuple[str, int], list[int]] = {}
    conn_agenda: dict[tuple[str, str, int], list[int]] = {}
    drones: list[tuple[int, list[tuple[Zone, int]]]] = []
    for drone_id in range(1, nb_drones + 1):
        try:
            timed_path = pathfinder.shortest_path(
                start_zone.name,
                end_zone.name,
                agenda,
                conn_agenda,
            )
        except PathNotFoundError as exc:
            print(f"UNSOLVABLE: drone {drone_id}: {exc}")
            sys.exit(1)

        route: list[tuple[Zone, int]] = [
            (zones[name], tick) for name, tick in timed_path
        ]
        for i in range(len(route)):
            current_zone, current_tick = route[i]
            zone = current_zone
            agenda.setdefault((zone.name, current_tick), []).append(drone_id)
            if i > 0:
                prev_zone, prev_tick = route[i - 1]
                if prev_zone.name != zone.name:
                    z1, z2 = sorted([prev_zone.name, zone.name])
                    for tick in range(prev_tick, current_tick):
                        conn_agenda.setdefault((z1, z2, tick), []).append(
                            drone_id
                        )
        drones.append((drone_id, route))

    zone_cap: dict[str, int | float] = {
        z.name: z.max_drones for z in zones.values()
    }
    conn_cap: dict[tuple[str, str], int] = {}
    for zone in zones.values():
        for connection in zone.connections:
            z1, z2 = sorted([connection.zone_a.name, connection.zone_b.name])
            conn_cap[(z1, z2)] = connection.max_link_capacity

    zone_usage: defaultdict[tuple[str, int], int] = defaultdict(int)
    conn_usage: defaultdict[tuple[str, str, int], int] = defaultdict(int)
    max_tick = 0
    for _, route in drones:
        for i, (zone, tick) in enumerate(route):
            current_zone = zone
            zone_usage[(current_zone.name, tick)] += 1
            max_tick = max(max_tick, tick)
            if i > 0:
                prev_zone, prev_tick = route[i - 1]
                if prev_zone.name != current_zone.name:
                    z1, z2 = sorted([prev_zone.name, current_zone.name])
                    for tick_id in range(prev_tick, tick):
                        conn_usage[(z1, z2, tick_id)] += 1

    violations: list[str] = []
    for (name, tick), used in zone_usage.items():
        capacity = zone_cap[name]
        if capacity != float("inf") and used > capacity:
            violations.append(
                f"ZONE OVERFLOW {name}@{tick}: {used}/{capacity}"
            )
    for (z1, z2, tick), used in conn_usage.items():
        capacity = conn_cap[(z1, z2)]
        if used > capacity:
            violations.append(
                f"LINK OVERFLOW {z1}-{z2}@{tick}: {used}/{capacity}"
            )

    init()
    print(
        f"{Style.BRIGHT}{Fore.GREEN}{bool(drones) and 'OK'}{Fore.RESET} "
        f"drones={Fore.CYAN}{nb_drones}{Fore.RESET} "
        f"total_turns={Fore.CYAN}{max_tick}{Fore.RESET} "
        f"violations={Fore.RED}{len(violations)}{Fore.RESET}"
    )
    for violation in violations[:20]:
        print("  " + violation)


if __name__ == "__main__":
    main(sys.argv[1])
