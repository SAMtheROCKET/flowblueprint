# FlowBlueprint for VS Code

FlowBlueprint, the Python architect: draw a script, a notebook or a whole
project as a block diagram, without running it and without leaving the
editor.

## Getting started

1. Install this extension, open a project and trust the workspace.
2. Right-click a `.py` file, an `.ipynb` notebook or a folder in the
   Explorer, or run a **FlowBlueprint:** command from the Command Palette
   (Ctrl+Shift+P).
3. The first time, if FlowBlueprint is not in your Python environment yet,
   click **Install**. The extension runs `pip install flowblueprint==0.2.1a0`
   in that interpreter (FuncLoom and RefacTrail come with it), and only
   after your click.

The interpreter is the one selected in VS Code's Python extension (or
`python` on your PATH). To use another, click **Choose interpreter** or set
`flowblueprint.pythonPath`.

## Commands

- **Draw architecture of this file**: the active (or right-clicked) script
  or notebook, saved next to it, for example `report.py` → `report.drawio`.
- **Draw architecture of this project**: the workspace (or right-clicked)
  folder, saved as `architecture.<format>` inside it: one block per script,
  module, package and notebook, with an arrow for each import.

Pick the format each time:

| Format | Opens in |
| --- | --- |
| `.drawio` (editable) | the *Draw.io Integration* extension, if installed |
| `.svg` (image) | VS Code |
| `.html` (web page) | your browser |
| `.md` (Mermaid flowchart) | the Markdown preview |

Settings: `flowblueprint.defaultFormat` (offered first) and
`flowblueprint.level` (`detailed`, one block per call, or `summary`).

An existing diagram is replaced only after you confirm. Your code is parsed,
never imported or run, and source files are never changed. Nothing is sent
to any service, and each drawing is limited to 180 seconds and 8 MB of
output.

## SQL resource workflow

The format picker offers `.drawio.png` for a PNG with embedded editable
draw.io XML, and `.png` for an image. Both require the PNG extra in the
selected Python environment. Literal query-file reads appear in diagrams.

## Local 0.3.0 development

Drawing now defaults to the reference operational canvas; choose
`flowblueprint.view: pages` for the previous format. The Explorer and
Command Palette also offer **Create modular draft and architecture** for
files and projects. Select a new destination folder. Optional settings
`flowblueprint.externalizeSql` and `flowblueprint.workflowPng` enable SQL
assets and an editable PNG. Partial conversion opens the diagram with a
warning to inspect `workflow.json`. Originals are preserved.

Requires the local FlowBlueprint 0.3.0a0 and FuncLoom 0.10.7a0 packages.
The extension source must be packaged/installed separately; no public
release was made by this development change.


Local 0.3.1a0 update: Python now starts with `-I -X utf8` for Unicode
diffs and diagnostics on Windows. Rebuild/reinstall this VSIX on each machine.


Local 0.3.2a0 update: the Python exporter now places editable diagram
metadata before image data so draw.io can import `.drawio.png`.
Use the supplied private wheel with this VSIX; this version is not
published. Previously generated PNGs must be repaired or regenerated.
