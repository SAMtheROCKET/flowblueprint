# Changelog

## Unreleased

Changes from the owner's hands-on trial (7 October 2026), where loops
were not visible, descriptions were vague and only one level of detail
was drawn:

- **Loops are visible**: each loop sits in a light dashed frame, reads
  "For each row in rows" ... "Next row" (or "While ..." ... "Check the
  condition again"), and has a *repeat* arrow from its closing shape
  back to its opening shape; the loop's exit is labelled *done*. A loop
  is never split across columns.
- **Every function gets its own page**: the functions the flow calls
  (and the ones they call, up to 40 per script) are drawn from their
  signature ("load_sales(path)") to what they return ("Return rows").
  A function of a developed module is read with that module's own
  imports. draw.io files get one tab per page; SVG and PNG stack the
  pages; HTML and Markdown show a section per page; .mmd keeps the
  first page.
- `--level full` (the new default): an overview at summary level (for
  flows of six or more top-level items), the detailed main flow and the
  function pages. `--level detailed` leaves the overview out;
  `--level summary` draws only the overview.
- **Project folders** add the detailed pages of each entry point and
  notebook after the import overview.
- **Clearer descriptions**: functions without a docstring are described
  from their body (files opened, CSV/JSON/database/web calls, loops and
  what they return); short statements are shown as written; print and
  logging steps show their message; os.makedirs reads "Create folder
  ...". A call to the script's own method named like a library writer
  (store.save) is no longer drawn as a file write.
- **Return types** of functions without annotations come from a
  returned literal or a returned name built from one literal type
  (rows = [] ... return rows gives list).
- `try`/`except` handlers are drawn as "KeyError raised?" decisions
  instead of being left out. A final `return` is the END terminator.
- When `main()` does more than hand over to one function, that function
  is drawn as a block with its own page instead of being pasted inline.
- **Quieter terminal**: notes about parts not drawn and info findings
  (unknown types) are summarised in one line; `--verbose` lists them.
- PNG output shows its text on systems without Helvetica or Arial: the
  SVG font list now also names Liberation Sans and DejaVu Sans.
- A column holding only the last one or two blocks joins the column
  before instead of adding a pair of connectors.
- VS Code: the *Level* setting offers full (default), detailed and
  summary.

- `-o diagram.png` writes a PNG picture (twice the SVG size, white
  background) through the optional resvg renderer:
  `pip install "flowblueprint[png]"`. Without it, FlowBlueprint explains
  the install command and writes nothing; every other format needs no
  extra package.
- Cleaner arrows in project overviews: every arrow gets its own start
  point on the bottom of its block, its own end point on the top of its
  target and its own line in each gap between rows (gaps grow when
  needed), so no two arrows share a line. Arrows that skip rows drop
  through the nearest free gap between blocks instead of a band of lanes
  on the far right, and arrows that close an import cycle are routed the
  same way instead of crossing blocks. A very busy block gathers
  neighbouring arrows of one direction into a shared line (a bundle).
  Checked on FuncLoom, RefacTrail and 129 installed packages, each drawn
  grouped and with one block per file (258 drawings): no arrow overlaps
  an unrelated arrow, passes behind a block or runs diagonally. SymPy
  (845 files, 6,887 imports, one block per file) lays out in about 4 s.
- `--up-to-date` draws nothing and exits 1 when the output file is
  missing or differs from a fresh drawing (line endings ignored), for CI.
  The GitHub Action gains `check: "true"` and pre-commit a
  `flowblueprint-architecture-check` hook that use it.

## 0.2.1a0 - VS Code extension and a simpler README, 2026-10-07

- VS Code extension (preview, `editor/flowblueprint`): *Draw architecture
  of this file* and *Draw architecture of this project* from the Explorer
  or the Command Palette, in draw.io, SVG, HTML or Markdown, with the
  result opened straight away. It offers to install FlowBlueprint into the
  selected interpreter on first use and replaces an existing diagram only
  after confirmation. It is on the Marketplace (publisher samtherocket)
  with an icon; `scripts/package_editor.py` writes the same VSIX layout
  as Microsoft's vsce.
- docs/OLDER_PYTHON.md: using FlowBlueprint on projects that stay on
  Python 3.8-3.11 (tested on 3.8, 3.9 and 3.10).
- The README starts with three steps (install, draw, open the result), a
  VS Code section and the older-Python steps; PyPI and VS Code badges.
- No drawing changes.

## 0.2.0a0 - Projects, Mermaid and HTML, 2026-10-07

- `flowblueprint FOLDER` draws a project overview: one block per script,
  module, package and notebook, an arrow for each import between project
  files (absolute, relative, sibling-script and `src` layouts), entry
  points on top, and per-file summaries with the data each file reads
  and writes. Tests are skipped unless `--include-tests` is given.
- New output formats chosen by the `-o` suffix: `.md` (Markdown with a
  Mermaid flowchart, rendered by GitHub and GitLab), `.mmd` (Mermaid
  text) and `.html` (a self-contained page). Unknown suffixes are refused.
- Mermaid labels escape quotes, angle brackets, pipes and backticks.
- Sections: a notebook's Markdown headings and `# %% Title` cell markers
  in scripts (VS Code, Jupytext, Spyder) become dashed section banners;
  plain statements are no longer grouped across a section boundary.
- Project overviews: arrows that skip rows are routed through lanes
  beside the blocks (draw.io waypoints, SVG); HTML pages fit the image to
  the page width.
- Projects above 40 files are grouped into one block per sub-package
  (automatic depth, or `--group-depth N`; 0 draws every file).
- A GitHub Action (`uses: SAMtheROCKET/flowblueprint@main`) and a
  pre-commit hook (`flowblueprint-architecture`) keep a project's
  ARCHITECTURE.md up to date.
- Robustness sweep: all 584 standard-library and 6,988 corpus files and
  92 corpus packages are drawn and rendered without an error.

## 0.1.0a0 - First alpha, 2026-10-06

- Scripts and notebooks to draw.io and SVG block diagrams with inputs,
  outputs, data types, loops, decisions, data sources and plots;
  detailed and summary levels; override files; diagram rule checks.
