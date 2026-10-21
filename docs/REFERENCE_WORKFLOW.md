# Reference-style architecture and modular drafts

FlowBlueprint 0.3.0a0 adds an operational architecture view based on the
supplied APS, battery-cancellation and stoppage-frequency examples.
Those private repositories are design references, not bundled fixtures.
The implementation uses their structure without copying domain names.

## Draw an existing script, notebook, or repository

```powershell
python -m flowblueprint PATH --view reference -o architecture.drawio
python -m flowblueprint PATH --view reference --level detailed -o architecture.drawio.png
```

The reference view uses START/END, function names and descriptions,
`in:`/`out:` ports with unverified type hints, decision diamonds, loop
limits, file parallelograms, database cylinders, and module colours with
legends. Independent entry scripts appear side by side. Long loops can
continue through numbered connector pairs; repeat arrows remain connected.
A large decision subtree stays together and can exceed the column target.

`--level full` produces high-level and implementation tabs. `summary`
keeps the high-level operational view; `detailed` keeps the implementation
canvas. Summary blocks group consecutive operations; they do not invent
business stages. Use `--overrides context.toml` to supply domain wording.

Folder entry points are detected statically. Use repeatable `--entry`
paths to select a subset or identify entry scripts explicitly:

```powershell
python -m flowblueprint my_repo --view reference --entry src/process.py --entry src/report.py -o architecture.drawio
```

An import or a shared filename does not establish execution order between
scripts. No such ordering arrow is invented. Unavailable dependencies,
dynamic dispatch, and omitted constructs still require review. Absolute
imports within ordinary packages and relative imports are read locally;
dynamic `sys.path` changes and namespace-package resolution are not proven.

The older file/import overview and individual function-page format remains
available through `--view pages` (the CLI default for compatibility).

## Modularize and draw in one command

```powershell
python -m flowblueprint INPUT --modularize-to NEW_FOLDER
python -m flowblueprint INPUT --modularize-to NEW_FOLDER --externalize-sql --png
```

`INPUT` is a script, one Python notebook, or a repository. The destination
must be new and outside an input repository. `--force` cannot override
this rule. Nothing is executed, uploaded, or changed in the original.

The bundle contains:

- `project/`: the FuncLoom-generated copy and copied project resources.
  A single script/notebook produces `project/main.py` and `project/src/`.
  Repository entries receive packages alongside their existing paths.
- `architecture.drawio`: high-level and implementation tabs.
- `high_level.drawio` and `detailed.drawio`: the individual canvases.
- `architecture.drawio.png`, when `--png` is supplied: an implementation
  image containing matching editable draw.io data. Requires the PNG extra.
- `workflow.json`: conversion coverage, located refusals, diagram notes,
  original provenance, and SHA-256 hashes of the diagrammed Python,
  notebook and SQL files.

Diagrams are read from `project/`, after modularization. Detailed diagrams
also expand steps recorded by this particular FuncLoom operation and show
configuration dependencies. They do not blindly inline arbitrary helper
functions. Returned function objects and dynamically chosen callbacks can
remain unresolved; their definition is not depicted as executed logic.

SQL externalization is optional and follows FuncLoom's bounded contract:
see [SQL_RESOURCES.md](SQL_RESOURCES.md). SQL content is not executed or
validated against a database. Missing context does not justify inventing
domain names, annotations, business meaning, or call relationships.

Exit 0 means the selected entries were converted and the draft was drawn.
It does not certify runtime behaviour. Exit 1 with a bundle means partial
conversion or a copy without converted entries: inspect `workflow.json`.
A complete refusal returns 1 without a bundle. Usage, parsing, rendering,
and filesystem failures return 2. Failed drafting/rendering leaves no
completed bundle. Review and run your own project tests before using it.

Whole-folder notebook conversion is not supported by this workflow yet;
pass each notebook individually. The original drawing command can still
draw notebooks inside repositories. Existing `--check` and `--up-to-date`
remain available for drawing, not for creating a modular draft.

## Editor integration

The extension source now defaults to the reference view. Set
`flowblueprint.view` to `pages` for the previous format. New commands
**Create modular draft and architecture of this file/project** ask for a
new destination and call the same CLI. `flowblueprint.externalizeSql` and
`flowblueprint.workflowPng` control optional assets. Workspace trust,
saved-file requirements, and argument-array subprocess execution remain.

These are local development changes. The extension must be packaged and
installed to expose them in VS Code; source tests do not validate the live
extension host. No release or upload is part of this workflow.


## Editable PNG compatibility fix (0.3.2a0, local)

Earlier local exports put diagram metadata after the image data. Ordinary
image viewers could display the pixels, but draw.io stopped searching at
the first IDAT chunk and could open an empty canvas. Version 0.3.2a0 puts
one mxfile text chunk before IDAT and removes stale diagram metadata.
The image data and unrelated metadata are preserved byte for byte.

Regenerate an old export to a new filename with the updated package:

```powershell
python -m flowblueprint PATH --view reference -o architecture-fixed.drawio.png
```

For a three-tool draft, choose a new `--pipeline-to` destination and add
`--png`. Open the generated PNG using draw.io's File > Open from > Device,
or VS Code's Draw.io Integration editor. The workflow PNG contains the
implementation page; `architecture.drawio` contains both architecture
levels. Changing the package alone does not repair a PNG already saved
on another computer.

The chunk-order requirement is documented in the
[draw.io file format](https://github.com/jgraph/drawio/wiki/File-Format).
