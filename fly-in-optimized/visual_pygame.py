"""Animated pygame visualization for the Fly-in drone simulation.

Draws the zone graph, then plays the simulation back turn by turn with
drones smoothly interpolating along connections instead of jumping.
The backdrop is a rotating set of images loaded from an `assets/backgrounds`
folder (shipped with a handful of generated themes) — drop extra .png/.jpg
files in that folder and they join the rotation automatically.

Controls:
    SPACE       pause / resume
    LEFT/RIGHT  step one turn back / forward (also works while paused)
    UP/DOWN     speed up / slow down playback
    B           cycle background image immediately
    R           restart the playback
    ESC / close quit
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import pygame

from models import Zone, Drone, ZoneType


# ---- Palette ---------------------------------------------------------

NAMED_COLORS: Dict[str, Tuple[int, int, int]] = {
    "green": (76, 201, 141),
    "blue": (74, 144, 226),
    "yellow": (241, 196, 15),
    "orange": (243, 156, 18),
    "red": (231, 76, 60),
    "purple": (155, 89, 182),
    "cyan": (26, 188, 212),
    "none": (149, 165, 166),
}

ZONE_TYPE_RING: Dict[ZoneType, Tuple[int, int, int]] = {
    ZoneType.NORMAL: (255, 255, 255),
    ZoneType.RESTRICTED: (155, 89, 182),
    ZoneType.PRIORITY: (26, 188, 212),
    ZoneType.BLOCKED: (60, 60, 60),
}

DRONE_PALETTE: List[Tuple[int, int, int]] = [
    (255, 99, 132), (54, 162, 235), (255, 206, 86), (75, 192, 192),
    (153, 102, 255), (255, 159, 64), (46, 204, 113), (231, 76, 60),
    (52, 152, 219), (241, 196, 15), (26, 188, 212), (230, 126, 34),
]

HUD_BG = (18, 18, 24, 190)
PANEL_TEXT = (235, 235, 240)
PANEL_DIM = (170, 170, 180)

# Keycap styling for the on-screen control legend.
KEYCAP_FACE = (245, 246, 250)
KEYCAP_EDGE = (120, 124, 140)
KEYCAP_SHADOW = (30, 32, 42)
KEYCAP_LABEL = (24, 26, 34)
KEYCAP_FLASH = (120, 240, 170)

# (keycap labels, description). Used for both the bottom bar and the
# full help overlay so the two can never drift apart.
CONTROLS: List[Tuple[List[str], str]] = [
    (["SPACE"], "Pause / Play"),
    (["\u2190", "\u2192"], "Step one turn"),
    (["\u2191", "\u2193"], "Speed up / down"),
    (["B"], "Change background"),
    (["R"], "Restart"),
    (["H"], "Help"),
    (["ESC"], "Quit"),
]


def _ease_in_out(t: float) -> float:
    """Smooth-step easing used for drone interpolation between two ticks."""
    return t * t * (3.0 - 2.0 * t)


def _lerp(a: Tuple[float, float], b: Tuple[float, float], t: float) -> Tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


class VisualPygame:
    """Loads a solved simulation and plays it back as an animated scene."""

    WIDTH, HEIGHT = 1280, 800
    MARGIN = 110
    ZONE_RADIUS = 26
    DRONE_RADIUS = 9
    SECONDS_PER_TURN_DEFAULT = 1.1
    BG_CROSSFADE_SECONDS = 0.9
    BG_TURNS_PER_IMAGE = 6
    HELP_AUTOSHOW_SECONDS = 4.0
    KEY_FLASH_SECONDS = 0.35

    def __init__(self, bg_dir: str | None = None,
                 seconds_per_turn: float | None = None,
                 autoplay: bool = False) -> None:
        """Set up asset paths and timing before the window is opened.

        Args:
            bg_dir: Folder of background images to rotate through. Defaults
                to the `assets/backgrounds` folder shipped alongside this
                file; any .png/.jpg/.jpeg dropped in there is picked up.
            seconds_per_turn: How long, in seconds, one simulation turn's
                animation takes to play at normal speed.
            autoplay: When False (the default) the replay opens paused on
                turn 0 and waits for the user to press SPACE. Pass True to
                have it start playing as soon as the window opens.
        """
        self.bg_dir = Path(bg_dir) if bg_dir else (
            Path(__file__).resolve().parent / "assets" / "backgrounds")
        self.seconds_per_turn = (
            seconds_per_turn or self.SECONDS_PER_TURN_DEFAULT)
        self.autoplay = autoplay

    # ---- Background handling ------------------------------------------

    def _load_backgrounds(self) -> List[pygame.Surface]:
        """Load every image in `bg_dir`, scaled to the window size.

        Falls back to a couple of procedurally-drawn gradients if the
        folder is missing or empty, so the visual still works out of the
        box even without any image assets present.
        """
        surfaces: List[pygame.Surface] = []
        if self.bg_dir.is_dir():
            for path in sorted(self.bg_dir.iterdir()):
                if path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                    continue
                try:
                    img = pygame.image.load(str(path)).convert()
                    img = pygame.transform.smoothscale(
                        img, (self.WIDTH, self.HEIGHT))
                    surfaces.append(img)
                except Exception:
                    continue
        if not surfaces:
            surfaces = [self._fallback_gradient((20, 24, 40), (40, 44, 70)),
                        self._fallback_gradient((10, 30, 30), (20, 60, 55))]
        return surfaces

    def _fallback_gradient(
            self, top: Tuple[int, int, int],
            bottom: Tuple[int, int, int]) -> pygame.Surface:
        """Build a simple vertical-gradient surface as a background fallback."""
        surf = pygame.Surface((self.WIDTH, self.HEIGHT))
        for y in range(self.HEIGHT):
            t = y / self.HEIGHT
            color = tuple(
                int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
            pygame.draw.line(surf, color, (0, y), (self.WIDTH, y))
        return surf

    # ---- Layout

    def _compute_layout(
            self, zones: Dict[str, Zone]) -> Dict[str, Tuple[float, float]]:
        """Map every zone's grid (x, y) to a screen position that fits the
        play area, preserving relative spacing and flipping y so that
        larger map rows read top-to-bottom on screen."""
        xs = [z.x for z in zones.values()]
        ys = [z.y for z in zones.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(max_x - min_x, 1)
        span_y = max(max_y - min_y, 1)

        playable_w = self.WIDTH - 2 * self.MARGIN
        playable_h = self.HEIGHT - 2 * self.MARGIN - 70  # leave room for HUD

        positions: Dict[str, Tuple[float, float]] = {}
        for z in zones.values():
            nx = (z.x - min_x) / span_x if span_x else 0.5
            ny = (z.y - min_y) / span_y if span_y else 0.5
            screen_x = self.MARGIN + nx * playable_w
            screen_y = self.MARGIN + 40 + ny * playable_h
            positions[z.name] = (screen_x, screen_y)
        return positions

    def _resolve_drone_positions(
        self, drone: Drone,
            positions: Dict[str, Tuple[float, float]]
    ) -> List[Tuple[float, float]]:
        """Turn a drone's zone-by-zone path into a parallel list of screen
        positions, resolving the placeholder 'connection' zones (used while
        a drone is mid-flight into a restricted zone) to the midpoint of
        the two real zones they sit between."""
        path = drone.path_to_follow
        resolved: List[Tuple[float, float]] = []
        for i, zone in enumerate(path):
            if zone.x == -1:
                prev_real = next(
                    (p for p in reversed(path[:i]) if p.x != -1), None)
                next_real = next(
                    (p for p in path[i + 1:] if p.x != -1), None)
                if prev_real is not None and next_real is not None:
                    resolved.append(_lerp(
                        positions[prev_real.name],
                        positions[next_real.name], 0.5))
                    continue
            resolved.append(positions.get(zone.name, resolved[-1] if resolved else (0, 0)))
        return resolved

    # ---- Drawing ----------------------------------------------------------

    def _draw_graph(
        self, screen: pygame.Surface, zones: Dict[str, Zone],
        positions: Dict[str, Tuple[float, float]],
            font: pygame.font.Font) -> None:
        """Draw every connection then every zone node with its label."""
        drawn_pairs = set()
        for zone in zones.values():
            for conn in zone.connections:
                pair = tuple(sorted([conn.zone_a.name, conn.zone_b.name]))
                if pair in drawn_pairs:
                    continue
                drawn_pairs.add(pair)
                a, b = positions[conn.zone_a.name], positions[conn.zone_b.name]
                width = 2 if conn.max_link_capacity <= 1 else 4
                pygame.draw.line(screen, (110, 116, 130), a, b, width)
                if conn.max_link_capacity > 1:
                    mid = _lerp(a, b, 0.5)
                    cap_label = font.render(
                        f"x{conn.max_link_capacity}", True, (200, 200, 210))
                    screen.blit(cap_label, cap_label.get_rect(center=mid))

        for zone in zones.values():
            if zone.zone_type == ZoneType.BLOCKED:
                continue
            pos = positions[zone.name]
            fill = NAMED_COLORS.get(zone.color, NAMED_COLORS["none"])
            ring = ZONE_TYPE_RING[zone.zone_type]
            label = font.render(zone.name, True, (20, 20, 24))
            radius = max(self.ZONE_RADIUS, label.get_width() // 2 + 8)
            if zone.role in ("start_hub", "end_hub"):
                radius += 6
            pygame.draw.circle(screen, fill, pos, radius)
            pygame.draw.circle(screen, ring, pos, radius, width=3)
            screen.blit(label, label.get_rect(center=pos))
            if zone.max_drones != float("inf"):
                cap = font.render(
                    f"{int(zone.max_drones)} max", True, (235, 235, 240))
                screen.blit(cap, cap.get_rect(
                    midtop=(pos[0], pos[1] + radius + 4)))

    def _draw_drones(
        self, screen: pygame.Surface, drone_tracks: List[
            Tuple[Drone, List[Tuple[float, float]]]],
        tick: float, font: pygame.font.Font) -> Tuple[int, int]:
        """Draw every drone at its interpolated position for `tick`.

        Returns:
            (delivered_count, in_flight_count) for the HUD.
        """
        delivered = 0
        in_flight = 0
        total = len(drone_tracks)
        for idx, (drone, track) in enumerate(drone_tracks):
            last_index = len(track) - 1
            index = min(int(tick), last_index)
            if index >= last_index:
                delivered += 1
                # Fan delivered drones out around the goal so they don't
                # all stack exactly on top of one another.
                angle = 2 * math.pi * idx / max(total, 1)
                ring = self.ZONE_RADIUS + 22
                base = track[last_index]
                pos = (base[0] + math.cos(angle) * ring,
                       base[1] + math.sin(angle) * ring)
            else:
                in_flight += 1
                frac = _ease_in_out(min(max(tick - index, 0.0), 1.0))
                pos = _lerp(track[index], track[index + 1], frac)
            color = DRONE_PALETTE[(drone.drone_id - 1) % len(DRONE_PALETTE)]
            pygame.draw.circle(screen, (0, 0, 0), pos, self.DRONE_RADIUS + 2)
            pygame.draw.circle(screen, color, pos, self.DRONE_RADIUS)
            label = font.render(f"D{drone.drone_id}", True, (255, 255, 255))
            screen.blit(label, label.get_rect(
                center=(pos[0], pos[1] - self.DRONE_RADIUS - 10)))
        return delivered, in_flight

    def _draw_keycap(
        self, screen: pygame.Surface, font: pygame.font.Font, label: str,
            x: int, y: int, flash: float = 0.0) -> int:
        """Draw one keyboard key as a small raised cap and return its width.

        Args:
            screen: Surface to draw on.
            font: Font used for the key's letter.
            label: Text inside the cap, e.g. "SPACE" or the arrow glyphs.
            x: Left edge of the cap.
            y: Top edge of the cap.
            flash: 0..1 highlight amount, used to briefly light up a key
                when the user actually presses it.

        Returns:
            The width in pixels the cap occupied, so callers can lay caps
            out left to right without measuring text themselves.
        """
        text = font.render(label, True, KEYCAP_LABEL)
        pad_x = 9
        w = max(text.get_width() + pad_x * 2, 26)
        h = text.get_height() + 10

        face = KEYCAP_FACE
        if flash > 0:
            face = tuple(
                int(KEYCAP_FACE[i] + (KEYCAP_FLASH[i] - KEYCAP_FACE[i]) * flash)
                for i in range(3))

        shadow_rect = pygame.Rect(x, y + 3, w, h)
        pygame.draw.rect(screen, KEYCAP_SHADOW, shadow_rect, border_radius=6)
        cap_rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(screen, face, cap_rect, border_radius=6)
        pygame.draw.rect(screen, KEYCAP_EDGE, cap_rect, width=2,
                         border_radius=6)
        screen.blit(text, text.get_rect(center=cap_rect.center))
        return w

    def _draw_control_bar(
        self, screen: pygame.Surface, key_font: pygame.font.Font,
            label_font: pygame.font.Font, flashes: Dict[str, float]) -> None:
        """Draw the always-visible control legend across the bottom.

        Each entry renders as real keycaps followed by what the key does,
        which reads far better at a glance than a run-on line of text.
        Entries are centred as a group and any that would overflow the
        window are dropped (the H help overlay still lists everything).
        """
        bar_h = 54
        gap_between_entries = 26
        gap_key_label = 8

        # Measure first so the whole row can be centred.
        entries = []
        total_w = 0
        for caps, desc in CONTROLS:
            cap_w = sum(
                max(key_font.size(c)[0] + 18, 26) + 4 for c in caps) - 4
            desc_w = label_font.size(desc)[0]
            entry_w = cap_w + gap_key_label + desc_w
            entries.append((caps, desc, entry_w))
            total_w += entry_w + gap_between_entries
        total_w -= gap_between_entries

        while total_w > self.WIDTH - 40 and len(entries) > 1:
            removed = entries.pop()
            total_w -= removed[2] + gap_between_entries

        bar = pygame.Surface((self.WIDTH, bar_h), pygame.SRCALPHA)
        bar.fill((12, 13, 20, 225))
        screen.blit(bar, (0, self.HEIGHT - bar_h))
        pygame.draw.line(screen, (70, 74, 92), (0, self.HEIGHT - bar_h),
                         (self.WIDTH, self.HEIGHT - bar_h), 2)

        x = (self.WIDTH - total_w) // 2
        cap_y = self.HEIGHT - bar_h + 13
        for caps, desc, entry_w in entries:
            for cap in caps:
                w = self._draw_keycap(
                    screen, key_font, cap, x, cap_y, flashes.get(cap, 0.0))
                x += w + 4
            x += gap_key_label - 4
            label = label_font.render(desc, True, PANEL_TEXT)
            screen.blit(label, label.get_rect(
                midleft=(x, cap_y + 14)))
            x += label_font.size(desc)[0] + gap_between_entries

    def _draw_help_overlay(
        self, screen: pygame.Surface, title_font: pygame.font.Font,
            key_font: pygame.font.Font, label_font: pygame.font.Font) -> None:
        """Dim the scene and show the full control list in a centred panel.

        Toggled with H (or ?) and shown automatically for the first few
        seconds so the controls are discovered without hunting for them.
        """
        dim = pygame.Surface((self.WIDTH, self.HEIGHT), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 165))
        screen.blit(dim, (0, 0))

        row_h = 44
        panel_w = 470
        panel_h = 118 + row_h * len(CONTROLS)
        px = (self.WIDTH - panel_w) // 2
        py = (self.HEIGHT - panel_h) // 2

        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((22, 24, 34, 245))
        screen.blit(panel, (px, py))
        pygame.draw.rect(screen, (90, 96, 120),
                         pygame.Rect(px, py, panel_w, panel_h),
                         width=2, border_radius=10)

        heading = title_font.render("Keyboard controls", True, PANEL_TEXT)
        screen.blit(heading, heading.get_rect(
            midtop=(px + panel_w // 2, py + 20)))

        y = py + 66
        for caps, desc in CONTROLS:
            x = px + 28
            for cap in caps:
                x += self._draw_keycap(screen, key_font, cap, x, y) + 5
            label = label_font.render(desc, True, PANEL_TEXT)
            screen.blit(label, label.get_rect(midleft=(px + 190, y + 14)))
            y += row_h

        footer = label_font.render(
            "Press H to close", True, PANEL_DIM)
        screen.blit(footer, footer.get_rect(
            midbottom=(px + panel_w // 2, py + panel_h - 12)))

    def _draw_hud(
        self, screen: pygame.Surface, font: pygame.font.Font,
        small_font: pygame.font.Font, key_font: pygame.font.Font,
        turn: int, max_turn: int, delivered: int, total_drones: int,
        playing: bool, speed: float, flashes: Dict[str, float],
        show_help: bool, title_font: pygame.font.Font,
            started: bool = True) -> None:
        """Draw the top status bar, the control legend and the help panel."""
        bar = pygame.Surface((self.WIDTH, 46), pygame.SRCALPHA)
        bar.fill(HUD_BG)
        screen.blit(bar, (0, 0))
        status = "playing" if playing else "paused"
        if not started:
            status = "ready"
        title = font.render(
            f"Turn {turn}/{max_turn}   "
            f"Delivered {delivered}/{total_drones}   "
            f"[{status}, x{speed:.1f}]", True, PANEL_TEXT)
        screen.blit(title, (16, 12))

        if delivered == total_drones and started:
            banner = font.render(
                "All drones delivered!", True, (120, 240, 160))
            screen.blit(banner, banner.get_rect(
                center=(self.WIDTH // 2, 70)))

        self._draw_control_bar(screen, key_font, small_font, flashes)

        # Before the first SPACE, tell the user the replay is waiting on
        # them rather than leaving a frozen-looking scene with no reason.
        if not started and not show_help:
            self._draw_start_prompt(screen, title_font, key_font)

        if show_help:
            self._draw_help_overlay(
                screen, title_font, key_font, small_font)

    def _draw_start_prompt(
        self, screen: pygame.Surface, title_font: pygame.font.Font,
            key_font: pygame.font.Font) -> None:
        """Draw the centred 'press SPACE to start' call to action."""
        label = title_font.render("Press", True, PANEL_TEXT)
        action = title_font.render("to start the replay", True, PANEL_TEXT)
        cap_w = max(key_font.size("SPACE")[0] + 18, 26)
        gap = 10
        total_w = label.get_width() + gap + cap_w + gap + action.get_width()

        box_w, box_h = total_w + 56, 76
        bx = (self.WIDTH - box_w) // 2
        by = self.HEIGHT // 2 - box_h // 2

        box = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        box.fill((18, 20, 30, 225))
        screen.blit(box, (bx, by))
        pygame.draw.rect(screen, (120, 240, 170),
                         pygame.Rect(bx, by, box_w, box_h),
                         width=2, border_radius=10)

        x = bx + 28
        cy = by + box_h // 2
        screen.blit(label, label.get_rect(midleft=(x, cy)))
        x += label.get_width() + gap
        self._draw_keycap(screen, key_font, "SPACE", x, cy - 14, flash=1.0)
        x += cap_w + gap
        screen.blit(action, action.get_rect(midleft=(x, cy)))

    # ---- Main loop ----------------------------------------------------

    def run_pygame_visual(
        self, zones: Dict[str, Zone], drones: List[Drone],
            max_len: int) -> None:
        """Open a window and play the solved simulation back frame by frame.

        Args:
            zones: All zones on the map, indexed by name (for the graph).
            drones: Every drone with its full tick-by-tick timeline.
            max_len: Length of the longest drone timeline in the batch.
        """
        pygame.init()
        pygame.display.set_caption("Fly-in Drones \u2014 simulation replay")
        screen = pygame.display.set_mode((self.WIDTH, self.HEIGHT))
        clock = pygame.time.Clock()

        font = pygame.font.SysFont("Verdana", 15, bold=True)
        small_font = pygame.font.SysFont("Verdana", 13)
        key_font = pygame.font.SysFont("Verdana", 13, bold=True)
        title_font = pygame.font.SysFont("Verdana", 20, bold=True)

        backgrounds = self._load_backgrounds()
        bg_index = 0
        bg_timer = 0.0

        positions = self._compute_layout(zones)
        drone_tracks = [
            (d, self._resolve_drone_positions(d, positions)) for d in drones]

        max_turn = max_len - 1
        tick = 0.0
        # The replay waits for the user instead of running off on its own:
        # nothing moves until SPACE is pressed (or --autoplay was passed).
        playing = self.autoplay
        started = self.autoplay
        speed = 1.0

        # Control-legend state: which caps are lit up right now, and
        # whether the full help panel is showing. The panel opens by
        # itself at launch so the controls are seen without being sought.
        flashes: Dict[str, float] = {}
        show_help = True
        help_auto_timer = self.HELP_AUTOSHOW_SECONDS

        running = True
        while running:
            dt = clock.tick(60) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        running = False
                    elif event.key == pygame.K_SPACE:
                        playing = not playing
                        started = True
                        flashes["SPACE"] = 1.0
                    elif event.key == pygame.K_RIGHT:
                        tick = min(float(int(tick) + 1), float(max_turn))
                        playing = False
                        started = True
                        flashes["\u2192"] = 1.0
                    elif event.key == pygame.K_LEFT:
                        tick = max(float(int(tick) - 1), 0.0)
                        playing = False
                        started = True
                        flashes["\u2190"] = 1.0
                    elif event.key == pygame.K_UP:
                        speed = min(speed * 1.5, 8.0)
                        flashes["\u2191"] = 1.0
                    elif event.key == pygame.K_DOWN:
                        speed = max(speed / 1.5, 0.15)
                        flashes["\u2193"] = 1.0
                    elif event.key == pygame.K_b:
                        bg_index = (bg_index + 1) % len(backgrounds)
                        bg_timer = 0.0
                        flashes["B"] = 1.0
                    elif event.key == pygame.K_r:
                        tick = 0.0
                        playing = True
                        started = True
                        flashes["R"] = 1.0
                    elif event.key in (pygame.K_h, pygame.K_QUESTION,
                                       pygame.K_F1):
                        show_help = not show_help
                        help_auto_timer = 0.0
                        flashes["H"] = 1.0

            # Fade each key highlight back out shortly after it was hit.
            for cap in list(flashes):
                flashes[cap] -= dt / self.KEY_FLASH_SECONDS
                if flashes[cap] <= 0:
                    del flashes[cap]

            # Close the auto-shown help panel once the user has had a
            # moment to read it (any manual H toggle cancels the timer).
            if help_auto_timer > 0:
                help_auto_timer -= dt
                if help_auto_timer <= 0:
                    show_help = False

            if playing and not show_help and tick < max_turn:
                tick = min(tick + dt * speed / self.seconds_per_turn,
                            float(max_turn))
                if tick >= max_turn:
                    playing = False

            # Auto-rotate the background every few turns, with a crossfade.
            if len(backgrounds) > 1:
                bg_timer += dt
                turns_elapsed = tick // self.BG_TURNS_PER_IMAGE
                target_index = int(turns_elapsed) % len(backgrounds)
                if target_index != bg_index and bg_timer > self.BG_CROSSFADE_SECONDS:
                    bg_index = target_index
                    bg_timer = 0.0

            current_bg = backgrounds[bg_index % len(backgrounds)]
            screen.blit(current_bg, (0, 0))
            if len(backgrounds) > 1 and bg_timer < self.BG_CROSSFADE_SECONDS:
                next_bg = backgrounds[(bg_index + 1) % len(backgrounds)]
                alpha = int(255 * (1 - bg_timer / self.BG_CROSSFADE_SECONDS))
                if alpha > 0:
                    faded = next_bg.copy()
                    faded.set_alpha(alpha)

            overlay = pygame.Surface((self.WIDTH, self.HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 70))
            screen.blit(overlay, (0, 0))

            self._draw_graph(screen, zones, positions, small_font)
            delivered, _ = self._draw_drones(screen, drone_tracks, tick, font)
            self._draw_hud(
                screen, font, small_font, key_font,
                min(int(tick), max_turn), max_turn,
                delivered, len(drones), playing, speed,
                flashes, show_help, title_font, started)

            pygame.display.flip()

        pygame.quit()
