"""Render a Diagram as a Mermaid flowchart.

Mermaid text renders directly in GitHub and GitLab Markdown, Notion,
Obsidian and many documentation sites, so a diagram can live in a
README next to the code. Mermaid places the shapes itself; positions,
column connectors and the drawn legend of the Diagram are not used.
Module colours become class styles with a legend subgraph.
"""

import json

from flowblueprint.model import (
    CONNECTOR_KIND, DATA_KIND, DATABASE_KIND, DECISION_KIND, DOCUMENT_KIND,
    LEGEND_KIND, LOOP_CLOSE_KIND, LOOP_OPEN_KIND, PLOT_KIND, STORAGE_KIND,
    TERMINATOR_KIND, TEXT_KIND, Diagram, Node)

# Opening and closing brackets of each shape, from Mermaid's classic
# flowchart shapes (supported by every current renderer).
SHAPE_BRACKETS_DICT = {
    TERMINATOR_KIND: ("([", "])"),
    DECISION_KIND: ("{", "}"),
    DATA_KIND: ("[/", "/]"),
    DATABASE_KIND: ("[(", ")]"),
    STORAGE_KIND: ("[[", "]]"),
    DOCUMENT_KIND: (">", "]"),
    PLOT_KIND: (">", "]"),
    LOOP_OPEN_KIND: ("{{", "}}"),
    LOOP_CLOSE_KIND: ("{{", "}}"),
    CONNECTOR_KIND: ("((", "))"),
}
ESCAPES_TUPLE = (("&", "#amp;"), ('"', "#quot;"), ("<", "#lt;"),
                 (">", "#gt;"), ("|", "#124;"), ("`", "#96;"))


def escape_text_str(text_str: str) -> str:
    """Escape text for a quoted Mermaid label.

    Args:
        text_str: Plain text.

    Returns:
        The text with Mermaid entity codes for characters that would
        end the label or be read as markup.
    """
    for character_str, code_str in ESCAPES_TUPLE:
        text_str = text_str.replace(character_str, code_str)
    return text_str


def format_label_str(node: Node) -> str:
    """A node's label: a bold title, then the other lines.

    Args:
        node: The node.

    Returns:
        The quoted label text with <br/> between lines.
    """
    lines_list = [escape_text_str(line_str) for line_str in node.label]
    if node.has_title and lines_list:
        lines_list[0] = f"<b>{lines_list[0]}</b>"
    return '"' + "<br/>".join(lines_list) + '"'


def collect_legend_dict(diagram: Diagram) -> dict[str, str]:
    """Map each legend colour to the module name shown beside it.

    Args:
        diagram: The diagram, whose legend swatches are each followed
            by their text node.

    Returns:
        Fill colour -> module name, in legend order.
    """
    legend_dict = {}
    nodes_list = diagram.nodes
    for index_int, node in enumerate(nodes_list[:-1]):
        following = nodes_list[index_int + 1]
        if node.kind == LEGEND_KIND and following.kind == TEXT_KIND:
            legend_dict[node.fill] = " ".join(following.label)
    return legend_dict


def render_mermaid_str(diagram: Diagram) -> str:
    """Render a diagram as a Mermaid flowchart.

    Args:
        diagram: The diagram.

    Returns:
        Mermaid text, starting with a title front matter block.
    """
    legend_dict = collect_legend_dict(diagram)
    classes_dict = {fill_str: f"module{index_int}" for index_int, fill_str
                    in enumerate(legend_dict, start=1)}
    ids_dict: dict[str, str] = {}
    lines_list = ["---", f"title: {json.dumps(diagram.title)}", "---",
                  "flowchart TD"]
    for node in diagram.nodes:
        if node.kind in (TEXT_KIND, LEGEND_KIND):
            continue
        ids_dict[node.node_id] = f"n{len(ids_dict) + 1}"
        opening_str, closing_str = SHAPE_BRACKETS_DICT.get(
            node.kind, ("[", "]"))
        class_str = (f":::{classes_dict[node.fill]}"
                     if node.fill in classes_dict else "")
        lines_list.append(f"    {ids_dict[node.node_id]}{opening_str}"
                          f"{format_label_str(node)}{closing_str}"
                          f"{class_str}")
    for edge in diagram.edges:
        if edge.source_id not in ids_dict or edge.target_id not in ids_dict:
            continue
        arrow_str = "-.->" if edge.is_side else "-->"
        label_str = (f'|"{escape_text_str(edge.label)}"|' if edge.label
                     else "")
        lines_list.append(f"    {ids_dict[edge.source_id]} {arrow_str}"
                          f"{label_str} {ids_dict[edge.target_id]}")
    lines_list.extend(list_legend_lines_list(legend_dict, classes_dict))
    return "\n".join(lines_list) + "\n"


def list_legend_lines_list(legend_dict: dict[str, str],
                           classes_dict: dict[str, str]) -> list[str]:
    """Class styles for module colours and a legend subgraph.

    Args:
        legend_dict: Fill colour -> module name.
        classes_dict: Fill colour -> class name.

    Returns:
        Mermaid lines; [] when no module is coloured.
    """
    if not legend_dict:
        return []
    lines_list = ['    subgraph legend["Legend"]']
    for index_int, (fill_str, module_str) in enumerate(legend_dict.items(),
                                                       start=1):
        lines_list.append(f'        legend{index_int}["'
                          f'{escape_text_str(module_str)}"]:::'
                          f"{classes_dict[fill_str]}")
    lines_list.append("    end")
    for fill_str, class_str in classes_dict.items():
        lines_list.append(f"    classDef {class_str} fill:{fill_str},"
                          "stroke:#222222,color:#000000")
    return lines_list


def render_markdown_str(diagram: Diagram, notes_list: list[str]) -> str:
    """A Markdown document holding the Mermaid flowchart.

    Args:
        diagram: The diagram.
        notes_list: Lines about what the diagram leaves out.

    Returns:
        Markdown text with a heading, the fenced flowchart and notes.
    """
    parts_list = [f"# {diagram.title}", "",
                  "Architecture generated by FlowBlueprint from the source"
                  " code, without running it.", "", "```mermaid",
                  render_mermaid_str(diagram).rstrip("\n"), "```", ""]
    if notes_list:
        parts_list.extend(["## Not drawn", ""])
        parts_list.extend(f"- {note_str}" for note_str in notes_list)
        parts_list.append("")
    return "\n".join(parts_list)
