"""Check a diagram against block-diagram architecture rules.

Codes (errors make ``--check`` fail; info findings never do):

- FB001 error: the flow lacks a START or END terminator.
- FB002 error: the script name is not shown at the top.
- FB003 error: a loop is opened but not closed, or the reverse.
- FB004 error: a block has no outgoing arrow (an open end).
- FB005 error: a data source is not on the left of the block reading it.
- FB006 warning: a column has more blocks than the limit.
- FB007 error: a module colour has no legend entry.
- FB008 info: a titled block does not start with a verb.
- FB009 info: an input or output type is unknown.
- FB010 error: an arrow points to a shape that does not exist.
"""

from dataclasses import dataclass

from flowblueprint.describe import check_verb_first_bool
from flowblueprint.model import (
    CONNECTOR_KIND, DECISION_KIND, LEGEND_KIND, LOOP_CLOSE_KIND,
    LOOP_OPEN_KIND, PLOT_KIND, PROCESS_KIND, SECTION_KIND,
    SOURCE_KINDS_TUPLE,
    TERMINATOR_KIND, TEXT_KIND, UNKNOWN_DTYPE_STR, Diagram)

BLOCK_KINDS_TUPLE = (PROCESS_KIND, PLOT_KIND, DECISION_KIND,
                     LOOP_OPEN_KIND, LOOP_CLOSE_KIND)


@dataclass
class Finding:
    """One rule finding.

    Args:
        code: The rule code, such as "FB004".
        severity: "error", "warning" or "info".
        message: What is wrong.
        line: The source line, or 0.
    """

    code: str
    severity: str
    message: str
    line: int = 0


def check_terminators(diagram: Diagram) -> list[Finding]:
    """FB001 and FB002: terminators and the script name.

    Args:
        diagram: The diagram.

    Returns:
        Findings.
    """
    findings_list = []
    leaving_set = {edge.source_id for edge in diagram.edges}
    entering_set = {edge.target_id for edge in diagram.edges}
    terminators_list = [node for node in diagram.nodes
                        if node.kind == TERMINATOR_KIND]
    for word_str, is_start in (("START", True), ("END", False)):
        if not any((node.node_id in leaving_set
                    and node.node_id not in entering_set) == is_start
                   for node in terminators_list):
            findings_list.append(Finding("FB001", "error",
                                         f"missing {word_str} terminator"))
    if not any(node.kind == TEXT_KIND and node.label == [diagram.title]
               for node in diagram.nodes):
        findings_list.append(Finding("FB002", "error",
                                     "the script name is not shown"))
    return findings_list


def check_loops(diagram: Diagram) -> list[Finding]:
    """FB003: every loop has an opening and a closing shape.

    Args:
        diagram: The diagram.

    Returns:
        Findings for opening or closing shapes that are not joined to
        a partner by a loop's back arrow.
    """
    kinds_dict = {node.node_id: node.kind for node in diagram.nodes}
    joined_set = set()
    for edge in diagram.edges:
        if edge.back_depth and kinds_dict.get(edge.source_id) == (
                LOOP_CLOSE_KIND) and kinds_dict.get(edge.target_id) == (
                    LOOP_OPEN_KIND):
            joined_set.update((edge.source_id, edge.target_id))
    return [Finding("FB003", "error",
                    f"loop '{' '.join(node.label)}' is not closed",
                    node.line)
            for node in diagram.nodes
            if node.kind in (LOOP_OPEN_KIND, LOOP_CLOSE_KIND)
            and node.node_id not in joined_set]


def check_open_ends(diagram: Diagram) -> list[Finding]:
    """FB004: every block and START leads somewhere.

    Args:
        diagram: The diagram.

    Returns:
        Findings for blocks without an outgoing flow arrow; the END
        terminator and the connector that ends a column are exempt.
    """
    leaving_set = {edge.source_id for edge in diagram.edges
                   if not edge.is_side}
    entering_set = {edge.target_id for edge in diagram.edges
                    if not edge.is_side}
    findings_list = []
    for node in diagram.nodes:
        is_flow_node = node.kind in BLOCK_KINDS_TUPLE or (
            node.kind == TERMINATOR_KIND
            and node.node_id not in entering_set)
        is_column_end = node.kind == CONNECTOR_KIND and (
            node.node_id in entering_set)
        if is_flow_node and not is_column_end and (
                node.node_id not in leaving_set):
            findings_list.append(Finding(
                "FB004", "error",
                f"'{' '.join(node.label)[:40]}' has no outgoing arrow",
                node.line))
    return findings_list


def check_sources(diagram: Diagram) -> list[Finding]:
    """FB005: data read by a block comes from its left.

    Args:
        diagram: The diagram.

    Returns:
        Findings.
    """
    nodes_dict = {node.node_id: node for node in diagram.nodes}
    findings_list = []
    for edge in diagram.edges:
        source = nodes_dict.get(edge.source_id)
        target = nodes_dict.get(edge.target_id)
        if source is None or target is None:
            findings_list.append(Finding(
                "FB010", "error",
                f"an arrow points to a missing shape ({edge.source_id} -> "
                f"{edge.target_id})"))
            continue
        if (source.kind in SOURCE_KINDS_TUPLE
                and source.x_px + source.width > target.x_px):
            findings_list.append(Finding(
                "FB005", "error",
                f"'{' '.join(source.label)}' is not left of its block",
                target.line))
    return findings_list


def check_columns(diagram: Diagram, max_blocks_int: int) -> list[Finding]:
    """FB006: columns stay within the block limit.

    Args:
        diagram: The diagram.
        max_blocks_int: The limit.

    Returns:
        Findings.
    """
    counts_dict: dict[int, int] = {}
    for node in diagram.nodes:
        if node.kind in BLOCK_KINDS_TUPLE:
            counts_dict[node.column] = counts_dict.get(node.column, 0) + 1
    return [Finding("FB006", "warning",
                    f"column {column_int + 1} has {count_int} blocks "
                    f"(limit {max_blocks_int}); a single loop or "
                    "decision this long cannot be split")
            for column_int, count_int in sorted(counts_dict.items())
            if count_int > max_blocks_int]


def check_legend(diagram: Diagram) -> list[Finding]:
    """FB007: every block colour is explained by the legend.

    Args:
        diagram: The diagram.

    Returns:
        Findings.
    """
    legend_set = {node.fill for node in diagram.nodes
                  if node.kind == LEGEND_KIND}
    used_set = {node.fill for node in diagram.nodes
                if node.kind in BLOCK_KINDS_TUPLE and node.fill}
    return [Finding("FB007", "error", f"colour {fill_str} has no legend")
            for fill_str in sorted(used_set - legend_set)]


def check_wording(diagram: Diagram) -> list[Finding]:
    """FB008 and FB009: verb-first titles and known types.

    Args:
        diagram: The diagram.

    Returns:
        Info findings.
    """
    findings_list = []
    for node in diagram.nodes:
        if node.kind != SECTION_KIND and node.has_title and node.label and (
                not check_verb_first_bool(node.label[0])):
            findings_list.append(Finding(
                "FB008", "info",
                f"title '{node.label[0]}' does not start with a verb",
                node.line))
        text_str = " ".join(node.label)
        if node.kind in BLOCK_KINDS_TUPLE and (
                f": {UNKNOWN_DTYPE_STR}" in text_str):
            findings_list.append(Finding(
                "FB009", "info", "a type is unknown in "
                f"'{node.label[0][:40]}'", node.line))
    return findings_list


def check_diagram(diagram: Diagram, max_blocks_int: int = 10
                  ) -> list[Finding]:
    """Run every rule.

    Args:
        diagram: The diagram.
        max_blocks_int: The column block limit.

    Returns:
        Findings, errors first, then by line.
    """
    findings_list = (check_terminators(diagram) + check_loops(diagram)
                     + check_open_ends(diagram) + check_sources(diagram)
                     + check_columns(diagram, max_blocks_int)
                     + check_legend(diagram) + check_wording(diagram))
    order_dict = {"error": 0, "warning": 1, "info": 2}
    return sorted(findings_list, key=lambda finding: (
        order_dict[finding.severity], finding.line, finding.code))
