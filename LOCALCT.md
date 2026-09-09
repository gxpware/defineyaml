# LOCALCT - Controlled Terminology & standards, local-first

DefineYAML's "smart mode": two read-only, local-first sources of CDISC Controlled
Terminology and standards metadata, wired into the web editor only. Neither touches
the `define/` tree, the linker, or the XML round-trip.

This is the normative spec for that subsystem. See [`XMLYAML.md`](XMLYAML.md) for the
file format and [`CLAUDE.md`](CLAUDE.md) for the design log.

---

## 0. Why local-first (and not the CDISC Library API)

This started as a CDISC Library API client. That API is the wrong foundation: the
useful content sits behind a paid membership, and the free parts are awkward to
reach. The client modules (`cdisc/client.py`, `cdisc/config.py`, `cdisc/cache.py`)
remain in the tree, unit-tested, unrouted - a museum exhibit. Nothing in the running
application calls them.

The two replacements below get you the same metadata without the login page.

---

## 1. NCI EVS Controlled Terminology (`cdisc/nci_evs.py`)

NCI's own EVS server (`evs.nci.nih.gov`) publishes the **full CDISC CT** as free,
no-key ODM-XML - one file per standard (SDTM, ADaM, SEND) per quarterly release, back
to 2011.

### Discovery

The site is an Angular SPA with no directory listing, but the file-serving API behind
it is a plain S3 `ListObjectsV2` proxy:

```
GET /ftp1/folder?folder=<prefix>
  -> {Contents: [{Key, Size, LastModified}], IsTruncated, CommonPrefixes}
```

`folder` is used as the S3 *prefix* - it need not be a real directory.

`list_available_versions(standard)` makes **one** call with a **narrow** prefix -
`CDISC/SDTM/Archive/SDTM Terminology` - and filters `Contents` to
`{prefix} YYYY-MM-DD.odm.xml`, newest first. The narrow prefix returns
`IsTruncated: false` in one call (the unfiltered `Archive/` is >1000 keys and would
need pagination). There's **no "current" pseudo-version** in the list: the undated
`CDISC/SDTM/SDTM Terminology.odm.xml` is byte-identical to the newest Archive file, so
the newest dated release *is* the current one. `resolve_version()` still accepts
`"current"` as an alias (→ the newest date); everything else is a `YYYY-MM-DD` date.

The version list is cached to
`~/.cache/defineyaml/cdisc/nci-evs/{standard}.versions.json` for **24h**. "Check for
updates" forces a re-fetch.

### Download and cache

`version` is `"current"` or a `YYYY-MM-DD` date. `ensure_downloaded(standard,
version)` fetches `{standard}@{version}.odm.xml` once and caches it **indefinitely** -
a published quarterly release's content never changes (SDTM ≈ 25 MB; ADaM ≈ 97 KB).
`downloaded_versions(standard)` scans the cache dir. Nothing re-fetches a file it
already has except on explicit `force`.

### Parsing (NCI's dialect, not plain Define-XML)

Confirmed against a real SDTM file (1208 codelists):

- Every term is an `EnumeratedItem` - never `CodeListItem` + `Decode`.
- Human-readable content lives in `nciodm:`-namespaced children
  (`http://ncicb.nci.nih.gov/xml/odm/EVS/CDISC`): `PreferredTerm`, `CDISCSynonym`,
  `CDISCDefinition`.
- NCI Concept ID and extensibility are plain attributes (`nciodm:ExtCodeID`,
  `nciodm:CodeListExtensible`), not a `def:Alias`.

Parsing uses `lxml.etree.iterparse` with `el.clear()` / sibling-pruning (bounded
memory over the 25 MB file). `_build_index` records each `CodeList`'s own attributes
to `{standard}@{version}.index.json` so "what codelists exist" does not re-stream the
file; `get_codelist_terms` early-exits the moment its target OID is found.

---

## 2. Local standards folder (`cdisc/local_standards.py`)

A directory of **CDISC CSV exports** - the kind the Data Standards Browser produces:
IG variable tables (`SDTMIG_v3.4.csv`, `ADaMIG_v1.3.csv`), CT term lists
(`SDTM_CT_2026-03-27.csv`), CDASH, QRS supplements. Each has its own column schema;
this module treats them generically.

**DefineYAML never downloads them.** The user adds new versions by hand as CDISC
publishes them; this only reads.

### `standards_folder:` - per-tree, no default

The folder is `standards.yaml`'s `standards_folder:`
(`models/study.py`'s `StandardsFile.standards_folder`), not a global app setting - two
projects can draw from different CSV bundles (different SDTMIG vintages, different
clients').

- A **local editor pointer only**: never emitted to `define.xml`, never read by
  `define import`.
- Absolute, or relative to the `define/` tree root
  (`webui/standard_scaffold.py`'s `resolve_folder`).
- No default - the editor and the Standards Viewer both show it unset until set.
- `local_standards` itself is purely functional: every entry point takes the resolved
  folder `Path` as its first argument.

### Reads

- `list_files(folder)` - walks `*.csv` recursively, groups by the folder's own
  subdirectory layout (`data_analysis`, `terminology/sdtm`, …), parses `_vX.Y` /
  trailing `YYYY-MM-DD` out of each filename for a version label.
- `read_file(folder, relpath, q, limit, offset)` - streams one CSV, optionally
  filters rows by a case-insensitive substring across all cells, paginates
  (`total_matched` = all matches, `rows` = the page).
- `search(folder, q, limit)` - the same across every CSV at once, capped.
- `rows(folder, relpath)` - the shared read primitive (columns + every row as a
  `''`-filled dict).
- `raw_path(folder, relpath)` - backs a `FileResponse` for downloading a CSV as-is.

All reads go through `_safe_csv(folder, relpath)` - `resolve()` then confirm the
target is inside `folder` - so `relpath=../../etc/passwd` is rejected.

### DuckDB query cache (`cdisc/csv_db.py`)

Re-streaming a multi-MB CT export per keystroke is wasteful, so browse / search go
through **one DuckDB database at `<tree>/.cache/standards.duckdb`**:

- **`csv_<hash>` per CSV** - queried by `rows` / `read_file` (single-file browse). A
  changed / new CSV is `DROP` + `CREATE TABLE … read_csv(?, all_varchar=true,
  null_padding=true, ignore_errors=true)`; a vanished one's table is dropped; an
  unchanged one is untouched (`_manifest` tracks each file's `size` + `mtime_ns`).
- **`_search_index(relpath, category, blob, row)`** - one row per CSV row across the
  whole folder, in lockstep with the per-file tables. `blob` is a pre-lowercased
  `concat_ws` of the cells; `row` is a `MAP` of the originals. `search` is one indexed
  `blob LIKE` scan of this table rather than a per-file loop (~30 ms vs ~110 ms over a
  folder of ~200k rows); the *filtered* `read_file` uses it too, via an ART index on
  `relpath`.
- `_meta` holds a `schema_version`; bumping it wipes the derived tables so an older
  cache rebuilds.
- `read_file` / `search` / `rows` mirror `local_standards`' signatures with a leading
  `cache_root` and return identical shapes.
- **The connection is kept open per DB path** and reused (`connect` + `close` is ~12 ms,
  the queries sub-ms); one process-wide `threading.RLock` serialises everything.
  `close_all()` runs on server shutdown, on "open another tree", and after every test.
- **Disposable and self-healing**: delete `.cache/` (or corrupt the file) and it
  rebuilds on the next query; a `.cache/.gitignore` with `*` is written on creation.
- If `duckdb` is not installed (it is in the `ui` extra) or a CSV won't parse, every
  function falls back to streaming via `local_standards`.

---

## 3. Scaffolding from a standard's CSV (`webui/standard_scaffold.py`)

### `standards_file:` - the per-entry CSV pointer

A `standards.yaml` entry may carry `standards_file:` - the CSV path (relative to
`standards_folder:`) that standard's content comes from, e.g.
`data_tabulation/SDTMIG_v3.4.csv`. Declared on `StandardDef` (because
`DefineBaseModel` is `extra="forbid"`), but - like the folder - **never emitted to
define.xml and never read by the importer**. The editor's "+ Add standard from local
folder" picker sets it automatically. `type` is inferred: a `terminology/*` path →
`CT`, else `IG`.

### CSV → model shapes (`cdisc/standard_csv.py`, pure functions)

Two file families, told apart by columns:

- **IG variable tables** - the "unit" column is `Dataset Name` (SDTMIG/SENDIG),
  `Domain` (CDASHIG), or `Data Structure Name` (ADaM: datasets are user-named
  instances of a structure). `unit_variables` maps `Char`→`text` / `Num`→`integer` (a
  documented default the user refines), `Core ∈ {Req, HR}`→`mandatory`, and the CT
  column to `codelist:`. SDTMIG populates only the codelist **C-code**, returned as
  `codelist_ccode` for the scaffold layer to resolve to a submission value.
- **CT term lists** - a row with an empty `Codelist Code` is a codelist header; rows
  whose `Codelist Code` matches their own `Code` are its terms. `codelist_detail`
  builds an `EnumeratedCodeList`: `name`←submission value, `nci_code`←C-code,
  `decode`←NCI Preferred Term (dropped from every term if any term lacks one - the
  model requires all-or-none). An optional `codes=[…]` keeps only that subset (a
  sponsor-narrowed list); the parent's C-code is retained.

### Orchestration over `tree.py`

- `create_dataset(root, standard, unit, name, key)` - a schema-valid dataset with
  every standard variable, `class` from the CSV, `standard:` pointing back at the
  entry, `label` / `structure` left blank. `_resolve_codelists` turns each
  `codelist_ccode` into a `codelist:` name against *any* configured CT `standards_file`
  (dropped if unresolvable).
- `create_codelists(root, standard, items)` - one file per item; an item is a plain
  submission-value string, or `{value, name?, codes?}` (`name` renames the codelist -
  file key + OID follow; `codes` keeps a term subset). Skips a target whose slug
  already exists; a `codes` set matching nothing lands in `skipped`, not fatal.
- `missing_referenced_codelists(root)` / `create_missing_codelists(root)` - every
  `codelist:` reference in datasets and value lists with no file yet, annotated with
  the CT file that provides it; the second creates all resolvable ones at once.
- `codelist_reference(root, name, nci_code)` - one codelist's full standard term list,
  matched across every attached CT file on the C-code first, then the submission
  value. Backs the CT-aware term editor.
- `external_dictionary_names(root)` - CT **C66788** ("CodeList Dictionary Name")
  submission values from an attached CT file (matched by C-code via
  `codelist_reference`), falling back to a built-in sample list. Feeds the
  `ExternalCodeList/@Dictionary` datalist. Input aid only - the field stays free text.
- `ig_catalog(root)` / `search_ig_variables(…)` - every variable of every attached IG
  standard, for the "+ Add variable(s) from standards" overlay. **Client-side add**:
  the frontend appends cleaned variable dicts to `working.variables` and the user
  saves - no server write, no other files touched.
- `dataset_standard_hints(root, dataset_key)` - the attached-standard units that
  *describe* the open dataset (SDTM/CDASH match on name/domain, ADaM on `class` = the
  structure name), plus per-variable `{codelist, role, sources}`. Drives the datalist
  on the variables list's Codelist and Role fields and the per-row "ⓘ Standard" info
  chip. ADaM templated names (`TRTxxPN`) are matched by a digit-pattern regex.

### CT-aware editing in the web UI

- **The codelist term editor** (`renderCodelistTerms`): when an attached CT
  `standards_file` has the open codelist, its terms drive `<datalist>` suggestions on
  Code / Decode, auto-fill of the rest of a row from a standard Code, and - for a Code
  the standard lacks - a blanked, disabled NCI Code plus an auto-ticked per-term
  `extended:` (`def:ExtendedValue`). Existing rows align to the standard once on open.
  CT matching and the "two terms can't share a Code" check are **case-sensitive**.
- **The "Codelist kind" selector** is three-way (CodeListItem / EnumeratedItem /
  ExternalCodeList); the External branch's Dictionary field is the C66788 datalist.

---

## 4. HTTP surface

All routes are thin wrappers: `ValueError` / `StandardCsvError` /
`LocalStandardsError` → 400, `NotFoundError` / `FileNotFoundError` → 404, `NciEvsError`
→ 502 / 404.

**NCI EVS**

```
GET  /api/cdisc/nci-evs/standards
GET  /api/cdisc/nci-evs/{standard}/versions
POST /api/cdisc/nci-evs/{standard}/download?version=
POST /api/cdisc/nci-evs/{standard}/save-to-folder?version=   # -> terminology/<std>/<STD>_CT_<date>.csv in the Standards folder
GET  /api/cdisc/nci-evs/{standard}/codelists?version=
GET  /api/cdisc/nci-evs/{standard}/codelists/{oid}?version=
```

**Local standards folder**

```
GET  /api/standards/config          # {folder, resolved, exists, creatable, error}
PUT  /api/standards/config          # writes standards_folder: via tree.save_object
POST /api/standards/config/create-folder   # mkdir -p a folder that's set but missing
GET  /api/standards/files
GET  /api/standards/file
GET  /api/standards/search
GET  /api/standards/raw
GET  /api/standards/external-dictionaries
```

**Scaffold** - under `/api/standards/scaffold/`: `standards`, `units`,
`unit-variables`, `POST dataset`, `ct-codelists`, `ct-codelist`, `ct-codelist-terms`,
`POST codelists`, `GET`/`POST missing-codelists`, `ig-catalog`, `ig-variables`,
`variable-hints`.

### The Standards Viewer window

`/cdisc-viewer` (`webui/static/cdisc-viewer.{html,js,css}`) opens from the editor's
`#sidebar-actions` row via a **named window target** (repeat clicks focus one window)
- a separate window, not a tab, because both sources are global per-machine, not tied
to one `define/` tree. Two panels: NCI EVS CT (per-standard version list, download &
browse, term-detail table) and the local standards folder (path setting, global
search, grouped file browser with a paginated in-file-searchable table).

---

## 5. Invariants

- Nothing here writes to `define.xml` or is read by `define import`. The round-trip
  tests are untouched by any of it.
- `standards_folder:` and `standards_file:` are local editor pointers. They live in
  `standards.yaml` only so the editor can find them.
- The NCI EVS cache (`~/.cache/defineyaml/`) and the DuckDB cache
  (`<tree>/.cache/`) are both disposable - delete either and it rebuilds.
- Wiring CT into the editor's own field-level validation (a `codelist:` /  CT mismatch
  flag on a variable, say) is still future work.
