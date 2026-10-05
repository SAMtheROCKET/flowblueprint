# FlowBlueprint

**The Python architect: turn any Python script or Jupyter notebook into a
clear block-diagram architecture (draw.io flowchart), without running it.**

FlowBlueprint reads your code and draws how it flows: what runs first,
which functions are called, what goes in and out of each step (with data
types), where loops and decisions are, which files, databases and storage
are read or written, and where plots are made. Managers, product owners
and new team members can understand a pipeline before reading a single
line of code; developers get an architecture diagram that stays in step
with the source.

Part of a family of standalone Python tools:
[FuncLoom](https://github.com/SAMtheROCKET/funcloom) (functionizer),
[RefacTrail](https://github.com/SAMtheROCKET/refactrail) (refactorizer)
and FlowBlueprint (architect).

![A detailed FlowBlueprint architecture: start, settings, a loop over stations with coloured helper-module blocks, a Yes/No decision, outputs to CSV, JSON and a plot, and end](https://raw.githubusercontent.com/SAMtheROCKET/flowblueprint/main/docs/images/station_report_detailed.svg)

**0.1.0a0 is an experimental alpha, not yet published.** Python 3.12 or
newer is required. No LLM, account or network connection is needed.

## Quick start

```bash
pip install flowblueprint
flowblueprint my_script.py                  # writes my_script.drawio
flowblueprint analysis.ipynb                # notebooks work too
flowblueprint my_script.py --level summary  # fewer, higher-level blocks
flowblueprint my_script.py -o overview.svg  # an image for slides/READMEs
```

Open the `.drawio` file in [diagrams.net](https://app.diagrams.net) or the
VS Code *Draw.io Integration* extension, where you can edit it freely or
save it as an editable `.drawio.png`.

## What you get

| In your code | In the diagram |
| --- | --- |
| The script or notebook name | A title above the flow |
| Start and end of the run | START and END terminators |
| A call to your own function or method | A block: **name**, one-line description, `in:` and `out:` with data types |
| Several small operations | One plain block, or one packed block at `--level summary` |
| Functions from your own modules | Coloured blocks, with a colour legend per module |
| `for` / `while` loops | Opening and closing loop-limit shapes |
| `if` / `elif` / `else` | A decision diamond with Yes and No paths |
| `continue`, `break`, `return` in a branch | An arrow to the loop end, past the loop, or to END |
| CSV, Parquet, Excel, JSON, config files | Data shapes on the left (read) or right (written) |
| SQL reads and writes | Database cylinders |
| `s3://`, `gs://`, network shares | Storage shapes |
| matplotlib, seaborn, plotly | A plot block, with saved figures as documents |
| Long flows | Columns of at most 10 blocks joined by A/B connectors |

Descriptions come from docstrings. Without one, FlowBlueprint writes a
short, deterministic description from the code itself ("Calculate
distance." for `calculate_distance`). Types come from annotations,
well-known library calls, literals and naming conventions such as `_df`
or `_list`; anything else is shown as `unknown` rather than guessed.

## Two levels: detailed and summary

One function is not always one block. `--level detailed` (the default)
draws one block per call. `--level summary` packs consecutive operations
into higher-level blocks (up to `--group-size`, default 4), each listing
its operations with the inputs it needs and the outputs it leaves:

![The same script at summary level: settings, a loop with one packed "Load, repair and flag" block, a decision, and one "Compute and save" block](https://raw.githubusercontent.com/SAMtheROCKET/flowblueprint/main/docs/images/station_report_summary.svg)

You choose the grouping when it matters, with an override file:

```toml
# blueprint.toml
[[groups]]
title = "prepare_readings"
description = "Load and clean the readings of one station."
functions = ["load_station_readings", "repair_missing_values"]

[blocks.flag_heat_events]
description = "Find the hours above the heat threshold."
```

```bash
flowblueprint station_report.py --overrides blueprint.toml
```

## Classes and well-structured code

FlowBlueprint works directly on any readable script; you do not need to
run FuncLoom or RefacTrail first. Classes are understood: `Pipeline(...)`
becomes a *Create the Pipeline* block, `pipeline.load()` resolves to the
method and its docstring, and when the entry point only hands over to one
method (`Pipeline(config).run()`), that method's steps are drawn.

## Checks

Every diagram is checked against block-diagram rules: start and end
terminators, the script name, closed loops, no open-ended blocks, data
sources on the left, the per-column limit, a legend for every colour, and
verb-first titles. `--check` only checks and exits with 1 on errors.
Statements that are not drawn (for example exception handlers) are
reported with their line numbers.

## Who uses it

- **Developers and data scientists**: document a pipeline, review a pull
  request, or explain a notebook to the team.
- **Managers, product owners and project managers**: see what a script
  does, step by step, before a review or planning meeting.
- **Students and teachers**: present coursework and assignments as a
  clear flowchart.
- **Teams taking over code**: get an architecture overview of unfamiliar
  scripts in seconds.

## Safety

The code is parsed with Python's own `ast` module and is never imported or
executed. The source file is never changed. Existing output files are not
overwritten unless you pass `--force`.

## How it fits with FuncLoom and RefacTrail

FlowBlueprint installs FuncLoom and RefacTrail and uses them through
absolute imports (for example RefacTrail's validated notebook reader).
Use them together for one flow: **FuncLoom** turns long scripts and
notebooks into functions and modules, **RefacTrail** checks, formats and
refactors them, and **FlowBlueprint** draws the architecture.

Looking for a *Python architecture diagram generator*, *code to flowchart*,
*script to architecture*, *notebook to architecture*, *workflow diagram
generator* or *auto architecture generator (archgen)*? That is what
FlowBlueprint does.

## Roadmap

- 0.2: a high-level project diagram across several scripts and modules,
  built on FuncLoom's project inventory.
- 0.3: richer notebook views (Markdown headings as sections) and more
  library knowledge for data types.
- Later, optional: AI-written descriptions, always shown with their source
  evidence and never required.

## License

MIT. See [LICENSE](LICENSE).
