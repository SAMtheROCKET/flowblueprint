"""Pack several steps into one higher-level block.

One function is not always one block. At the summary level, runs of
consecutive process steps are packed into blocks of a few operations
each; an override file can also name groups explicitly, at any level.
A packed block lists its operations, takes the inputs its steps read
from outside the group, and gives the outputs the rest of the flow can
use. Loops, decisions and plots keep their own shapes.
"""

from collections.abc import Callable

from flowblueprint import describe
from flowblueprint.model import PROCESS_KIND, Branch, Item, Loop, Port, Step


def describe_operation_str(step: Step) -> str:
    """One short phrase for a step inside a packed block.

    Args:
        step: The step.

    Returns:
        "load station readings" for a titled step, else its
        description without the full stop.
    """
    if step.title:
        return " ".join(describe.split_words_list(step.title))
    text_str = step.description.rstrip(".")
    return text_str[:1].lower() + text_str[1:]


def make_group_title_str(steps_list: list[Step]) -> str:
    """A verb-first title from the leading verbs of the steps.

    Args:
        steps_list: The packed steps.

    Returns:
        A title such as "Load, repair and flag".
    """
    verbs_list = []
    for step in steps_list:
        words_list = describe_operation_str(step).split()
        verb_str = words_list[0].lower() if words_list else ""
        if verb_str and verb_str not in verbs_list:
            verbs_list.append(verb_str)
    return describe.make_sentence_str(
        describe.join_names_str(verbs_list)).rstrip(".")


def collect_group_ports_tuple(steps_list: list[Step]
                              ) -> tuple[list[Port], list[Port]]:
    """Inputs read from outside a group and outputs it leaves behind.

    Args:
        steps_list: The packed steps, in order.

    Returns:
        (inputs, outputs). Values made and used only inside the group
        are left out, except the last step's outputs.
    """
    inputs_list: list[Port] = []
    produced_set: set[str] = set()
    for step in steps_list:
        for port in step.inputs:
            if port.name not in produced_set and port.name not in {
                    known.name for known in inputs_list}:
                inputs_list.append(port)
        produced_set.update(port.name for port in step.outputs)
    outputs_dict: dict[str, Port] = {}
    for index_int, step in enumerate(steps_list):
        later_set = {port.name for later in steps_list[index_int + 1:]
                     for port in later.inputs}
        for port in step.outputs:
            if port.name not in later_set or step is steps_list[-1]:
                outputs_dict[port.name] = port
    return inputs_list, list(outputs_dict.values())


def pack_steps(steps_list: list[Step], title_str: str = "",
               description_str: str = "") -> Step:
    """Pack consecutive steps into one block.

    Args:
        steps_list: The steps, in order.
        title_str: A title; derived from the steps when "".
        description_str: A description; the list of operations when "".

    Returns:
        The packed step, keeping every file, database and plot output.
    """
    inputs_list, outputs_list = collect_group_ports_tuple(steps_list)
    modules_set = {step.module for step in steps_list}
    description_str = description_str or describe.make_sentence_str(
        "; ".join(describe_operation_str(step) for step in steps_list))
    return Step(PROCESS_KIND, title_str or make_group_title_str(steps_list),
                description_str, inputs_list, outputs_list,
                modules_set.pop() if len(modules_set) == 1 else "",
                steps_list[0].line,
                [source for step in steps_list for source in step.sources],
                packed=True)


def map_nested_list(items_list: list[Item],
                    transform: Callable[[list[Item]], list[Item]]
                    ) -> list[Item]:
    """Apply a sequence transform to every nested sequence.

    Args:
        items_list: Items of one sequence.
        transform: Function from a list of items to a list of items.

    Returns:
        The transformed sequence, with loop and branch bodies
        transformed too.
    """
    for item in items_list:
        if isinstance(item, Loop):
            item.body = map_nested_list(item.body, transform)
        elif isinstance(item, Branch):
            item.yes = map_nested_list(item.yes, transform)
            item.no = map_nested_list(item.no, transform)
    return transform(items_list)


def pack_runs_list(sequence_list: list[Item], size_int: int) -> list[Item]:
    """Pack runs of unpacked process steps in one sequence.

    Args:
        sequence_list: Items of one sequence.
        size_int: The most operations per packed block.

    Returns:
        The sequence with each run split into packed chunks.
    """
    packed_list: list[Item] = []
    run_list: list[Step] = []
    for item in [*sequence_list, None]:
        if (isinstance(item, Step) and item.kind == PROCESS_KIND
                and not item.packed):
            run_list.append(item)
            continue
        for start_int in range(0, len(run_list), size_int):
            chunk_list = run_list[start_int:start_int + size_int]
            packed_list.append(chunk_list[0] if len(chunk_list) == 1
                               else pack_steps(chunk_list))
        run_list = []
        if item is not None:
            packed_list.append(item)
    return packed_list


def summarise_items_list(items_list: list[Item],
                         group_size_int: int = 4) -> list[Item]:
    """Pack runs of process steps into blocks of up to group_size_int.

    Args:
        items_list: The flow's items.
        group_size_int: The most operations per packed block (at
            least 2).

    Returns:
        The summary-level items.
    """
    size_int = max(2, group_size_int)
    return map_nested_list(items_list, lambda sequence_list: pack_runs_list(
        sequence_list, size_int))


def find_group_int(item: Item, groups_list: list[dict]) -> int:
    """The index of the override group naming a step, or -1.

    Args:
        item: An item.
        groups_list: Override group entries.

    Returns:
        The first group whose "functions" list holds the step's title.
    """
    for index_int, group_dict in enumerate(groups_list):
        if isinstance(item, Step) and item.title and item.title in (
                group_dict.get("functions", [])):
            return index_int
    return -1


def pack_groups_list(sequence_list: list[Item],
                     groups_list: list[dict]) -> list[Item]:
    """Pack maximal runs of steps named by one group, in one sequence.

    Args:
        sequence_list: Items of one sequence.
        groups_list: Override group entries.

    Returns:
        The sequence with each run packed into its group's block.
    """
    packed_list: list[Item] = []
    index_int = 0
    while index_int < len(sequence_list):
        group_int = find_group_int(sequence_list[index_int], groups_list)
        end_int = index_int + 1
        while group_int >= 0 and end_int < len(sequence_list) and (
                find_group_int(sequence_list[end_int], groups_list)
                == group_int):
            end_int += 1
        if group_int < 0:
            packed_list.append(sequence_list[index_int])
        else:
            group_dict = groups_list[group_int]
            packed_list.append(pack_steps(
                sequence_list[index_int:end_int],
                str(group_dict.get("title", "")),
                str(group_dict.get("description", ""))))
        index_int = end_int
    return packed_list


def apply_groups_list(items_list: list[Item],
                      groups_list: list[dict]) -> list[Item]:
    """Pack the steps named by override groups.

    Args:
        items_list: The flow's items.
        groups_list: Override entries, each with "functions" (step
            titles), and optionally "title" and "description".

    Returns:
        The items, with each maximal run of consecutive steps whose
        titles all belong to one group packed into that group's block.
    """
    return map_nested_list(items_list, lambda sequence_list: (
        pack_groups_list(sequence_list, groups_list)))
