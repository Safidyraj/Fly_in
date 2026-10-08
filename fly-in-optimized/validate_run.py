"""Run a map through the simulator and independently verify that no
zone or connection capacity was ever exceeded, then report turn count.

Usage: python3 validate_run.py <map_file>
"""

import sys
from collections import defaultdict

from algo import Pathfinder, Graph, Connection, Zone as AlgoZone, PathNotFoundError
from parser import Parser


def main(path: str) -> None:
    zones, nb_drones = Parser().file_parser(path)
    start_zone = next(z for z in zones.values() if z.role == "start_hub")
    end_zone = next(z for z in zones.values() if z.role == "end_hub")

    graph = Graph()
    for zone in zones.values():
        graph.add_zone(
            AlgoZone(zone.name, zone.x, zone.y, zone.zone_type.value, zone.max_drones)
        )
    for zone in zones.values():
        for c in zone.connections:
            graph.add_connection(
                Connection(c.zone_a.name, c.zone_b.name, c.max_link_capacity)
            )

    pf = Pathfinder(graph)
    agenda: dict = {}
    conn_agenda: dict = {}
    drones = []
    for drone_id in range(1, nb_drones + 1):
        try:
            timed_path = pf.shortest_path(
                start_zone.name, end_zone.name, agenda, conn_agenda
            )
        except PathNotFoundError as e:
            print(f"UNSOLVABLE: drone {drone_id}: {e}")
            sys.exit(1)
        path = [(zones[name], tick) for name, tick in timed_path]
        for i in range(len(path)):
            curr_zone, curr_tick = path[i]
            agenda.setdefault((curr_zone.name, curr_tick), []).append(drone_id)
            if i > 0:
                prev_zone, prev_tick = path[i - 1]
                if prev_zone.name != curr_zone.name:
                    z1, z2 = sorted([prev_zone.name, curr_zone.name])
                    for t in range(prev_tick, curr_tick):
                        conn_agenda.setdefault((z1, z2, t), []).append(drone_id)
        drones.append((drone_id, path))

    # --- Independent re-validation from the booked path (not the search) ---
    zone_cap = {z.name: z.max_drones for z in zones.values()}
    conn_cap = {}
    for z in zones.values():
        for c in z.connections:
            z1, z2 = sorted([c.zone_a.name, c.zone_b.name])
            conn_cap[(z1, z2)] = c.max_link_capacity

    zone_usage = defaultdict(int)
    conn_usage = defaultdict(int)
    max_tick = 0
    for drone_id, path in drones:
        for i, (zone, tick) in enumerate(path):
            zone_usage[(zone.name, tick)] += 1
            max_tick = max(max_tick, tick)
            if i > 0:
                prev_zone, prev_tick = path[i - 1]
                if prev_zone.name != zone.name:
                    z1, z2 = sorted([prev_zone.name, zone.name])
                    for t in range(prev_tick, tick):
                        conn_usage[(z1, z2, t)] += 1

    violations = []
    for (name, tick), used in zone_usage.items():
        cap = zone_cap[name]
        if cap != float("inf") and used > cap:
            violations.append(f"ZONE OVERFLOW {name}@{tick}: {used}/{cap}")
    for (z1, z2, tick), used in conn_usage.items():
        cap = conn_cap[(z1, z2)]
        if used > cap:
            violations.append(f"LINK OVERFLOW {z1}-{z2}@{tick}: {used}/{cap}")

    from colorama import init, Fore, Style

    init()

    print(
        f"{Style.BRIGHT}{Fore.GREEN}{path and 'OK'}{Fore.RESET} "
        f"drones={Fore.CYAN}{nb_drones}{Fore.RESET} "
        f"total_turns={Fore.CYAN}{max_tick}{Fore.RESET} "
        f"violations={Fore.RED}{len(violations)}{Fore.RESET}"
    )
    for v in violations[:20]:
        print("  " + v)


if __name__ == "__main__":
    main(sys.argv[1])
