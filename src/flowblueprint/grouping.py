"""Group a large project's files into one block per sub-package.

A project overview with hundreds of blocks is hard to read. Grouping
keeps the first N folder levels of each path: every file below such a
folder joins one block, which sums the files' sizes, joins the data
they read and write, and keeps the imports between groups. Files that
are not that deep keep their own block.
"""

from pathlib import Path

from flowblueprint.project import (
    ENTRY_KIND, NOTEBOOK_KIND, PACKAGE_KIND, FileInfo, Project,
    name_some_str)

AUTO_MAX_BLOCKS_INT = 40


def find_group_key_str(info: FileInfo, depth_int: int) -> str:
    """The group a file belongs to at a folder depth.

    Args:
        info: The file.
        depth_int: How many leading folders name a group.

    Returns:
        The folder path ("pkg/sub") for files at least that deep, else
        the file's own path.
    """
    folders_tuple = info.path.parts[:-1]
    if len(folders_tuple) >= depth_int:
        return "/".join(folders_tuple[:depth_int])
    return info.path.as_posix()


def merge_group_info(key_str: str, members_list: list[FileInfo]
                     ) -> FileInfo:
    """One block standing for several files.

    Args:
        key_str: The group's folder path.
        members_list: Its files, in path order.

    Returns:
        A FileInfo whose path is the folder and kind is package (notebook
        when all members are notebooks); its summary names the files and
        the entry points among them, and its sizes, reads and writes are
        the members' together.
    """
    if len(members_list) == 1 and members_list[0].path.as_posix() == key_str:
        return members_list[0]
    kinds_set = {info.kind for info in members_list}
    kind_str = NOTEBOOK_KIND if kinds_set == {NOTEBOOK_KIND} else PACKAGE_KIND
    entries_list = [info.path.name for info in members_list
                    if info.kind == ENTRY_KIND]
    init_list = [info for info in members_list
                 if info.path.name == "__init__.py" and info.summary
                 and info.path.parent.as_posix() == key_str]
    names_list = [info.path.name for info in members_list]
    summary_str = (init_list[0].summary if init_list else "")
    summary_str = (summary_str + " " if summary_str else "") + (
        f"{len(members_list)} files: {name_some_str(names_list)}.")
    if entries_list:
        summary_str += f" Runs: {name_some_str(entries_list)}."
    return FileInfo(
        Path(key_str), members_list[0].module, kind_str, summary_str,
        sum(info.functions_count for info in members_list),
        sum(info.classes_count for info in members_list),
        join_labels_list([info.reads for info in members_list]),
        join_labels_list([info.writes for info in members_list]))


def join_labels_list(labels_lists: list[list[str]]) -> list[str]:
    """Join label lists, keeping the first occurrence of each label.

    Args:
        labels_lists: The members' reads (or writes).

    Returns:
        The unique labels in order.
    """
    return list(dict.fromkeys(label for labels_list in labels_lists
                              for label in labels_list))


def group_project(project: Project, depth_int: int) -> Project:
    """The project with files grouped by their first folders.

    Args:
        project: The project.
        depth_int: Leading folder levels that name a group (at least 1).

    Returns:
        A new Project with one block per group and the imports between
        groups (imports inside a group are left out).
    """
    keys_list = [find_group_key_str(info, depth_int)
                 for info in project.files]
    order_list = list(dict.fromkeys(keys_list))
    members_dict: dict[str, list[FileInfo]] = {key: [] for key in order_list}
    for key_str, info in zip(keys_list, project.files):
        members_dict[key_str].append(info)
    grouped = Project(project.name, notes=list(project.notes))
    grouped.files = [merge_group_info(key_str, members_dict[key_str])
                     for key_str in order_list]
    position_dict = {key_str: index_int
                     for index_int, key_str in enumerate(order_list)}
    for source_int, target_int in project.edges:
        pair_tuple = (position_dict[keys_list[source_int]],
                      position_dict[keys_list[target_int]])
        if pair_tuple[0] != pair_tuple[1] and pair_tuple not in (
                grouped.edges):
            grouped.edges.append(pair_tuple)
    return grouped


def choose_group_depth_int(project: Project,
                           max_blocks_int: int = AUTO_MAX_BLOCKS_INT) -> int:
    """The deepest grouping that keeps the overview readable.

    Args:
        project: The project.
        max_blocks_int: The most blocks wanted.

    Returns:
        0 (no grouping) when the files fit; otherwise the deepest folder
        level whose groups fit, or 1 when even that is too many.
    """
    if len(project.files) <= max_blocks_int:
        return 0
    deepest_int = max(len(info.path.parts) - 1 for info in project.files)
    for depth_int in range(deepest_int, 0, -1):
        keys_set = {find_group_key_str(info, depth_int)
                    for info in project.files}
        if len(keys_set) <= max_blocks_int:
            return depth_int
    return 1
