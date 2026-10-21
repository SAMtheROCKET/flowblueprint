"""Continue long operational loops across columns with labelled connectors."""

from flowblueprint.layout import (
    LayoutBuilder, Token, count_blocks_int, flatten_list,
)
from flowblueprint.model import Diagram, Item, Node

ROUTE_GAP_FLOAT = 28.0


class ReferenceLayoutBuilder(LayoutBuilder):
    """Retain loop pairs while using columns for long loop bodies."""

    def split_columns_list(self, items_list: list[Item]) -> list[list[Token]]:
        """Split sequences inside loops; keep each decision subtree intact.

        Args:
            items_list: Entry operations.
        Returns:
            list: Columns of tokens, with loop state spanning columns.
        Warnings:
            A large decision subtree can still exceed the block target.
        """
        columns_list: list[list[Token]] = [[]]
        count_int = 0
        for token_info in flatten_list(items_list):
            size_int = count_blocks_int(token_info)
            if columns_list[-1] and count_int + size_int > self.max_blocks_int:
                columns_list.append([])
                count_int = 0
            columns_list[-1].append(token_info)
            count_int += size_int
        return columns_list

    def build_loop_frames_list(self, nodes_list: list[Node]) -> list[Node]:
        """Frame loops contained in one column without covering other flows.

        Args:
            nodes_list: Positioned shapes.
        Returns:
            list[Node]: Frames for loops wholly inside one column.
        Warnings:
            Cross-column loops retain their limits and repeat arrows.
        """
        columns_dict = {info.node_id: info.column for info in nodes_list}
        saved_list = self.loop_pairs_list
        self.loop_pairs_list = [pair for pair in saved_list
                               if columns_dict[pair[0]] ==
                               columns_dict[pair[1]]]
        try:
            return super().build_loop_frames_list(nodes_list)
        finally:
            self.loop_pairs_list = saved_list

    def build(self) -> Diagram:
        """Route repeat arrows around the bottoms of continuing columns.

        Args:
            None: Uses the configured entry flow.
        Returns:
            Diagram: Editable loop-aware column layout.
        Warnings:
            Column connector pairs preserve order; no branch is invented.
        """
        diagram_info = super().build()
        route_column_loops_none(diagram_info)
        preserve_left_margin_none(diagram_info)
        return diagram_info


def route_column_loops_none(diagram_info: Diagram) -> None:
    """Place cross-column repeat arrows below all process blocks.

    Args:
        diagram_info: Diagram whose edge waypoints are updated.
    Returns:
        None: Preserves endpoints, loop depth and edge semantics.
    Warnings:
        Extra bottom space is needed for nested repeating paths.
    """
    nodes_dict = {info.node_id: info for info in diagram_info.nodes}
    bottom_float = max(info.y_px + info.height
                       for info in diagram_info.nodes)
    for edge_info in diagram_info.edges:
        source_info = nodes_dict[edge_info.source_id]
        target_info = nodes_dict[edge_info.target_id]
        if not edge_info.back_depth or (
                source_info.column == target_info.column):
            continue
        bottom_float += ROUTE_GAP_FLOAT
        lefts_list = [min(info.x_px for info in diagram_info.nodes
                         if info.column == column_int) - ROUTE_GAP_FLOAT
                      for column_int in (source_info.column,
                                         target_info.column)]
        source_y_float = source_info.y_px + source_info.height / 2
        target_y_float = target_info.y_px + target_info.height / 2
        edge_info.waypoints = [
            (lefts_list[0], source_y_float), (lefts_list[0], bottom_float),
            (lefts_list[1], bottom_float), (lefts_list[1], target_y_float),
        ]


def preserve_left_margin_none(diagram_info: Diagram) -> None:
    """Keep repeat-arrow gutters inside the exported image bounds.

    Args:
        diagram_info: Diagram with final routed edge waypoints.
    Returns:
        None: Moves all geometry together when its gutter is negative.
    Warnings:
        Relative geometry and flow connections stay unchanged.
    """
    left_float = min([node.x_px for node in diagram_info.nodes]
                     + [point[0] for edge in diagram_info.edges
                        for point in edge.waypoints])
    shift_float = max(0.0, 20.0 - left_float)
    for node_info in diagram_info.nodes:
        node_info.x_px += shift_float
    for edge_info in diagram_info.edges:
        edge_info.waypoints = [(x_float + shift_float, y_float)
                              for x_float, y_float in edge_info.waypoints]
