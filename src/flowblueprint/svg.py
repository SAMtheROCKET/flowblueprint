"""Render a Diagram as a standalone SVG image.

The SVG is a preview for READMEs, documents and slides; the draw.io
file stays the editable original. Shapes and arrows use the same
geometry as the draw.io output, with simple right-angled arrow routes.
"""

import html

from flowblueprint.model import (
    CONNECTOR_KIND, DATA_KIND, DATABASE_KIND, DECISION_KIND, DOCUMENT_KIND,
    LOOP_CLOSE_KIND, LOOP_FRAME_KIND, LOOP_OPEN_KIND, PLOT_KIND,
    SECTION_KIND, STORAGE_KIND, TERMINATOR_KIND, TEXT_KIND, Diagram, Edge,
    Node)
from flowblueprint.layout import route_back_list

LINE_HEIGHT_FLOAT = 15.0
# Renderers without Helvetica or Arial (Linux PNG output) skip the text
# unless a family they have is listed.
FONT_FAMILY_STR = ("Helvetica, Arial, 'Liberation Sans', 'DejaVu Sans', "
                   "sans-serif")
STROKE_STR = 'stroke="#222222" stroke-width="1.2"'


def format_points_str(points_list: list[tuple[float, float]]) -> str:
    """Format points for an SVG points or path attribute.

    Args:
        points_list: (x, y) pairs.

    Returns:
        "x1,y1 x2,y2 ...".
    """
    return " ".join(f"{x_float:.1f},{y_float:.1f}"
                    for x_float, y_float in points_list)


def draw_shape_str(node: Node) -> str:
    """The SVG element of a node's outline.

    Args:
        node: The node.

    Returns:
        SVG markup ("" for text nodes).
    """
    left, top = node.x_px, node.y_px
    right, bottom = left + node.width, top + node.height
    fill_str = f'fill="{node.fill or "#ffffff"}" {STROKE_STR}'
    if node.kind == TEXT_KIND:
        return ""
    if node.kind in (TERMINATOR_KIND, SECTION_KIND, LOOP_FRAME_KIND):
        return draw_rounded_str(node, fill_str)
    if node.kind == CONNECTOR_KIND:
        return (f'<circle cx="{left + node.width / 2}" '
                f'cy="{top + node.height / 2}" r="{node.width / 2}" '
                f'{fill_str}/>')
    polygon_list = list_polygon_points_list(node)
    if polygon_list:
        return (f'<polygon points="{format_points_str(polygon_list)}" '
                f'{fill_str}/>')
    if node.kind == DATABASE_KIND:
        return draw_cylinder_str(node, fill_str)
    if node.kind in (DOCUMENT_KIND, PLOT_KIND):
        wave_float = node.height * 0.12
        return (f'<path d="M{left},{top} H{right} V{bottom - wave_float} '
                f'Q{left + node.width * 0.75},{bottom - 3 * wave_float} '
                f'{left + node.width / 2},{bottom - wave_float} '
                f'T{left},{bottom - wave_float} Z" {fill_str}/>')
    extra_str = ""
    if node.kind == STORAGE_KIND:
        extra_str = (f'<path d="M{left + 12},{top} V{bottom} '
                     f'M{left},{top + 12} H{right}" {STROKE_STR} '
                     'fill="none"/>')
    return (f'<rect x="{left}" y="{top}" width="{node.width}" '
            f'height="{node.height}" {fill_str}/>' + extra_str)


def draw_rounded_str(node: Node, fill_str: str) -> str:
    """A terminator, a dashed section banner or a loop frame.

    Args:
        node: The node.
        fill_str: Fill and stroke attributes.

    Returns:
        SVG markup.
    """
    if node.kind == LOOP_FRAME_KIND:
        return (f'<rect x="{node.x_px}" y="{node.y_px}" '
                f'width="{node.width}" height="{node.height}" rx="8" '
                f'fill="{node.fill}" stroke="#8a9bb5" stroke-width="1" '
                'stroke-dasharray="5 4"/>')
    dash_str = (' stroke-dasharray="5 3"' if node.kind == SECTION_KIND
                else "")
    return (f'<rect x="{node.x_px}" y="{node.y_px}" width="{node.width}" '
            f'height="{node.height}" rx="{node.height / 2}" '
            f'{fill_str}{dash_str}/>')


def list_polygon_points_list(node: Node) -> list[tuple[float, float]]:
    """The corner points of polygon-shaped nodes.

    Args:
        node: The node.

    Returns:
        The points, or [] for other shapes.
    """
    left, top = node.x_px, node.y_px
    right, bottom = left + node.width, top + node.height
    middle_x, middle_y = left + node.width / 2, top + node.height / 2
    cut_float = 16.0
    if node.kind == DECISION_KIND:
        return [(middle_x, top), (right, middle_y), (middle_x, bottom),
                (left, middle_y)]
    if node.kind == DATA_KIND:
        return [(left + cut_float, top), (right, top),
                (right - cut_float, bottom), (left, bottom)]
    if node.kind == LOOP_OPEN_KIND:
        return [(left + cut_float, top), (right - cut_float, top),
                (right, top + cut_float), (right, bottom), (left, bottom),
                (left, top + cut_float)]
    if node.kind == LOOP_CLOSE_KIND:
        return [(left, top), (right, top), (right, bottom - cut_float),
                (right - cut_float, bottom), (left + cut_float, bottom),
                (left, bottom - cut_float)]
    return []


def draw_cylinder_str(node: Node, fill_str: str) -> str:
    """A database cylinder.

    Args:
        node: The node.
        fill_str: Fill and stroke attributes.

    Returns:
        SVG markup.
    """
    left, top = node.x_px, node.y_px
    right, bottom = left + node.width, top + node.height
    radius_x, radius_y = node.width / 2, 7.0
    return (f'<path d="M{left},{top + radius_y} V{bottom - radius_y} '
            f'A{radius_x},{radius_y} 0 0 0 {right},{bottom - radius_y} '
            f'V{top + radius_y} A{radius_x},{radius_y} 0 0 0 {left},'
            f'{top + radius_y} A{radius_x},{radius_y} 0 0 0 {right},'
            f'{top + radius_y}" {fill_str}/>')


def draw_label_str(node: Node) -> str:
    """The node's text, centred, with a bold first line for titles.

    Args:
        node: The node.

    Returns:
        SVG text markup.
    """
    count_int = len(node.label)
    is_left = node.align == "left"
    middle_x = node.x_px if is_left else node.x_px + node.width / 2
    first_y = (node.y_px + node.height / 2 - (count_int - 1)
               * LINE_HEIGHT_FLOAT / 2 + 4)
    parts_list = []
    for index_int, line_str in enumerate(node.label):
        weight_str = (' font-weight="bold"'
                      if index_int == 0 and node.has_title else "")
        parts_list.append(
            f'<text x="{middle_x:.1f}" '
            f'y="{first_y + index_int * LINE_HEIGHT_FLOAT:.1f}" '
            f'text-anchor="{"start" if is_left else "middle"}"'
            f'{weight_str}>{html.escape(line_str)}'
            '</text>')
    return "".join(parts_list)


def route_upward_list(start_tuple: tuple[float, float], source: Node,
                      target: Node) -> list[tuple[float, float]]:
    """Route an arrow back up (to a loop end or an earlier column).

    Args:
        start_tuple: Where the arrow leaves the source.
        source: The source node.
        target: The target node, above the start.

    Returns:
        A route through a gutter left of the target, entering it from
        the left.
    """
    target_mid_y = target.y_px + target.height / 2
    gutter_x = (target.x_px if target.x_px > source.x_px + source.width
                else min(source.x_px, target.x_px)) - 24.0
    return [start_tuple, (start_tuple[0], start_tuple[1] + 12.0),
            (gutter_x, start_tuple[1] + 12.0), (gutter_x, target_mid_y),
            (target.x_px, target_mid_y)]


def route_down_list(source: Node, target: Node,
                    waypoints_list: list[tuple[float, float]]
                    ) -> list[tuple[float, float]]:
    """Route an arrow from a block's bottom into the top of one below.

    Args:
        source: The source node.
        target: The target node, wholly below the source.
        waypoints_list: Corner points chosen by the layout, or [].

    Returns:
        Down from the source, through the waypoints or across just
        above the target, then down into it. With waypoints, the arrow
        leaves and enters at the first and last waypoint's x; when the
        target is above, it leaves the source's top and enters the
        target's bottom.
    """
    source_mid_x = source.x_px + source.width / 2
    target_mid_x = target.x_px + target.width / 2
    if waypoints_list and target.y_px + target.height <= source.y_px:
        return [(waypoints_list[0][0], source.y_px), *waypoints_list,
                (waypoints_list[-1][0], target.y_px + target.height)]
    if waypoints_list:
        return [(waypoints_list[0][0], source.y_px + source.height),
                *waypoints_list, (waypoints_list[-1][0], target.y_px)]
    turn_y = target.y_px - 16.0
    return [(source_mid_x, source.y_px + source.height),
            (source_mid_x, turn_y), (target_mid_x, turn_y),
            (target_mid_x, target.y_px)]


def route_side_list(source: Node, target: Node
                    ) -> list[tuple[float, float]]:
    """Route a horizontal arrow to or from a data shape beside a block.

    Args:
        source: The source node.
        target: The target node, beside the source.

    Returns:
        Two points at the middle of the overlapping heights.
    """
    middle_y = (max(source.y_px, target.y_px) + min(
        source.y_px + source.height, target.y_px + target.height)) / 2
    return [(source.x_px + source.width, middle_y), (target.x_px, middle_y)]


def route_points_list(edge: Edge, nodes_dict: dict[str, Node]
                      ) -> list[tuple[float, float]]:
    """A right-angled route for an arrow.

    Args:
        edge: The edge.
        nodes_dict: Nodes by id.

    Returns:
        The route's points, from the source to the arrow tip.
    """
    source, target = nodes_dict[edge.source_id], nodes_dict[edge.target_id]
    if edge.back_depth:
        return route_back_list(source, target, edge.back_depth)
    source_mid_x = source.x_px + source.width / 2
    target_mid_x = target.x_px + target.width / 2
    target_mid_y = target.y_px + target.height / 2
    if edge.waypoints or (edge.enters_top
                          and target.y_px > source.y_px + source.height):
        return route_down_list(source, target, edge.waypoints)
    if edge.is_side:
        return route_side_list(source, target)
    if source.kind == DECISION_KIND and edge.label == "Yes":
        start_tuple = (source.x_px + source.width,
                       source.y_px + source.height / 2)
        if target_mid_x > start_tuple[0]:
            return [start_tuple, (target_mid_x, start_tuple[1]),
                    (target_mid_x, target.y_px)]
    else:
        start_tuple = (source_mid_x, source.y_px + source.height)
    if target.y_px + target.height < start_tuple[1]:
        return route_upward_list(start_tuple, source, target)
    if start_tuple[0] > target_mid_x + 1.0:
        side_x = max(start_tuple[0], target.x_px + target.width) + 20.0
        return [start_tuple, (start_tuple[0], start_tuple[1] + 12.0),
                (side_x, start_tuple[1] + 12.0), (side_x, target_mid_y),
                (target.x_px + target.width, target_mid_y)]
    middle_y = (start_tuple[1] + target.y_px) / 2
    return [start_tuple, (start_tuple[0], middle_y), (target_mid_x, middle_y),
            (target_mid_x, target.y_px)]


def draw_edge_str(edge: Edge, nodes_dict: dict[str, Node]) -> str:
    """An arrow with its label.

    Args:
        edge: The edge.
        nodes_dict: Nodes by id.

    Returns:
        SVG markup. A loop's back arrow carries its label upright
        along the arrow's vertical part.
    """
    points_list = route_points_list(edge, nodes_dict)
    markup_str = (f'<polyline points="{format_points_str(points_list)}" '
                  f'fill="none" {STROKE_STR} marker-end="url(#arrow)"/>')
    if edge.label and edge.back_depth:
        gutter_x = points_list[1][0] + 10
        middle_y = (points_list[1][1] + points_list[2][1]) / 2
        return markup_str + (
            f'<text x="{gutter_x:.1f}" y="{middle_y:.1f}" '
            'text-anchor="middle" font-style="italic" '
            f'transform="rotate(-90 {gutter_x:.1f} {middle_y:.1f})">'
            f'{html.escape(edge.label)}</text>')
    if edge.label:
        label_x, label_y = points_list[0]
        return markup_str + (f'<text x="{label_x + 6:.1f}" '
                             f'y="{label_y + 14:.1f}">'
                             f'{html.escape(edge.label)}</text>')
    return markup_str


def render_svg_str(diagram: Diagram) -> str:
    """Render a diagram as SVG.

    Args:
        diagram: The diagram.

    Returns:
        The SVG document text.
    """
    nodes_dict = {node.node_id: node for node in diagram.nodes}
    width_float = max([node.x_px + node.width for node in diagram.nodes]
                      + [point_tuple[0] for edge in diagram.edges
                         for point_tuple in edge.waypoints]) + 40
    height_float = max([node.y_px + node.height for node in diagram.nodes]
                       + [point_tuple[1] for edge in diagram.edges
                          for point_tuple in edge.waypoints]) + 40
    parts_list = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width_float:.0f}" height="{height_float:.0f}" '
        f'viewBox="0 0 {width_float:.0f} {height_float:.0f}" '
        f'font-family="{FONT_FAMILY_STR}" font-size="11">',
        f'<title>{html.escape(diagram.title)}</title>',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" fill="#222222"/></marker></defs>',
        '<rect width="100%" height="100%" fill="#ffffff"/>']
    # Loop frames lie under the arrows; every other shape lies over them.
    frames_list = [node for node in diagram.nodes
                   if node.kind == LOOP_FRAME_KIND]
    parts_list.extend(draw_shape_str(node) for node in frames_list)
    parts_list.extend(draw_edge_str(edge, nodes_dict)
                      for edge in diagram.edges)
    for node in diagram.nodes:
        if node.kind != LOOP_FRAME_KIND:
            parts_list.append(draw_shape_str(node) + draw_label_str(node))
    parts_list.append("</svg>")
    return "\n".join(parts_list) + "\n"
