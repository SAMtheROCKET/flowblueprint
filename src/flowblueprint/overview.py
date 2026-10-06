"""Place a Project on a page as rows of files ordered by import depth.

Files nothing imports (entry points, notebooks, unused modules) form the
top row; each other file sits one row below the deepest file that
imports it, so arrows point down from a file to the files it uses.
Import cycles are cut at the arrow that closes them. Within a row,
files are ordered by the position of the files importing them, which
keeps most arrows short and uncrossed.
"""

from flowblueprint.layout import (
    BLOCK_CHARS_INT, BLOCK_PADDING_FLOAT, BLOCK_WIDTH_FLOAT,
    HEADER_HEIGHT_FLOAT, LEGEND_WIDTH_FLOAT, LINE_HEIGHT_FLOAT,
    MARGIN_FLOAT, wrap_list)
from flowblueprint.model import (
    LEGEND_KIND, PROCESS_KIND, TEXT_KIND, Diagram, Edge, Node)
from flowblueprint.project import (
    ENTRY_KIND, MODULE_KIND, NOTEBOOK_KIND, PACKAGE_KIND, FileInfo, Project,
    name_some_str)
from flowblueprint.routing import route_overview_none

KIND_FILLS_DICT = {ENTRY_KIND: "#d5e8d4", NOTEBOOK_KIND: "#fff2cc",
                   MODULE_KIND: "#dae8fc", PACKAGE_KIND: "#e1d5e7"}
KIND_LEGENDS_DICT = {ENTRY_KIND: "entry point (runs)",
                     NOTEBOOK_KIND: "notebook", MODULE_KIND: "module",
                     PACKAGE_KIND: "package or folder"}
ROW_GAP_FLOAT = 70.0
BLOCK_GAP_FLOAT = 40.0
KINDS_ORDER_TUPLE = (ENTRY_KIND, NOTEBOOK_KIND, PACKAGE_KIND, MODULE_KIND)


def find_back_edges_set(count_int: int, edges_list: list[tuple[int, int]],
                        roots_list: list[int]) -> set[tuple[int, int]]:
    """The arrows that close import cycles.

    Args:
        count_int: The number of files.
        edges_list: (importer, imported) pairs.
        roots_list: Files to start from first (those nothing imports).

    Returns:
        The edges found pointing back to a file still being visited by
        a depth-first search.
    """
    children_list: list[list[int]] = [[] for _ in range(count_int)]
    for source_int, target_int in edges_list:
        children_list[source_int].append(target_int)
    state_list = [0] * count_int  # 0 new, 1 visiting, 2 done
    back_set: set[tuple[int, int]] = set()
    for root_int in roots_list + list(range(count_int)):
        if state_list[root_int]:
            continue
        state_list[root_int] = 1
        stack_list = [(root_int, iter(children_list[root_int]))]
        while stack_list:
            node_int, children = stack_list[-1]
            child_int = next(children, None)
            if child_int is None:
                state_list[node_int] = 2
                stack_list.pop()
            elif state_list[child_int] == 1:
                back_set.add((node_int, child_int))
            elif state_list[child_int] == 0:
                state_list[child_int] = 1
                stack_list.append((child_int,
                                   iter(children_list[child_int])))
    return back_set


def compute_rows_list(project: Project) -> list[list[int]]:
    """Group files into rows by import depth.

    Args:
        project: The project.

    Returns:
        Rows of file indices, top row first, each row in drawing order.
    """
    count_int = len(project.files)
    imported_set = {target_int for _, target_int in project.edges}
    roots_list = [index_int for index_int in range(count_int)
                  if index_int not in imported_set]
    back_set = find_back_edges_set(count_int, project.edges, roots_list)
    forward_list = [edge for edge in project.edges if edge not in back_set]
    depth_list = [0] * count_int
    for _ in range(count_int):  # longest paths in an acyclic graph
        changed = False
        for source_int, target_int in forward_list:
            if depth_list[target_int] < depth_list[source_int] + 1:
                depth_list[target_int] = depth_list[source_int] + 1
                changed = True
        if not changed:
            break
    rows_list: list[list[int]] = [[] for _ in range(max(depth_list,
                                                        default=-1) + 1)]
    for index_int in range(count_int):
        rows_list[depth_list[index_int]].append(index_int)
    return order_rows_list(project, rows_list, forward_list)


def make_row_key_tuple(project: Project, index_int: int,
                       edges_list: list[tuple[int, int]],
                       position_dict: dict[int, float]) -> tuple:
    """The sort key of a file within its row.

    Args:
        project: The project.
        index_int: The file.
        edges_list: The acyclic (importer, imported) pairs.
        position_dict: Positions of files in the rows above, centred
            on 0.

    Returns:
        (mean position of its importers, kind order, path).
    """
    info = project.files[index_int]
    parents_list = [position_dict[source_int]
                    for source_int, target_int in edges_list
                    if target_int == index_int and source_int in position_dict]
    centre_float = (sum(parents_list) / len(parents_list) if parents_list
                    else 0.0)
    return (centre_float, KINDS_ORDER_TUPLE.index(info.kind),
            info.path.as_posix())


def order_rows_list(project: Project, rows_list: list[list[int]],
                    edges_list: list[tuple[int, int]]) -> list[list[int]]:
    """Order each row: entry points first on top, then by importers.

    Args:
        project: The project.
        rows_list: Rows of file indices.
        edges_list: The acyclic (importer, imported) pairs.

    Returns:
        The rows in drawing order.
    """
    position_dict: dict[int, float] = {}
    ordered_list = []
    for row_list in rows_list:
        row_list = sorted(row_list, key=lambda index_int: make_row_key_tuple(
            project, index_int, edges_list, position_dict))
        for place_int, index_int in enumerate(row_list):
            position_dict[index_int] = place_int - (len(row_list) - 1) / 2
        ordered_list.append(row_list)
    return ordered_list


def find_common_folder_int(files_list: list[FileInfo]) -> int:
    """How many leading folders every file path shares.

    Args:
        files_list: The project files.

    Returns:
        The number of shared leading folder parts (for example 2 when
        every file lies below src/pkg/), which block titles leave out.
    """
    folders_list = [info.path.parts[:-1] for info in files_list]
    if not folders_list:
        return 0
    shared_int = min(len(parts_tuple) for parts_tuple in folders_list)
    for index_int in range(shared_int):
        if len({parts_tuple[index_int] for parts_tuple in folders_list}) > 1:
            return index_int
    return shared_int


def build_file_label_list(info: FileInfo, skip_int: int = 0) -> list[str]:
    """The label lines of a file's block.

    Args:
        info: The file.
        skip_int: Leading folders shared by all files, left out of the
            title.

    Returns:
        Path (the title), kind and size, summary, reads and writes.
    """
    sizes_list = []
    for count_int, noun_str in ((info.functions_count, "function"),
                                (info.classes_count, "class")):
        if count_int:
            plural_str = "es" if noun_str == "class" else "s"
            sizes_list.append(f"{count_int} {noun_str}"
                              f"{plural_str if count_int > 1 else ''}")
    kind_str = info.kind + (": " + ", ".join(sizes_list) if sizes_list
                            else "")
    title_str = "/".join(info.path.parts[skip_int:]) or info.path.name
    if not info.path.suffix:
        title_str += "/"  # a grouped folder
    lines_list = [title_str, kind_str]
    for text_str in (info.summary,
                     "reads: " + name_some_str(info.reads) if info.reads
                     else "",
                     "writes: " + name_some_str(info.writes) if info.writes
                     else ""):
        if text_str:
            lines_list.extend(wrap_list(text_str, BLOCK_CHARS_INT))
    return lines_list


def build_legend_list(kinds_list: list[str]) -> list[Node]:
    """Colour swatches and names of the file kinds present.

    Args:
        kinds_list: The kinds, in legend order.

    Returns:
        Swatch and text nodes, each swatch followed by its text.
    """
    nodes_list = []
    for index_int, kind_str in enumerate(kinds_list):
        y_float = MARGIN_FLOAT + HEADER_HEIGHT_FLOAT + index_int * 34.0
        nodes_list.append(Node(f"legend{index_int}", LEGEND_KIND, [],
                               MARGIN_FLOAT, y_float, 40.0, 24.0,
                               fill=KIND_FILLS_DICT[kind_str]))
        nodes_list.append(Node(f"legend{index_int}text", TEXT_KIND,
                               [KIND_LEGENDS_DICT[kind_str]],
                               MARGIN_FLOAT + 50, y_float,
                               LEGEND_WIDTH_FLOAT - 60, 24.0, align="left"))
    return nodes_list


def place_row_list(project: Project, row_list: list[int], skip_int: int,
                   x_float: float, y_float: float) -> list[Node]:
    """Place one row of file blocks.

    Args:
        project: The project.
        row_list: The row's file indices, in drawing order.
        skip_int: Leading folders left out of the titles.
        x_float: The left edge of the row.
        y_float: The top edge of the row.

    Returns:
        The row's block nodes, left to right.
    """
    nodes_list = []
    for index_int in row_list:
        info = project.files[index_int]
        label_list = build_file_label_list(info, skip_int)
        height_float = (len(label_list) * LINE_HEIGHT_FLOAT
                        + 2 * BLOCK_PADDING_FLOAT)
        nodes_list.append(Node(
            f"file{index_int}", PROCESS_KIND, label_list, x_float, y_float,
            BLOCK_WIDTH_FLOAT, height_float, fill=KIND_FILLS_DICT[info.kind],
            has_title=True))
        x_float += BLOCK_WIDTH_FLOAT + BLOCK_GAP_FLOAT
    return nodes_list


def layout_project(project: Project) -> Diagram:
    """Place a project overview on a page.

    Args:
        project: The project.

    Returns:
        The diagram: a title, a legend of file kinds, one block per
        file in rows, and an arrow from each file to each project file
        it imports.
    """
    diagram = Diagram(f"{project.name} architecture")
    skip_int = find_common_folder_int(project.files)
    kinds_list = [kind_str for kind_str in KIND_FILLS_DICT
                  if any(info.kind == kind_str for info in project.files)]
    diagram.nodes.extend(build_legend_list(kinds_list))
    rows_list = compute_rows_list(project)
    widest_int = max((len(row_list) for row_list in rows_list), default=1)
    left_float = MARGIN_FLOAT + LEGEND_WIDTH_FLOAT
    full_width_float = (widest_int * BLOCK_WIDTH_FLOAT
                        + (widest_int - 1) * BLOCK_GAP_FLOAT)
    diagram.nodes.append(Node(
        "title", TEXT_KIND, [diagram.title], left_float, MARGIN_FLOAT,
        max(full_width_float, BLOCK_WIDTH_FLOAT), 24.0))
    y_float = MARGIN_FLOAT + HEADER_HEIGHT_FLOAT
    rows_nodes_list = []
    for row_list in rows_list:
        row_width_float = (len(row_list) * BLOCK_WIDTH_FLOAT
                           + (len(row_list) - 1) * BLOCK_GAP_FLOAT)
        nodes_list = place_row_list(
            project, row_list, skip_int,
            left_float + (full_width_float - row_width_float) / 2, y_float)
        diagram.nodes.extend(nodes_list)
        rows_nodes_list.append(nodes_list)
        y_float += max(node.height for node in nodes_list) + ROW_GAP_FLOAT
    diagram.edges.extend(Edge(f"file{source_int}", f"file{target_int}",
                              enters_top=True)
                         for source_int, target_int in project.edges)
    route_overview_none(diagram, rows_nodes_list, left_float, ROW_GAP_FLOAT)
    return diagram
