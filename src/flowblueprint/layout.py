"""Place a flow on a page, top to bottom and left to right.

Each piece is laid out around a vertical spine at x = 0 and then moved
into place. Loops become an opening and a closing loop-limit shape in
the sequence, so a long loop may continue in the next column. A column
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
    LOOP_OPEN_KIND, TERMINATOR_KIND, TEXT_KIND, Branch, Diagram,
    Edge, Flow, Item, Loop, Node, Port, Step)

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
    """

    header: str
    is_open: bool
    line: int = 0


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
            tokens_list.append(LoopMark(item.header, False, item.line))
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
        self.loop_jumps_list: list[dict[str, list[tuple[str, str]]]] = []
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
        lines_list = wrap_list(mark.header, BLOCK_CHARS_INT)
        height_float = max(44.0, len(lines_list) * LINE_HEIGHT_FLOAT + 22)
        kind_str = LOOP_OPEN_KIND if mark.is_open else LOOP_CLOSE_KIND
        group = self.place_single(kind_str, lines_list, BLOCK_WIDTH_FLOAT + 20,
                                  height_float, mark.line)
        if mark.is_open:
            self.loop_jumps_list.append({"continue": [], "break": []})
        elif self.loop_jumps_list:
            jumps_dict = self.loop_jumps_list.pop()
            self.extra_edges_list.extend(
                Edge(source_id, group.entry, label_str)
                for source_id, label_str in jumps_dict["continue"])
            group.exits.extend(jumps_dict["break"])
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

    def split_columns_list(self, tokens_list: list[Token]
                           ) -> list[list[Token]]:
        """Split top-level tokens into columns of at most max blocks.

        Args:
            tokens_list: The top-level tokens.

        Returns:
            The tokens of each column; a token larger than the limit
            gets a column of its own.
        """
        columns_list: list[list[Token]] = [[]]
        count_int = 0
        for token in tokens_list:
            size_int = count_blocks_int(token)
            if columns_list[-1] and count_int + size_int > self.max_blocks_int:
                columns_list.append([])
                count_int = 0
            columns_list[-1].append(token)
            count_int += size_int
        return columns_list

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
            groups_list.append(self.place_single(TERMINATOR_KIND, ["START"],
                                                 TERMINATOR_WIDTH_FLOAT,
                                                 TERMINATOR_HEIGHT_FLOAT))
        else:
            groups_list.append(self.place_connector(letters_str[(index_int - 1)
                                                                % 26]))
        groups_list.extend(self.place_token(token) for token in tokens_list)
        if index_int == total_int - 1:
            end_group = self.place_single(TERMINATOR_KIND, ["END"],
                                          TERMINATOR_WIDTH_FLOAT,
                                          TERMINATOR_HEIGHT_FLOAT)
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
        tokens_list = flatten_list(self.flow.items)
        columns_list = self.split_columns_list(tokens_list)
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
                start_node = column.nodes[0]
                diagram.nodes.append(Node(
                    self.make_id_str(), TEXT_KIND, [self.flow.script_name],
                    start_node.x_px + start_node.width / 2
                    - BLOCK_WIDTH_FLOAT / 2, MARGIN_FLOAT,
                    BLOCK_WIDTH_FLOAT, 24.0))
            diagram.nodes.extend(column.nodes)
            diagram.edges.extend(column.edges)
            x_float = column.right + COLUMN_GAP_FLOAT
        diagram.edges.extend(self.extra_edges_list)
        return diagram


def layout_flow(flow: Flow, max_blocks_int: int = 10) -> Diagram:
    """Place a flow on a page.

    Args:
        flow: The flow.
        max_blocks_int: The most blocks per column (at least 3).

    Returns:
        The diagram.
    """
    return LayoutBuilder(flow, max_blocks_int).build()
