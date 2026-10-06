"""Route the arrows of a project overview between its rows of blocks.

Every arrow that points down gets its own exit point along the bottom of
its source block, its own entry point along the top of its target, and
its own track (height) in each gap between rows, so no two arrows share
a line. An arrow that skips rows drops through the nearest vertical
corridor that is free of blocks in every row it passes; only when no
corridor nearby is free does it run beside the widest row. Gaps between
rows grow when they need more tracks. When a block has more arrows than
its edge can space apart, neighbouring arrows share a point and run
together as a bundle into (or out of) that block; arrows between other
blocks never share a line.

An arrow that points up (it closes an import cycle) is routed the same
way between the bottom of the upper block and the top of the lower one,
then reversed, so its tip enters the upper block from below.
"""

import bisect
from dataclasses import dataclass, field
import math

from flowblueprint.model import Diagram, Edge, Node

TRACK_GAP_FLOAT = 7.0
GAP_PAD_FLOAT = 14.0
LANE_GAP_FLOAT = 8.0
CLEARANCE_FLOAT = 10.0
PORT_SPREAD_FLOAT = 0.7
NUDGE_FLOAT = 5.0
MIN_PORT_GAP_FLOAT = 4.0


@dataclass
class Route:
    """One arrow between rows while it is being routed, upper end first.

    Args:
        edge: The arrow (its waypoints are set at the end).
        source: The upper block (the arrow's source, or its target when
            the arrow points up).
        target: The lower block.
        source_row: The upper block's row index.
        target_row: The lower block's row index.
        exit_x: Where the route meets the upper block's bottom edge.
        entry_x: Where it meets the lower block's top edge.
        lane_x: The corridor it runs through when it skips rows.
        tracks: Track index in each gap it crosses horizontally.
        upward: True when the arrow points up, from the lower block.
    """

    edge: Edge
    source: Node
    target: Node
    source_row: int
    target_row: int
    exit_x: float = 0.0
    entry_x: float = 0.0
    lane_x: float | None = None
    tracks: dict[int, int] = field(default_factory=dict)
    upward: bool = False


def find_centre_x_float(node: Node) -> float:
    """The horizontal centre of a block.

    Args:
        node: The block.

    Returns:
        Its centre x.
    """
    return node.x_px + node.width / 2


def collect_routes_list(diagram: Diagram, rows_list: list[list[Node]]
                        ) -> list[Route]:
    """Find the arrows between blocks in different rows.

    Args:
        diagram: The overview.
        rows_list: Block nodes per row, top to bottom.

    Returns:
        One Route per arrow, upper block first; arrows within one row
        are left to the renderers.
    """
    row_dict = {node.node_id: (row_int, node)
                for row_int, row_nodes in enumerate(rows_list)
                for node in row_nodes}
    routes_list = []
    for edge in diagram.edges:
        source_tuple = row_dict.get(edge.source_id)
        target_tuple = row_dict.get(edge.target_id)
        if not (source_tuple and target_tuple) or (
                source_tuple[0] == target_tuple[0]):
            continue
        upper_tuple, lower_tuple = sorted((source_tuple, target_tuple),
                                          key=lambda pair: pair[0])
        routes_list.append(Route(
            edge, upper_tuple[1], lower_tuple[1], upper_tuple[0],
            lower_tuple[0], upward=target_tuple[0] < source_tuple[0]))
    return routes_list


def pack_slots_tuple(upward_list: list[bool], slots_int: int
                     ) -> tuple[list[int], int] | None:
    """Share connection points only between arrows of one direction.

    Args:
        upward_list: Each arrow's direction, in order along the edge.
        slots_int: The most points that fit on the edge.

    Returns:
        Each arrow's point index and the number of points used. Shared
        points hold neighbouring arrows that point the same way (so they
        share a source or a target). None when the directions alternate
        more often than the edge has points.
    """
    count_int = len(upward_list)
    for size_int in range(-(-count_int // slots_int), count_int + 1):
        slots_list: list[int] = []
        slot_int, used_int, previous_bool = -1, 0, None
        for upward_bool in upward_list:
            if used_int == size_int or upward_bool != previous_bool:
                slot_int, used_int = slot_int + 1, 0
            slots_list.append(slot_int)
            used_int, previous_bool = used_int + 1, upward_bool
        if slot_int + 1 <= slots_int:
            return slots_list, slot_int + 1
    return None


def place_ports_none(node: Node, group_list: list[Route],
                     field_str: str) -> None:
    """Spread a block edge's connection points and give them to arrows.

    Args:
        node: The block.
        group_list: Its arrows on that edge, in the preferred order (the
            list is reordered when points must be shared).
        field_str: "exit_x" or "entry_x", the route field to set.

    Returns:
        None. Points sit evenly along the middle of the edge. When there
        are more arrows than points at the minimum spacing, neighbours
        pointing the same way share one; if directions alternate too
        often for that, the arrows are regrouped by direction first.
    """
    span_float = node.width * PORT_SPREAD_FLOAT
    left_float = node.x_px + (node.width - span_float) / 2
    slots_int = int(span_float // MIN_PORT_GAP_FLOAT) + 1
    packed = pack_slots_tuple([route.upward for route in group_list],
                              slots_int)
    if packed is None:
        group_list.sort(key=lambda route: route.upward)
        packed = pack_slots_tuple([route.upward for route in group_list],
                                  slots_int)
    slots_list, used_int = packed
    for route, slot_int in zip(group_list, slots_list):
        setattr(route, field_str,
                left_float + span_float * (slot_int + 0.5) / used_int)


def assign_exits_none(routes_list: list[Route]) -> None:
    """Give each arrow its own exit point, ordered by where it goes.

    Args:
        routes_list: The routes (changed in place).

    Returns:
        None.
    """
    by_source_dict: dict[str, list[Route]] = {}
    for route in routes_list:
        by_source_dict.setdefault(route.source.node_id, []).append(route)
    for group_list in by_source_dict.values():
        group_list.sort(key=lambda route: (find_centre_x_float(route.target),
                                           route.target_row, route.upward))
        place_ports_none(group_list[0].source, group_list, "exit_x")


def find_free_intervals_list(row_nodes: list[Node], left_float: float
                        ) -> list[tuple[float, float]]:
    """The x ranges where a vertical line passes a row without a block.

    Args:
        row_nodes: The row's blocks, left to right.
        left_float: The left edge of the drawing area (the legend sits
            further left, so lines never go there).

    Returns:
        Ranges keeping a clearance from every block; the last one is
        open to the right.
    """
    intervals_list = []
    start_float = left_float
    for node in row_nodes:
        end_float = node.x_px - CLEARANCE_FLOAT
        if end_float >= start_float:
            intervals_list.append((start_float, end_float))
        start_float = node.x_px + node.width + CLEARANCE_FLOAT
    intervals_list.append((start_float, math.inf))
    return intervals_list


def intersect_intervals_list(first_list: list[tuple[float, float]],
                             second_list: list[tuple[float, float]]
                             ) -> list[tuple[float, float]]:
    """The x ranges free in both of two rows.

    Args:
        first_list: Free ranges of one row.
        second_list: Free ranges of another.

    Returns:
        Their overlaps.
    """
    return [(max(a_float, c_float), min(b_float, d_float))
            for a_float, b_float in first_list
            for c_float, d_float in second_list
            if max(a_float, c_float) <= min(b_float, d_float)]


def count_near_int(sorted_list: list[float], x_float: float,
                   distance_float: float) -> int:
    """Count values strictly closer than a distance to x.

    Args:
        sorted_list: Values in ascending order.
        x_float: The position.
        distance_float: The distance.

    Returns:
        How many values lie in (x - distance, x + distance).
    """
    low_int = bisect.bisect_right(sorted_list, x_float - distance_float)
    high_int = bisect.bisect_left(sorted_list, x_float + distance_float)
    return max(high_int - low_int, 0)


def check_lane_free_bool(x_float: float, route: Route,
                         lanes_dict: dict[int, list[tuple[float, int, int]]],
                         exits_dict: dict[int, list[float]]) -> bool:
    """Whether a corridor position is clear of other vertical lines.

    Args:
        x_float: The candidate lane x.
        route: The route that wants it.
        lanes_dict: Lanes taken so far by x bucket: (x, first gap,
            last gap).
        exits_dict: Sorted exit x positions by row.

    Returns:
        True when no other lane runs within a lane gap over the same
        rows and no exit of the source row sits on it.
    """
    first_int, last_int = route.source_row, route.target_row - 1
    bucket_int = int(x_float // LANE_GAP_FLOAT)
    for lane_float, lane_first_int, lane_last_int in (
            lane for key_int in (bucket_int - 1, bucket_int, bucket_int + 1)
            for lane in lanes_dict.get(key_int, ())):
        if (abs(lane_float - x_float) < LANE_GAP_FLOAT
                and lane_first_int <= last_int
                and first_int <= lane_last_int):
            return False
    return not count_near_int(exits_dict.get(route.source_row, []), x_float,
                              NUDGE_FLOAT)


def list_candidate_lanes_list(interval: tuple[float, float], aim_float: float
                         ) -> list[float]:
    """Lane positions inside a free range, nearest to an aim first.

    Args:
        interval: The free range.
        aim_float: The x the arrow would like to drop at.

    Returns:
        Positions one lane gap apart, starting from the one nearest
        the aim and alternating outwards.
    """
    low_float, high_float = interval
    start_float = min(max(aim_float, low_float), high_float)
    positions_list = [start_float]
    for step_int in range(1, 200):
        for sign_int in (1, -1):
            x_float = start_float + sign_int * step_int * LANE_GAP_FLOAT
            if low_float <= x_float <= high_float:
                positions_list.append(x_float)
    return positions_list


def measure_detour_float(route: Route, x_float: float) -> float:
    """How far an arrow travels sideways through a lane.

    Args:
        route: The route.
        x_float: The lane x.

    Returns:
        The horizontal distance from the exit to the lane and from the
        lane to the target's centre.
    """
    return (abs(route.exit_x - x_float)
            + abs(x_float - find_centre_x_float(route.target)))


def choose_lane_float(route: Route, rows_list: list[list[Node]],
                      left_float: float,
                      lanes_dict: dict[int, list[tuple[float, int, int]]],
                      exits_dict: dict[int, list[float]]) -> float:
    """Pick the corridor an arrow that skips rows drops through.

    Args:
        route: The route.
        rows_list: Block nodes per row.
        left_float: The left edge of the drawing area.
        lanes_dict: Lanes taken so far by x bucket (extended in place).
        exits_dict: Sorted exit x positions by row.

    Returns:
        The lane x: free of blocks in every row the arrow passes and as
        close as possible to the line from its exit to its target.
    """
    free_list = find_free_intervals_list(rows_list[route.source_row + 1],
                                         left_float)
    for row_int in range(route.source_row + 2, route.target_row):
        free_list = intersect_intervals_list(free_list,
                                             find_free_intervals_list(
                                                 rows_list[row_int],
                                                 left_float))
    aim_float = (route.exit_x + find_centre_x_float(route.target)) / 2
    candidates_list = sorted(
        (x_float for interval in free_list
         for x_float in list_candidate_lanes_list(interval, aim_float)),
        key=lambda x_float: measure_detour_float(route, x_float))
    chosen_float = next(
        (x_float for x_float in candidates_list
         if check_lane_free_bool(x_float, route, lanes_dict, exits_dict)),
        None)
    if chosen_float is None:
        chosen_float = LANE_GAP_FLOAT + max(
            [free_list[-1][0], *(lane[0] for bucket_list in
                                 lanes_dict.values() for lane in bucket_list)])
    lanes_dict.setdefault(int(chosen_float // LANE_GAP_FLOAT), []).append(
        (chosen_float, route.source_row, route.target_row - 1))
    return chosen_float


def assign_lanes_none(routes_list: list[Route], rows_list: list[list[Node]],
                      left_float: float) -> None:
    """Give every arrow that skips rows its own corridor lane.

    Args:
        routes_list: The routes (changed in place).
        rows_list: Block nodes per row.
        left_float: The left edge of the drawing area.

    Returns:
        None. Shorter arrows choose first, so long ones go around them.
    """
    lanes_dict: dict[int, list[tuple[float, int, int]]] = {}
    exits_dict: dict[int, list[float]] = {}
    for route in routes_list:
        exits_dict.setdefault(route.source_row, []).append(route.exit_x)
    for exits_list in exits_dict.values():
        exits_list.sort()
    skipping_list = [route for route in routes_list
                     if route.target_row > route.source_row + 1]
    skipping_list.sort(key=lambda route: (
        route.target_row - route.source_row, route.source_row,
        route.exit_x))
    for route in skipping_list:
        route.lane_x = choose_lane_float(route, rows_list, left_float,
                                         lanes_dict, exits_dict)


def assign_entries_none(routes_list: list[Route]) -> None:
    """Give each arrow its own entry point, ordered by where it comes from.

    Args:
        routes_list: The routes (changed in place).

    Returns:
        None. An entry that would sit on another arrow's vertical line
        in the same gap is nudged sideways, staying on the block.
    """
    by_target_dict: dict[str, list[Route]] = {}
    for route in routes_list:
        by_target_dict.setdefault(route.target.node_id, []).append(route)
    for group_list in by_target_dict.values():
        group_list.sort(key=lambda route: (
            route.exit_x if route.lane_x is None else route.lane_x,
            route.source_row, route.upward))
        place_ports_none(group_list[0].target, group_list, "entry_x")
    taken_dict = index_gap_verticals_dict(routes_list)
    for route in routes_list:
        opposite_list = [other for other in
                         by_target_dict[route.target.node_id]
                         if other.upward != route.upward]
        route.entry_x = choose_entry_float(route, taken_dict, opposite_list)


def index_gap_verticals_dict(routes_list: list[Route]
                             ) -> dict[int, list[float]]:
    """The x of every exit drop and lane in each gap, sorted.

    Args:
        routes_list: The routes, exits and lanes assigned.

    Returns:
        Gap index -> sorted x positions of vertical lines there.
    """
    taken_dict: dict[int, list[float]] = {}
    for route in routes_list:
        taken_dict.setdefault(route.source_row, []).append(route.exit_x)
        if route.lane_x is not None:
            for gap_int in range(route.source_row, route.target_row):
                taken_dict.setdefault(gap_int, []).append(route.lane_x)
    for taken_list in taken_dict.values():
        taken_list.sort()
    return taken_dict


def choose_entry_float(route: Route, taken_dict: dict[int, list[float]],
                       opposite_list: list[Route]) -> float:
    """Move an entry point off other arrows' vertical lines in its gap.

    Args:
        route: The route whose entry may move.
        taken_dict: Sorted vertical-line x positions per gap.
        opposite_list: Routes meeting the same block edge in the other
            direction; their points are avoided too.

    Returns:
        The entry x: unchanged when clear, otherwise the nearest clear
        position on the target's top edge.
    """
    gap_int = route.target_row - 1
    taken_list = taken_dict.get(gap_int, [])
    own_list = [value for value in (
        route.exit_x if route.source_row == gap_int else None,
        route.lane_x) if value is not None]
    target = route.target
    for step_int in range(0, 40):
        for sign_int in (1, -1):
            x_float = route.entry_x + sign_int * step_int * NUDGE_FLOAT
            inside_bool = (target.x_px + 4.0 <= x_float
                           <= target.x_px + target.width - 4.0)
            own_int = sum(abs(x_float - value) < 3.0 for value in own_list)
            clear_bool = count_near_int(taken_list, x_float,
                                        3.0) <= own_int and all(
                abs(other.entry_x - x_float) >= 3.0
                for other in opposite_list)
            if inside_bool and clear_bool:
                return x_float
    return route.entry_x


def group_segments_dict(routes_list: list[Route]
                         ) -> dict[int, list[tuple[Route, float, float]]]:
    """The horizontal pieces of every arrow, grouped by row gap.

    Args:
        routes_list: The routes.

    Returns:
        Gap index (the gap below that row) -> (route, from x, to x).
    """
    segments_dict: dict[int, list[tuple[Route, float, float]]] = {}
    for route in routes_list:
        if route.lane_x is None:
            pieces_list = [(route.source_row, route.exit_x, route.entry_x)]
        else:
            pieces_list = [(route.source_row, route.exit_x, route.lane_x),
                           (route.target_row - 1, route.lane_x,
                            route.entry_x)]
        for gap_int, from_float, to_float in pieces_list:
            segments_dict.setdefault(gap_int, []).append(
                (route, from_float, to_float))
    return segments_dict


def rank_segment_float(segment: tuple[Route, float, float]) -> float:
    """The order in which a gap's pieces claim tracks, top track first.

    Args:
        segment: (route, from x, to x).

    Returns:
        A sort key: pieces running right claim upper tracks from the
        right-most start, pieces running left from the left-most start,
        so a piece's drop rarely crosses another piece's line.
    """
    _, from_float, to_float = segment
    return -from_float if to_float >= from_float else from_float


def assign_tracks_int(gap_int: int,
                      segments_list: list[tuple[Route, float, float]]
                      ) -> int:
    """Give each horizontal piece in one gap its own track.

    Args:
        gap_int: The gap index.
        segments_list: Its pieces (their routes are changed in place).

    Returns:
        The number of tracks the gap needs.
    """
    tracks_list: list[list[tuple[float, float]]] = []
    for route, from_float, to_float in sorted(segments_list,
                                              key=rank_segment_float):
        span = (min(from_float, to_float) - 4.0,
                max(from_float, to_float) + 4.0)
        for track_int, taken_list in enumerate(tracks_list):
            if all(span[1] < low_float or high_float < span[0]
                   for low_float, high_float in taken_list):
                taken_list.append(span)
                route.tracks[gap_int] = track_int
                break
        else:
            tracks_list.append([span])
            route.tracks[gap_int] = len(tracks_list) - 1
    return len(tracks_list)


def place_rows_list(rows_list: list[list[Node]], track_counts_dict:
                    dict[int, int], min_gap_float: float) -> list[float]:
    """Move the rows down so every gap has room for its tracks.

    Args:
        rows_list: Block nodes per row (their y changes in place).
        track_counts_dict: Tracks needed per gap.
        min_gap_float: The smallest gap between rows.

    Returns:
        The bottom y of every row, top to bottom.
    """
    y_float = rows_list[0][0].y_px
    bottoms_list = []
    for row_int, row_nodes in enumerate(rows_list):
        for node in row_nodes:
            node.y_px = y_float
        bottom_float = y_float + max(node.height for node in row_nodes)
        bottoms_list.append(bottom_float)
        needed_float = (2 * GAP_PAD_FLOAT + TRACK_GAP_FLOAT
                        * max(track_counts_dict.get(row_int, 1) - 1, 0))
        y_float = bottom_float + max(min_gap_float, needed_float)
    return bottoms_list


def track_y_float(bottoms_list: list[float], gap_int: int,
                  track_int: int) -> float:
    """The height of a track in a gap.

    Args:
        bottoms_list: Bottom y of every row.
        gap_int: The gap (below that row).
        track_int: The track index, 0 nearest the row above.

    Returns:
        The track's y.
    """
    return bottoms_list[gap_int] + GAP_PAD_FLOAT + track_int * TRACK_GAP_FLOAT


def route_overview_none(diagram: Diagram, rows_list: list[list[Node]],
                        left_float: float, min_gap_float: float) -> None:
    """Route every downward arrow of a project overview.

    Args:
        diagram: The overview (edge waypoints and row positions change in
            place).
        rows_list: Block nodes per row, top to bottom, left to right.
        left_float: The left edge of the drawing area.
        min_gap_float: The smallest gap between rows.

    Returns:
        None. Each arrow gets waypoints: down from its exit to its track,
        across (through its lane when it skips rows) and down into its
        entry, so every renderer draws the same lines.
    """
    if not rows_list:
        return
    routes_list = collect_routes_list(diagram, rows_list)
    assign_exits_none(routes_list)
    assign_lanes_none(routes_list, rows_list, left_float)
    assign_entries_none(routes_list)
    counts_dict = {gap_int: assign_tracks_int(gap_int, segments_list)
                   for gap_int, segments_list
                   in group_segments_dict(routes_list).items()}
    bottoms_list = place_rows_list(rows_list, counts_dict, min_gap_float)
    for route in routes_list:
        set_waypoints_none(route, bottoms_list)


def set_waypoints_none(route: Route, bottoms_list: list[float]) -> None:
    """Turn a routed arrow into its corner points.

    Args:
        route: The route (its edge's waypoints are set).
        bottoms_list: Bottom y of every row.

    Returns:
        None. Points run from the upper block to the lower one and are
        reversed for an arrow that points up.
    """
    first_y = track_y_float(bottoms_list, route.source_row,
                            route.tracks[route.source_row])
    if route.lane_x is None:
        points_list = [(route.exit_x, first_y), (route.entry_x, first_y)]
    else:
        last_gap_int = route.target_row - 1
        last_y = track_y_float(bottoms_list, last_gap_int,
                               route.tracks[last_gap_int])
        points_list = [(route.exit_x, first_y), (route.lane_x, first_y),
                       (route.lane_x, last_y), (route.entry_x, last_y)]
    if route.upward:
        points_list.reverse()
    route.edge.waypoints = points_list
