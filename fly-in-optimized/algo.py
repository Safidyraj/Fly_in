"""Pathfinding module for the Fly-in project.

Implements a *capacity-aware, time-expanded* shortest-path search
("space-time A*", a.k.a. cooperative A* / prioritized planning) so that
multiple drones can be routed one at a time while genuinely respecting:

    - zone capacity        (max_drones)
    - connection capacity  (max_link_capacity)
    - zone movement cost:
          normal:     1 turn
          priority:   1 turn (preferred on ties)
          restricted: 2 turns
          blocked:    never traversable

Unlike a plain Dijkstra over the static graph, this search happens over
*states* of the form ``(zone_name, tick)`` so it can:

    - make a drone WAIT one turn in place when the next zone/connection
      it needs is momentarily full (instead of blindly colliding with it),
    - route a drone around a busy bottleneck via an alternative path
      when waiting would be worse,
    - be called once per drone, in sequence, each call being aware of
      every reservation made by the drones scheduled before it
      (this is the classic "prioritized planning" / cooperative A*
      scheme for multi-agent pathfinding).

The caller (see ``main.py``) is responsible for booking the returned
path into the shared reservation tables before planning the next drone.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Optional

ZONE_COSTS: dict[str, int] = {
    "normal": 1,
    "priority": 1,
    "restricted": 2,
}

BLOCKED_ZONE_TYPE = "blocked"
PRIORITY_ZONE_TYPE = "priority"

# Tiny tie-breaking bonus (never changes the integer turn count) so that,
# among several equally-cheap routes, the search prefers the one that
# passes through 'priority' zones, as requested by the map design.
_PRIORITY_BIAS = 1e-4

# Hard safety cap on how many turns a single-drone search is allowed to
# explore. Generous enough for every provided map (including 25-drone
# capacity chains) while still preventing runaway search on a malformed
# or genuinely unsolvable map.
DEFAULT_MAX_HORIZON = 2000


Reservation = dict[tuple[str, int], list[int]]
ConnReservation = dict[tuple[str, str, int], list[int]]


@dataclass
class Zone:
    """Represents a single zone (node) in the drone network.

    Attributes:
        name: Unique identifier of the zone.
        x: X coordinate.
        y: Y coordinate.
        zone_type: One of 'normal', 'priority', 'restricted', 'blocked'.
        max_drones: Maximum number of drones allowed simultaneously
            (``float('inf')`` for unlimited, e.g. start/end hubs).
    """

    name: str
    x: int
    y: int
    zone_type: str = "normal"
    max_drones: int | float = 1

    def movement_cost(self) -> int:
        """Return the turn cost to move into this zone.

        Raises:
            ValueError: If the zone is blocked and therefore not
                traversable.
        """
        if self.zone_type == BLOCKED_ZONE_TYPE:
            raise ValueError(f"Zone '{self.name}' is blocked.")
        return ZONE_COSTS.get(self.zone_type, 1)


@dataclass
class Connection:
    """Represents a bidirectional edge between two zones.

    Attributes:
        zone_a: Name of the first zone.
        zone_b: Name of the second zone.
        max_link_capacity: Max number of drones on this connection at once.
    """

    zone_a: str
    zone_b: str
    max_link_capacity: int = 1

    def other(self, zone_name: str) -> str:
        """Return the zone on the other side of this connection."""
        if zone_name == self.zone_a:
            return self.zone_b
        if zone_name == self.zone_b:
            return self.zone_a
        raise ValueError(f"Zone '{zone_name}' is not part of this connection.")


@dataclass
class Graph:
    """Holds all zones and connections of the drone network."""

    zones: dict[str, Zone] = field(default_factory=dict)
    connections: list[Connection] = field(default_factory=list)
    _adjacency: dict[str, list[Connection]] = field(default_factory=dict)

    def add_zone(self, zone: Zone) -> None:
        """Register a zone in the graph."""
        self.zones[zone.name] = zone
        self._adjacency.setdefault(zone.name, [])

    def add_connection(self, connection: Connection) -> None:
        """Register a connection and update the adjacency list."""
        self.connections.append(connection)
        self._adjacency.setdefault(connection.zone_a, []).append(connection)
        self._adjacency.setdefault(connection.zone_b, []).append(connection)

    def neighbors(self, zone_name: str) -> list[Connection]:
        """Return the connections attached to a given zone."""
        return self._adjacency.get(zone_name, [])


class PathNotFoundError(Exception):
    """Raised when no valid (capacity-respecting) path exists in time."""


class Pathfinder:
    """Computes capacity-aware turn-optimal paths using space-time A*.

    One instance is created per simulation and reused for every drone:
    the static per-zone-type Dijkstra heuristic is cached across calls
    since the graph topology never changes, only the reservations do.
    """

    def __init__(self, graph: Graph) -> None:
        """Store a reference to the graph to search on.

        Args:
            graph: The Graph instance describing zones and connections.
        """
        self._graph = graph
        self._heuristic_cache: dict[str, dict[str, float]] = {}

    # API
    def shortest_path(
        self,
        start: str,
        end: str,
        agenda: Optional[Reservation] = None,
        conn_agenda: Optional[ConnReservation] = None,
        earliest_departure: int = 0,
        max_horizon: int = DEFAULT_MAX_HORIZON,
    ) -> list[tuple[str, int]]:
        """Return the cheapest capacity-respecting timed path.

        Args:
            start: Name of the starting zone.
            end: Name of the target zone.
            agenda: Existing zone-occupancy reservations
                ``{(zone_name, tick): [drone_id, ...]}`` made by drones
                already scheduled. Not mutated.
            conn_agenda: Existing connection-usage reservations
                ``{(zone_a, zone_b, tick): [drone_id, ...]}`` (zone_a <
                zone_b alphabetically), made by drones already
                scheduled. Not mutated.
            earliest_departure: Tick at which this drone starts (0 for
                every drone in this project, kept for flexibility).
            max_horizon: Safety cap on how many ticks the search may
                explore before giving up.

        Returns:
            A list of ``(zone_name, tick)`` pairs from start to end,
            inclusive, in increasing tick order. Consecutive pairs with
            the same zone name represent the drone waiting one turn in
            place; consecutive pairs with a tick gap of 2 represent a
            move into a 'restricted' zone.

        Raises:
            PathNotFoundError: If no valid timed path exists within
                ``max_horizon`` turns (unknown zones, permanently
                blocked, or capacity deadlock).
        """
        if start not in self._graph.zones or end not in self._graph.zones:
            raise PathNotFoundError(f"Unknown zone: '{start}' or '{end}'.")

        agenda = agenda or {}
        conn_agenda = conn_agenda or {}
        heuristic = self._distances_to(end)
        if start not in heuristic:
            raise PathNotFoundError(f"'{end}' is unreachable from '{start}'.")

        start_state = (start, earliest_departure)
        g_score: dict[tuple[str, int], float] = {start_state: 0.0}
        came_from: dict[tuple[str, int], tuple[str, int]] = {}
        closed: set[tuple[str, int]] = set()

        counter = 0
        open_heap: list[tuple[float, int, str, int]] = [
            (heuristic[start], counter, start, earliest_departure)
        ]

        while open_heap:
            _, _, zone_name, tick = heapq.heappop(open_heap)
            state = (zone_name, tick)
            if state in closed:
                continue
            if zone_name == end:
                return self._rebuild_path(came_from, state)
            closed.add(state)
            if tick >= max_horizon:
                continue

            current_g = g_score[state]

            # --- Option 1: wait one turn in place -----------------------
            wait_state = (zone_name, tick + 1)
            if wait_state not in closed and self._zone_has_room(
                zone_name, tick + 1, agenda
            ):
                counter = self._relax(
                    wait_state,
                    current_g + 1.0,
                    state,
                    g_score,
                    came_from,
                    open_heap,
                    heuristic,
                    counter,
                )

            # --- Option 2: move to a neighboring zone --------------------
            for connection in self._graph.neighbors(zone_name):
                neighbor_name = connection.other(zone_name)
                neighbor_zone = self._graph.zones[neighbor_name]
                if neighbor_zone.zone_type == BLOCKED_ZONE_TYPE:
                    continue

                duration = neighbor_zone.movement_cost()
                arrival_tick = tick + duration

                if not self._connection_has_room(
                    zone_name,
                    neighbor_name,
                    tick,
                    duration,
                    connection.max_link_capacity,
                    conn_agenda,
                ):
                    continue
                if not self._zone_has_room(neighbor_name,
                                           arrival_tick, agenda):
                    continue

                neighbor_state = (neighbor_name, arrival_tick)
                if neighbor_state in closed:
                    continue
                bias = (
                    -_PRIORITY_BIAS
                    if neighbor_zone.zone_type == PRIORITY_ZONE_TYPE
                    else 0.0
                )
                counter = self._relax(
                    neighbor_state,
                    current_g + duration + bias,
                    state,
                    g_score,
                    came_from,
                    open_heap,
                    heuristic,
                    counter,
                )

        raise PathNotFoundError(
            f"No capacity-respecting path found between '{start}' and "
            f"'{end}' within {max_horizon} turns."
        )

    # Internals
    @staticmethod
    def _relax(
        state: tuple[str, int],
        tentative_g: float,
        parent: tuple[str, int],
        g_score: dict[tuple[str, int], float],
        came_from: dict[tuple[str, int], tuple[str, int]],
        open_heap: list[tuple[float, int, str, int]],
        heuristic: dict[str, float],
        counter: int,
    ) -> int:
        """Push `state` onto the open heap if this path to it is better."""
        if tentative_g < g_score.get(state, float("inf")):
            g_score[state] = tentative_g
            came_from[state] = parent
            counter += 1
            zone_name, tick = state
            h = heuristic.get(zone_name, 0.0)
            heapq.heappush(open_heap, (tentative_g + h, counter,
                                       zone_name, tick))
        return counter

    def _zone_has_room(self, zone_name: str,
                       tick: int, agenda: Reservation) -> bool:
        """Return True if `zone_name` has a free slot at turn `tick`."""
        zone = self._graph.zones[zone_name]
        if zone.max_drones == float("inf"):
            return True
        used = len(agenda.get((zone_name, tick), ()))
        return used < zone.max_drones

    @staticmethod
    def _connection_has_room(
        zone_a: str,
        zone_b: str,
        depart_tick: int,
        duration: int,
        max_link_capacity: int,
        conn_agenda: ConnReservation,
    ) -> bool:
        """Return True if the edge has room for every tick of the transit.

        A restricted-zone entry takes 2 turns, during which the drone
        physically occupies the connection for both ticks, so both must
        be checked (a 1-turn move only checks the departure tick).
        """
        pair = (zone_a, zone_b) if zone_a < zone_b else (zone_b, zone_a)
        for tick in range(depart_tick, depart_tick + duration):
            used = len(conn_agenda.get((pair[0], pair[1], tick), ()))
            if used >= max_link_capacity:
                return False
        return True

    def _distances_to(self, target: str) -> dict[str, float]:
        """Static (capacity-ignoring) Dijkstra distance from every zone
        to `target`, used as an admissible A* heuristic. Cached per
        target since the graph topology is fixed for the whole run.
        """
        if target in self._heuristic_cache:
            return self._heuristic_cache[target]

        distances: dict[str, float] = {target: 0.0}
        visited: set[str] = set()
        heap: list[tuple[float, str]] = [(0.0, target)]

        while heap:
            dist, node = heapq.heappop(heap)
            if node in visited:
                continue
            visited.add(node)
            node_zone = self._graph.zones[node]
            if node_zone.zone_type == BLOCKED_ZONE_TYPE:
                continue
            hop_cost = node_zone.movement_cost()

            for connection in self._graph.neighbors(node):
                neighbor_name = connection.other(node)
                neighbor_zone = self._graph.zones[neighbor_name]
                if neighbor_zone.zone_type == BLOCKED_ZONE_TYPE:
                    continue
                candidate = dist + hop_cost
                if candidate < distances.get(neighbor_name, float("inf")):
                    distances[neighbor_name] = candidate
                    heapq.heappush(heap, (candidate, neighbor_name))

        self._heuristic_cache[target] = distances
        return distances

    @staticmethod
    def _rebuild_path(
        came_from: dict[tuple[str, int], tuple[str, int]],
        end_state: tuple[str, int],
    ) -> list[tuple[str, int]]:
        """Reconstruct the (zone, tick) path from the `came_from` chain."""
        path: list[tuple[str, int]] = [end_state]
        current = end_state
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path


if __name__ == "__main__":
    # Small manual example matching the sample map from the subject.
    graph = Graph()
    graph.add_zone(Zone("hub", 0, 0, "normal", max_drones=float("inf")))
    graph.add_zone(Zone("goal", 10, 10, "normal", max_drones=float("inf")))
    graph.add_zone(Zone("roof1", 3, 4, "restricted"))
    graph.add_zone(Zone("roof2", 6, 2, "normal"))
    graph.add_zone(Zone("corridorA", 4, 3, "priority", max_drones=2))
    graph.add_zone(Zone("tunnelB", 7, 4, "normal"))
    graph.add_zone(Zone("obstacleX", 5, 5, "blocked"))

    graph.add_connection(Connection("hub", "roof1"))
    graph.add_connection(Connection("hub", "corridorA"))
    graph.add_connection(Connection("roof1", "roof2"))
    graph.add_connection(Connection("roof2", "goal"))
    graph.add_connection(Connection("corridorA", "tunnelB",
                                    max_link_capacity=2))
    graph.add_connection(Connection("tunnelB", "goal"))

    pathfinder = Pathfinder(graph)
    result = pathfinder.shortest_path("hub", "goal")
    print("Path:", " -> ".join(f"{name}@{tick}" for name, tick in result))
