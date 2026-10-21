"""Attach RefacTrail results and a practical review checklist to a bundle."""

import json
from pathlib import Path

from refactrail import prepare_refactoring_dict


def refactor_workflow_dict(staging_path: Path) -> dict:
    """Refactor only the new project copy and save its evidence.

    Args:
        staging_path: Workflow-owned temporary bundle.
    Returns:
        dict: RefacTrail result with unresolved context questions.
    Warnings:
        A written draft with findings is not complete rule compliance.
    """
    report_dict = prepare_refactoring_dict(
        staging_path / "project", write_bool=True)
    (staging_path / "refactrail.json").write_text(
        json.dumps(report_dict, indent=2) + "\n", "utf-8")
    (staging_path / "context-questions.json").write_text(
        json.dumps({"schema_version": "context-questions-1",
                    "purpose": "Human review; answers are not applied.",
                    "questions": report_dict["context_questions"]},
                   indent=2) + "\n", "utf-8")
    return report_dict


def write_workflow_review_none(staging_path: Path, record_dict: dict) -> None:
    """Explain completed stages and actionable remaining work.

    Args:
        staging_path: Bundle before its final rename.
        record_dict: Conversion, refactoring and drawing evidence.
    Returns:
        None: Writes a Markdown review beside the generated project.
    Warnings:
        Compilation and style checks do not replace application regressions.
    """
    report_dict = record_dict["refactoring"]
    lines_list = ["# Pipeline review", "",
        f"FuncLoom modularization: {record_dict['modularization']}.",
        f"RefacTrail checks: {report_dict['status']}; "
        f"{report_dict['changed_files']} files changed; "
        f"{len(report_dict['findings'])} findings remain.",
        "FlowBlueprint diagrams describe the final project/ copy.", "",
        "Open architecture.drawio for high-level and implementation maps.",
        "Open function_details.drawio for declared function bodies.",
        "Read refactrail.json for diffs, source hashes and declined edits.",
        "Answer context-questions.json as a review checklist; this release "
        "does not apply those answers to public names or signatures.", "",
        "Original source was not changed or executed. Runtime behavior "
        "remains unverified. Run the project's regressions before adoption.",
        "", "## Remaining findings", ""]
    for finding_dict in report_dict["findings"]:
        lines_list.append(
            f"- {finding_dict['path']}:{finding_dict['line']}: "
            f"{finding_dict['code']} {finding_dict['message']}")
    for file_dict in report_dict["files"]:
        if file_dict["status"] != "checked":
            lines_list.append(f"- {file_dict['path']}: "
                              f"{file_dict['reason']}")
        lines_list.extend(f"- {file_dict['path']}: {note_str}"
                          for note_str in file_dict.get("notes", []))
    (staging_path / "review.md").write_text(
        "\n".join(lines_list) + "\n", "utf-8")
