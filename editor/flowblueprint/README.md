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
   click **Install**. The extension runs `pip install flowblueprint==0.2.0a0`
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
