"""Place a flow on a page, top to bottom and left to right.

Each piece is laid out around a vertical spine at x = 0 and then moved
into place. Loops become an opening and a closing loop-limit shape with
an arrow from the closing shape back up to the opening one, inside a
light dashed frame; a loop is never split across columns. A column
holds at most ``max_blocks_int`` blocks; longer flows continue in the
next column through a pair of lettered connectors (A, B, ...). Data
sources sit to the left of the block that reads them and outputs to
the right of the block that writes them.
"""

from dataclasses import dataclass, field
import string
import textwrap

from flowblueprint.model import (
    CONNECTOR_KIND, DECISION_KIND, LEGEND_KIND, LOOP_CLOSE_KIND,
    LOOP_FRAME_KIND, LOOP_OPEN_KIND, TERMINATOR_KIND, TEXT_KIND, Branch,
    Diagram, Edge, Flow, Item, Loop, Node, Port, Step)

BLOCK_WIDTH_FLOAT = 240.0
BLOCK_CHARS_INT = 36
LINE_HEIGHT_FLOAT = 15.0
BLOCK_PADDING_FLOAT = 14.0
GAP_FLOAT = 30.0
SIDE_GAP_FLOAT = 50.0
SIDE_WIDTH_FLOAT = 140.0
SIDE_HEIGHT_FLOAT = 44.0
SIDE_CHARS_INT = 20
DECISION_WIDTH_FLOAT = 220.0
DECISION_CHARS_INT = 22
BRANCH_GAP_FLOAT = 50.0
COLUMN_GAP_FLOAT = 90.0
TERMINATOR_WIDTH_FLOAT = 110.0
TERMINATOR_HEIGHT_FLOAT = 40.0
CONNECTOR_SIZE_FLOAT = 44.0
LEGEND_WIDTH_FLOAT = 220.0
MARGIN_FLOAT = 20.0
HEADER_HEIGHT_FLOAT = 40.0
LOOP_FRAME_FILL_STR = "#f4f8fd"
LOOP_FRAME_PADDING_FLOAT = 8.0

# Light fills that keep black text readable, one per developed module.
MODULE_COLOURS_TUPLE = ("#dae8fc", "#d5e8d4", "#ffe6cc", "#e1d5e7",
                        "#fff2cc", "#f8cecc", "#b1ddf0", "#d0cee2")


@dataclass
class LoopMark:
    """The opening or closing shape of a loop, as a sequence token.

    Args:
        header: The loop text.
        is_open: True for the opening shape.
        line: The loop's source line.
        footer: The closing shape's text ("" repeats the header).
    """

    header: str
    is_open: bool
    line: int = 0
    footer: str = ""


type Token = Step | LoopMark | Branch


@dataclass
class Group:
    """Laid-out nodes around the spine x = 0, starting at y = 0.

    Args:
        nodes: The nodes, in relative coordinates.
        edges: The edges between them.
        entry: The node arrows into the group point to.
        exits: (node id, edge label) pairs that leave the group.
        left: The smallest x used.
        right: The largest x used.
        height: The height used.
    """

    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    entry: str = ""
    exits: list[tuple[str, str]] = field(default_factory=list)
    left: float = 0.0
    right: float = 0.0
    height: float = 0.0

    def shift_none(self, dx_float: float, dy_float: float) -> None:
        """Move every node by (dx_float, dy_float).

        Args:
            dx_float: Horizontal offset.
            dy_float: Vertical offset.

        Returns:
            None.
        """
        for node in self.nodes:
            node.x_px += dx_float
            node.y_px += dy_float
        self.left += dx_float
        self.right += dx_float


def wrap_list(text_str: str, width_int: int) -> list[str]:
    """Wrap text into lines of at most width_int characters.

    Args:
        text_str: The text.
        width_int: The line width.

    Returns:
        The lines; long words are broken.
    """
    return textwrap.wrap(text_str, width_int, break_on_hyphens=False) or [
        ""]


def format_ports_str(prefix_str: str, ports_list: list[Port]) -> str:
    """Format ports as "in: a: DataFrame, b: int".

    Args:
        prefix_str: "in" or "out".
        ports_list: The ports.

    Returns:
        The text, or "" for no ports.
    """
    if not ports_list:
        return ""
    joined_str = ", ".join(f"{port.name}: {port.dtype}" for port in ports_list)
    return f"{prefix_str}: {joined_str}"


def step_label_list(step: Step) -> list[str]:
    """The wrapped label lines of a step's block.

    Args:
        step: The step.

    Returns:
        Title (if any), description, inputs and outputs as lines.
    """
    lines_list = [step.title] if step.title else []
    for text_str in (step.description, format_ports_str("in", step.inputs),
                     format_ports_str("out", step.outputs)):
        if text_str:
            lines_list.extend(wrap_list(text_str, BLOCK_CHARS_INT))
    return lines_list


def count_blocks_int(token: Token | Item) -> int:
    """How many blocks a token or item draws (side shapes excluded).

    Args:
        token: A step, loop mark, loop or branch.

    Returns:
        The number of blocks.
    """
    if isinstance(token, Branch):
        return 1 + sum(map(count_blocks_int, token.yes)) + sum(
            map(count_blocks_int, token.no))
    if isinstance(token, Loop):
        return 2 + sum(map(count_blocks_int, token.body))
    return 1


def flatten_list(items_list: list[Item]) -> list[Token]:
    """Replace loops by their opening mark, body and closing mark.

    Args:
        items_list: Items of one sequence.

    Returns:
        Tokens; branches keep their own nested items.
    """
    tokens_list: list[Token] = []
    for item in items_list:
        if isinstance(item, Loop):
            tokens_list.append(LoopMark(item.header, True, item.line))
            tokens_list.extend(flatten_list(item.body))
            tokens_list.append(LoopMark(item.header, False, item.line,
                                        item.footer))
        else:
            tokens_list.append(item)
    return tokens_list


class LayoutBuilder:
    """Builds a Diagram from a Flow; see layout_flow."""

    def __init__(self, flow: Flow, max_blocks_int: int) -> None:
        """Prepare the builder.

        Args:
            flow: The flow to place.
            max_blocks_int: The most blocks per column.
        """
        self.flow = flow
        self.max_blocks_int = max(3, max_blocks_int)
        self.count_int = 0
        self.loop_jumps_list: list[dict] = []
        self.loop_pairs_list: list[tuple[str, str, int]] = []
        self.return_exits_list: list[tuple[str, str]] = []
        self.extra_edges_list: list[Edge] = []
        self.colours_dict = {
            module_str: MODULE_COLOURS_TUPLE[index_int
                                             % len(MODULE_COLOURS_TUPLE)]
            for index_int, module_str in enumerate(flow.modules)}

    def make_id_str(self) -> str:
        """A new node id.

        Returns:
            "n1", "n2", ... in creation order.
        """
        self.count_int += 1
        return f"n{self.count_int}"

    def place_single(self, kind_str: str, label_list: list[str],
                     width_float: float, height_float: float,
                     line_int: int = 0) -> Group:
        """A group of one node centred on the spine.

        Args:
            kind_str: The node kind.
            label_list: Its label lines.
            width_float: Its width.
            height_float: Its height.
            line_int: Its source line.

        Returns:
            The group, entered and left through the node.
        """
        node = Node(self.make_id_str(), kind_str, label_list,
                    -width_float / 2, 0.0, width_float, height_float,
                    line=line_int)
        return Group([node], [], node.node_id, [(node.node_id, "")],
                     -width_float / 2, width_float / 2, height_float)

    def place_step(self, step: Step) -> Group:
        """A step's block with its data shapes beside it.

        Args:
            step: The step.

        Returns:
            The group.
        """
        label_list = step_label_list(step)
        height_float = len(label_list) * LINE_HEIGHT_FLOAT + 2 * (
            BLOCK_PADDING_FLOAT)
        group = self.place_single(step.kind, label_list, BLOCK_WIDTH_FLOAT,
                                  height_float, step.line)
        main_node = group.nodes[0]
        main_node.has_title = bool(step.title)
        main_node.fill = self.colours_dict.get(step.module, "")
        for is_output in (False, True):
            sources_list = [source for source in step.sources
                            if source.is_output == is_output]
            for index_int, source in enumerate(sources_list):
                self.add_side_node_none(group, source.kind, source.label,
                                        is_output, index_int, step.line)
        return group

    def add_side_node_none(self, group: Group, kind_str: str,
                           label_str: str, is_output: bool, index_int: int,
                           line_int: int) -> None:
        """Add a data shape beside a group's block, with its arrow.

        Args:
            group: The step's group (changed in place).
            kind_str: The source kind.
            label_str: The shape text.
            is_output: True to place it on the right, written to.
            index_int: Its position among shapes on the same side.
            line_int: The step's source line.

        Returns:
            None.
        """
        main_node = group.nodes[0]
        lines_list = wrap_list(label_str, SIDE_CHARS_INT)
        height_float = max(SIDE_HEIGHT_FLOAT, len(lines_list)
                           * LINE_HEIGHT_FLOAT + 16)
        x_float = (main_node.x_px + main_node.width + SIDE_GAP_FLOAT
                   if is_output
                   else main_node.x_px - SIDE_GAP_FLOAT - SIDE_WIDTH_FLOAT)
        y_float = max(0.0, main_node.height / 2 - height_float / 2) + (
            index_int * (height_float + 12))
        node = Node(self.make_id_str(), kind_str, lines_list, x_float, y_float,
                    SIDE_WIDTH_FLOAT, height_float, line=line_int)
        group.nodes.append(node)
        edge = (Edge(main_node.node_id, node.node_id, is_side=True)
                if is_output
                else Edge(node.node_id, main_node.node_id, is_side=True))
        group.edges.append(edge)
        group.left = min(group.left, node.x_px)
        group.right = max(group.right, node.x_px + node.width)
        group.height = max(group.height, node.y_px + node.height)

    def place_loop_mark(self, mark: LoopMark) -> Group:
        """A loop-limit shape.

        Args:
            mark: The loop's opening or closing mark.

        Returns:
            The group.
        """
        text_str = mark.header if mark.is_open else (mark.footer
                                                     or mark.header)
        lines_list = wrap_list(text_str, BLOCK_CHARS_INT)
        height_float = max(44.0, len(lines_list) * LINE_HEIGHT_FLOAT + 22)
        kind_str = LOOP_OPEN_KIND if mark.is_open else LOOP_CLOSE_KIND
        group = self.place_single(kind_str, lines_list, BLOCK_WIDTH_FLOAT + 20,
                                  height_float, mark.line)
        if mark.is_open:
            self.loop_jumps_list.append({"continue": [], "break": [],
                                         "open": group.entry})
        elif self.loop_jumps_list:
            depth_int = len(self.loop_jumps_list)
            jumps_dict = self.loop_jumps_list.pop()
            self.extra_edges_list.extend(
                Edge(source_id, group.entry, label_str)
                for source_id, label_str in jumps_dict["continue"])
            self.extra_edges_list.append(Edge(
                group.entry, jumps_dict["open"], "repeat",
                back_depth=depth_int))
            self.loop_pairs_list.append((jumps_dict["open"], group.entry,
                                         depth_int))
            group.exits = [(group.entry, "done"), *jumps_dict["break"]]
        return group

    def place_branch(self, branch: Branch) -> Group:
        """A decision with its No path below and Yes path to the right.

        Args:
            branch: The branch.

        Returns:
            The group; its exits are both paths' ends.
        """
        lines_list = wrap_list(branch.condition, DECISION_CHARS_INT)
        height_float = max(80.0, len(lines_list) * LINE_HEIGHT_FLOAT + 50)
        group = self.place_single(DECISION_KIND, lines_list,
                                  DECISION_WIDTH_FLOAT, height_float,
                                  branch.line)
        decision_id = group.entry
        group.exits = []
        below_float = height_float + GAP_FLOAT
        paths_height_float = 0.0
        for items_list, label_str, jump_str in (
                (branch.no, "No", branch.no_jump),
                (branch.yes, "Yes", branch.yes_jump)):
            exits_count_int = len(group.exits)
            part = self.place_sequence(items_list)
            if part is None:
                group.exits.append((decision_id, label_str))
            else:
                dx_float = 0.0 if label_str == "No" else max(
                    group.right, DECISION_WIDTH_FLOAT / 2) + (
                        BRANCH_GAP_FLOAT - part.left)
                part.shift_none(dx_float, below_float)
                self.attach_none(group, part, [(decision_id, label_str)])
                paths_height_float = max(paths_height_float, part.height)
            path_exits_list = group.exits[exits_count_int:]
            if self.route_jump(jump_str, path_exits_list):
                del group.exits[exits_count_int:]
        group.height = below_float + paths_height_float
        return group

    def route_jump(self, jump_str: str,
                   exits_list: list[tuple[str, str]]) -> bool:
        """Send a path ending in continue, break or return to its target.

        Args:
            jump_str: "continue", "break", "return" or "".
            exits_list: The path's exits.

        Returns:
            True when the exits were routed (they then no longer flow
            to the next block): continue to the loop's closing shape,
            break past it, return to END.
        """
        if jump_str == "return":
            self.return_exits_list.extend(exits_list)
            return True
        if jump_str in ("continue", "break") and self.loop_jumps_list:
            self.loop_jumps_list[-1][jump_str].extend(exits_list)
            return True
        return False

    def attach_none(self, group: Group, part: Group,
                    sources_list: list[tuple[str, str]]) -> None:
        """Add a placed part to a group, linking sources to its entry.

        Args:
            group: The group to extend (changed in place).
            part: The placed part.
            sources_list: (node id, label) pairs that lead into the part.

        Returns:
            None.
        """
        group.nodes.extend(part.nodes)
        group.edges.extend(part.edges)
        group.edges.extend(Edge(source_id, part.entry, label_str)
                           for source_id, label_str in sources_list)
        group.exits.extend(part.exits)
        group.left = min(group.left, part.left)
        group.right = max(group.right, part.right)

    def place_token(self, token: Token) -> Group:
        """Lay out one token.

        Args:
            token: A step, loop mark or branch.

        Returns:
            Its group.
        """
        if isinstance(token, Branch):
            return self.place_branch(token)
        if isinstance(token, LoopMark):
            return self.place_loop_mark(token)
        return self.place_step(token)

    def stack(self, groups_list: list[Group]) -> Group | None:
        """Stack groups top to bottom, each linked to the next.

        Args:
            groups_list: Placed groups in order.

        Returns:
            One group, or None for an empty list.
        """
        if not groups_list:
            return None
        whole = groups_list[0]
        for part in groups_list[1:]:
            part.shift_none(0.0, whole.height + GAP_FLOAT)
            exits_list = whole.exits
            whole.exits = []
            self.attach_none(whole, part, exits_list)
            whole.height += GAP_FLOAT + part.height
        return whole

    def place_sequence(self, items_list: list[Item]) -> Group | None:
        """Lay out a nested sequence (inside a branch) in one column.

        Args:
            items_list: The items.

        Returns:
            The group, or None when there are no items.
        """
        return self.stack([self.place_token(token)
                           for token in flatten_list(items_list)])

    def split_columns_list(self, items_list: list[Item]
                           ) -> list[list[Token]]:
        """Split top-level items into columns of at most max blocks.

        Args:
            items_list: The top-level items.

        Returns:
            The tokens of each column. A loop stays in one column; an
            item larger than the limit gets a column of its own.
        """
        columns_list: list[list[Item]] = [[]]
        count_int = 0
        for token in items_list:
            size_int = count_blocks_int(token)
            if columns_list[-1] and count_int + size_int > self.max_blocks_int:
                columns_list.append([])
                count_int = 0
            columns_list[-1].append(token)
            count_int += size_int
        if len(columns_list) > 1 and count_int <= 2:
            # A column holding only the last block or two is not worth
            # a pair of connectors: those blocks join the column before.
            columns_list[-2].extend(columns_list.pop())
        return [flatten_list(column_list) for column_list in columns_list]

    def place_column(self, tokens_list: list[Token], index_int: int,
                     total_int: int) -> Group:
        """Lay out one column with its terminators or connectors.

        Args:
            tokens_list: The column's tokens.
            index_int: The column's position.
            total_int: The number of columns.

        Returns:
            The column group.
        """
        letters_str = string.ascii_uppercase
        groups_list = []
        if index_int == 0:
            groups_list.append(self.place_terminator(self.flow.start_label))
        else:
            groups_list.append(self.place_connector(letters_str[(index_int - 1)
                                                                % 26]))
        groups_list.extend(self.place_token(token) for token in tokens_list)
        if index_int == total_int - 1:
            end_group = self.place_terminator(self.flow.end_label)
            self.extra_edges_list.extend(
                Edge(source_id, end_group.entry, label_str)
                for source_id, label_str in self.return_exits_list)
            groups_list.append(end_group)
        else:
            groups_list.append(
                self.place_connector(letters_str[index_int % 26]))
        column = self.stack(groups_list)
        assert column is not None  # it always has a start and an end
        for node in column.nodes:
            node.column = index_int
        return column

    def place_title_node(self, start_node: Node, left_float: float) -> Node:
        """The page title, centred over START but never left of the flow.

        Args:
            start_node: The placed START terminator.
            left_float: The left edge of the first column.

        Returns:
            A text node wide enough for the whole title.
        """
        width_float = max(BLOCK_WIDTH_FLOAT,
                          7.0 * len(self.flow.script_name) + 20.0)
        centre_float = start_node.x_px + start_node.width / 2
        return Node(self.make_id_str(), TEXT_KIND, [self.flow.script_name],
                    max(left_float, centre_float - width_float / 2),
                    MARGIN_FLOAT, width_float, 24.0)

    def place_terminator(self, text_str: str) -> Group:
        """A START or END terminator, wide enough for its text.

        Args:
            text_str: "START", "END", a signature or a return value.

        Returns:
            The group.
        """
        lines_list = textwrap.wrap(text_str.replace(", ", ",\u00a0"), 40,
                                   break_long_words=False) or [""]
        lines_list = [line_str.replace("\u00a0", " ")
                      for line_str in lines_list]
        width_float = max(TERMINATOR_WIDTH_FLOAT,
                          7.0 * max(map(len, lines_list)) + 36.0)
        height_float = max(TERMINATOR_HEIGHT_FLOAT,
                           len(lines_list) * LINE_HEIGHT_FLOAT + 16.0)
        return self.place_single(TERMINATOR_KIND, lines_list, width_float,
                                 height_float)

    def place_connector(self, letter_str: str) -> Group:
        """An on-page connector circle.

        Args:
            letter_str: Its letter.

        Returns:
            The group.
        """
        return self.place_single(CONNECTOR_KIND, [letter_str],
                                 CONNECTOR_SIZE_FLOAT, CONNECTOR_SIZE_FLOAT)

    def build_legend_nodes_list(self) -> list[Node]:
        """Colour swatches and names of the developed modules.

        Returns:
            Legend nodes at the top-left of the page.
        """
        nodes_list = []
        for index_int, module_str in enumerate(self.flow.modules):
            y_float = MARGIN_FLOAT + index_int * 34.0
            nodes_list.append(Node(self.make_id_str(), LEGEND_KIND, [],
                                   MARGIN_FLOAT, y_float, 40.0, 24.0,
                                   fill=self.colours_dict[module_str]))
            nodes_list.append(Node(self.make_id_str(), TEXT_KIND, [module_str],
                                   MARGIN_FLOAT + 50, y_float,
                                   LEGEND_WIDTH_FLOAT - 60, 24.0,
                                   align="left"))
        return nodes_list

    def build(self) -> Diagram:
        """Place the whole flow.

        Returns:
            The diagram with absolute coordinates.
        """
        columns_list = self.split_columns_list(self.flow.items)
        diagram = Diagram(self.flow.script_name,
                          column_count=len(columns_list))
        diagram.nodes.extend(self.build_legend_nodes_list())
        x_float = MARGIN_FLOAT + (LEGEND_WIDTH_FLOAT if self.flow.modules
                                  else 0.0)
        top_float = MARGIN_FLOAT + HEADER_HEIGHT_FLOAT
        for index_int, tokens in enumerate(columns_list):
            column = self.place_column(tokens, index_int, len(columns_list))
            column.shift_none(x_float - column.left, top_float)
            if index_int == 0:
                diagram.nodes.append(self.place_title_node(
                    column.nodes[0], x_float))
            diagram.nodes.extend(column.nodes)
            diagram.edges.extend(column.edges)
            x_float = column.right + COLUMN_GAP_FLOAT
        diagram.edges.extend(self.extra_edges_list)
        diagram.nodes[:0] = self.build_loop_frames_list(diagram.nodes)
        overflow_float = MARGIN_FLOAT - min(node.x_px
                                            for node in diagram.nodes)
        if overflow_float > 0:
            for node in diagram.nodes:
                node.x_px += overflow_float
        return diagram

    def build_loop_frames_list(self, nodes_list: list[Node]) -> list[Node]:
        """Light frames behind each loop, from its opening to closing shape.

        Args:
            nodes_list: The placed nodes.

        Returns:
            One frame per loop, outer loops first (drawn underneath),
            covering the shapes created between the loop's two shapes
            and its back arrow.
        """
        order_dict = {node.node_id: int(node.node_id[1:])
                      for node in nodes_list}
        frames_list = []
        for open_id, close_id, depth_int in sorted(
                self.loop_pairs_list, key=lambda pair: pair[2]):
            members_list = [
                node for node in nodes_list
                if order_dict[open_id] <= order_dict[node.node_id]
                <= order_dict[close_id]]
            left_float = min([node.x_px for node in members_list] + [
                compute_back_gutter_float(members_list[0], depth_int)])
            right_float = max(node.x_px + node.width for node in members_list)
            top_float = min(node.y_px for node in members_list)
            bottom_float = max(node.y_px + node.height
                               for node in members_list)
            pad_float = LOOP_FRAME_PADDING_FLOAT
            frames_list.append(Node(
                self.make_id_str(), LOOP_FRAME_KIND, [],
                left_float - pad_float, top_float - pad_float,
                right_float - left_float + 2 * pad_float,
                bottom_float - top_float + 2 * pad_float,
                fill=LOOP_FRAME_FILL_STR, column=members_list[0].column))
        return frames_list


def compute_back_gutter_float(open_node: Node, depth_int: int) -> float:
    """The x of a loop's back arrow, left of its opening shape.

    Args:
        open_node: The loop's opening shape.
        depth_int: 1 for an outermost loop, 2 inside it, and so on.

    Returns:
        The x coordinate; inner loops run closer to their shapes, so
        nested back arrows do not overlap.
    """
    return open_node.x_px - max(6.0, 26.0 - 8.0 * (depth_int - 1))


def route_back_list(source: Node, target: Node, depth_int: int
                    ) -> list[tuple[float, float]]:
    """The route of a loop's back arrow, up its left side.

    Args:
        source: The loop's closing shape.
        target: The loop's opening shape.
        depth_int: The loop's nesting depth (see Edge.back_depth).

    Returns:
        Points from the closing shape's left middle to the opening
        shape's left middle.
    """
    gutter_float = compute_back_gutter_float(target, depth_int)
    source_y = source.y_px + source.height / 2
    target_y = target.y_px + target.height / 2
    return [(source.x_px, source_y), (gutter_float, source_y),
            (gutter_float, target_y), (target.x_px, target_y)]


def layout_flow(flow: Flow, max_blocks_int: int = 10) -> Diagram:
    """Place a flow on a page.

    Args:
        flow: The flow.
        max_blocks_int: The most blocks per column (at least 3).

    Returns:
        The diagram.
    """
    return LayoutBuilder(flow, max_blocks_int).build()
