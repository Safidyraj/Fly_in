"""Data models for the Fly-in simulation."""
from enum import Enum
from typing import List


class ZoneType(Enum):
    """The movement category of a zone, which determines its traversal cost."""

    NORMAL = "normal"
    RESTRICTED = "restricted"
    PRIORITY = "priority"
    BLOCKED = "blocked"


class Zone:
    """A single location in the drone network."""

    def __init__(
        self,
        name: str,
        x: int,
        y: int,
        role: str,
        zone_type: ZoneType = ZoneType.NORMAL,
        color: str = "none",
            max_drones: int | float = 1) -> None:
        """Create a zone representing a single location in the drone network.

        Args:
        name: Unique identifier of the zone.
        x: X coordinate on the map grid.
        y: Y coordinate on the map grid.
        role: "start_hub", "end_hub", or "hub" (regular zone).
        zone_type: Movement category (normal/blocked/restricted/priority).
        color: Optional display color for visual representation.
        max_drones: Maximum number of drones allowed in this zone at once.
        """
        self.name: str = name
        self.x: int = x
        self.y: int = y
        self.role: str = role
        self.zone_type: ZoneType = zone_type
        self.color: str = color
        self.max_drones: int | float = max_drones
        self.connections: List[Connection] = []

    def __repr__(self) -> str:
        """Return a debug-friendly string representation of the zone."""
        return ("Zone("
                f"name={self.name}, "
                f"pos=({self.x, self.y}), "
                f"role={self.role}, "
                f"type={self.zone_type}, "
                f"color={self.color}, "
                f"cap={self.max_drones}, "
                f"nb_conn={len(self.connections)})"
                )

    def get_neighbors(self) -> List["Zone"]:
        """Return the list of zones directly connected to this zone."""
        return [
            c.zone_b if c.zone_a == self else c.zone_a
            for c in self.connections]


class Connection:
    """A bidirectional link between two zones."""

    def __init__(
        self,
        zone_a: Zone,
        zone_b: Zone,
            max_link_capacity: int = 1) -> None:
        """Create a bidirectional link between two zones.

        Args:
            zone_a: One endpoint of the connection.
            zone_b: The other endpoint of the connection.
            max_link_capacity: Maximum number of drones allowed to traverse
                this connection during the same simulation turn.
        """
        self.zone_a: Zone = zone_a
        self.zone_b: Zone = zone_b
        self.max_link_capacity: int = max_link_capacity

    def __repr__(self) -> str:
        """Return a debug-friendly string representation of the connection."""
        return (f"Connection({self.zone_a.name}<->{self.zone_b.name},"
                f" cap={self.max_link_capacity})")


class Drone():
    """A single drone and the full tick-by-tick timeline it will follow."""

    def __init__(
        self,
        drone_id: int,
            path_to_follow: list[Zone]) -> None:
        """Create a single drone.

        Args:
            drone_id: Unique identifier of the drone.
            path_to_follow: The zone occupied by this drone at every
                simulation tick, from departure to arrival.
        """
        self.drone_id: int = drone_id
        self.path_to_follow: list[Zone] = path_to_follow

    def __repr__(self) -> str:
        """Return a debug-friendly string representation of the drone."""
        return (f"Drone(id={self.drone_id}, "
                "path_to_follow: ("
                f"{', '.join([p.name for p in self.path_to_follow])}))"
                )
