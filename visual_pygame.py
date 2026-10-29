"""Animated pygame visualization for the Fly-in drone simulation.

Draws the zone graph, then plays the simulation back turn by turn with
drones smoothly interpolating along connections instead of jumping.
The backdrop is a rotating set of images loaded from an `assets/backgrounds`
folder (shipped with a handful of generated themes) -- drop extra .png/.jpg
files in that folder and they join the rotation automatically.

Controls:
    SPACE       pause / resume
    LEFT/RIGHT  step one turn back / forward (also works while paused)
    UP/DOWN     speed up / slow down playback
    B           cycle background image immediately
    R           restart the playback
    H           show / hide the help panel
    ESC / close quit
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

import pygame

from models import Zone, Drone, ZoneType

Color = Tuple[int, int, int]
Point = Tuple[float, float]

NAMED_COLORS: Dict[str, Color] = {
    "green": (76, 201, 141),
    "blue": (74, 144, 226),
    "yellow": (241, 196, 15),
    "orange": (243, 156, 18),
    "red": (231, 76, 60),
    "purple": (155, 89, 182),
    "cyan": (26, 188, 212),
    "none": (149, 165, 166),
}

ZONE_TYPE_RING: Dict[ZoneType, Color] = {
    ZoneType.NORMAL: (255, 255, 255),
    ZoneType.RESTRICTED: (155, 89, 182),
    ZoneType.PRIORITY: (26, 188, 212),
    ZoneType.BLOCKED: (60, 60, 60),
}

DRONE_PALETTE: List[Color] = [
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
KEYCAP_MIN_WIDTH = 26
KEYCAP_PADDING = 18  # horizontal padding, both sides combined

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

# Which keycap lights up when a given pygame key is pressed.
KEY_NAMES: Dict[int, str] = {
    pygame.K_SPACE: "SPACE",
    pygame.K_RIGHT: "\u2192",
    pygame.K_LEFT: "\u2190",
    pygame.K_UP: "\u2191",
    pygame.K_DOWN: "\u2193",
    pygame.K_b: "B",
    pygame.K_r: "R",
    pygame.K_h: "H",
    pygame.K_QUESTION: "H",
    pygame.K_F1: "H",
    pygame.K_ESCAPE: "ESC",
    pygame.K_q: "ESC",
}


# ---- Small helpers -----------------------------------------------------

def _ease_in_out(t: float) -> float:
    """Smooth-step easing used for drone interpolation between two ticks."""
    return t * t * (3.0 - 2.0 * t)


def _lerp(a: Point, b: Point, t: float) -> Point:
    """Linear interpolation between two points (t=0 -> a, t=1 -> b)."""
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _fill_alpha(screen: pygame.Surface, rect: pygame.Rect,
                color: Tuple[int, int, int, int]) -> None:
    """Fill `rect` with a semi-transparent RGBA colour."""
    surf = pygame.Surface(rect.size, pygame.SRCALPHA)
    surf.fill(color)
    screen.blit(surf, rect.topleft)


def _keycap_width(font: pygame.font.Font, label: str) -> int:
    """Width in pixels of a keycap showing `label`."""
    return int(max(font.size(label)[0] + KEYCAP_PADDING, KEYCAP_MIN_WIDTH))


@dataclass
class Fonts:
    """The four fonts used by the visual, bundled to shorten signatures."""

    normal: pygame.font.Font
    small: pygame.font.Font
    key: pygame.font.Font
    title: pygame.font.Font


@dataclass
class PlayerState:
    """Everything that changes while the replay runs."""

    tick: float = 0.0
    playing: bool = False
    started: bool = False
    speed: float = 1.0
    running: bool = True
    show_help: bool = True
    help_timer: float = 0.0
    bg_index: int = 0
    prev_bg_index: int = 0
    # Starts "infinite" so no crossfade plays on the very first frame.
    bg_timer: float = math.inf
    flashes: Dict[str, float] = field(default_factory=dict)


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
    CONTROL_BAR_HEIGHT = 54

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

    # ---- Background handling ---------------------------------------------

    def _load_backgrounds(self) -> List[pygame.Surface]:
        """Load every image in `bg_dir`, scaled to the window size.

        Falls back to a couple of procedurally-drawn gradients if the
        folder is missing or empty, so the visual still works out of the
        box even without any image assets present.
        """
        size = (self.WIDTH, self.HEIGHT)
        surfaces: List[pygame.Surface] = []
        if self.bg_dir.is_dir():
            for path in sorted(self.bg_dir.iterdir()):
                if path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                    continue
                try:
                    img = pygame.image.load(str(path)).convert()
                    surfaces.append(pygame.transform.smoothscale(img, size))
                except (pygame.error, OSError):
                    continue
        return surfaces or [
            self._fallback_gradient((20, 24, 40), (40, 44, 70)),
            self._fallback_gradient((10, 30, 30), (20, 60, 55)),
        ]

    def _fallback_gradient(
        self, top: Color, bottom: Color
    ) -> pygame.Surface:
        """Build a vertical-gradient surface as a background fallback."""
        surf = pygame.Surface((self.WIDTH, self.HEIGHT))
        for y in range(self.HEIGHT):
            t = y / self.HEIGHT
            color = tuple(
                int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
            pygame.draw.line(surf, color, (0, y), (self.WIDTH, y))
        return surf

    def _switch_background(self, state: PlayerState, new_index: int) -> None:
        """Start a crossfade from the current background to `new_index`."""
        state.prev_bg_index = state.bg_index
        state.bg_index = new_index
        state.bg_timer = 0.0

    def _draw_background(self, screen: pygame.Surface,
                         backgrounds: List[pygame.Surface],
                         state: PlayerState) -> None:
        """Blit the background, fading from the previous image if needed."""
        current = backgrounds[state.bg_index]
        progress = min(state.bg_timer / self.BG_CROSSFADE_SECONDS, 1.0)
        if progress >= 1.0:
            screen.blit(current, (0, 0))
            return
        screen.blit(backgrounds[state.prev_bg_index], (0, 0))
        current.set_alpha(int(255 * progress))
        screen.blit(current, (0, 0))
        current.set_alpha(255)

    # ---- Layout ----------------------------------------------------------

    def _compute_layout(self, zones: Dict[str, Zone]) -> Dict[str, Point]:
        """Map every zone's grid (x, y) to a screen position.

        The result fits the play area and preserves relative spacing.
        """
        xs = [z.x for z in zones.values()]
        ys = [z.y for z in zones.values()]
        min_x, min_y = min(xs), min(ys)
        span_x = max(max(xs) - min_x, 1)
        span_y = max(max(ys) - min_y, 1)

        playable_w = self.WIDTH - 2 * self.MARGIN
        playable_h = self.HEIGHT - 2 * self.MARGIN - 70  # leave room for HUD

        return {
            z.name: (
                self.MARGIN + (z.x - min_x) / span_x * playable_w,
                self.MARGIN + 40 + (z.y - min_y) / span_y * playable_h,
            )
            for z in zones.values()
        }

    def _resolve_drone_positions(
            self, drone: Drone,
            positions: Dict[str, Point]) -> List[Point]:
        """Turn a drone's zone path into a list of screen positions.

        Placeholder 'connection' zones (x == -1, used while a drone is
        mid-flight into a restricted zone) are resolved to the midpoint
        of the two real zones they sit between.
        """
        path = drone.path_to_follow
        resolved: List[Point] = []
        for i, zone in enumerate(path):
            if zone.x == -1:
                prev_real = next(
                    (p for p in reversed(path[:i]) if p.x != -1), None)
                next_real = next(
                    (p for p in path[i + 1:] if p.x != -1), None)
                if prev_real is not None and next_real is not None:
                    resolved.append(_lerp(positions[prev_real.name],
                                          positions[next_real.name], 0.5))
                    continue
            fallback = resolved[-1] if resolved else (0, 0)
            resolved.append(positions.get(zone.name, fallback))
        return resolved

    # ---- Scene drawing ---------------------------------------------------

    def _draw_graph(self, screen: pygame.Surface, zones: Dict[str, Zone],
                    positions: Dict[str, Point],
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
                multi = conn.max_link_capacity > 1
                pygame.draw.line(screen, (110, 116, 130), a, b,
                                 4 if multi else 2)
                if multi:
                    cap_label = font.render(
                        f"x{conn.max_link_capacity}", True, (200, 200, 210))
                    screen.blit(cap_label,
                                cap_label.get_rect(center=_lerp(a, b, 0.5)))

        for zone in zones.values():
            if zone.zone_type == ZoneType.BLOCKED:
                continue
            pos = positions[zone.name]
            label = font.render(zone.name, True, (20, 20, 24))
            radius = max(self.ZONE_RADIUS, label.get_width() // 2 + 8)
            if zone.role in ("start_hub", "end_hub"):
                radius += 6
            pygame.draw.circle(
                screen, NAMED_COLORS.get(zone.color, NAMED_COLORS["none"]),
                pos, radius)
            pygame.draw.circle(
                screen, ZONE_TYPE_RING[zone.zone_type], pos, radius, width=3)
            screen.blit(label, label.get_rect(center=pos))
            if zone.max_drones != math.inf:
                cap = font.render(
                    f"{int(zone.max_drones)} max", True, PANEL_TEXT)
                screen.blit(cap, cap.get_rect(
                    midtop=(pos[0], pos[1] + radius + 4)))

    def _draw_drones(
            self, screen: pygame.Surface,
            drone_tracks: List[Tuple[Drone, List[Point]]],
            tick: float, font: pygame.font.Font) -> int:
        """Draw every drone at its interpolated position for `tick`.

        Returns:
            The number of drones that have reached their destination.
        """
        delivered = 0
        total = max(len(drone_tracks), 1)
        for idx, (drone, track) in enumerate(drone_tracks):
            last = len(track) - 1
            index = min(int(tick), last)
            if index >= last:
                delivered += 1
                # Fan delivered drones out around the goal so they don't
                # all stack exactly on top of one another.
                angle = 2 * math.pi * idx / total
                ring = self.ZONE_RADIUS + 22
                pos = (track[last][0] + math.cos(angle) * ring,
                       track[last][1] + math.sin(angle) * ring)
            else:
                frac = _ease_in_out(min(max(tick - index, 0.0), 1.0))
                pos = _lerp(track[index], track[index + 1], frac)
            color = DRONE_PALETTE[(drone.drone_id - 1) % len(DRONE_PALETTE)]
            pygame.draw.circle(screen, (0, 0, 0), pos, self.DRONE_RADIUS + 2)
            pygame.draw.circle(screen, color, pos, self.DRONE_RADIUS)
            label = font.render(f"D{drone.drone_id}", True, (255, 255, 255))
            screen.blit(label, label.get_rect(
                center=(pos[0], pos[1] - self.DRONE_RADIUS - 10)))
        return delivered

    # ---- HUD drawing -----------------------------------------------------

    def _draw_keycap(self, screen: pygame.Surface, font: pygame.font.Font,
                     label: str, x: int, y: int, flash: float = 0.0) -> int:
        """Draw one keyboard key as a small raised cap and return its width.

        Args:
            screen: Surface to draw on.
            font: Font used for the key's letter.
            label: Text inside the cap, e.g. "SPACE" or an arrow glyph.
            x: Left edge of the cap.
            y: Top edge of the cap.
            flash: 0..1 highlight amount, used to briefly light up a key
                when the user actually presses it.

        Returns:
            The width in pixels the cap occupied, so callers can lay caps
            out left to right without measuring text themselves.
        """
        text = font.render(label, True, KEYCAP_LABEL)
        w = _keycap_width(font, label)
        h = text.get_height() + 10

        face = tuple(
            int(KEYCAP_FACE[i] + (KEYCAP_FLASH[i] - KEYCAP_FACE[i]) * flash)
            for i in range(3))

        pygame.draw.rect(screen, KEYCAP_SHADOW,
                         pygame.Rect(x, y + 3, w, h), border_radius=6)
        cap_rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(screen, face, cap_rect, border_radius=6)
        pygame.draw.rect(screen, KEYCAP_EDGE, cap_rect, width=2,
                         border_radius=6)
        screen.blit(text, text.get_rect(center=cap_rect.center))
        return w

    def _draw_control_bar(self, screen: pygame.Surface, fonts: Fonts,
                          flashes: Dict[str, float]) -> None:
        """Draw the always-visible control legend across the bottom.

        Entries are centred as a group and any that would overflow the
        window are dropped (the H help overlay still lists everything).
        """
        bar_h = self.CONTROL_BAR_HEIGHT
        gap_entries, gap_key_label, gap_caps = 26, 8, 4

        # Measure first so the whole row can be centred.
        entries = []
        for caps, desc in CONTROLS:
            caps_w = sum(_keycap_width(fonts.key, c) + gap_caps
                         for c in caps) - gap_caps
            entries.append((caps, desc,
                            caps_w + gap_key_label
                            + fonts.small.size(desc)[0]))

        def row_width() -> int:
            return int(
                sum(e[2] for e in entries)
                + gap_entries * (len(entries) - 1)
            )

        while row_width() > self.WIDTH - 40 and len(entries) > 1:
            entries.pop()

        top = self.HEIGHT - bar_h
        _fill_alpha(screen, pygame.Rect(0, top, self.WIDTH, bar_h),
                    (12, 13, 20, 225))
        pygame.draw.line(screen, (70, 74, 92), (0, top), (self.WIDTH, top), 2)

        x = (self.WIDTH - row_width()) // 2
        cap_y = top + 13
        for caps, desc, _ in entries:
            for cap in caps:
                x += self._draw_keycap(screen, fonts.key, cap, x, cap_y,
                                       flashes.get(cap, 0.0)) + gap_caps
            x += gap_key_label - gap_caps
            label = fonts.small.render(desc, True, PANEL_TEXT)
            screen.blit(label, label.get_rect(midleft=(x, cap_y + 14)))
            x += label.get_width() + gap_entries

    def _draw_help_overlay(self, screen: pygame.Surface,
                           fonts: Fonts) -> None:
        """Dim the scene and show the full control list in a centred panel.

        Toggled with H and shown automatically for the first few seconds
        so the controls are discovered without hunting for them.
        """
        _fill_alpha(screen, screen.get_rect(), (0, 0, 0, 165))

        row_h, panel_w = 44, 470
        panel_h = 118 + row_h * len(CONTROLS)
        panel = pygame.Rect((self.WIDTH - panel_w) // 2,
                            (self.HEIGHT - panel_h) // 2, panel_w, panel_h)
        _fill_alpha(screen, panel, (22, 24, 34, 245))
        pygame.draw.rect(screen, (90, 96, 120), panel, width=2,
                         border_radius=10)

        heading = fonts.title.render("Keyboard controls", True, PANEL_TEXT)
        screen.blit(heading, heading.get_rect(
            midtop=(panel.centerx, panel.top + 20)))

        y = panel.top + 66
        for caps, desc in CONTROLS:
            x = panel.left + 28
            for cap in caps:
                x += self._draw_keycap(screen, fonts.key, cap, x, y) + 5
            label = fonts.small.render(desc, True, PANEL_TEXT)
            screen.blit(label, label.get_rect(
                midleft=(panel.left + 190, y + 14)))
            y += row_h

        footer = fonts.small.render("Press H to close", True, PANEL_DIM)
        screen.blit(footer, footer.get_rect(
            midbottom=(panel.centerx, panel.bottom - 12)))

    def _draw_start_prompt(self, screen: pygame.Surface,
                           fonts: Fonts) -> None:
        """Draw the centred 'press SPACE to start' call to action."""
        label = fonts.title.render("Press", True, PANEL_TEXT)
        action = fonts.title.render("to start the replay", True, PANEL_TEXT)
        cap_w = _keycap_width(fonts.key, "SPACE")
        gap = 10
        total_w = label.get_width() + gap + cap_w + gap + action.get_width()

        box = pygame.Rect(0, 0, total_w + 56, 76)
        box.center = (self.WIDTH // 2, self.HEIGHT // 2)
        _fill_alpha(screen, box, (18, 20, 30, 225))
        pygame.draw.rect(screen, KEYCAP_FLASH, box, width=2, border_radius=10)

        x, cy = box.left + 28, box.centery
        screen.blit(label, label.get_rect(midleft=(x, cy)))
        x += label.get_width() + gap
        self._draw_keycap(screen, fonts.key, "SPACE", x, cy - 14, flash=1.0)
        x += cap_w + gap
        screen.blit(action, action.get_rect(midleft=(x, cy)))

    def _draw_hud(self, screen: pygame.Surface, fonts: Fonts,
                  state: PlayerState, max_turn: int,
                  delivered: int, total_drones: int) -> None:
        """Draw the top status bar, the control legend and the help panel."""
        _fill_alpha(screen, pygame.Rect(0, 0, self.WIDTH, 46), HUD_BG)

        if not state.started:
            status = "ready"
        else:
            status = "playing" if state.playing else "paused"
        title = fonts.normal.render(
            f"Turn {min(int(state.tick), max_turn)}/{max_turn}   "
            f"Delivered {delivered}/{total_drones}   "
            f"[{status}, x{state.speed:.1f}]", True, PANEL_TEXT)
        screen.blit(title, (16, 12))

        if delivered == total_drones and state.started:
            banner = fonts.normal.render(
                "All drones delivered!", True, (120, 240, 160))
            screen.blit(banner, banner.get_rect(
                center=(self.WIDTH // 2, 70)))

        self._draw_control_bar(screen, fonts, state.flashes)

        if state.show_help:
            self._draw_help_overlay(screen, fonts)
        elif not state.started:
            # Before the first SPACE, tell the user the replay is waiting
            # on them rather than leaving a frozen-looking scene.
            self._draw_start_prompt(screen, fonts)

    # ---- Input and state updates -----------------------------------------

    def _handle_key(self, key: int, state: PlayerState,
                    max_turn: int, bg_count: int) -> None:
        """Apply one key press to the playback state."""
        if key in KEY_NAMES:
            state.flashes[KEY_NAMES[key]] = 1.0

        if key in (pygame.K_ESCAPE, pygame.K_q):
            state.running = False
        elif key == pygame.K_SPACE:
            state.playing = not state.playing
            state.started = True
        elif key in (pygame.K_RIGHT, pygame.K_LEFT):
            step = 1 if key == pygame.K_RIGHT else -1
            state.tick = float(min(max(int(state.tick) + step, 0), max_turn))
            state.playing = False
            state.started = True
        elif key == pygame.K_UP:
            state.speed = min(state.speed * 1.5, 8.0)
        elif key == pygame.K_DOWN:
            state.speed = max(state.speed / 1.5, 0.15)
        elif key == pygame.K_b:
            self._switch_background(state, (state.bg_index + 1) % bg_count)
        elif key == pygame.K_r:
            state.tick = 0.0
            state.playing = True
            state.started = True
        elif key in (pygame.K_h, pygame.K_QUESTION, pygame.K_F1):
            state.show_help = not state.show_help
            state.help_timer = 0.0  # a manual toggle cancels the auto-close

    def _update(self, state: PlayerState, dt: float,
                max_turn: int, bg_count: int) -> None:
        """Advance flashes, help timer, playback and background rotation."""
        # Fade each key highlight back out shortly after it was hit.
        for cap in list(state.flashes):
            state.flashes[cap] -= dt / self.KEY_FLASH_SECONDS
            if state.flashes[cap] <= 0:
                del state.flashes[cap]

        # Close the auto-shown help panel once the user has had time to read.
        if state.help_timer > 0:
            state.help_timer -= dt
            if state.help_timer <= 0:
                state.show_help = False

        if state.playing and not state.show_help and state.tick < max_turn:
            state.tick = min(
                state.tick + dt * state.speed / self.seconds_per_turn,
                float(max_turn))
            if state.tick >= max_turn:
                state.playing = False

        # Auto-rotate the background every few turns, with a crossfade.
        if bg_count > 1:
            state.bg_timer += dt
            target = int(state.tick // self.BG_TURNS_PER_IMAGE) % bg_count
            if (target != state.bg_index
                    and state.bg_timer > self.BG_CROSSFADE_SECONDS):
                self._switch_background(state, target)

    # ---- Main loop -------------------------------------------------------

    def run_pygame_visual(self, zones: Dict[str, Zone], drones: List[Drone],
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

        fonts = Fonts(
            normal=pygame.font.SysFont("Verdana", 15, bold=True),
            small=pygame.font.SysFont("Verdana", 13),
            key=pygame.font.SysFont("Verdana", 13, bold=True),
            title=pygame.font.SysFont("Verdana", 20, bold=True),
        )

        backgrounds = self._load_backgrounds()
        positions = self._compute_layout(zones)
        drone_tracks = [
            (d, self._resolve_drone_positions(d, positions)) for d in drones]
        max_turn = max_len - 1

        # The replay waits for the user instead of running off on its own:
        # nothing moves until SPACE is pressed (or autoplay is enabled).
        # The help panel opens by itself so the controls are discovered.
        state = PlayerState(
            playing=self.autoplay, started=self.autoplay,
            help_timer=self.HELP_AUTOSHOW_SECONDS)
        while state.running:
            dt = clock.tick(60) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    state.running = False
                elif event.type == pygame.KEYDOWN:
                    self._handle_key(
                        event.key, state, max_turn, len(backgrounds))

            self._update(state, dt, max_turn, len(backgrounds))

            self._draw_background(screen, backgrounds, state)
            _fill_alpha(screen, screen.get_rect(), (0, 0, 0, 70))
            self._draw_graph(screen, zones, positions, fonts.small)
            delivered = self._draw_drones(
                screen, drone_tracks, state.tick, fonts.normal)
            self._draw_hud(
                screen, fonts, state, max_turn, delivered, len(drones))

            pygame.display.flip()

        pygame.quit()
