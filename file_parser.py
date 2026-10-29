"""File-parser and constraint for the Fly-in."""
from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Dict, Tuple

from models import Connection, Zone
from terminal import error_print

if TYPE_CHECKING:
    from parser import Parser


def file_parser(self: Parser, path: str) -> Tuple[Dict[str, Zone], int]:
    """Parse a full map file into its zones and drone count.

    Args:
        self: Parser instance that owns the XML-like map parsing helpers.
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

    with open(path, "r", encoding="utf-8") as file:
        for line_num, raw_line in enumerate(file, 1):
            line = raw_line.strip()
            if "#" in line:
                idx = line.find("#")
                line = line[:idx].rstrip()
                if not line:
                    continue
            if not line:
                continue

            lower_line = line.lower()
            if first_line and not lower_line.startswith("nb_drones:"):
                error_print(
                    f"Error Line {line_num}: the first line must "
                    "define nb_drones"
                )
                sys.exit(1)
            first_line = False

            try:
                if lower_line.startswith("nb_drones:"):
                    if is_nb_drones:
                        error_print(
                            f"Error line {line_num}: Duplicate nb_drones"
                        )
                        sys.exit(1)
                    is_nb_drones = True
                    nb_drones = int(lower_line.split(":", 1)[1].strip())
                    if nb_drones <= 0:
                        error_print(
                            f"Error line {line_num}: number of drones must "
                            "be a positive number "
                            f"got {nb_drones!r}"
                        )
                        sys.exit(1)
                elif lower_line.startswith(("start_hub:", "hub:", "end_hub:")):
                    role: str = lower_line.split(":", 1)[0].strip()
                    zone: Zone | None = self.parse_zone_line(
                        lower_line, role, line_num
                    )
                    if zone is None:
                        continue
                    if (zone.x, zone.y) in seen_coords:
                        error_print(
                            f"Error Line {line_num}: Got duplicate "
                            f"coordinates ({zone.x}, {zone.y})"
                        )
                        sys.exit(1)
                    seen_coords.add((zone.x, zone.y))
                    if zone.name in zones:
                        error_print(
                            f"Error Line {line_num}: Duplicate zone "
                            f"name {zone.name!r}"
                        )
                        sys.exit(1)
                    if role == "start_hub":
                        start_count += 1
                    elif role == "end_hub":
                        end_count += 1
                    zones[zone.name] = zone
                elif lower_line.startswith("connection:"):
                    metadata: Dict[str, str] = {}
                    if "[" in lower_line or "]" in lower_line:
                        if "[" not in lower_line or "]" not in lower_line:
                            error_print(
                                f"Error Line {line_num}: malformed metadata "
                                "block"
                            )
                            sys.exit(1)
                        start_idx: int = lower_line.find("[")
                        end_idx: int = lower_line.find("]")
                        if start_idx > end_idx:
                            error_print(
                                f"Error line {line_num}: inverted metadata "
                                f"brackets in {lower_line.strip()!r}"
                            )
                            sys.exit(1)
                        if lower_line[start_idx - 1] in (" ", "\t"):
                            metadata = self.parse_metadata(
                                lower_line[start_idx: end_idx + 1].strip(),
                                line_num,
                                lower_line,
                            )
                        else:
                            error_print(
                                f"Error line {line_num}: Invalid metadata"
                            )
                            sys.exit(1)
                        lower_line = (
                            lower_line[:start_idx] + lower_line[end_idx + 1:]
                        ).strip()

                    content: str = lower_line.split(":", 1)[1].strip()
                    if "-" not in content:
                        error_print(
                            f"Error Line {line_num}: Invalid connection format"
                        )
                        sys.exit(1)

                    name_a, name_b = content.split("-", 1)
                    name_a, name_b = name_a.strip(), name_b.strip()
                    zone_a = zones.get(name_a)
                    zone_b = zones.get(name_b)
                    if zone_a is None or zone_b is None:
                        error_print(
                            f"Error Line {line_num} in {path!r}: Zone not "
                            f"found for connection {name_a}-{name_b}"
                        )
                        sys.exit(1)

                    pair: tuple[str, str] = (
                        min(name_a, name_b),
                        max(name_a, name_b),
                    )
                    if pair in seen_connections:
                        error_print(
                            f"Error Line {line_num} in {path!r}: duplicate "
                            f"connection {name_a}-{name_b}"
                        )
                        sys.exit(1)
                    seen_connections.add(pair)

                    try:
                        max_link_cap: int = int(
                            metadata.get("max_link_capacity", "1")
                        )
                        if max_link_cap <= 0:
                            error_print(
                                f"Error line {line_num}: max link capacity "
                                f"must be a positive number got "
                                f"{max_link_cap!r}"
                            )
                            sys.exit(1)
                    except ValueError as exc:
                        raise ValueError(f"{exc}") from exc

                    conn: Connection = Connection(zone_a, zone_b, max_link_cap)
                    zone_a.connections.append(conn)
                    zone_b.connections.append(conn)
                else:
                    error_print(
                        f"Error line {line_num}: Unrecognized line "
                        f"{lower_line!r}"
                    )
                    sys.exit(1)
            except Exception as exc:
                error_print(f"Error Line {line_num}: {exc}")
                sys.exit(1)

    if start_count != 1 or end_count != 1:
        error_print(
            "Error line: Exactly one start_hub and one end_hub required. "
            f"Found {start_count} start_hub, {end_count} end_hub."
        )
        sys.exit(1)
    return zones, nb_drones


def parse_metadata(
    metadata_str: str,
    line_num: int,
    line: str,
) -> Dict[str, str]:
    """Compatibility wrapper for the metadata parser.

    This is kept for the original public API used by the project.
    """
    from parser import Parser

    return Parser.parse_metadata(metadata_str, line_num, line)


def parse_zone_line(
    line: str,
    role: str,
    line_num: int,
) -> Zone | None:
    """Compatibility wrapper for the zone parser used by the Parser class."""
    from parser import Parser

    return Parser().parse_zone_line(line, role, line_num)
