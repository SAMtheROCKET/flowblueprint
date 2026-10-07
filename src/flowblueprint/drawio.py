"""Render a Diagram as an uncompressed draw.io file.

The file opens in diagrams.net and in the VS Code draw.io extension,
which can also convert it to an editable .drawio.png. Shapes come from
draw.io's standard flowchart library; output is deterministic.
"""

import html
import xml.etree.ElementTree as ET

from flowblueprint.layout import route_back_list

from flowblueprint.model import (
    CONNECTOR_KIND, DATA_KIND, DATABASE_KIND, DECISION_KIND, DOCUMENT_KIND,
    LEGEND_KIND, LOOP_CLOSE_KIND, LOOP_FRAME_KIND, LOOP_OPEN_KIND, PLOT_KIND,
    PROCESS_KIND,
    SECTION_KIND, STORAGE_KIND, TERMINATOR_KIND, TEXT_KIND, Diagram, Edge,
    Node)

COMMON_STYLE_STR = "whiteSpace=wrap;html=1;fontSize=11;strokeColor=#000000;"
SHAPE_STYLES_DICT = {
    PROCESS_KIND: "rounded=0;",
    PLOT_KIND: "shape=document;boundedLbl=1;size=0.15;",
    TERMINATOR_KIND: "rounded=1;arcSize=50;",
    DECISION_KIND: "rhombus;",
    DATA_KIND: "shape=parallelogram;perimeter=parallelogramPerimeter;"
               "fixedSize=1;size=16;",
    DATABASE_KIND: "shape=cylinder3;boundedLbl=1;backgroundOutline=1;"
                   "size=10;",
    STORAGE_KIND: "shape=internalStorage;backgroundOutline=1;dx=12;dy=12;",
    DOCUMENT_KIND: "shape=document;boundedLbl=1;size=0.15;",
    LOOP_OPEN_KIND: "shape=loopLimit;size=18;",
    LOOP_CLOSE_KIND: "shape=loopLimit;size=18;flipV=1;",
    CONNECTOR_KIND: "ellipse;aspect=fixed;",
    TEXT_KIND: "text;align=center;verticalAlign=middle;",
    LEGEND_KIND: "rounded=0;",
    SECTION_KIND: "rounded=1;arcSize=40;dashed=1;fontSize=12;",
    LOOP_FRAME_KIND: "rounded=1;arcSize=4;dashed=1;"
                     "connectable=0;",
}
EDGE_STYLE_STR = ("edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;"
                  "endArrow=block;endFill=1;fontSize=11;")


def label_html_str(node: Node) -> str:
    """The HTML label of a node: bold title, then the other lines.

    Args:
        node: The node.

    Returns:
        HTML text with <br> between lines.
    """
    lines_list = [html.escape(line_str) for line_str in node.label]
    if node.has_title and lines_list:
        lines_list[0] = f"<b>{lines_list[0]}</b>"
    return "<br>".join(lines_list)


def build_node_style_str(node: Node) -> str:
    """The draw.io style of a node.

    Args:
        node: The node.

    Returns:
        The style string.
    """
    style_str = SHAPE_STYLES_DICT.get(node.kind, "rounded=0;")
    style_str += COMMON_STYLE_STR
    if node.kind == LOOP_FRAME_KIND:
        return style_str + f"strokeColor=#8a9bb5;fillColor={node.fill};"
    if node.kind == TEXT_KIND:
        return style_str + (f"strokeColor=none;fillColor=none;"
                            f"align={node.align};")
    return style_str + f"fillColor={node.fill or '#ffffff'};"


def find_centre_tuple(node: Node) -> tuple[float, float]:
    """The centre of a node.

    Args:
        node: The node.

    Returns:
        (x, y) of its centre.
    """
    return node.x_px + node.width / 2, node.y_px + node.height / 2


def build_edge_style_str(edge: Edge, nodes_dict: dict[str, Node]) -> str:
    """The draw.io style of an edge, with exit and entry sides.

    Args:
        edge: The edge.
        nodes_dict: Nodes by id.

    Returns:
        The style string. Side arrows run horizontally; a Yes branch
        leaves a decision to the right; an arrow from a path to the
        right of its target enters the target from the right.
    """
    source = nodes_dict[edge.source_id]
    target = nodes_dict[edge.target_id]
    source_x_float, _ = find_centre_tuple(source)
    target_x_float, _ = find_centre_tuple(target)
    style_str = EDGE_STYLE_STR
    if edge.back_depth:
        return style_str + ("exitX=0;exitY=0.5;entryX=0;entryY=0.5;"
                            "fontStyle=2;")
    if edge.is_side:
        return style_str + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;"
    if edge.enters_top and (target.y_px > source.y_px + source.height
                            or edge.waypoints):
        return style_str + build_port_style_str(edge, source, target)
    if source.kind == DECISION_KIND and edge.label == "Yes":
        style_str += "exitX=1;exitY=0.5;"
    elif source.kind == DECISION_KIND and edge.label == "No":
        style_str += "exitX=0.5;exitY=1;"
    if target.y_px + target.height < source.y_px:
        style_str += "entryX=0;entryY=0.5;"
    elif source_x_float > target_x_float + 1.0:
        style_str += "entryX=1;entryY=0.5;"
    elif source_x_float + 1.0 < target_x_float and (
            source.kind != DECISION_KIND):
        style_str += "entryX=0;entryY=0.5;"
    else:
        style_str += "entryX=0.5;entryY=0;"
    return style_str


def add_node_cell_none(root: ET.Element, node: Node) -> None:
    """Add a node's cell and geometry to the draw.io model.

    Args:
        root: The model's root element (changed in place).
        node: The node.

    Returns:
        None.
    """
    cell = ET.SubElement(root, "mxCell", id=node.node_id,
                         value=label_html_str(node),
                         style=build_node_style_str(node), vertex="1",
                         parent="1")
    ET.SubElement(cell, "mxGeometry", x=format_number_str(node.x_px),
                  y=format_number_str(node.y_px),
                  width=format_number_str(node.width),
                  height=format_number_str(node.height),
                  attrib={"as": "geometry"})


def render_drawio_str(diagram: Diagram) -> str:
    """Render a diagram as draw.io XML.

    Args:
        diagram: The diagram.

    Returns:
        The file text.
    """
    return render_drawio_pages_str([diagram])


def render_drawio_pages_str(pages_list: list[Diagram]) -> str:
    """Render diagrams as the pages (tabs) of one draw.io file.

    Args:
        pages_list: The pages, in order.

    Returns:
        The file text.
    """
    mxfile = ET.Element("mxfile", host="flowblueprint", type="device")
    for index_int, diagram in enumerate(pages_list):
        add_page_none(mxfile, diagram, "flowblueprint" + (
            f"-{index_int + 1}" if index_int else ""))
    ET.indent(mxfile)
    return ET.tostring(mxfile, encoding="unicode") + "\n"


def add_page_none(mxfile: ET.Element, diagram: Diagram, id_str: str) -> None:
    """Add one diagram as a page of a draw.io file.

    Args:
        mxfile: The file's root element (changed in place).
        diagram: The page's diagram.
        id_str: A page id unique within the file.

    Returns:
        None.
    """
    page = ET.SubElement(mxfile, "diagram", id=id_str,
                         name=diagram.title[:60])
    model = ET.SubElement(page, "mxGraphModel", grid="1", gridSize="10",
                          guides="1", tooltips="1", connect="1", arrows="1",
                          fold="1", page="1", pageScale="1",
                          math="0", shadow="0")
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", id="1", parent="0")
    nodes_dict = {node.node_id: node for node in diagram.nodes}
    for node in diagram.nodes:
        add_node_cell_none(root, node)
    for index_int, edge in enumerate(diagram.edges, start=1):
        cell = ET.SubElement(root, "mxCell", id=f"e{index_int}",
                             value=html.escape(edge.label),
                             style=build_edge_style_str(edge, nodes_dict),
                             edge="1", parent="1", source=edge.source_id,
                             target=edge.target_id)
        geometry = ET.SubElement(cell, "mxGeometry", relative="1",
                                 attrib={"as": "geometry"})
        waypoints_list = edge.waypoints or (route_back_list(
            nodes_dict[edge.source_id], nodes_dict[edge.target_id],
            edge.back_depth)[1:3] if edge.back_depth else [])
        if waypoints_list:
            points = ET.SubElement(geometry, "Array", attrib={"as": "points"})
            for x_float, y_float in waypoints_list:
                ET.SubElement(points, "mxPoint", x=format_number_str(x_float),
                              y=format_number_str(y_float))


def build_port_style_str(edge: Edge, source: Node, target: Node) -> str:
    """Exit and entry points of an arrow from a block down into another.

    Args:
        edge: The arrow; its first and last waypoints sit straight
            beside the exit and the entry (below and above, or the other
            way round for an arrow that points up).
        source: The block it leaves.
        target: The block it enters.

    Returns:
        The draw.io exit/entry style, centred when there are no
        waypoints.
    """
    if not edge.waypoints:
        return "exitX=0.5;exitY=1;entryX=0.5;entryY=0;"
    exit_float = (edge.waypoints[0][0] - source.x_px) / source.width
    entry_float = (edge.waypoints[-1][0] - target.x_px) / target.width
    upward_bool = target.y_px + target.height <= source.y_px
    return (f"exitX={exit_float:.4f};exitY={0 if upward_bool else 1};"
            f"entryX={entry_float:.4f};entryY={1 if upward_bool else 0};")


def format_number_str(value_float: float) -> str:
    """Format a coordinate without needless decimals.

    Args:
        value_float: The value.

    Returns:
        "120" or "120.5".
    """
    rounded_float = round(value_float, 1)
    if rounded_float == int(rounded_float):
        return str(int(rounded_float))
    return str(rounded_float)
