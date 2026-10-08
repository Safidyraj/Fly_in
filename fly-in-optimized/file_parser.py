"""File-parser and constraint for the Fly-in."""
import sys
from typing import Dict, Tuple
from models import Zone, Connection
from terminal import error_print


def file_parser(self, path: str) -> Tuple[Dict[str, Zone], int]:
    """Parse a full map file into its zones and drone count.

    Args:
        path: Path to the map file to read.

    Returns:
        A tuple of (zones indexed by name, number of drones to route).
    """
    zones: Dict[str, Zone] = {}
    nb_drones: int = 0
    seen_connections: set[tuple[str, str]] = set()
    seen_coords: set[tuple[int, int]] = set()
    start_count: int = 0
    end_count: int = 0
    is_nb_drones: bool = False
    first_line: bool = True
    with open(path, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            l_line: str = line.lower()
            if first_line and not l_line.startswith("nb_drones:"):
                error_print(
                    f"Error Line {line_num}: the first line must"
                    " define nb_drones"
                )
                sys.exit(1)
            first_line = False
            try:
                if l_line.startswith("nb_drones:"):
                    try:
                        if is_nb_drones:
                            error_print(
                                f"Error line {line_num}:" " Duplicate"
                                "nb_drones"
                            )
                            sys.exit(1)
                        is_nb_drones = True
                        nb_drones = int(l_line.split(":", 1)[1].strip())
                        if nb_drones <= 0:
                            error_print(
                                f"Error line {line_num}: number of"
                                " drones must be ",
                                "a positive number" f" got {nb_drones!r}",
                            )
                            sys.exit(1)
                    except ValueError as e:
                        raise ValueError(f"{e}")
                elif l_line.startswith(("start_hub:", "hub:", "end_hub:")):
                    role: str = l_line.split(":", 1)[0].strip()
                    zone: Zone | None = self.parse_zone_line(
                        line, role, line_num)
                    if zone:
                        if (zone.x, zone.y) not in seen_coords:
                            seen_coords.add((zone.x, zone.y))
                        else:
                            error_print(
                                f"Error Line {line_num}: "
                                "Got duplicate coordinates"
                                f" ({zone.x},"
                                f" {zone.y})"
                            )
                            sys.exit(1)
                        if zone.name in zones:
                            error_print(
                                f"Error Line {line_num}: "
                                "Duplicate zone "
                                f"name {zone.name!r}"
                            )
                            sys.exit(1)
                        elif role == "start_hub":
                            start_count += 1
                        elif role == "end_hub":
                            end_count += 1
                        zones[zone.name] = zone
                elif l_line.startswith("connection:"):
                    m_data: Dict[str, str] = {}
                    if "[" in l_line or "]" in l_line:
                        if "[" not in l_line or "]" not in l_line:
                            error_print(
                                f"Error Line {line_num}:"
                                " malformed metadata block"
                            )
                            sys.exit(1)
                        start_idx: int = l_line.find("[")
                        end_idx: int = l_line.find("]")
                        if start_idx > end_idx:
                            error_print(
                                f"Error line {line_num}: inverted"
                                " metadata brackets  in"
                                f" {l_line.strip()!r}"
                            )
                            sys.exit(1)
                        if l_line[start_idx - 1] in (" ", "\t"):
                            m_data = self.parse_metadata(
                                l_line[start_idx: end_idx + 1].strip(),
                                line_num,
                                l_line,
                            )
                        else:
                            error_print(f"Error line {line_num}: "
                                        "Ivalid metadata")
                            sys.exit(1)
                        l_line = (line[:start_idx] +
                                  l_line[end_idx + 1:]).strip()
                    content: str = l_line.split(":", 1)[1].strip()
                    if "-" not in content:
                        error_print(
                            f"Error Line {line_num}:" " Invalid connection"
                            "format"
                        )
                        sys.exit(1)
                    name_a, name_b = content.split("-", 1)
                    name_a, name_b = name_a.strip(), name_b.strip()
                    zone_a = zones.get(name_a)
                    zone_b = zones.get(name_b)
                    if zone_a and zone_b:
                        pair: tuple[str, str] = (
                            min(name_a, name_b),
                            max(name_a, name_b),
                        )
                        if pair in seen_connections:
                            error_print(
                                f"Error Line {line_num} in {path!r}: "
                                f"duplicate connection {name_a}-"
                                f"{name_b}"
                            )
                            sys.exit(1)
                        seen_connections.add(pair)
                        try:
                            max_link_cap: int = int(
                                m_data.get("max_link_capacity", 1))
                            if max_link_cap <= 0:
                                error_print(
                                    f"Error line {line_num}: max link"
                                    " capacity must be",
                                    " a positive number got "
                                    f"{max_link_cap!r}",
                                )
                                sys.exit(1)
                        except ValueError as e:
                            raise ValueError(f"{e}")
                        conn: Connection = Connection(
                            zone_a, zone_b, max_link_cap)
                        zone_a.connections.append(conn)
                        zone_b.connections.append(conn)
                    else:
                        error_print(
                            f"Error Line {line_num} in {path}: "
                            "Zone not found"
                            " for connection "
                            f"{name_a}-{name_b}"
                        )
                        sys.exit(1)
                else:
                    error_print(
                        f"Error line {line_num}:" " Unrecognized line"
                        f" {l_line!r}"
                    )
            except Exception as e:
                error_print(f"Error Line {line_num}: {e}")
                sys.exit(1)
    if start_count != 1 or end_count != 1:
        error_print(
            f"Error line: Exactly one start_hub"
            " and one end_hub required."
            f" Found {start_count} start_hub,"
            f" {end_count} end_hub."
        )
        sys.exit(1)
    return zones, nb_drones
