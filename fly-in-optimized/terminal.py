"""Centralized terminal output for the Fly-in simulation.

Every piece of output the program produces (the required turn-by-turn
simulation log, the optional capacity report, informational diagnostics,
and error messages) is routed through this module so there is a single
place that owns how things get printed.
"""
from rich.panel import Panel
import time
from rich.console import Console


def print_turn(moves: list[str]) -> None:
    """Print one line of the mandatory simulation output.

    Per the spec, a turn line lists every drone movement for that turn,
    space-separated, using the exact 'D<ID>-<zone>' / 'D<ID>-<connection>'
    tokens. Drones that don't move that turn are simply omitted, so if
    `moves` is empty, nothing is printed for this turn.

    Args:
        moves: The movement tokens (e.g. ["D1-waypoint1", "D2-corridorA"])
            for a single simulation turn, already formatted.
    """
    if not moves:
        return
    print(" ".join(moves))


def print_turn_count(turn: int) -> None:
    """Print a dim, non-intrusive 'Total turns: N' diagnostic to stderr.

    Args:
        turn: The current turn number reached by the simulation.
    """
    console = Console(stderr=True)
    console.print(f"[dim]Total turns: {turn}[/]")


def print_capacity_line(message: str) -> None:
    """Print one line of the optional -- report to stdout.

    Args:
        message: The already-formatted capacity/connection usage line.
    """
    console = Console()
    console.print(message)


def error_print(error: str) -> None:
    """Affiche une erreur formatée sur la sortie d'erreur standard."""
    console = Console(stderr=True)
    with console.status("[bold green] Loading...", spinner="dots12"):
        time.sleep(0.4)
    panel = Panel(
        f"[bold purple]{error}", expand=False, border_style="purple",
        title="[bold red]>>>> Failure <<<<[/]"
    )
    console.print(panel)
