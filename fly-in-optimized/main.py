"""Main entry point for the Fly-in simulation."""
from models import (
    Zone,
    ZoneType,
    Drone
)
from algo import (
    Pathfinder,
    Graph,
    Connection,
    Zone as AlgoZone,
    PathNotFoundError as PathfinderError,
)
from parser import Parser
from terminal import print_turn, print_turn_count, print_capacity_line, error_print
import argparse
import sys


class Simulator:
    """Parses CLI arguments, then plans and runs the full drone simulation."""

    @staticmethod
    def map_path_flag() -> argparse.Namespace:
        """Parse the command-line arguments (map file path, --visual flag)."""
        parser = argparse.ArgumentParser(
            description=("Design an efficient drone routing"
                         " system that navigates multiple drones"),
            usage=("uv run python3 -m src <path to a map file>"
                   " [--visual text or pygame]")
        )
        parser.add_argument(
            "map_path",
            help="The name of the file to process")
        parser.add_argument(
            "--visual",
            choices=["text", "pygame"],
            default="text",
            help="Display mode: plain-text turn log (default) or a pygame"
            " graphical simulation.")
        parser.add_argument(
                    "--capacity-info",
                    action="store_true"
                )
        parser.add_argument(
            "--bg-dir",
            default=None,
            help="Folder of background images (.png/.jpg) to rotate"
            " through in --visual pygame mode. Defaults to"
            " assets/backgrounds.")
        parser.add_argument(
            "--speed",
            type=float,
            default=1.1,
            help="Seconds of animation per simulation turn in --visual"
            " pygame mode (lower = faster).")
        parser.add_argument(
            "--autoplay",
            action="store_true",
            help="Start the pygame replay immediately. Without this flag"
            " the replay opens paused and waits for SPACE.")
        return parser.parse_args()

    def args(self) -> tuple[
            dict[str, Zone], int, str, bool, str | None, float, bool]:
        """Read the CLI arguments and parse the resulting map file.

        Returns:
            A tuple of (zones indexed by name, number of drones to route,
            the requested visual mode ('text' or 'pygame'), whether
            --capacity-info was requested, the background image folder for
            pygame mode, and the per-turn animation duration in seconds).
        """
        parser: Parser = Parser()
        args: argparse.Namespace = self.map_path_flag()
        map_path: str = args.map_path
        zones, nb_drones = parser.file_parser(map_path)
        return (zones, nb_drones, args.visual, bool(args.capacity_info),
                args.bg_dir, args.speed, bool(args.autoplay))

    @staticmethod
    def book_a_spot(
        path: list[tuple[Zone, int]],
        drone_id: int,
        agenda: dict[tuple[str, int], list[int]],
        conn_agenda: dict[tuple[str, str, int], list[int]]) -> tuple[
            dict[tuple[str, int],
                 list[int]], dict[tuple[str, str, int], list[int]]]:
        """Reserve every zone/connection slot a drone's path will occupy.

        Mirrors exactly what `Pathfinder.shortest_path` checked while
        planning this path: one zone-occupancy reservation per (zone,
        tick) state actually visited (including waits), and one
        connection reservation per tick of every transit (2 ticks for a
        move into a 'restricted' zone, 1 tick otherwise). Mutates
        `agenda` and `conn_agenda` in place so later calls to
        `Pathfinder` treat these slots as already taken.

        Args:
            path: The (zone, tick) path found for this drone.
            drone_id: The drone this path belongs to.
            agenda: Shared zone-occupancy calendar to update.
            conn_agenda: Shared connection-usage calendar to update.

        Returns:
            The same (agenda, conn_agenda) objects, already mutated in place.
        """
        for i in range(len(path)):
            curr_zone, curr_tick = path[i]
            key: tuple[str, int] = (curr_zone.name, curr_tick)
            agenda.setdefault(key, []).append(drone_id)
            if i > 0:
                prev_zone, prev_tick = path[i - 1]
                if prev_zone.name != curr_zone.name:
                    zone1, zone2 = sorted([prev_zone.name, curr_zone.name])
                    duration = curr_tick - prev_tick
                    for t in range(prev_tick, prev_tick + duration):
                        conn_key = (zone1, zone2, t)
                        conn_agenda.setdefault(conn_key, []).append(drone_id)

        return (agenda, conn_agenda)

    def fly_in(
        self,
        zones: dict[str, Zone],
        nb_drones: int,
        visual: str = "text",
        capacity_info=False,
        bg_dir: str | None = None,
            speed: float = 1.1,
            autoplay: bool = False) -> None:
        """Route every drone from start to end and report the simulation.

        Routes drones one at a time (first-come-first-served), booking each
        drone's path before searching for the next one, then expands every
        drone's path into a full tick-by-tick timeline and either shows the
        pygame visualization or prints the turn-by-turn movement log.

        Args:
            zones: All zones on the map, indexed by name.
            nb_drones: Number of drones to route from start to end.
            visual: "text" (default) for the plain turn-by-turn log, or
                "pygame" to open the graphical simulation window instead.
            bg_dir: Folder of background images for the pygame replay.
            speed: Seconds of animation per turn for the pygame replay.
            autoplay: Start the pygame replay immediately instead of
                waiting for the user to press SPACE.
        """
        start_zone = next(zone for zone in zones.values()
                          if zone.role == "start_hub")
        end_zone = next(zone for zone in zones.values()
                        if zone.role == "end_hub")

        graph = Graph()
        for zone in zones.values():
            graph.add_zone(AlgoZone(
                name=zone.name,
                x=zone.x,
                y=zone.y,
                zone_type=zone.zone_type.value,
                max_drones=zone.max_drones,
            ))
        for zone in zones.values():
            for connection in zone.connections:
                graph.add_connection(Connection(
                    connection.zone_a.name,
                    connection.zone_b.name,
                    connection.max_link_capacity,
                ))

        pathfinder = Pathfinder(graph)
        drones: list[Drone] = []
        agenda: dict[tuple[str, int], list[int]] = {}
        conn_agenda: dict[tuple[str, str, int], list[int]] = {}
        for drone_id in range(1, nb_drones + 1):
            try:
                timed_path = pathfinder.shortest_path(
                    start_zone.name, end_zone.name, agenda, conn_agenda)
            except PathfinderError as e:
                error_print(f"Unable to find a path "
                            f"for drone {drone_id}! ({e})")
                sys.exit(1)

            # (zone_name, tick) -> (Zone, lap); tick already accounts for
            # every movement cost AND every wait the capacity-aware
            # pathfinder needed to insert.
            path: list[tuple[Zone, int]] = [
                (zones[name], tick) for name, tick in timed_path
            ]

            agenda, conn_agenda = self.book_a_spot(
                path, drone_id, agenda, conn_agenda)
            # expand to full tick-by-tick timeline
            full_timeline_path: list[Zone] = []
            for i in range(len(path)):
                zone, lap = path[i]
                if i == 0:
                    full_timeline_path.append(zone)
                    continue
                prev_zone, _ = path[i - 1]
                while len(full_timeline_path) < lap:
                    if (
                        zone.zone_type == ZoneType.RESTRICTED and len(
                            full_timeline_path) == lap - 1):
                        conn_name = f"{prev_zone.name}-{zone.name}"
                        conn_zone = Zone(conn_name, -1, -1, "connection")
                        full_timeline_path.append(conn_zone)
                    else:
                        full_timeline_path.append(prev_zone)
                full_timeline_path.append(zone)
            drones.append(Drone(drone_id, full_timeline_path))
        max_len = max(len(d.path_to_follow) for d in drones)

        if visual == "pygame":
            from visual_pygame import VisualPygame
            visual_pygame: VisualPygame = VisualPygame(
                bg_dir=bg_dir, seconds_per_turn=speed, autoplay=autoplay)
            visual_pygame.run_pygame_visual(zones, drones, max_len)
            return

        total_turns = 0
        for global_lap in range(1, max_len):
            moves = []
            for d in drones:
                if global_lap < len(d.path_to_follow):
                    curr_zone = d.path_to_follow[global_lap]
                    prev_zone = d.path_to_follow[global_lap - 1]
                    if curr_zone.name != prev_zone.name:
                        moves.append(f"D{d.drone_id}-{curr_zone.name}")
            total_turns = global_lap
            if capacity_info:
                for z in zones.values():
                    if z.role not in ("start_hub", "end_hub"):
                        used_z = len(agenda.get((z.name, global_lap), []))
                        print_capacity_line(
                            f"{z.name}: {used_z}/{z.max_drones} drones")
                seen_conns = set()
                for z in zones.values():
                    for conn in z.connections:
                        pair = tuple(sorted([
                            conn.zone_a.name, conn.zone_b.name]))
                        if pair not in seen_conns:
                            seen_conns.add(pair)
                            used_c = len(conn_agenda.get((pair[0], pair[1],
                                                          global_lap), []))
                            print_capacity_line(
                                f"Connection {pair[0]}-{pair[1]}: "
                                f"{used_c}/{conn.max_link_capacity} "
                                "capacity used")
            else:
                print_turn(moves)
        print_turn_count(total_turns)


if __name__ == "__main__":
    try:
        simulator = Simulator()
        (zones, nb_drones, visual, capacity_info,
         bg_dir, speed, autoplay) = simulator.args()
        simulator.fly_in(zones, nb_drones, visual, capacity_info,
                         bg_dir, speed, autoplay)
    except KeyboardInterrupt as e:
        error_print(str(e) or "Interrupted by user.")
    except Exception as e:
        error_print(str(e))
        sys.exit(1)
