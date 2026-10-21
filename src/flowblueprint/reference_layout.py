"""Place operational entry flows beside one another on a shared canvas."""

from copy import deepcopy
from dataclasses import replace

from flowblueprint.reference_columns import ReferenceLayoutBuilder
from flowblueprint.model import (
    CONNECTOR_KIND, Diagram, Flow, Node, TEXT_KIND,
)
from flowblueprint.summary import summarise_items_list

CANVAS_GAP_FLOAT = 100.0
HEADER_HEIGHT_FLOAT = 70.0
EVIDENCE_NOTE_STR = (
    "Static source view; types and dispatch are unverified. "
    "Independent scripts are not linked by an assumed execution order."
)


def append_diagram_none(
    target_info: Diagram, source_info: Diagram, offset_float: float,
    prefix_str: str,
) -> None:
    """Translate a script diagram and keep its edges and ids distinct.

    Args:
        target_info: Canvas to extend.
        source_info: Diagram whose positions remain unchanged.
        offset_float: Horizontal translation in pixels.
        prefix_str: Unique script prefix for every node id.
    Returns:
        None: Appends translated shapes and arrows.
    Warnings:
        This places independent flows; it adds no execution edges.
    """
    leaving_set = {edge.source_id for edge in source_info.edges}
    for node_info in source_info.nodes:
        labels_list = list(node_info.label)
        if node_info.kind == CONNECTOR_KIND:
            boundary_int = node_info.column + (
                node_info.node_id not in leaving_set)
            labels_list = [f"{prefix_str[1:-1]}.{boundary_int}"]
        target_info.nodes.append(replace(
            node_info, node_id=prefix_str + node_info.node_id,
            label=labels_list,
            x_px=node_info.x_px + offset_float,
            y_px=node_info.y_px + HEADER_HEIGHT_FLOAT,
            column=node_info.column + target_info.column_count))
    for edge_info in source_info.edges:
        target_info.edges.append(replace(
            edge_info, source_id=prefix_str + edge_info.source_id,
            target_id=prefix_str + edge_info.target_id,
            waypoints=[(x_float + offset_float,
                        y_float + HEADER_HEIGHT_FLOAT)
                       for x_float, y_float in edge_info.waypoints]))
    target_info.column_count += source_info.column_count


def layout_reference_canvas(
    flows_list: list[Flow], title_str: str, max_blocks_int: int = 10,
) -> Diagram:
    """Draw entry flows with consistent module colours across scripts.

    Args:
        flows_list: Independent operational entry flows.
        title_str: Canvas title.
        max_blocks_int: Column size target; loops stay together.
    Returns:
        Diagram: One editable implementation architecture canvas.
    Warnings:
        Colours identify modules, not verified runtime dependencies.
    """
    canvas_info = Diagram(title_str, column_count=0)
    modules_list = sorted({name_str for flow_info in flows_list
                           for name_str in flow_info.modules})
    offset_float = 0.0
    for index_int, flow_info in enumerate(flows_list):
        drawing_info = deepcopy(flow_info)
        drawing_info.modules = modules_list
        diagram_info = ReferenceLayoutBuilder(
            drawing_info, max_blocks_int).build()
        append_diagram_none(canvas_info, diagram_info, offset_float,
                            f"f{index_int + 1}_")
        offset_float += max(
            [node_info.x_px + node_info.width
             for node_info in diagram_info.nodes] +
            [point[0] for edge in diagram_info.edges
             for point in edge.waypoints])
        offset_float += CANVAS_GAP_FLOAT
    canvas_info.nodes.insert(0, Node(
        "canvas_title", TEXT_KIND, [title_str], 20, 0,
        max(600.0, offset_float - CANVAS_GAP_FLOAT), 30, has_title=True))
    canvas_info.nodes.insert(1, Node(
        "canvas_evidence", TEXT_KIND, [EVIDENCE_NOTE_STR], 20, 32,
        max(800.0, offset_float - CANVAS_GAP_FLOAT), 30))
    return canvas_info


def build_reference_pages_list(
    flows_list: list[Flow], title_str: str, level_str: str = "full",
    max_blocks_int: int = 10, group_size_int: int = 4,
) -> list[Diagram]:
    """Build high-level and detailed operational canvases.

    Args:
        flows_list: Parsed entry flows.
        title_str: Project or script title.
        level_str: full, summary, or detailed.
        max_blocks_int: Column size target.
        group_size_int: Consecutive operations per summary block.
    Returns:
        list[Diagram]: Summary and/or detailed canvas in that order.
    Warnings:
        Summary grouping changes presentation only; source is untouched.
    """
    pages_list = []
    if level_str != "detailed":
        summary_list = deepcopy(flows_list)
        for flow_info in summary_list:
            flow_info.items = summarise_items_list(
                flow_info.items, group_size_int)
        pages_list.append(layout_reference_canvas(
            summary_list, f"{title_str}: high level", max_blocks_int))
    if level_str != "summary":
        pages_list.append(layout_reference_canvas(
            flows_list, f"{title_str}: implementation", max_blocks_int))
    return pages_list
