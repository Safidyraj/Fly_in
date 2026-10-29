"""Parsing utilities for map files."""

import sys
import re
from pygame import Color
from typing import Dict, Optional
from models import Zone, ZoneType
from terminal import error_print

from file_parser import file_parser as _file_parser_impl


class Parser:
    """Parses a full map file into its zones and drone count."""

    def file_parser(self, path: str) -> tuple[dict[str, Zone], int]:
        """Parse a map file (wrapper used by `main.py`).

        Args:
            path: Path to the map file to read.

        Returns:
            The parsed zones by name and the number of drones.
        """
        return _file_parser_impl(self, path)

    @staticmethod
    def parse_metadata(
        metadata_str: str,
        line_num: int,
        line: str
    ) -> Dict[str, str]:
        """Parse a bracketed metadata block into a key/value dictionary.

        Args:
            metadata_str: The raw "[key=value key2=value2]" text.

        Returns:
            A dict mapping each lowercase key to its lowercase value.
        """
        zone_key: list[str] = ["color", "max_drones", "zone"]
        # `line` is expected lowercased by callers
        is_conn: bool = line.startswith(("start_hub", "hub", "end_hub"))
        m_data: Dict[str, str] = {}
        strict_metadata = (
            r"^\[[ \t]*([a-zA-Z_]+[ \t]*=[ \t]*[a-zA-Z0-9_]+[ \t]*"
            r"([ \t]+[a-zA-Z_]+[ \t]*=[ \t]*[a-zA-Z0-9_]+[ \t]*)*)\]$"
        )
        if not re.fullmatch(strict_metadata, metadata_str):
            error_print(f"Error line {line_num}: Invalid metadata format.")
            sys.exit(1)
        clean_str = metadata_str.strip().replace("[", "").replace("]", "")
        pairs = re.findall(r"([a-zA-Z_]+)[ \t]*=[ \t]*([a-zA-Z0-9_]+)",
                           clean_str)
        for k, v in pairs:
            k_clean = k.lower()
            if is_conn and k_clean not in zone_key:
                error_print(
                    f"Error line {line_num}: {k!r} not in metadata key"
                )
                sys.exit(1)
            if not is_conn and k_clean != "max_link_capacity":
                error_print(
                    f"Error line {line_num}: Wrong metadata key {k_clean!r} in"
                    f" {metadata_str!r}"
                )
                sys.exit(1)
            # validation spécifique for color
            if k_clean == "color":
                val = v.lower()
                if val != "rainbow":
                    try:
                        Color(val)
                    except ValueError:
                        error_print(
                            f"Error line {line_num}: Invalid color {v!r}")
                        sys.exit(1)
                m_data[k_clean] = val
            else:
                m_data[k_clean] = v.lower()
        return m_data

    def parse_zone_line(
        self,
        line: str,
        role: str,
        line_num: int,
    ) -> Optional[Zone]:
        """Parse a single 'start_hub:' / 'end_hub:' / 'hub:' line into a Zone.

        Args:
            line: The raw line, already lowercased.
            May still contain its bracketed metadata block, if any — this
            method locates and strips it.
            role: The zone's role, taken from the line prefix.

        Returns:
            The parsed Zone, or None if the line doesn't carry enough fields.
        """
        try:
            m_data: Dict[str, str] = {}
            if "[" in line or "]" in line:
                if "[" not in line or "]" not in line:
                    error_print(
                        f"Error line {line_num}: malformed metadata block in"
                        f" '{line.strip()}'"
                    )
                    sys.exit(1)
                start_idx = line.find("[")
                end_idx = line.find("]")
                if start_idx > end_idx:
                    error_print(
                        f"Error line {line_num}: inverted"
                        " metadata brackets in"
                        f" '{line.strip()}'"
                    )
                    sys.exit(1)
                if line[start_idx - 1] in (" ", "\t"):
                    m_data = self.parse_metadata(
                        line[start_idx: end_idx + 1].strip(), line_num, line
                    )
                else:
                    error_print(f"Error line {line_num}: Invalid metadata")
                    sys.exit(1)
                line = line[:start_idx] + line[end_idx + 1:]
            content = line.split(":", 1)[1].strip()
            parts = content.split()
            if len(parts) != 3:
                error_print(
                    f"Error line {line_num}: zone line"
                    " missing required fields (name x y):"
                    f" {line.strip()!r}"
                )
                sys.exit(1)
            name = parts[0]
            if "-" in name or " " in name:
                error_print(
                    f"Error line {line_num}: Invalid zone name {name!r}"
                    " (dash and space forbidden)"
                )
                sys.exit(1)
            x = int(parts[1])
            y = int(parts[2])
            z_type_str = m_data.get("zone", "normal").lower()
            if z_type_str not in [t.value for t in ZoneType]:
                error_print(
                    f"Error line {line_num}: Invalid zone"
                    f" type {z_type_str!r}"
                )
                sys.exit(1)
            zone_type = ZoneType(z_type_str)
            color = m_data.get("color", "none").lower()
            try:
                if role in ["start_hub", "end_hub"]:
                    max_drones = float("inf")
                else:
                    max_drones = int(m_data.get("max_drones", 1))
                if max_drones <= 0:
                    error_print(
                        f"Error line {line_num}: max drones must"
                        " be a positive number"
                        f" got {max_drones!r}"
                    )
                    sys.exit(1)
            except ValueError as e:
                raise ValueError(f"{e}")
            return Zone(
                name=name,
                x=x,
                y=y,
                role=role,
                zone_type=zone_type,
                color=color,
                max_drones=max_drones,
            )
        except Exception as e:
            error_print(f"Parsing error on line [{line!r}]: {e}")
            sys.exit(1)
