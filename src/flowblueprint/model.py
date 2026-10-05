"""Data model shared by the extractor, the layout and the renderers.

A Flow is what a script does, in order: Steps (one block each), Loops
and Branches. A Diagram is the same flow placed on a page: Nodes with
positions and Edges between them. Nothing here touches the source code.
"""

from dataclasses import dataclass, field

UNKNOWN_DTYPE_STR = "unknown"

# Step kinds, named after the flowchart shapes they become.
PROCESS_KIND = "process"
PLOT_KIND = "plot"
DATA_KIND = "data"
DATABASE_KIND = "database"
STORAGE_KIND = "storage"
DOCUMENT_KIND = "document"
SOURCE_KINDS_TUPLE = (DATA_KIND, DATABASE_KIND, STORAGE_KIND, DOCUMENT_KIND)

# Diagram node kinds that are not Step kinds.
TERMINATOR_KIND = "terminator"
DECISION_KIND = "decision"
LOOP_OPEN_KIND = "loop_open"
LOOP_CLOSE_KIND = "loop_close"
CONNECTOR_KIND = "connector"
TEXT_KIND = "text"
LEGEND_KIND = "legend"


@dataclass
class Port:
    """A named input or output of a step, with its data type.

    Args:
        name: The variable or expression as written in the source.
        dtype: The type as far as the source shows it, else "unknown".
    """

    name: str
    dtype: str = UNKNOWN_DTYPE_STR


@dataclass
class Source:
    """A file, database or storage location a step reads or writes.

    Args:
        kind: One of DATA_KIND, DATABASE_KIND, STORAGE_KIND or
            DOCUMENT_KIND.
        label: The file name or expression shown inside the shape.
        is_output: True when the step writes to it (drawn on the right).
    """

    kind: str
    label: str
    is_output: bool = False


@dataclass
class Step:
    """One block: a call, a group of plain statements or a plot.

    Args:
        kind: PROCESS_KIND or PLOT_KIND.
        title: The function name in bold, or "" for plain steps.
        description: A short sentence about what the step does.
        inputs: The values the step reads.
        outputs: The values the step produces.
        module: The developed (local) module the function comes from,
            which decides the block colour; "" for none.
        line: The first source line of the step.
        sources: Files, databases and storage it reads or writes.
        packed: True for a block that packs several operations.
    """

    kind: str
    title: str = ""
    description: str = ""
    inputs: list[Port] = field(default_factory=list)
    outputs: list[Port] = field(default_factory=list)
    module: str = ""
    line: int = 0
    sources: list[Source] = field(default_factory=list)
    packed: bool = False


@dataclass
class Loop:
    """A for or while loop: an opening and a closing loop-limit shape.

    Args:
        header: The short loop text, such as "for row in rows_list".
        body: The items repeated inside the loop.
        line: The source line of the loop statement.
    """

    header: str
    body: list["Item"] = field(default_factory=list)
    line: int = 0


@dataclass
class Branch:
    """An if statement: a decision diamond with Yes and No paths.

    Args:
        condition: The decision text shown in the diamond.
        yes: Items run when the condition holds.
        no: Items run otherwise (elif chains nest here).
        line: The source line of the if statement.
        yes_jump: "continue", "break" or "return" when the Yes path
            ends with that statement, else "".
        no_jump: The same for the No path.
    """

    condition: str
    yes: list["Item"] = field(default_factory=list)
    no: list["Item"] = field(default_factory=list)
    line: int = 0
    yes_jump: str = ""
    no_jump: str = ""


type Item = Step | Loop | Branch


@dataclass
class Note:
    """Something the diagram leaves out, with the reason and location.

    Args:
        line: The source line.
        message: What was left out and why.
    """

    line: int
    message: str


@dataclass
class Flow:
    """The ordered flow of one script.

    Args:
        script_name: The file name shown at the top of the diagram.
        items: The steps, loops and branches from start to end.
        modules: Developed modules used, in order of first use.
        notes: Statements not drawn, with reasons.
    """

    script_name: str
    items: list[Item] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)


@dataclass
class Node:
    """A placed shape. Coordinates are the top-left corner in pixels.

    Args:
        node_id: A unique id within the diagram.
        kind: A Step, Source or diagram node kind.
        label: The plain-text lines shown in the shape; the first line
            is bold when the node has a title.
        x_px: Left edge.
        y_px: Top edge.
        width: Width.
        height: Height.
        fill: Fill colour as "#rrggbb", or "" for the default.
        has_title: True when the first label line is a bold title.
        column: The diagram column the node belongs to.
        line: The source line it came from, or 0.
        align: Text alignment, "center" or "left".
    """

    node_id: str
    kind: str
    label: list[str]
    x_px: float
    y_px: float
    width: float
    height: float
    fill: str = ""
    has_title: bool = False
    column: int = 0
    line: int = 0
    align: str = "center"


@dataclass
class Edge:
    """An arrow between two nodes.

    Args:
        source_id: The node the arrow leaves.
        target_id: The node the arrow points to.
        label: Text on the arrow, such as "Yes" or "No".
        is_side: True for arrows to and from data shapes beside a block.
    """

    source_id: str
    target_id: str
    label: str = ""
    is_side: bool = False


@dataclass
class Diagram:
    """A flow placed on a page, ready to render.

    Args:
        title: The script name.
        nodes: All shapes, including text and legend entries.
        edges: All arrows.
        column_count: Number of columns the flow was split into.
    """

    title: str
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    column_count: int = 1
