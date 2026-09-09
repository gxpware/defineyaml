# `define` CLI

The `define` command edits a define.xml v2.1 submission as a tree of YAML
files (see `CLAUDE.md` for the file layout and OID derivation rules) and
converts between that tree and a real `define.xml`.

## Install

```sh
uv venv
uv pip install -e ".[dev]"
```

This installs the `define` console script into `.venv/bin/`. Run it via
`uv run define ...`, or activate the venv (`source .venv/bin/activate`) and
run `define ...` directly. `define edit` needs the optional `ui` extra:
`uv pip install -e ".[dev,ui]"`.

## Commands

### `define` (no arguments)

Opens the web editor to a **launcher** screen with three ways in:

- **Recent** - up to 10 trees you've opened before (per machine, in
  `~/.config/defineyaml/config.json`), most-recent first, each labelled with
  its study/protocol name. A tree that's been moved or deleted quietly drops
  off the list. One click reopens it.
- **Browse** - a folder picker; navigate to a `define/` tree you already have
  (folders containing a `study.yaml` are flagged) and open it.
- **Create** - a new tree in the folder you've browsed to: a folder name plus a
  study name. The OIDs are derived from a slug of the study name and the ODM
  header is pre-filled (see `define init` below) - all editable in `study.yaml`
  afterward.

Opening or creating one points the running server at it in place - no restart -
and moves it to the front of the Recent list. `define edit` (with its explicit
`--source`) does the same. For an explicit host or port, use `define edit`.

```sh
define            # the launcher: recent trees, browse, or create
```

### `define init`

Scaffolds a new `define/` file tree from scratch (`src/defineyaml/scaffold.py`):
a subdirectory for every object kind (`datasets/`, `codelists/`, `methods/`,
`comments/`, `valuelists/`, `whereclauses/`, `analysis-results/`), plus a
`study.yaml`. `standards.yaml`/`documents.yaml` aren't created - both are
optional (an absent file loads as empty) - so there's nothing to put in either
until there's real content.

Prompts interactively for the six fields `StudyFile` actually requires (an
ODM file OID; the Study's own OID, name and protocol name; the
MetaDataVersion's OID and name). On top of those, the ODM header is
**pre-filled** so a fresh tree builds a spec-complete `define.xml` header
without hand-editing:

| `study.yaml` field | Seeded with |
|---|---|
| `odm.as_of_datetime` | now, local time, ISO 8601 |
| `odm.originator` | the current OS user |
| `odm.source_system` / `odm.source_system_version` | `DefineYAML` / this tool's version |
| `odm.stylesheet` | `define2-1.xsl` (the `<?xml-stylesheet?>` href) |
| `metadata_version.define_version` | `2.1.0` |

`odm.creation_datetime` is deliberately **left blank**. The XSD-required
`CreationDateTime` is filled at build time (`define build`, "View
define.xml"/"View define.html") from the define tree's **latest modification**:
if the tree is a git working tree, the date of the last commit that touched it
(`git log -- .` - deletes and renames included); otherwise the newest
`*.yaml`/`*.yml` file's mtime. Set `odm.creation_datetime` explicitly to
override; it's then emitted verbatim (so a re-imported define.xml keeps its
original stamp). The web editor shows the would-be value as the field's
placeholder.

All of it stays hand-editable in `study.yaml` afterward, same as everything
else. Refuses to run - before prompting for anything - if the destination
already exists, so it never overwrites an in-progress tree.

```sh
define init [--destination PATH]
```

| Option | Default | Meaning |
|---|---|---|
| `--destination` | `define` | Root of the file tree to create |

### `define build`

File tree &rarr; `define.xml`. Runs the linker pass (resolve every
`codelist:`/`method:`/`comment:`/`valuelist:`/... reference to an OID, hard-fail
on collisions or unresolved references), then emits XML.

```sh
define build [--source PATH] [--output PATH]
```

| Option | Default | Meaning |
|---|---|---|
| `--source` | `define` | Root of the file tree to build |
| `--output` | `define.xml` | Path to write the generated define.xml |

### `define fmt`

Canonical formatting: normalised key order, 2-space indent, consistent
quoting (`code:`/`name:`/`nci_code:`/`oid:` double-quoted, multi-line text as
`|` block literals). Rewrites files in place; run it before committing so any
diff git reports is a real semantic conflict, not whitespace.

```sh
define fmt [--source PATH]
```

| Option | Default | Meaning |
|---|---|---|
| `--source` | `define` | Root of the file tree to reformat |

### `define lint`

Everything the XSD and the pydantic models don't already catch on their own
(`src/defineyaml/lint.py`). Tolerant, unlike `build`: one file failing schema
validation is reported and skipped, not fatal to every other check.

- **error** - would also fail `define build`: a schema-validation failure, an
  unresolved reference or OID collision (xref integrity, reusing the real
  linker + `build_odm`), or a slug collision between two objects of the same
  kind (two names that normalise to the same derived OID - checked
  proactively, ahead of a full build).
- **warning** - schema-valid but worth a look: an orphaned codelist/method/
  comment/where-clause nothing references (this also covers a named
  where-clause unused by both ARM and value lists, since both resolve
  through the same symbol-table lookup); a name reused across different
  object kinds; an `AnalysisResult` `reason:`/`purpose:` outside the CDISC
  2.1 controlled list; a `FormalExpression`/`ProgrammingCode` `context:` not
  declared in `study.yaml`'s `expression_contexts:` (silent until a study
  opts in by declaring a non-empty list); a method with neither
  `description:` nor `expressions:`; a value list whose entries mix named
  `where:` references and inline condition lists; a `Collected` origin whose
  `data_source:` is `Investigator` or `Subject` but which cites no CRF page
  (`document:`/`pages:`) - Define-XML requires a `def:PDFPageRef` there.
- **info** - CLAUDE.md §3's `{oid: ...}` and `oid:` escape hatches, surfaced
  for visibility (every occurrence in the tree), not because either is wrong.

Exits 1 only if any **error**-level finding exists.

```sh
define lint [--source PATH]
```

| Option | Default | Meaning |
|---|---|---|
| `--source` | `define` | Root of the file tree to lint |

### `define import`

Parse an existing define.xml v2.1 and explode it into the file tree,
writing `oid:` overrides only where the existing OID differs from what would
be derived.

```sh
define import DEFINE_XML [--destination PATH]
```

| Argument / Option | Default | Meaning |
|---|---|---|
| `define_xml` | *(required)* | Existing define.xml v2.1 to import |
| `--destination` | `define` | Root of the file tree to write |

### `define edit`

Starts a local web editor (FastAPI + a dependency-free vanilla-JS frontend,
`src/defineyaml/webui/`) over the file tree: browse every object kind in the
sidebar, edit it in a structured form (or as raw JSON, for whatever a form
doesn't cover yet), Save writes back through `ruamel.yaml`'s round-trip mode
so comments, key order and untouched fields survive - the same guarantee
`define fmt` is built on (CLAUDE.md §1). No auth; it's a localhost-only tool.
Opening a tree here also adds it to the Recent list a bare `define` (above)
offers.

If `--source` isn't a directory (the default `define/` doesn't exist, or a
typo'd path), `define edit` doesn't error - it starts on the same launcher a
bare `define` shows, so you can pick or create a tree from the browser. And
once a tree is open, an **"Open another tree"** link in the sidebar switches
to a different one without restarting the server.

Two links under the sidebar header, "View define.xml" and "View define.html",
build the current tree on demand and open it in a new browser tab -
`GET /api/render/xml`/`GET /api/render/html`, the same linker pass and XML
emission `define build` runs, plus (for HTML) an XSLT transform through the
vendored CDISC stylesheet (`src/defineyaml/stylesheets/define2-1.xsl`, from
https://github.com/lexjansen/define-xml-2.1-stylesheets, MIT-licensed). A
tree with an unresolved reference or a naming collision returns a 422 with
the same message `define build` would print, rather than a broken page.

Drop additional `*.xsl` files into `src/defineyaml/stylesheets/` (a restyled
fork, a sponsor's house variant - each must be self-contained XSLT 1.0, same
as the bundled one) and a small stylesheet picker appears next to "View
define.html"; with only the bundled stylesheet present it stays a plain
link. `GET /api/render/stylesheets` lists what's available;
`GET /api/render/html?stylesheet=<stem>` renders with a chosen one (unknown
name → 400).

The dataset list in the sidebar can be dragged (or moved with ▲/▼ buttons)
into whatever order matters for a review - the ItemGroupDef sequence
`define.html` is read top to bottom in - writing `study.yaml`'s
`dataset_order:` (`PUT /api/datasets/order`). No other kind's list reorders:
every other kind's document order is cosmetic, since each object is
independently OID-referenced rather than read in sequence.

A "CDISC Standards Browser" link opens a separate window (`/cdisc-viewer`,
CLAUDE.md §9) - a local-first lookup for Controlled Terminology and standards
metadata, independent of any one `define/` tree (so a window, not a tab).
Two panels:

**NCI EVS Controlled Terminology** - NCI's free, no-key CT export
(`evs.nci.nih.gov`), one ODM-XML file per standard (SDTM, ADaM, SEND) per
quarterly release. Per standard, "List versions" shows every dated release
(newest first, back to 2011 - no separate "current release" entry, since the
newest date *is* the current one) with a mark for the ones already on disk;
pick one and "Download & browse" fetches it if needed - cached indefinitely
per `(standard, date)` under `~/.cache/defineyaml/cdisc/nci-evs/`, never
re-fetched once local - then browse and search its codelists and terms.
"Check for updates" re-lists (the listing itself is cached 24h). If a local
standards folder is configured for this tree, a **"Save to standards folder"**
button converts the browsed release to a CDISC-DSB-style CT CSV and writes it
to `terminology/<standard>/<STANDARD>_CT_<date>.csv` there - ready to scaffold
datasets and codelists from, like any hand-downloaded export.

**Local standards folder** - a directory of CDISC CSV exports you maintain by
hand (variable tables, CT term lists, CDASH, QRS supplements); new versions are
yours to add as CDISC publishes them, this only reads. The path is **per-tree** -
`standards.yaml`'s `standards_folder:` (absolute, or relative to the `define/`
tree), set in the Standards editor or the Standards Viewer, no default. If the
path is set but the folder isn't there yet (a hand-edited `standards.yaml`, a
cloned or moved tree), a **"Create this folder"** button next to the warning
`mkdir -p`s it. Files are
grouped by the folder's own layout; a global search box scans every CSV at once,
and opening one file gives a paginated, column-searchable table plus a raw-CSV
download. Browsing and searching run off a DuckDB cache at
`<tree>/.cache/standards.duckdb` (one table per CSV, rebuilt for a file only when
its size or mtime changes) so a big CT export isn't re-parsed on every request;
`.cache/` is disposable and git-ignored. Without the `ui` extra's `duckdb` it
falls back to streaming the CSVs directly.

**Scaffold from a standard** - set the folder above, then give a `standards.yaml`
entry a `standards_file:` (the "+ Add standard from local folder" button sets it,
or type the path in the Local CSV field). Then the datasets and codelists sidebar
"+" offer *From standard*: pick an SDTM domain / ADaM structure to create a dataset pre-filled
with all its standard variables (types default `Char`→text / `Num`→integer for
you to refine), or pick codelists from a CT export - each of which you can
**rename** and **trim to a subset of its terms** before creating (a No/Yes
codelist reduced to just `Y`, say) - plus a one-click "add every codelist a
dataset references but that doesn't exist yet".

The datasets editor's variables list also has **"+ Add variable(s) from standards"**
- an overlay listing every variable of every attached IG standard, filterable by
standard, by domain / structure, and by a substring over name / label / CDISC
notes; tick as many as you want and they're appended to the dataset (client-side,
review then save). Added variables get their **SAS Field Name and Role**
pre-filled from the standard.

When the open dataset corresponds to a domain / structure in an attached
standard, the **Codelist and Role fields suggest** that standard's values for
each variable (a `<datalist>`, keyed on the variable name), and every described
variable gets an **"ⓘ Standard"** link that opens an overlay with the standard's
full definition (label, type, core, role, codelist, notes). ADaM templated names
like `TRT01PN` match the IG's `TRTxxPN` - a 2-letter lowercase run (`xx`/`yy`/`zz`)
is two digits, a single letter (`y`/`z`/`w`) is one or more. Role suggestions need
an SDTM/CDASH IG (ADaM IG CSVs carry no Role column); the note above the list says
which fields actually have values.

With a CT file attached, the **codelist term editor** gains autocomplete: Code
and Decode suggest from the standard, picking one fills the rest of the row, and
a Code the standard doesn't have is auto-flagged Extended with its NCI Code
cleared. Opening a codelist aligns its existing rows to the standard.

The CDISC Library API client this page began as is retired - see CLAUDE.md
§9. Every `/static/` asset is still served `Cache-Control: no-store` so this
actively-edited page can't get stuck showing an old script in a reused
window.

```sh
define edit [--source PATH] [--host HOST] [--port PORT] [--open/--no-open]
```

| Option | Default | Meaning |
|---|---|---|
| `--source` | `define` | Root of the file tree to edit |
| `--host` | `127.0.0.1` | Interface to bind to |
| `--port` | `8765` | Port to bind to |
| `--open` / `--no-open` | `--open` | Open the editor in a browser on startup |

## Status

`init`, `build`, `import`, `lint` and `edit` are implemented (`init` is step
0, ahead of the numbered build order in `CLAUDE.md` §6; `build`/`import`/
`lint`/`edit` are steps 2, 1, 4 and 7 - `edit` is a first cut at "UI", ahead
of `fmt`/define.html, which is out of build order but was requested
directly). `fmt` (step 5) still exits 1 with a "not yet implemented"
message. `--help` works on the app and on every subcommand
(`define build --help`, etc).
