# Changelog

## Unreleased

- VS Code extension (preview, `editor/flowblueprint`): *Draw architecture
  of this file* and *Draw architecture of this project* from the Explorer
  or the Command Palette, in draw.io, SVG, HTML or Markdown, with the
  result opened straight away. It offers to install FlowBlueprint into the
  selected interpreter on first use and replaces an existing diagram only
  after confirmation.

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
