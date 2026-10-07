"""Turn a flow into the pages of an architecture document.

A script's document has up to three kinds of page:

- an overview: the main flow at the summary level (packed blocks), for
  readers who want the big picture first;
- the main flow in detail, from START to END;
- one detailed page per function of the script that the flow calls,
  from the function's signature to what it returns.

draw.io keeps each page as a tab; SVG and PNG stack the pages in one
image; HTML and Markdown show them as sections.
"""

import copy

from flowblueprint.layout import layout_flow
from flowblueprint.model import Diagram, Flow
from flowblueprint.summary import summarise_items_list

LEVELS_TUPLE = ("full", "detailed", "summary")
PAGE_GAP_FLOAT = 70.0
# A summary page adds nothing when the main flow is already this short.
OVERVIEW_MIN_ITEMS_INT = 6


def make_overview_flow(flow: Flow, group_size_int: int) -> Flow:
    """The main flow packed into fewer, higher-level blocks.

    Args:
        flow: The detailed main flow (left unchanged).
        group_size_int: The most operations per packed block.

    Returns:
        A copy at the summary level, titled as the overview.
    """
    overview = copy.deepcopy(flow)
    overview.functions = []
    overview.items = summarise_items_list(overview.items, group_size_int)
    overview.script_name = f"{flow.script_name}: overview"
    return overview


def list_page_flows_list(flow: Flow, level_str: str,
                         group_size_int: int) -> list[Flow]:
    """The flows to draw, one per page, in reading order.

    Args:
        flow: The script's flow with its function flows.
        level_str: "full" (overview, main flow and function pages),
            "detailed" (main flow and function pages) or "summary"
            (the overview only).
        group_size_int: The most operations per packed block.

    Returns:
        The page flows. "full" leaves the overview out when the main
        flow is already short.
    """
    overview = make_overview_flow(flow, group_size_int)
    if level_str == "summary":
        overview.script_name = flow.script_name
        return [overview]
    pages_list = [flow, *flow.functions]
    if level_str == "full" and len(flow.items) >= OVERVIEW_MIN_ITEMS_INT:
        pages_list.insert(0, overview)
    return pages_list


def layout_pages_list(flows_list: list[Flow],
                      max_blocks_int: int) -> list[Diagram]:
    """Lay out each page flow.

    Args:
        flows_list: The page flows.
        max_blocks_int: The most blocks per column.

    Returns:
        One diagram per page.
    """
    return [layout_flow(page_flow, max_blocks_int)
            for page_flow in flows_list]


def stack_pages_diagram(pages_list: list[Diagram]) -> Diagram:
    """Stack page diagrams top to bottom as one diagram.

    Args:
        pages_list: The pages (left unchanged).

    Returns:
        One diagram for single-image formats. Node ids get a page
        prefix ("p2n5") so they stay unique; the first page's title is
        the whole diagram's title.
    """
    if len(pages_list) == 1:
        return pages_list[0]
    whole = Diagram(pages_list[0].title)
    top_float = 0.0
    for index_int, page in enumerate(pages_list, start=1):
        prefix_str = f"p{index_int}"
        for node in page.nodes:
            moved = copy.copy(node)
            moved.node_id = prefix_str + node.node_id
            moved.y_px += top_float
            whole.nodes.append(moved)
        for edge in page.edges:
            moved_edge = copy.copy(edge)
            moved_edge.source_id = prefix_str + edge.source_id
            moved_edge.target_id = prefix_str + edge.target_id
            moved_edge.waypoints = [(x_float, y_float + top_float)
                                    for x_float, y_float in edge.waypoints]
            whole.edges.append(moved_edge)
        whole.column_count = max(whole.column_count, page.column_count)
        top_float = max(node.y_px + node.height
                        for node in whole.nodes) + PAGE_GAP_FLOAT
    return whole

