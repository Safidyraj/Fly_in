*This project has been created as part of the 42 curriculum by safiraja* 

# Fly-in

## Description

Fly-in is a drone routing simulator designed to schedule multiple drones through a network of zones while respecting both zone capacity and connection capacity constraints. The program reads a map specification, builds a graph of hubs and connections, computes safe routes, and outputs either a textual turn-by-turn log or a graphical replay.

The core challenge is to assign every drone a feasible path from a start hub to an end hub without causing collisions, bottlenecks, or illegal occupancy. Each zone has a type such as normal, priority, restricted, or blocked, and each zone or link can accept only a limited number of drones at the same time. This turns the problem into a capacity-aware pathfinding task rather than a simple shortest-path problem.

The project was built around a time-expanded routing strategy: instead of only searching the static graph, the algorithm searches through space-time states of the form (zone, tick). This makes it possible to wait in place, plan around congestion, and preserve turn-by-turn feasibility when multiple drones are scheduled sequentially.

### Project goals

- Route an arbitrary number of drones from a start hub to an end hub.
- Respect per-zone and per-connection capacities.
- Prefer efficient, low-turn routes while still handling congestion.
- Support both terminal output and visual playback for debugging and demonstration.
- Accept custom map files created for easy, medium, hard, and challenge levels.

## Instructions

### Requirements

- Python 3.13+
- Pygame
- Rich
- Colorama

The project includes a local virtual environment under `flyin/`, and the provided `Makefile` installs the required dependencies automatically.

### Setup

From the project root:

```bash
make install
```

This creates a virtual environment named `flyin` and installs the Python dependencies used by the simulator.

### Run the simulator

Run a predefined example map:

```bash
make run
```

Run the same scenario with the graphical visualizer:

```bash
make run-visual
```

You can also invoke the program directly:

```bash
./flyin/bin/python main.py maps/easy/01_linear_path.txt
./flyin/bin/python main.py maps/easy/01_linear_path.txt --visual pygame
```

### Useful options

- `--visual text` or `--visual pygame`
- `--capacity-info` to print zone/connection usage statistics per turn
- `--bg-dir <folder>` to customize the background images used in the pygame view
- `--speed <seconds>` to control animation speed
- `--autoplay` to start the replay immediately

### Map file format

Maps are plain text files. A simple example looks like this:

```text
nb_drones: 2

start_hub: start 0 0 [color=green]
hub: waypoint1 1 0 [color=blue]
hub: waypoint2 2 0 [color=blue]
end_hub: goal 3 0 [color=red]

connection: start-waypoint1
connection: waypoint1-waypoint2
connection: waypoint2-goal
```

Zoning and connection metadata can include properties such as color, max capacity, and zone type. The parser validates these values before routing begins.

## Algorithm and implementation strategy

### Core idea

This project is not a plain static graph shortest-path solver. The main challenge is congestion management under simultaneous drone traffic. A drone cannot simply choose the shortest path in a static graph because that path may no longer be legal after earlier drones have reserved capacity.

To solve this, the project uses a capacity-aware, time-expanded search based on the A* family of algorithms. The planner represents each possible state as:

- current zone
- current simulation tick

This makes it possible to consider waiting in place, moving through different zone types, and avoiding congested connections in time rather than only in space.

### Why a time-expanded search

Each zone and connection can have a maximum number of drones allowed at any given simulation tick. A route that looks valid on the static map may fail because a connection or zone is already occupied at the moment the drone wants to use it.

The implementation therefore stores reservations in shared data structures:

- `agenda[(zone_name, tick)] = [drone_ids]`
- `conn_agenda[(zone_a, zone_b, tick)] = [drone_ids]`

The pathfinder checks these reservation tables before allowing a drone to wait or move. If the next step is full, the search may wait one or more turns, or it may explore another feasible branch of the graph.

### Zone types and costs

The simulation models multiple movement costs:

- normal: 1 turn
- priority: 1 turn, but slightly preferred in tie-breaking
- restricted: 2 turns
- blocked: never traversable

This design encourages realistic route planning and strategic use of priority routes when they do not create congestion.

### Sequential planning

The algorithm routes drones one at a time, in order. After each drone receives a valid timed path, that path is booked into the global reservations. This is the classic prioritized planning strategy commonly used in multi-agent pathfinding. It ensures that each new drone sees the reservations created by the earlier drones and avoids collisions.

### Heuristic and efficiency

The project uses a heuristic distance map computed with a static backward Dijkstra pass from the target node. This gives a lower-bound estimate for the remaining travel cost, which keeps the search focused and efficient even for larger maps.

The implementation also includes safety guards such as a maximum search horizon to avoid infinite exploration on unsolvable or malformed maps.

## Visual representation

The graphical output uses Pygame to animate the drone simulation turn by turn. It is designed to make the behavior easy to understand for both debugging and presentation.

### Features

- The graph is drawn as nodes and links on a clean, scalable map layout.
- Each zone type has a distinct visual identity:
  - normal zones are neutral
  - restricted zones use a purple highlight
  - priority zones use a cyan highlight
  - blocked zones are rendered as dark obstacles
- Drone paths are interpolated smoothly instead of jumping instantly between cells.
- Backgrounds rotate through a set of included images or fallback generated gradients.
- A HUD shows the current turn, active drones, and playback controls.
- Keyboard controls allow users to pause, resume, step one turn at a time, change speed, restart, and cycle backgrounds.

### User experience enhancement

The visual mode transforms a purely algorithmic task into an understandable animation. It helps users verify:

- whether drones are taking valid routes,
- whether blocks and bottlenecks are being avoided,
- whether priorities are being used sensibly,
- whether the final application is producing a clean schedule.

This is especially useful when developing on maps with many drones and complex intersections.

## Example input and expected output

### Sample map

```text
# Easy Level 1: Simple linear path
nb_drones: 2

start_hub: start 0 0 [color=green]
hub: waypoint1 1 0 [color=blue]
hub: waypoint2 2 0 [color=blue]
end_hub: goal 3 0 [color=red]

connection: start-waypoint1
connection: waypoint1-waypoint2
connection: waypoint2-goal
```

### Command

```bash
./flyin/bin/python main.py maps/easy/01_linear_path.txt
```

### Output

```text
Total turns: 4
D1-waypoint1
D1-waypoint2 D2-waypoint1
D1-goal D2-waypoint2
D2-goal
```

This output shows the scheduled progression over time. At each turn, the simulator reports which drones move to which zone, preserving the timing constraints and ensuring that no capacity limits are exceeded.

## Resources

### References

- A* search algorithm: classic pathfinding foundations and heuristic planning
- Graph theory and shortest-path topics in computer science
- Multi-agent pathfinding and reservation-based scheduling techniques
- Pygame documentation for animation and user interface rendering

### Documentation and learning resources

- https://en.wikipedia.org/wiki/A*_search_algorithm
- https://www.redblobgames.com/pathfinding/a-star/introduction.html
- https://www.pygame.org/docs/
- General graph traversal and time-expanded planning references from algorithmic routing literature

### AI usage

AI tools were used to support the project in the following ways:

- drafting the project structure and clarifying the overall architecture,
- checking the logic behind the time-expanded pathfinding design,
- helping review route-planning edge cases and capacity constraints,
- assisting with README documentation and technical explanation,
- suggesting ways to structure the visualizer and improve readability of the code.

AI was not used to replace the core algorithm design or the final decision-making; it served as a development aid for reasoning, validation, and documentation.

## Repository structure

```text
fly-in-optimized/
├── algo.py
├── file_parser.py
├── main.py
├── Makefile
├── models.py
├── parser.py
├── terminal.py
├── validate_run.py
├── visual_pygame.py
├── README.md
├── maps/
│   ├── easy/
│   ├── medium/
│   ├── hard/
│   └── challenger/
└── assets/
    └── backgrounds/
```

## Summary

Fly-in combines efficient path planning, congestion-aware scheduling, and an interactive visual replay into a single project. It demonstrates how classical graph algorithms can be extended to real-time, capacity-limited routing problems and how a well-designed visualization can make algorithmic reasoning accessible to users and evaluators.
