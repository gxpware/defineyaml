# define.xml v2.1 distributed editor - format & OID design

**This file is the design log** - the *why*, the alternatives rejected, the evidence
behind each call, and running notes on what round-trip testing has found. The
reader-facing specs have been extracted:

- [`XMLYAML.md`](XMLYAML.md) - the define.xml ⟷ YAML mapping: file format, layout, OID
  derivation, references, the linker pass, per-element handling, the round-trip
  guarantee.
- [`LOCALCT.md`](LOCALCT.md) - the local-first CT / standards subsystem (§9 here):
  NCI EVS, the local standards folder, CSV scaffolding, the DuckDB cache.
- [`CLI.md`](CLI.md) - the `define` command reference.
- [`SETUP.md`](SETUP.md) - dev environment and per-OS binary builds (`pyinstaller`).

Keep those in sync when a decision below changes.

Status: decided (v1 scope = "dumb mode"). "Smart mode" (§9) is now a local-first Controlled Terminology / standards browser: NCI EVS CT (version-pickable, downloaded on demand) plus a user-configured folder of CDISC CSV exports. The CDISC Library API integration it started as is retired - its `cdisc/client.py`/`config.py`/`cache.py` modules are still in the tree but nothing routes to them. Wiring CT into the editor's own fields (autocomplete, `codelist:`/CT mismatch flags) is still future work.

---

## 1. File format decision: **YAML 1.2, via `ruamel.yaml`**

### Options considered

| Format | Verdict | Reason |
|---|---|---|
| Split XML fragments | Reject | Namespace prefixes, entity escaping, and `xml:lang` wrappers make hand-editing worse than the problem being solved. Diffs are still XML diffs. |
| JSON | Reject | No comments. The whole point of splitting is that each object gets explained; the explanation has to live next to the object and must *not* leak into the generated define.xml. |
| TOML (`tomlkit`) | Reject | Round-trips with comments and diffs cleanly, but define.xml is deeply nested and list-heavy (codelist terms, ItemRefs, where-clause range checks). Arrays-of-tables get verbose fast, and multi-line derivation text is awkward. TOML is strongest for flat config; this is not flat config. |
| Markdown + front-matter | Reject | Two parsers, two failure modes, no schema validation story. |
| **YAML 1.2** | **Accept** | Block scalars (`\|`) for derivations and comments - which are the longest and most-edited text in any define - diff line-by-line. Native comment support. Mature round-trip editing. Editor tooling (schema-driven autocomplete) is free. |

### Why `ruamel.yaml` specifically, not `PyYAML`

Two hard reasons, not preference:

1. **Comment and order preservation on round-trip.** Required for step 3 ("on save, update individual files"): a save must rewrite only what changed and leave a contractor's explanatory comments, key order, and block style intact. `ruamel.yaml` preserves comments, key ordering, block style, and flow style across load-modify-dump; PyYAML discards all of it.
2. **YAML 1.2 semantics.** PyYAML implements YAML 1.1, where bare `NO`, `Y`, `N`, `ON`, `OFF` parse as booleans. define.xml is saturated with exactly these tokens: `Mandatory="No"`, `Repeating="No"`, `IsReferenceData="Yes"`, `NY` codelists with codes `Y`/`N`, and ISO 3166 country code `NO` (Norway). Under YAML 1.1 a `RACE` codelist is fine but a `COUNTRY` codelist silently corrupts. YAML 1.2 restricts booleans to `true`/`false`, which removes the class of bug.

**Belt and braces anyway:** the serialiser always emits values in *code positions* (`code:`, `name:`, `nci_code:`, `oid:`) as double-quoted strings, regardless. This protects against a contractor's own editor, a `yq` in someone's CI, or a future non-Python reader. Leading-zero codes (`"01"`) and version strings (`"2.1"`) get the same treatment.

**Canonical formatting.** A `define fmt` command (and matching pre-commit hook) rewrites every file with normalised key order, 2-space indent, and consistent quoting. This is `black` for the define: it eliminates the entire class of whitespace/ordering merge conflicts, so any conflict git reports is a *real* semantic conflict between two contractors.

---

## 2. File layout

```
define/
  study.yaml                    # Study, MetaDataVersion, ODM header attrs
  standards.yaml                # def:Standards (2.1) - CT versions, IG versions
  documents.yaml                # def:leaf for aCRF, SAP, SDRG/ADRG, external docs
  datasets/
    adsl.yaml                   # ItemGroupDef + inline variable list (ItemRef+ItemDef)
    adae.yaml
  codelists/
    race.yaml
    ny.yaml
    meddra.yaml                 # ExternalCodeList
  methods/
    adsl/trtsdt.yaml
    adlb/aval__alt.yaml         # value-level method
  comments/
    adsl__usubjid.yaml
    empty-dataset-adpp.yaml
  valuelists/
    adlb__aval.yaml             # ValueListDef + inline WhereClauseDefs + value-level ItemDefs
  whereclauses/
    alt-week4.yaml              # named, shared across value lists and/or ARM
  analysis-results/
    primary-efficacy-ancova.yaml   # ARM (native in 2.1)
```

### Granularity rationale

Not everything gets its own file - granularity follows **ownership and sharing**, because that is where concurrent edits actually collide.

- **Codelists: one file each.** Shared across datasets, edited by whoever owns CT. This is the highest-contention object in a define and the one your instinct was right about.
- **Methods: one file each.** Long free text, per-variable, frequently rewritten. Inlining them would make dataset files enormous and turn every derivation tweak into a diff in a file five other people are also editing.
- **Comments, value lists, ARM displays: one file each.** Same argument.
- **Variables: inline in the dataset file.** A variable is ~6 lines. ADSL has 150 of them; exploding that into 150 files makes browsing hostile and `grep` the only navigation tool. A dataset is also the natural *ownership* unit - one programmer owns ADSL. Two people editing different variables of ADSL touch non-adjacent lines, which git merges cleanly; two people editing the *same* variable is a genuine conflict that should surface.
  - Escape hatch: `datasets/adsl/` as a directory with `_dataset.yaml` + one file per variable, for the rare monster domain. Loader accepts either shape.

---

## 3. OID and reference automation

### Core rule: **OIDs are not stored, they are derived - but storing one is always allowed.**

By default, no file contains an OID: cross-references are written by **human-meaningful name**, and the build step resolves names to OIDs and emits the XML. This is the single most important decision in the design, because:

- There is no shared counter anywhere, so two contractors adding objects in parallel branches can never collide on an identifier. Counter-based schemes (`CL.1`, `CL.2`) generate a merge conflict on *every* concurrent addition and silently misassign references if merged carelessly.
- Derived OIDs are legible in the generated XML, which matters when a reviewer or a P21 report points at `IT.ADSL.TRTSDT` rather than `IT.000147`.
- Renaming an object is a rename of one file plus a find-replace of its name; the OID follows automatically and consistently.

Both halves of this - derivation and name-based reference resolution - are the default, not a requirement. Every object definition can carry an explicit `oid:` instead of deriving one, and every reference field can hold a literal `{oid: ...}` instead of a name (see "The `oid:` override" and "The reference-side counterpart" below). This is what lets `define import` followed by `define build` reproduce a source define.xml's OIDs and cross-references even when they don't follow this scheme at all.

### Derivation table

| Object | OID pattern | Example |
|---|---|---|
| Standard | `STD.<name>` | `STD.ADAMIG.1.3` |
| ItemGroupDef | `IG.<DATASET>` | `IG.ADSL` |
| ItemDef | `IT.<DATASET>.<VARIABLE>` | `IT.ADSL.TRTSDT` |
| ItemDef (value-level) | `IT.<DATASET>.<VARIABLE>.<ENTRY>` | `IT.ADLB.AVAL.ALT` |
| CodeList | `CL.<NAME>` | `CL.RACE` |
| MethodDef | `MT.<PATH>` (file path under `methods/`) | `MT.ADSL.TRTSDT` |
| CommentDef | `COM.<PATH>` (file path under `comments/`) | `COM.ADSL.USUBJID` |
| ValueListDef | `VL.<DATASET>.<VARIABLE>` | `VL.ADLB.AVAL` |
| WhereClauseDef (inline) | `WC.<DATASET>.<VARIABLE>.<ENTRY>` | `WC.ADLB.AVAL.ALT` |
| WhereClauseDef (named) | `WC.<PATH>` (file path under `whereclauses/`) | `WC.ALT.WEEK4` |

`<ENTRY>` is the `name:` key of an entry in the value list file - **not** the where-clause condition value. Deriving from the condition breaks as soon as a where clause has two conditions (`PARAMCD EQ ALT AND AVISITN EQ 4`), since there is no single value to name it after.

**Shared objects derive from path, not from the referencing variable.** Methods, comments and named where clauses are all many-to-one: one method can serve `ADSL.TRTSDT` and `ADSL.TRTEDT`; one where clause can serve a value list entry and an ARM analysis dataset. Deriving their OIDs from a referencing variable would name them after an arbitrary one of their consumers. Path derivation means `methods/shared/last-dose-date.yaml` → `MT.SHARED.LAST.DOSE.DATE` regardless of who uses it. Only objects that are genuinely owned by one parent - ItemDef, ValueListDef, inline WhereClauseDef - derive from the parent.
| def:leaf (dataset) | `LF.<DATASET>` | `LF.ADSL` |
| def:leaf (document) | `LF.<NAME>` | `LF.ACRF` |
| arm:ResultDisplay | `RD.<PATH>` (file path under `analysis-results/`) | `RD.T14.2.1` |
| arm:AnalysisResult | `AR.<PATH>.<ENTRY>` | `AR.T14.2.1.ANCOVA` |

Slug rule: uppercase; `[^A-Z0-9._]` → `.`; collapse repeats; strip leading/trailing separators. Derivation is a pure function of `(kind, path/name)` - same inputs always give the same OID, on any machine, in any branch.

**Collision handling:** the build performs a full OID uniqueness check and **hard-fails** on any collision, naming both source files. There is no auto-disambiguating suffix, because a suffix would make OIDs order-dependent and therefore merge-unstable. A collision is a naming problem the humans should fix.

**Standard is a partial exception: two objects legitimately share a `name:`.** A submission can carry more than one `def:Standard` with the same `Name` - most commonly two CT vintages for the same model (`PublishingSet` differs), or two versions of the same IG in one define.xml (neither `PublishingSet` nor even that differs - only `Version` does). This is real, observed CDISC output (confirmed importing both bundled `tests/fixtures/definexml/examples/` submissions), not a hypothetical. A bare `name:` stays the reference key exactly as the derivation table says whenever it is unique across `standards.yaml` - that is the only form worth hand-authoring, and is how every dataset's `standard:` reference resolves. When a `name:` is ambiguous, the linker keys those entries by `name` + `PublishingSet` + `Version` instead, and they become reachable only via `{oid: ...}` - nothing needs to reference one of them by bare name, since `dataset.standard:` always targets exactly one, unambiguously-named IG standard by convention. `codelist.standard:` (§7.2) resolves through the same table.

`dataset.standard:` and `codelist.standard:` are both **optional** - `def:StandardOID` is optional in the schema on both `ItemGroupDef` and `CodeList` (e.g. a custom domain with no declared IG version), and omitting the field, rather than writing an empty reference, is how that's represented.

### The `oid:` override

One optional field, `oid:`, on any object. Two legitimate uses:

1. **Importing an existing define.xml** where OIDs were assigned by another tool and you want submission-to-submission continuity across a resubmission. The importer writes `oid:` only where the existing OID differs from what would be derived, so a clean file set stays clean.
2. Sponsor OID conventions mandated by a partner or a legacy pipeline.

`define lint` reports overrides so they stay visible rather than accumulating silently.

### The reference-side counterpart: `{oid: ...}`

The `oid:` override above makes OID *definition* optional - an object's identifier need not be derived at all. Every reference field that actually resolves to an OID (`codelist:`, `method:`, `comment:`, `valuelist:`, `same_as:`, `origin.document:`, `standard:`, `where:` (named or on a `RangeCheck.variable:`), ARM `dataset:` / `variables:` / `parameter:` / `join_comment:`, `def:DocumentRef`'s `ref:`) accepts the same idea in reference form. (`origin.source:` is not in this list: for a `Predecessor` origin it is free descriptive text - e.g. `DM.STUDYID` - that the emitter writes into `def:Origin/Description`. Define-XML's `def:Origin` has no OID slot for it at all, only a separate controlled-term `Source` attribute - `Investigator`/`Sponsor`/`Subject`/`Vendor` - modeled as `origin.data_source:`, a plain `Literal`, not a `Ref`: it's a fixed vocabulary, not a cross-reference, so there's nothing for a symbol table to resolve.)

```yaml
codelist: race                  # resolved by name through the symbol table, as always
codelist: {oid: CL.RACE_LEGACY} # literal OID; no symbol table lookup
```

A bare string is still the normal, preferred form - it is what keeps references legible and rename-safe, and is the only form worth writing by hand. The `{oid: ...}` form exists for exactly the case the `oid:` override exists for: **round-tripping a define.xml this tool did not generate.**

Why both are needed together, not the `oid:` override alone: the override makes an object's *own* identifier round-trip correctly, but every *reference to* that object is still written as a name, which the linker resolves by deriving an OID from it and matching it against the symbol table. If the importer cannot recover a name for the referenced object at all, a name-based reference is impossible without inventing one. This is not a corner case - `def:WhereClauseDef` has no `Name` attribute in Define-XML at all, so a where clause discovered on import has nothing to name it by, only the raw `def:WhereClauseDef/@OID` string the source tool assigned. An invented name is harmless for a file's own identity (the importer can call the file anything and set `oid:` to the real value), but a fabricated name burned into every *reference* to that object is exactly the accidental-coupling churn the naming scheme exists to avoid - rename it later and every reference site has to move with it, for a name nobody chose. `{oid: ...}` skips the invention step: write the literal OID at every use site, no symbol table entry required.

Practically, this changes what the importer's default strategy is. It is not "derive names everywhere and paper over the mismatches with `oid:` overrides" - it is "use a name-based reference wherever a clean name recovers (dataset, variable and codelist names are the common case, and the only one worth hand-authoring), and fall back to `{oid: ...}` plus a bare `oid:` override on the target wherever it doesn't." Both escape hatches together, not either alone, are what let define.xml → yaml → define.xml preserve OIDs and references regardless of the source tool's naming conventions, without forcing every hand-authored file to deal with raw OIDs for the common case.

The linker resolves a `Ref` field as: mapping with `oid:` → use that OID directly, no lookup; plain string → resolve through the symbol table exactly as before (derived OID, or the target's own `oid:` override if it has one). `define lint` reports `{oid: ...}` references alongside `oid:` overrides, for the same reason: visibility, not restriction.

### Ordering attributes are positional, never stored

- `ItemRef/@OrderNumber` = index of the variable in the dataset file's `variables:` list.
- `ItemRef/@KeySequence` = position in the dataset's `keys:` list.
- `CodeListItem/@OrderNumber` = index in `terms:`.
- `ItemRef/@Role`, `@Mandatory` etc. remain explicit fields.

Storing these as numbers would guarantee a conflict every time two people insert a variable - the whole list renumbers. Positional derivation confines the conflict to the actual insertion point.

**`CodeListItem`/`EnumeratedItem`'s `@Rank` is the exception on a term, and it's stored** (`Term.rank`, `int | float | None`). Define-XML is explicit that `@Rank` "does not imply a display order" - it's the numeric significance of the term relative to its siblings (severity 1/2/3, age-group ordering), a semantic value with no positional signal to derive it from, exactly like `dataset_order:`. It's optional but, per the Define-XML business rule plus this tool's own distinctness rule, all-or-none across a codelist and distinct when set - `EnumeratedCodeList._check_ranks`. `@OrderNumber` stays positional (row index); `define import` captures `@Rank` verbatim, drops `@OrderNumber`.

**One exception: dataset (`ItemGroupDef`) sequence.** Every case above orders things *within* one file - a YAML list whose position a build derives an attribute from. Datasets are separate *files*, with no shared list to derive a position from, so their document order in the emitted XML has nothing to be positional *about* - it defaults to alphabetical-by-name, which buries ADSL under every other ADaM dataset a reviewer would expect to read first. `study.yaml`'s `dataset_order: [ADSL, ADAE, ...]` is the one ordering concern in the whole model that's stored explicitly rather than derived, precisely because there's no positional signal available to derive it from. It's optional and additive: a dataset not listed sorts after every listed one, alphabetically - so a study that never touches it stays exactly as alphabetical as it always was, and `define lint`'s `dataset-order` rule flags a listed name that no longer matches any dataset (a stale rename, or a typo) as an error. `define import` captures a source define.xml's actual `ItemGroupDef` sequence into `dataset_order:` (only when it isn't already alphabetical, to avoid writing noise for the common case) so re-running `define build` reproduces the same order, not a freshly-alphabetized one. The webui's sidebar reorders datasets with drag-and-drop or move-up/down, the same interaction `cardListEditor`'s list reordering already uses - the one kind that gets this, since every other kind's document order is cosmetic (each object is independently OID-referenced, so nothing reads it top-to-bottom the way a reviewer reads datasets).

### The linker pass

Reference resolution is a distinct build stage that runs before any XML is emitted:

1. Load every file, validate each against its schema.
2. Build the symbol table: name → derived OID, per object kind.
3. Resolve every reference: `codelist:`, `method:`, `comment:`, `valuelist:`, `origin.document:`, ARM `dataset`/`variable`/`whereclause`. Each of these is a `Ref` (§3, "The reference-side counterpart") - a literal `{oid: ...}` resolves with no lookup; a name resolves through the symbol table as below. (`origin.source:` is plain descriptive text for a `Predecessor` origin, not a reference - see the note above.)
4. **Unresolved reference → hard error**, with file and line number from the ruamel node.
5. **Orphan object → warning** (a codelist, method or named where clause nothing references).
6. Emit.

### Where-clause specific rules

- **Multiple `values:` require `IN` or `NOTIN`.** `EQ` with two check values is invalid; error.
- **Cross-dataset conditions require a comment.** Per the Define-XML errata, `def:WhereClauseDef/@def:CommentOID` must reference a CommentDef describing how the datasets are joined whenever the clause references variables in more than one dataset. Missing comment → error, not warning.
- **Duplicate inline clauses → warning.** Two or more inline `where:` blocks with identical resolved content suggests promoting to a named clause under `whereclauses/`. Not auto-merged: automatic content-addressed deduplication is how tools end up emitting OIDs like `WC.SUPPCL.QNAM.EQ.1ea50245ec370ef4afdec5db2faea0cfccfd14f4`, which is valid but unreadable and exactly what this scheme exists to avoid.
- **No OR.** The model has no representation for it, by design, because Define-XML has none. Disjunction is expressed as multiple ItemRefs against one ItemDef via `same_as:`.

This matters concretely: broken hyperlinks are the single most common define.html defect, and they almost always trace back to a method or codelist that is referenced but never defined. Making that a build-time error rather than a reviewer-time discovery is most of the value of this tool.

---

## 4. Worked examples

**`datasets/adsl.yaml`**
```yaml
name: ADSL                                # -> IG.ADSL
label: Subject-Level Analysis Dataset
class: SUBJECT LEVEL ANALYSIS DATASET
structure: One record per subject
purpose: Analysis
repeating: false
is_reference_data: false
standard: adamig-1-3                      # -> def:StandardOID = STD.ADAMIG.1.3
leaf:
  href: adsl.xpt                          # explicit; ID derived as LF.ADSL
keys: [STUDYID, USUBJID]

variables:
  - name: STUDYID                         # -> IT.ADSL.STUDYID, OrderNumber 1
    label: Study Identifier
    type: text
    length: 12
    mandatory: true
    origin:
      type: Predecessor
      source: DM.STUDYID

  - name: TRTSDT
    label: Date of First Exposure to Treatment
    type: integer
    display_format: DATE9.
    mandatory: false
    origin: {type: Derived}
    method: adsl/trtsdt                   # -> MT.ADSL.TRTSDT

  # CT extended per protocol s7.2 - see codelists/race.yaml for rationale
  - name: RACE
    label: Race
    type: text
    length: 40
    mandatory: false
    codelist: race                        # -> CL.RACE
    origin: {type: Collected, document: acrf, pages: [4, 5]}
```

**`codelists/race.yaml`**
```yaml
name: RACE                                # -> CL.RACE
label: Race
type: text
nci_code: "C74457"                        # -> Alias Context="nci:ExtCodeID"
extended: false                           # -> def:IsNonStandard / ExtendedValue
terms:
  - code: "WHITE"
    decode: White
    nci_code: "C41261"
  - code: "AMERICAN INDIAN OR ALASKA NATIVE"
    decode: American Indian or Alaska Native
    nci_code: "C41259"
```

**`methods/adsl/trtsdt.yaml`**
```yaml
name: Treatment Start Date
type: Computation
description: |
  Date part of the earliest non-missing EXSTDTC in EX where EXDOSE > 0,
  converted to a numeric SAS date. Subjects with no qualifying exposure
  record have TRTSDT set to missing.

  Partial dates are not imputed; see ADRG s4.1.
expressions:
  - context: SAS 9.4
    code: |
      trtsdt = datepart(min(of _exstdtc[*]));
      if trtsdt = . then call missing(trtsdt);
  - context: R
    code: |
      trtsdt <- ex |>
        dplyr::filter(EXDOSE > 0, !is.na(EXSTDTC)) |>
        dplyr::pull(EXSTDTC) |>
        min(na.rm = TRUE)
```

Everything after `#` and every word of prose above is preserved on save and never reaches the XML.

---

## 5. Python stack

| Concern | Choice | Note |
|---|---|---|
| YAML I/O | `ruamel.yaml` (round-trip mode) | Comment/order preservation, YAML 1.2 |
| Model + validation | `pydantic` v2 | Typed model, precise error messages, and `model_json_schema()` gives JSON Schema for free |
| XML emission | `lxml` | Namespace handling, pretty-printing |
| XSD validation | `lxml.etree.XMLSchema` against `define2-1-0.xsd` | Runs in CI on every commit |
| define.html | `lxml` XSLT (libxslt) | The CDISC 2.1 stylesheet is XSLT 1.0, which libxslt covers; no Saxon dependency needed |
| CLI | `typer` | `define build` / `fmt` / `lint` / `import` / `edit` |
| Web editor | `fastapi` + `uvicorn` (optional `ui` extra), dependency-free vanilla JS frontend | `define edit` - local-only, no build step, no auth |
| Packaging | `uv` + `pyinstaller` for single-file binaries | Avoids the "get Python approved on the CRO laptop" fight |

### Free win worth exploiting

Exporting the pydantic model as JSON Schema and publishing a `# yaml-language-server: $schema=...` header on generated files gives every contractor **autocomplete, inline validation, and hover docs in VS Code with zero installation**. For a lot of users that is already a usable editor, which takes pressure off the GUI and lets you defer the native-app question until the data model has settled.

---

## 6. Build order

0. `init` - scaffold a brand-new file tree (every object-kind subdirectory, a minimal study.yaml) for a submission with no existing define.xml to import from. Not part of the original numbered sequence - added once `import` (step 1) turned out to only cover *half* of "how does a `define/` tree come into existence": the other half is a study with nothing to import yet.
1. `import` - parse a real define.xml v2.1 you already have, explode into the file tree, write `oid:` overrides where needed.
2. `build` - file tree → define.xml, byte-comparable in content to the original (attribute order and whitespace will differ; compare canonicalised XML).
3. Round-trip test on several real submissions. **Do not write a line of UI until this passes.** If the model is wrong, it is wrong cheaply now and expensively later.
4. `lint` - xref integrity, orphans, P21-adjacent rules.
5. `fmt` + pre-commit hook.
6. define.html via XSLT.
7. UI.
8. "Smart mode" (§9) - a local-first CT / standards browser: NCI EVS CT (version-pickable, on-demand download) + a user-configured folder of CDISC CSV exports. The CDISC Library API client this started as is retired (modules kept, unrouted). Wiring CT into the editor's own fields is still ahead.

**Status:** steps 0-2 are implemented and wired into the CLI (see `CLI.md`) - `init` (`src/defineyaml/scaffold.py`, `tests/test_scaffold.py`) is a thin `cli.py` prompt wrapper around a plain `scaffold_tree()` function, the same split every other command uses, so the scaffolding logic is tested directly rather than through faked stdin. `scaffold_tree()` prompts for the six required `StudyFile` fields but also **pre-fills the ODM header** (both `define init` and the webui launcher's "Create" get this): `as_of_datetime` = now (local, ISO 8601), `originator` = the OS user, `source_system`/`source_system_version` = `DefineYAML`/`importlib.metadata.version("defineyaml")`, `stylesheet` = `define2-1.xsl`, `metadata_version.define_version` = `2.1.0` (written explicitly even though it equals the model default, since a preparer should see it). `creation_datetime` is **left blank on purpose** - `build_document_tree` (so `define build`, "View define.xml" and "View define.html" alike) fills the XSD-required `CreationDateTime` with `tree_time.latest_modification(source)` whenever `odm.creation_datetime` is empty: the committer date of the last commit touching the tree path when it's a git working tree with tracked files (`git log -1 --format=%cI -- .` - adds, edits, deletes and renames all count), else the newest `*.yaml`/`*.yml` mtime under the tree (dot-dirs skipped), else `now` (a tree with no files, which can't build anyway). An explicitly-set `creation_datetime` is emitted verbatim and never touched, so import→build round-trips it. The webui study editor shows this computed value as the field's placeholder (ghost text) via `GET /api/tree/last-modified`, with a hint explaining the git-vs-mtime rule. A fresh tree still builds a spec-complete `<ODM>` header + `<?xml-stylesheet?>` PI with no hand-editing, and everything stays editable in `study.yaml`. Step 3 is a hard gate now: `tests/test_roundtrip.py` runs `import` → `build` against both bundled submissions (vendored under `tests/fixtures/definexml/`) and checks XSD validity (against `arm1-0-0.xsd`, which transitively redefines the full ODM → define-extension → arm-extension chain - `define2-1-0.xsd` alone doesn't pull in ARM) plus object/reference/content/ordering survival and per-object canonicalised-XML equivalence. See §8 for what that testing has found and fixed, and what's still open.

**Step 4 (`lint`) is implemented** (`src/defineyaml/lint.py`, `tests/test_lint.py`; the full rule list, with severities, is in `CLI.md`). Worth calling out here because getting it working uncovered a real, pre-existing bug in `xml_emit.py`, not something this pass introduced: every `_xxx_def` emission function (`_codelist`, `_method_def`, `_comment_def`, `_where_clause_def`, and eight others) retrieves its own registered OID via `table.lookup(kind, own_key) or derive(...)` - so that an `oid:` override is respected without re-deriving it - but `SymbolTable.lookup()` marks whatever it looks up as *referenced*, as a side effect meant for tracking genuine cross-references (`resolve_ref` and friends in `linker.py`). Every object's own emission touching its own key this way meant `SymbolTable.orphans()` could never find a real orphan for any of the four kinds it's called with (`codelist`, `method`, `comment`, `whereclause`) - the self-lookup always marked it "referenced" first. Fixed with a new `SymbolTable.lookup_own()` (identical, minus the side effect) and all fourteen self-lookup call sites in `xml_emit.py` switched to it; `resolve_ref`/`resolve_item_ref`/`resolve_scoped_item_ref`/`resolve_valuelist_ref` - the ones representing an actual reference from one object to another - still use `lookup()` unchanged. Confirmed against the bundled example tree (`tests/fixtures/define/`): `define lint` (and now `define build`'s own orphan warning, which was equally silent before) correctly flags `codelists/meddra.yaml` as unreferenced, where it previously reported nothing.

**Step 6 (define.html) is implemented for the webui, ahead of `fmt` (step 5), since it was asked for directly**: `src/defineyaml/html_render.py` runs the same linker pass + XML emission `define build` does (`xml_emit.build_document_tree`, extracted so `write_define_xml`/`render_xml_bytes`/`render_html` can never produce different XML for the same tree) and feeds the result through `stylesheets/define2-1.xsl` via `lxml.etree.XSLT` - libxslt covers this stylesheet's XSLT 1.0 directly, no Saxon dependency, exactly per the table above. The stylesheet is vendored from https://github.com/lexjansen/define-xml-2.1-stylesheets (`cdisc-2019/stylesheets`, MIT-licensed, `stylesheets/define2-1.xsl.LICENSE.TXT`) rather than fetched at runtime - self-contained, no further `xsl:import`/`xsl:include` to chase down, so vendoring is one file. The webui gets two new links, "View define.xml" and "View define.html", in a `#sidebar-actions` row under the study/protocol header - plain `<a target="_blank">`s pointing at `GET /api/render/xml`/`GET /api/render/html`, not fetch()-driven buttons, since each endpoint already returns the whole document with the right `Content-Type`; the browser's own tab does the rendering (or download), and a `LinkError` (the identical unresolved-reference/collision conditions that would fail a real `define build`) surfaces as a 422 with the same message the CLI would print, shown as the browser's own error page rather than needing to be caught and displayed by the frontend.

**Stylesheet is pluggable.** `html_render.available_stylesheets()` globs every `*.xsl` in `stylesheets/` (default `define2-1` sorts first; `.LICENSE.TXT` isn't matched), `render_html(source, stylesheet=DEFAULT_STYLESHEET)` takes a stem and caches one compiled `etree.XSLT` per `(process, stylesheet)`, and an unknown name is a `ValueError` - membership-checked against the glob, which is also the path-traversal guard (`../foo` is never a stem). `GET /api/render/stylesheets` returns `[{name, label, default}]` (`stylesheet_label()` prettifies the stem - `define2-1` → "Classic (CDISC 2019 stylesheet)", `define2-1-modern` → "Modern"); `GET /api/render/html` gained an optional `?stylesheet=` (unknown → 400). The frontend (`renderSidebarActions`) renders the plain "View define.html" link first, then - only if the endpoint reports **more than one** stylesheet - appends a `<select>` beside it that rewrites the link's `href` to `/api/render/html?stylesheet=<name>`; a slow or failed fetch just leaves the default-stylesheet link. The repo currently ships two: the vendored `define2-1.xsl` and `define2-1-modern.xsl` (a self-contained restyle, same XSLT-1.0 / no-import constraint).

**Step 7 (UI) has a first cut**, out of order (`fmt` - step 5 - isn't built yet; this was asked for directly): `define edit` (`src/defineyaml/webui/`), a local FastAPI server plus a dependency-free vanilla-JS frontend, structured "structure only, editor-appropriate" per the stylesheet's information architecture (dataset/variable/codelist tables, cross-linked), not a visual clone of the static define.html report. It reads and writes every object kind - a save PUTs the whole edited object back, and `webui/tree.py`'s `_merge` folds it into the on-disk `CommentedMap`/`CommentedSeq` loaded from that file, so an untouched key or list item (matched by `name`/`code`/`context`) keeps its comment; a field the UI has no widget for round-trips unmodified because it was never removed from the working copy in the first place, not because anything special-cases it. Validation runs the real pydantic model before anything is written - an invalid save is rejected with field-level errors and the file is left untouched. Ahead of that, individual fields highlight **live** as you type (`attachValidation` in `app.js` - a red outline + message for an error, amber for a soft warning, re-checked on every `input`/`change` bubbling out of the row, reading the control's own value so it needs no item/key): a field spec (or a `*Field` opts object) carries `validate(value) -> null | "error" | {msg, warn:true}`, with `requiredField`/`maxLenField` helpers. Currently wired for the required Name/Label/Class/Structure of a dataset and Name/Label/Type of a variable, plus the 40-char xpt label cap as a warning, and a variable-name convention check (`variableNameWarnings`) that amber-flags a name that's `--`/lowercase-templated (`--SEQ`, `SMQzzSC`), over 8 chars, or not `[A-Za-z_][A-Za-z0-9_]*` - on both `name:` and `sas_field_name:`. This is a visual aid only - empty `class:`/`structure:` are valid `str` to pydantic, an off-spec variable name is a valid `str` too, so the highlight catches what a save otherwise wouldn't. Every object also has a raw-JSON fallback for whatever the structured widgets don't cover yet (the deeper `arm:AnalysisResult` nesting - `datasets:`, `documentation:`, `programming_code:` - most notably). `tests/test_webui.py` covers the comment-preservation guarantee directly against a real file, not just the merge function in isolation.

**`define` with no arguments** opens the editor to a **launcher** (`cli.py`'s `_default` → `_serve_editor(None, ...)` → `create_app(None)`, so `app.state.root` starts `None`; `create_app`'s param is now `Path | None` and `/api/info` returns `{"source": null}` rather than 500-ing). `boot()` sees `/api/setup/status`'s `needs_setup` and renders `renderSetup()` instead of the two-pane editor. Three ways in: **Recent** (`/api/setup/recent` → up to 10 trees from `~/.config/defineyaml/config.json`'s `recent_trees` list - `webui/config.py`, MRU, deduped, each filtered to still-a-directory and labelled from its `study.yaml`; migrates the old single `last_tree` key), **Browse** (`/api/setup/browse` - a server-side directory picker, since a browser can't hand back a real filesystem path; lists sub-directories, flags the ones with a `study.yaml`), **Create** (`/api/setup/init` → `scaffold_tree`, OIDs from a slug of the study name). `/api/setup/open` or `/api/setup/init` points `app.state.root` at the choice in place, no restart, and `config.remember_tree()` moves it to the front of the recent list - as does `define edit` on its explicit `--source`. `define edit` with a `--source` that isn't a directory (the default `define/` missing, a typo) no longer errors - it prints a note and starts on the same launcher (`_serve_editor` coerces a non-dir source to `None`). Once a tree is open, an **"Open another tree"** link in `#sidebar-actions` calls `renderSetup()` over the live editor (guarding `state.dirty` with a confirm); the launcher then shows a "← Back to the current tree" button (it fetches `/api/info` to know a tree is open) and picking one `location.reload()`s onto it. `webui/config.py` is deliberately a flat machine-wide file, distinct from `state.py`'s per-tree `editor-state.json`. `tests/test_editor_setup.py` covers the recent-list MRU/cap/migration, the bare-`define` dispatch, the `define edit` fallback, and every setup route.

Also: an **autosave toggle** (debounced ~900ms after the last edit, cancelled if you switch objects mid-debounce so it can't fire against the wrong key); **collapsible cards** in every list-of-objects editor (variables, terms, expressions, ...) - a list longer than 5 starts collapsed (a 150-variable dataset opens scannable, not a wall of open forms), with per-card and collapse-all/expand-all toggles, tracked by object identity (a `WeakMap`, not a data field, so it never leaks into a save payload); a **collapsible sidebar** - each kind group (Datasets, Codelists, ...) toggles independently, and a group holding the current selection can't collapse out from under it; and a **remembered last-opened view** plus the autosave preference, persisted per source tree in `~/.config/defineyaml/editor-state.json` (`webui/state.py`) rather than browser storage or inside the tree itself - deliberately not tracked content, so opening `define edit` again (any browser, same machine) returns to where you left off. (Sidebar collapse state itself is in-memory only, not persisted - an ordinary tree-view expand state, not edit-session state.)

**Every object shows what references it, or that nothing does** (`webui/usages.py`). Deliberately independent of `linker.py`'s resolution, the same way `tree.py`'s reads are: the linker needs the *whole* tree to validate before it resolves anything, which would blank the usages panel for every object the moment one file has a typo, not just the broken one. Instead it re-walks raw YAML across every file (skipping one that fails to parse, rather than failing the whole scan) and matches reference text against each candidate's identity - `name:` for most kinds, path-derived for the "no Name in Define-XML" kinds (methods, comments, whereclauses, analysis-results), `dataset:`+`variable:` for value lists (which have neither - the first cut of this got that wrong and returned `None` for every value list, so nothing could ever show as using one; a regression test pins it now) - via the same `oid.slugify()`/`path_to_slug()` normalisation the real linker uses, so a match here is one a real build would resolve the same way. `{oid: literal}` references aren't tracked (no name to match against - CLAUDE.md §3's escape hatch, not the form anyone hand-authors) and are invisible here by design, called out in the UI copy rather than silently pretended not to exist. A singleton file (study/standards/documents) is never flagged orphan - nothing ever references the *file*, only individual entries within it, which this scans at file granularity - so "unused" isn't a meaningful question to ask of one. Every other kind gets both a sidebar badge (`unused`, computed once per kind-list request, not per item) and, on the object's own page, a panel listing every referencing object grouped by kind, each a link that jumps straight to it.

**Every list-of-objects card (variables, terms, expressions, ...) can be reordered** - move-up/move-down buttons and native HTML5 drag-and-drop, both routed through one `moveItem()` in `cardListEditor` so the two input methods can't drift apart. This isn't cosmetic: CLAUDE.md §3's "Ordering attributes are positional, never stored" means list position *is* `OrderNumber`/`KeySequence`/term order/etc. - dragging a variable is literally how a user changes its derived `OrderNumber`. A reorder mutates the array and goes through the same `notifyDirty()`/autosave path as any other edit, and - verified against the real repo tree, not just asserted - a save after reordering correctly carries each moved item's own comment with it (`_merge`'s identity-matching by `name:`/`code:`/`context:`, not list position, is what makes that work).

**The dataset list in the sidebar can be reordered too** - the same move-up/move-down-plus-drag-and-drop interaction, but this one writes `study.yaml`'s `dataset_order:` (§3's one exception to "ordering is always positional, never stored") through a dedicated `PUT /api/datasets/order`, since a sidebar reorder touches a *different* object (`study.yaml`) than whatever happens to be open in the editor pane - `cardListEditor`'s `moveItem()` mutates the list it's already editing in place, which doesn't apply here. `webui/tree.py`'s `list_items()` sorts its "datasets" response through the same `dataset_order:` (a small, independent re-implementation of `linker.py`'s `_ordered_datasets`, on the raw `{key, label, name}` shape `list_items` already works with, since this module deliberately doesn't require the whole tree to validate the way `linker.load_tree` does) - so the sidebar's own ordering always matches what a build would actually produce, not a stale alphabetical view of it. Every other kind's sidebar list stays unreorderable, since only dataset sequence is real content (§3) - reordering codelists or methods would be UI for its own sake.

**The browser tab title and sidebar header identify which tree and study are open**, not a generic "define edit" - the only way to tell two tabs on different studies (or two checkouts of the same study) apart. A new `GET /api/info` returns the tree's absolute, resolved path; `app.js`'s `applyTreeIdentity()` combines that with a read of `study.yaml`'s `study.name`/`study.protocol_name` (the same object-read endpoint the sidebar already uses, no new backend surface needed for that half) into `"{name} - {protocol} - define edit"` for the tab, and a two-line sidebar header (name/protocol bold, the full path in small monospace beneath, wrapping onto further lines rather than truncating - a real tree's path is often longer than the 300px sidebar, and unlike a card's summary line this is the one piece of text in the UI whose entire job is telling two otherwise-identical windows apart, so hiding half of it behind an ellipsis would defeat the point). Best-effort like every other startup read here: a study.yaml with the fields still blank, or a pre-`/api/info` server, just falls back to the plain "define edit" title rather than erroring.

**The sidebar has Expand all / Collapse all buttons**, above the kind-group list, alongside the per-group collapse toggles from before - `sidebarCollapsed.clear()` / adding every kind to it, then `renderSidebar()`, the same two-line shape as the identical buttons every card-list editor already has. A group holding the current selection still can't collapse out from under it (the existing override in `renderSidebar`'s render loop applies regardless of which button - or neither - put it in `sidebarCollapsed`), so "Collapse all" is safe to call unconditionally rather than needing to special-case the selected kind.

**Every list-of-objects editor can switch between table and card layout** - a "Table view"/"Card view" toggle, generalised to all nine lists (`documents.documents`, `datasets.variables`, `codelists.terms`, `methods.expressions`, `comments.documents`, `whereclauses.conditions`, `valuelists.entries`, `analysis_results.results`, plus `standards`). **Table is the default** - a compact grid reads better for the common case (many rows, a few short fields) and, per the guarantee below, is never a narrower editor than cards; a wide list (the ~15-column variables table) scrolls horizontally in its `.table-list` container rather than squashing every field. The user can switch any single list to cards, file-by-file, and that choice sticks. Implementation-wise `listViewState[viewKey]` is absent until the user toggles a list and then holds `false` for card / `true` for table, so `listViewState[viewKey] !== false` is "table unless they said otherwise".

`tableListEditor(list, fields, opts)` takes the identical `list`/`fields`/`opts` shape `cardListEditor` already does - same field specs, same `newItem`/`addLabel` - and renders one `<tr>` per item, one `<td>` per field, reusing `duplicateItem()`'s identity-uniqueness prompt and the same in-place `moveItem()` (drag-and-drop plus move-up/down buttons) so the two layouts can never allow different things. `opts.extra` (the nested Origin editor on a variable, the where-clause/Item sub-form on a value-list entry, ...) - the one thing a `<td>` grid has no natural column for - renders as a full-width row directly under the item's own row instead, specifically so table view is never a *narrower* editor than card view for the four kinds that use it; switching views must never hide something the other one could edit. Getting there required splitting each field widget (`textField`, `selectField`, `refField`, ...) into a bare `*Control` (the input/select alone, with the `notified()` onChange wiring) and the existing `*Field` (that control inside `fieldRow`'s label+hint wrapper) - `buildCellFromSpec` uses the bare controls directly for a `<td>`, where the column header is already the label. `toggleableListEditor(viewKey, list, fields, opts)` is the small wrapper every editor calls - `viewKey` (e.g. `"codelists.terms"`) rather than a `getView`/`setView` pair, since the view choice for each of the nine lives in one shared `listViewState` object keyed by that string, not nine separate module-level variables. The choice is persisted (`API.putEditorState({list_views: listViewState})` → `~/.config/defineyaml/editor-state.json`, `webui/state.py`) and restored in `boot()`, the same per-machine-UI-preference bucket as the autosave toggle.

**Closing or reloading the tab with unsaved edits asks for confirmation** - a `window.beforeunload` handler that fires only when `state.dirty` is true. `state.dirty` is already the exact right signal for this: `notifyDirty()` sets it on every edit, and it's cleared the instant an edit is actually persisted (a manual save, the autosave debounce firing, or switching away from the object via `resetEditingState()`), so the prompt appears only when something would genuinely be lost - never when autosave has already caught up, and correctly when it's off or a change is still sitting inside the ~900ms debounce window. No custom warning text: every modern browser shows its own generic wording regardless of what `returnValue` is set to; setting it anyway (alongside `preventDefault()`) is what actually triggers the native dialog across browsers, not what it says.

---

## 7. Resolved decisions

### 7.1 ARM - in scope from the start

Analysis Results Metadata is native in Define-XML 2.1 (`arm:` namespace), not a bolt-on extension. Including it now avoids a layout migration later, and it exercises the shared-object machinery immediately: an `arm:AnalysisDataset` references a `def:WhereClauseDef` by exactly the same mechanism a value list entry does, which is the strongest argument for having made named where clauses shareable.

**One file per ResultDisplay; results are entries within it.** A display (a table or figure in the submission) is the unit a statistician owns and reviews, and it maps to one TFL output. Its results are rarely edited independently of it.

```yaml
# analysis-results/t14-2-1.yaml               -> RD.T14.2.1
name: Table 14.2.1
title: Change from Baseline in ALT at Week 24 - Primary Efficacy
document:
  ref: t14-2-1                                # leaf from documents.yaml
  pages: {first: 112, last: 114}              # or  pages: [112, 113, 114]

results:
  - name: ANCOVA                              # -> AR.T14.2.1.ANCOVA
    description: |
      ANCOVA of change from baseline in ALT at Week 24, with treatment as a
      fixed effect and baseline ALT as a covariate. Safety population.
    parameter: ADLB.PARAMCD                   # -> ParameterOID = IT.ADLB.PARAMCD
    reason: SPECIFIED IN PROTOCOL
    purpose: PRIMARY OUTCOME MEASURE
    datasets:
      - dataset: ADLB
        where: alt-week24                     # named WC, or an inline condition list
        variables: [AVAL, BASE, CHG, TRTPN]
      - dataset: ADSL
        variables: [SAFFL]
    join_comment: join-adsl-adlb              # required whenever >1 dataset
    documentation:
      description: See SAP section 9.2.
      document: {ref: sap, pages: {first: 45, last: 46}}
    programming_code:
      context: SAS 9.4
      code: |
        proc mixed data=adlb;
          class trtpn;
          model chg = trtpn base / ddfm=kr;
        run;
```

`programming_code` accepts either an inline `code:` block scalar or a `document:` reference to a submitted program, not both.

**Lint rule:** `arm:AnalysisDatasets` requires a `def:CommentOID` when the result spans more than one dataset, explaining the join - the same obligation, and the same rule, as a cross-dataset where clause. Missing `join_comment` with two or more datasets is an error.

### 7.2 External codelists - distinct shape, shared namespace

An `ExternalCodeList` is a dictionary reference, not an enumerable membership list. The schema forbids mixing it with `CodeListItem`/`EnumeratedItem` children, so the two are a **discriminated union on the presence of `external:`**, not one model with optional fields:

```yaml
# codelists/meddra.yaml                       -> CL.MEDDRA
name: MEDDRA
label: MedDRA
type: text
external:
  dictionary: MedDRA
  version: "26.1"
```

```xml
<CodeList OID="CL.MEDDRA" Name="MedDRA" DataType="text">
  <ExternalCodeList Dictionary="MedDRA" Version="26.1"/>
</CodeList>
```

They stay in `codelists/` alongside enumerated lists rather than in a subdirectory, because **the reference namespace must be unified**: an ItemDef references either kind identically, via `CodeListRef`, so `codelist: meddra` and `codelist: race` have to resolve out of one symbol table. Only the file's internal shape differs.

Consequences the model enforces:
- `terms:`, `extended:` and `nci_code:` are **rejected fields** on an external codelist - pydantic errors with a readable message before the XSD gets a chance to produce an opaque one.
- CT lint rules (term coverage, NCI code presence, extensibility) skip external codelists entirely rather than reporting thousands of false positives against MedDRA.
- `where-used` and type-agreement checks still apply, since both kinds are referenced the same way.

`ExternalCodeList/@Dictionary` in the webui gets a **datalist fed from CT C66788** ("CodeList Dictionary Name", NCI `C66788`, itself an extensible codelist - COSTART, ICD, LOINC, MedDRA, SNOMED, WHOART, WHODD, …): `standard_scaffold.external_dictionary_names(root)` reads C66788's submission values out of an attached CT `standards_file` (matched by the C-code, via the existing `codelist_reference`), falling back to a built-in sample list when no CT is attached or it doesn't carry C66788. Route `GET /api/standards/external-dictionaries`. It's an input aid only - the field stays free-text (the user can type a value CDISC hasn't listed), and a chosen dictionary name is never a `def:Standard` entry, just the `@Dictionary` string.

**A term can omit `decode:`.** ODM's `CodeList` content model is a three-way choice - `CodeListItem*` (has `Decode`) *or* `EnumeratedItem*` (a coded value with no human-readable label) *or* `ExternalCodeList` - never a mix of the first two within one `CodeList`. A term with no `decode:` emits as `EnumeratedItem`; real submissions use this for lists where the code is already self-explanatory (age groups, treatment-arm labels). `terms:` must be uniform - either every entry has `decode:` or none do - enforced by a pydantic validator, since mixing the two would silently violate the schema's choice.

```yaml
# codelists/agegr1.yaml
name: AGEGR1
label: Age Group
extended: true
terms:
  - code: "<65"
  - code: "65-80"
  - code: ">80"
```

**`standard:` links a codelist to the CT version its terms come from** (`def:StandardOID`), resolving the same reference through the same symbol table as `dataset.standard:` - see the Standard disambiguation note in §3.

```yaml
codelist: race
standard: ct-2024-06-28   # -> def:StandardOID = STD.CT.2024.06.28
```

### 7.3 `def:leaf` - explicit href

Datasets carry an explicit `leaf:` block rather than deriving the href from the dataset name. Non-standard filenames, split datasets and `.xpt` versus other transport formats all break derivation, and a wrong `xlink:href` produces a define.html that looks perfect and links nowhere.

```yaml
leaf:
  href: adsl.xpt
  title: adsl.xpt          # optional; defaults to basename(href)
```

Two deliberate softenings, flagged rather than hidden:
- **`title:` defaults to the href basename.** `def:title` is identical to the filename in essentially every submission; making all 40 datasets state it twice is noise, not explicitness.
- **The leaf `ID` is still derived** (`LF.ADSL`), because a dataset leaf has exactly one owner. That is the same ownership rule that governs ItemDefs and ValueListDefs, applied consistently.

Documents are explicit throughout, since they have no owning dataset to derive from:

```yaml
# documents.yaml
documents:
  - name: acrf                                # -> LF.ACRF
    href: acrf.pdf
    title: Annotated Case Report Form
  - name: adrg
    href: adrg.pdf
    title: Analysis Data Reviewer's Guide

annotated_crf: [acrf]                         # -> def:AnnotatedCRF/def:DocumentRef
supplemental_docs: [adrg]                     # -> def:SupplementalDoc/def:DocumentRef
```

`annotated_crf:`/`supplemental_docs:` are each a plain list of names resolved through the same `documents:` symbol table as any other `document:` reference - no separate definition, just a reference to one already listed above.

### 7.4 `xml:lang` - hard-coded `en`

Descriptive text is a plain string in the model; the emitter wraps it in `<TranslatedText xml:lang="en">`. No language field anywhere in the file format. Multi-language `TranslatedText` is effectively unused in regulatory submissions, and modelling it would put an `xml:lang` key on every description in every file for a case nobody hits.

**The importer must fail loudly, not silently.** If an incoming define.xml contains any `TranslatedText` with a lang other than `en`, or more than one per parent, importing would silently discard content - real data loss, and the kind that is invisible until a reviewer notices. The importer errors, lists every offending element with its XPath, and offers `--force-lang en` for the user who has looked and decided the non-`en` text is disposable.

This is the one decision that is genuinely hard to reverse: adding `xml:lang` later means touching every description field in every file. Worth revisiting only if a non-US submission actually requires it.

### 7.5 FormalExpression - modelled, in MethodDef

`MethodDef` carries a human-readable `Description` and zero or more `FormalExpression` elements holding the machine-readable implementation. `Context` is required and must be distinct per expression within a method.

```yaml
expressions:
  - context: SAS 9.4
    code: |
      trtsdt = datepart(min(of _exstdtc[*]));
  - context: R
    code: |
      trtsdt <- min(ex$EXSTDTC[ex$EXDOSE > 0], na.rm = TRUE)
```

```xml
<MethodDef OID="MT.ADSL.TRTSDT" Name="Treatment Start Date" Type="Computation">
  <Description><TranslatedText xml:lang="en">Date part of the earliest ...</TranslatedText></Description>
  <FormalExpression Context="SAS 9.4">trtsdt = datepart(min(of _exstdtc[*]));</FormalExpression>
  <FormalExpression Context="R">trtsdt &lt;- min(ex$EXSTDTC[ex$EXDOSE &gt; 0], na.rm = TRUE)</FormalExpression>
</MethodDef>
```

Always a list, even for one expression. A scalar shorthand would mean two shapes for the emitter and the formatter to handle, for four saved characters.

**This is the strongest argument for the whole file format.** Code is multi-line and whitespace-significant. In a spreadsheet-metadata workflow it lives in one cell with embedded newlines - unreviewable, undiffable, and mangled by every round-trip through Excel. As a YAML block scalar it is ordinary source code in an ordinary text file: syntax-highlighted, line-diffable, greppable, and reviewable in a pull request like any other code.

Handling rules:

- **Block scalars only.** The formatter rewrites every `code:` value as `|` regardless of input. Never `>` (folded), which destroys line structure, and never a quoted scalar, which turns newlines into escapes.
- **Whitespace fidelity is a hard requirement.** Block scalars strip the common leading indent on load and re-add it on dump; relative indentation inside the code must survive untouched. Chomping matters too - `|` clips to a single trailing newline, `|-` strips it. Pick one (`|`) and normalise, then assert byte-equality of every `code:` value across a load-dump cycle in the round-trip test suite. This is the one field where a formatter bug silently corrupts a submission.
- **Let lxml escape; do not emit CDATA.** `<`, `>` and `&` are common in real derivation code. lxml escapes text nodes correctly, and the entities are what a conformant reader expects. CDATA looks nicer in the raw XML but most parsers do not preserve it, which makes the import direction lossy.
- **`Context` needs a project convention.** It is free text with no controlled terminology, so left alone a repo accumulates `SAS`, `SAS 9.4`, `sas9.4` and `SAS v9.4` as four distinct contexts. Declare the permitted set once in `study.yaml` (`expression_contexts: ["SAS 9.4", "R 4.4"]`) and lint every `context:` against it.
- **Duplicate `Context` within one method → error.** Multiple expressions are legal only when each context differs.
- **`expressions:` without `description:` → error.** Per the ODM semantics, a receiving system that cannot interpret the machine-readable expression falls back to the `TranslatedText`, so an expression-only method is unreadable to any consumer that does not speak its context - including the define.html stylesheet and the human reviewer.
- **Element order comes from the XSD**, not from the YAML key order. The emitter follows the schema sequence for `MethodDef` children; the XSD validation step catches it if that is wrong, which is exactly what that step is for.

**Not in where clauses, by default.** ODM permits `FormalExpression` inside `RangeCheck` as an alternative to `Comparator`/`CheckValue` - mutually exclusive, not additive, and confirmed XSD-valid inside a `def:WhereClauseDef` too (§8, "Resolved"; `tests/test_schema_questions.py`). But Define-XML's `def:WhereClauseDef/RangeCheck` business rules are built around `def:ItemOID` plus `Comparator`, the stylesheet renders that form, and most validators check it - P21 conformance is unverifiable in this environment. An expression-based where clause would very likely be flagged. Support it behind an explicit opt-in flag if a real need appears; do not offer it as a normal authoring path.

Note that `arm:ProgrammingCode` (section 7.1) is a separate element with the same `Context` + code shape but different semantics - it documents the program that produced a TFL, not an algorithm that derives a variable. The model keeps them distinct; the `expression_contexts` lint list applies to both.

---

## 8. Remaining unknowns

Step 3 (round-trip testing) is now a hard gate: `tests/test_roundtrip.py`, run against both bundled example submissions vendored under `tests/fixtures/definexml/` (the two source XMLs plus the XSD tree needed to validate them). The CDISC prose specs (*Define-XML v2.1*, *Analysis Results Metadata v1.0*) aren't vendored - consult them separately for a business rule the XSD alone won't show. It checks, per object kind: every OID and reference survives with nothing lost or invented, `TranslatedText`/`Decode`/`FormalExpression` content survives (the last one byte-for-byte), ordering survives, external codelists survive, and - the strongest check - each OID-bearing object's own canonicalised XML subtree is equivalent between the original and the rebuild (whitespace-normalised; whole-document comparison isn't used since this tool deliberately reorders top-level children to the XSD's mandated sequence, which a source file need not already follow). `test_object_canonical_xml_equivalent`'s `_normalize_for_comparison` scrubs exactly the gaps below from both sides before comparing - extending that scrub list is how a newly-accepted gap gets folded into the gate; anything not on that list is a real regression, not a known one.

Below is what that testing has actually found, not speculation - each confirmed by running `define import`/`define build` against the two bundled submissions:

Fixed this pass: `ItemDef/@SASFieldName` vs `@Name` (`Variable.sas_field_name:`, defaulting to `name:`); `Standard`/`ItemGroupDef`/`CodeList`/`CommentDef`'s `def:CommentOID` (`comment:` on each, following the same pattern - this one recurred four times before all instances were found); `ItemGroupDef/@Domain` (`Dataset.domain:`); `CodeList/@SASFormatName` (`sas_format_name:`); `ItemGroupDef`/`CodeList`'s `def:StandardOID` being required when the schema makes it optional (`dataset.standard:`/`codelist.standard:` are now `| None`); `def:leaf` being required on `ItemGroupDef` when it's genuinely optional (a documentation-only domain); `ItemRef/@Role` (the `Variable.role:` field existed but was never wired to import/export); `CommentDef`'s `def:DocumentRef` (`comment.document:`, single-ref); a cross-dataset `same_as:` alias (STUDYID shared verbatim across every SDTM domain) silently dropping its own `MethodOID`/`Role`; `ItemDef/@SignificantDigits` (`significant_digits:`); `def:Origin/@Source` (`origin.data_source:`, per the note in §3 above); `def:AnnotatedCRF` / `def:SupplementalDoc` (`documents.yaml`'s `annotated_crf:` / `supplemental_docs:`, each a plain list of document references - `def:leaf`'s existing symbol table, nothing new to derive); the `<?xml-stylesheet type="text/xsl" href="..."?>` processing instruction between the XML declaration and `<ODM>` (spec §5.3.2 - found by a manual whole-document `xmllint --c14n` diff, since it sits outside the ODM/def content model entirely and so isn't reachable by anything the per-object round-trip checks iterate; `study.yaml`'s `odm.stylesheet:`, and now its own round-trip test); `def:PDFPageRef/@Title` (a human label for a named destination - `DocumentRef.title:` for the three kinds that already nest a `DocumentRef` model (`ResultDisplay.document`, `Documentation.document`, `ProgrammingCode.document`), and a parallel `pages_title:` sibling field for the two kinds that spell a document reference as flat `document:`/`pages:` fields instead (`Origin`, `CommentDef`) - confirmed against the five real `Title` values in the bundled ADaM submission (`Table 14-3.01`, `SAP Section 10.1.1` ×2, `Table 14-5.02`, `SAP Section 11.2`), all five surviving the full import → build cycle byte-for-byte); `def:PDFPageRef/@PageRefs` being non-numeric - `def:PDFPageRef/@Type` distinguishes a `PhysicalRef` (a real page number) from a `NamedDestination` (a PDF bookmark name, e.g. `"section2.1"`, confirmed real in the bundled SDTM example), and `@FirstPage`/`@LastPage` are schema-typed `odm:integer` with no such alternative - so `Pages` grew a `list[str]` alternative alongside its existing `list[int]`/`PageRange`, `PageRange` stays numeric-only, and `Type` still isn't stored: `xml_emit` infers `PhysicalRef` vs `NamedDestination` from which of `list[int]`/`list[str]` a given `pages:` value actually parsed as (YAML itself already keeps them apart - `pages: [4, 5]` can only parse as ints, `pages: [section2.1]` can only parse as strings), the same derive-don't-store principle the whole OID scheme runs on. `section2.1` confirmed surviving the real SDTM submission's full import → build cycle, `Type` correctly re-derived as `NamedDestination`; `def:SubClass` under `def:Class` (ADaM's two-level classification - a `def:Class` can carry zero or more `def:SubClass` children, e.g. `OCCURRENCE DATA STRUCTURE` > `ADVERSE EVENT`, confirmed real on the bundled ADaM `ADAE` dataset) - a new `SubClass` model (`Dataset.subclasses: list[SubClass]`) with `name:` and optional `parent_class:`; `ItemGroupSubClass` (the `Name` enumeration) is a genuinely *closed* 2-value XSD restriction, unlike the `AnalysisReason`/`AnalysisPurpose` unions above, so `name:` is `Literal["TIME-TO-EVENT", "ADVERSE EVENT"]` rather than deferred to lint; `parent_class:` (`ParentClass`) is a union of `ItemGroupClass` and `ItemGroupSubClass` - it may name either the enclosing top-level class or another subclass - so it's left as free text rather than re-deriving that union as its own type; `def:IsNonStandard` / `def:HasNoData` on `ItemGroupDef` and `ItemRef` (a sponsor-defined domain/variable outside the standard; a domain or variable legitimately submitted with zero records) - both are schema-typed `odm:YesOnly`, an attribute that is either present with value `"Yes"` or absent entirely (no `"No"` exists), so `Dataset.is_non_standard:`/`.has_no_data:` and `Variable.is_non_standard:`/`.has_no_data:` are plain `bool = False`, only emitted when true. Confirmed real on the bundled SDTM submission: `IsNonStandard` on the non-standard `XS`/`XX` findings domains, `HasNoData` on `XX`/`SUPPVS`/`SUPPDM` (zero-record domains) and on individual variables (`XS.XSORRESU`, `XS.XSSTRESU`). These attributes were a quieter gap than most: both were already listed in the importer's known-attributes set to avoid a spurious "not implemented" report, so the value was being silently dropped rather than surfaced - the fix restores capture on both `ItemGroupDef` and every `ItemRef` path (a dataset's own variables, a value-list entry's `ItemRef`, and the cross-dataset `same_as` alias path); `def:ExtendedValue` on `CodeListItem`/`EnumeratedItem` (`Term.extended:`) - a per-*term* extensibility flag distinct from the codelist-wide `extended:` (`def:IsNonStandard`), confirmed genuinely independent on the bundled SDTM `LBRESU` unit codelist: two sponsor-added units (`X10^9/L`, `pg/mL`) each carry `ExtendedValue="Yes"` while the codelist itself carries no `def:IsNonStandard` at all. Also `odm:YesOnly`-typed like the `IsNonStandard`/`HasNoData` pair above, and the same quiet-gap shape: the attribute was already in the importer's known-attributes set (no "not implemented" report), so it was being silently dropped rather than surfaced. `def:Origin/Description` for a non-`Predecessor` origin - `Origin.source:` stays `Predecessor`-only (a dataset.variable mnemonic, e.g. `DM.STUDYID`); every other origin type's `Description` is free-form descriptive prose with no dataset.variable shape to it, so it gets its own field, `Origin.description:`, rather than one field meaning two different things depending on `type:` - a `model_validator` enforces exactly one of `source:`/`description:` is settable per type (`Predecessor` → `source:` only, everything else → `description:` only). Confirmed real on the bundled SDTM submission (previously self-reported via `not implemented: element 'Description on a non-Predecessor def:Origin'` on several `LB`/`VS` entries) - e.g. `VS.VSSTRESC`'s own `Type="Derived" Source="Sponsor"` origin carries `Description="EDC System"`, and an `LB` value-level entry carries `Type="Collected" Source="Vendor"` with `Description="From Central lab (LB.LBNAM NE \"LOCAL LAB\")"`. `CommentDef`'s `def:DocumentRef` upgraded from single-ref to the schema's actual `maxOccurs="unbounded"`: the flat `comment.document:`/`pages:`/`pages_title:` fields (which only ever captured the first `def:DocumentRef`) are replaced by `comment.documents:`, a list of the same `DocumentRef` model already used by `ResultDisplay.document`/`Documentation.document`/`ProgrammingCode.document` - so a comment citing both an ADRG section and a supporting SAS program can now say so. Neither bundled fixture happens to have a multi-`DocumentRef` `CommentDef`, so this one is verified by a synthetic round-trip test rather than fixture content; the webui's comment editor (`webui/static/app.js`) moved from a single `refField` to a `cardListEditor` over the list, and `webui/usages.py`'s reference scanner needed no change at all - its generic `"ref": "documents"` field mapping already walks into any nested `{ref: ...}` regardless of whether the parent is a single dict or a list. `ItemGroupDef`'s `Alias` (`Dataset.aliases: list[Alias]`, a new generic `Alias{context, name}` model in `models/common.py`, reused rather than adding a one-off shape) - confirmed real on the bundled SDTM submission: `SUPPDM`/`SUPPVS` each carry a single `Context="DomainDescription"` alias naming their parent domain (`"Demographics"`, `"Vital Signs"`). Modeled as an unrestricted list rather than a single `domain_description:`-style field, since the schema itself places `maxOccurs="unbounded"` on `Alias` with no restriction on `Context` - the same generic `Alias` model is intended for `CodeList`/`Term`'s still-open sponsor-`Alias` gap below, rather than that getting its own bespoke shape. A `CodeList`, or one of its terms, carrying a sponsor-defined `Alias` (any `Context` other than `nci:ExtCodeID`, which stays modeled separately via `nci_code:`) - `EnumeratedCodeList.aliases:`/`Term.aliases:`, both `list[Alias]`, reusing the model above rather than inventing a second shape. A `model_validator` on each rejects `Context="nci:ExtCodeID"` inside `aliases:`, since `nci_code:` is the only supported way to write that one - allowing both would be two spellings of the same thing with no rule for which wins if they disagreed. Confirmed real on the bundled SDTM submission: `CL.XSTEST`'s `EnumeratedItem`s each carry a single `Context="Sponsor"` term-level alias (an internal test-code cross-reference) and the codelist itself carries one too; `CL.XSRESU` shows an NCI alias and a sponsor alias coexisting on the same term without conflict, confirming the two are genuinely independent, matching the schema's own per-element `Context`-uniqueness constraint (`UC-CL-5`/`UC-CLI-1` in the ODM foundation schema) that permits any number of *differently*-contexted aliases on one element. `CodeListItem`/`EnumeratedItem`'s `@Rank` (`Term.rank`) - previously scrubbed from both sides of the round-trip comparison as "not modeled", it's now captured and re-emitted (`xml_import` parses `float(Rank)`, storing an `int` when integral; `xml_emit` writes it back); confirmed real on the bundled ADaM submission (15 `@Rank` values across `Age Group`, `BMI Category`, `Causality`, `Severity` and others) and SDTM (`Size`), all surviving import → build. `@Rank` is left in place by `_normalize_for_comparison` now (`test_codelist_rank_survives` gates it); `@OrderNumber` is still positional and still scrubbed. See §3's ordering note for why `@Rank` is stored where every other codelist-item ordinal is derived. `MethodDef`'s `def:DocumentRef` (+ optional `def:PDFPageRef`) - the last unmodeled `def:DocumentRef` nesting; now `MethodDef.documents: list[DocumentRef]` (same model as `CommentDef.documents`), emitted last per the XSD child order, captured on import, no longer scrubbed from the round-trip comparison (`test_methoddef_document_ref_survives`). Both fixtures carry one (a `PhysicalRef` page in ADaM, a `NamedDestination` in SDTM). With this, every `def:DocumentRef` this tool emits - `Origin`, `MethodDef`, `CommentDef`, ARM `ResultDisplay`/`Documentation`/`ProgrammingCode` - round-trips its `def:PDFPageRef`; only `def:AnnotatedCRF`/`def:SupplementalDoc` stays a bare `list[str]` of document names (no per-ref page refs there in practice). Alongside it, a `define lint` `collected-origin-page-ref` **warning**: the Define-XML business rule that a `def:Origin`'s `def:PDFPageRef` is *required* (not just allowed) when `@Type="Collected"` and `@Source` ∈ {`Investigator`, `Subject`} - schema-optional, so lint-enforced - fires on a variable/value-list-entry origin that fits the condition but cites no page.

### Resolved (with evidence, not assumption)

`tests/test_schema_questions.py` settles the four questions this section used to carry open, each against the actual vendored XSD rather than a guess:

- **`MethodDef` child order is `Description, FormalExpression*, Alias*, def:DocumentRef*`** - `def:DocumentRef` is appended at the *end* via `MethodDefElementExtension`'s redefine (define-extension.xsd), not straight after `Description` as this file used to guess. `test_methoddef_documentref_before_formalexpression_is_invalid` proves the old guess actually fails validation, not just that the right order happens to also pass. `MethodDef`'s `def:DocumentRef` (a method citing the documentation it's specified in, e.g. an ADRG page, `maxOccurs="unbounded"` like `CommentDef`'s) **is now modeled** - `MethodDef.documents: list[DocumentRef]`, the same `DocumentRef` model (with its optional `def:PDFPageRef`) `CommentDef.documents` uses, emitted last in the child sequence per the order above. Both bundled fixtures carry one (`MT.ADQSADAS.AVAL.ACTOT` → an ADRG `PhysicalRef` page; `MT.AGE` → a `NamedDestination`), covered by `test_methoddef_document_ref_survives`; `_normalize_for_comparison` no longer scrubs `MethodDef/def:DocumentRef`.
- **`FormalExpression` inside a `def:WhereClauseDef`'s `RangeCheck` is XSD-valid** - `def:WhereClauseDef` uses plain `odm:RangeCheck` unmodified, whose content model is `(CheckValue+ | FormalExpression+)`. `test_formal_expression_in_wc_rangecheck_is_schema_valid` confirms it. This settles only the XSD half of §7.5's question, though: P21 conformance is unverifiable in this environment (no P21 CLI/service available here), and most tooling assumes the `Comparator`+`CheckValue` form regardless of what the XSD alone permits - §7.5's opt-in-only stance (no ordinary authoring path) stands until a real submission actually needs it.
- **`def:Origin/@Type`'s XSD enumeration has no standard-dependent split** - SEND's "`COLLECTED` only in a SEND context" is a Define-XML business rule, not an XSD one (`define-enumerations.xsd`'s `OriginType` is one flat list). Confirms the model is right to leave `Origin.type` unconstrained by `standard:` - a SEND-specific check belongs in `define lint` once that exists (it needs the dataset's `standard:`, which isn't visible from the `Origin` field alone), never as a global `Literal` restriction.
- **`arm:AnalysisResult/@AnalysisReason` and `@AnalysisPurpose` are extensible CT, not closed enumerations** - each is an XSD *union* of the CDISC 2.1 controlled list with unrestricted free text (`cdisc-arm-1.0/arm-ns.xsd`), i.e. CDISC itself made them sponsor-extensible. `src/defineyaml/ct.py` hard-codes the 2.1 lists (`ANALYSIS_REASON_CT`, `ANALYSIS_PURPOSE_CT`), checked against the vendored XSD by `test_analysis_reason_and_purpose_ct_matches_the_vendored_xsd` so a future CDISC revision would be caught. Confirms these belong in `define lint` as a warning (CLAUDE.md §6 item 4's errors-vs-warnings split), not a pydantic-level hard error, which is why `AnalysisResult.reason`/`.purpose` stay plain `str`.

### Still open

- `def:IsNonStandard` and `ExternalCodeList/@href` on an *external* codelist aren't modeled - deliberately, per §7.2's narrow `ExternalCodeListDef` (`standard:`/`comment:` are `EnumeratedCodeList`-only for the same reason).

---

## 9. Controlled Terminology / standards browser ("smart mode")

Deferred at the project's outset (§1's status line). It started as a CDISC Library API client (configure a server, check reachability, query the HATEOAS `/mdr/*` tree, cache responses). That API turned out to be the wrong foundation to build on - most of the useful content sits behind a paid membership, and the parts that don't are awkward to reach - so **the CDISC Library integration is retired**: `cdisc/client.py`, `cdisc/config.py` and `cdisc/cache.py` are still in the tree (unit-tested directly, kept in case a future need re-justifies them) but `server.py` no longer routes to any of them, and `/cdisc-viewer` no longer surfaces them. What replaced it is two **local-first** sources, both under `src/defineyaml/cdisc/`, both still read-only and independent of `linker.py`/`xml_emit.py`/`xml_import.py` and of the `define/` tree, both wired into the webui only. Wiring CT into the editor's own fields (autocomplete, `codelist:`/CT mismatch flags) is still future work.

### 9.1 NCI EVS Controlled Terminology (`cdisc/nci_evs.py`) - the primary CT source

NCI's own EVS server (`evs.nci.nih.gov`) publishes the full CDISC CT as free, no-key ODM-XML - one file per standard per quarterly release. It's an Angular SPA with no directory listing, but the file-serving API behind it is a plain S3 `ListObjectsV2` proxy: `GET /ftp1/folder?folder=<prefix>` returns `{Contents: [{Key, Size, LastModified}], IsTruncated, CommonPrefixes}`, and `folder` is used as the S3 *prefix* - it doesn't have to be a real directory.

- **Version listing.** `list_available_versions(standard)` makes **one** folder call with a *narrow* prefix - `CDISC/SDTM/Archive/SDTM Terminology` - and filters `Contents` to `{prefix} YYYY-MM-DD.odm.xml`, newest first. The narrow prefix is deliberate: `CDISC/SDTM/Archive/` unfiltered is >1000 keys (CDASH/QRS/QS/COA terminology all live there too) and would need S3 continuation-token pagination; the narrow prefix returns `IsTruncated: false` in one call. **No separate "current" entry:** the undated `CDISC/SDTM/SDTM Terminology.odm.xml` is byte-identical to the newest Archive file (confirmed - same S3 `Size` and upload timestamp), so listing it too was noise. `CURRENT = "current"` survives only as an *alias* - `resolve_version(standard, version)` maps `"current"`/None → `list_available_versions()[0]["version"]`, a real date passes through, anything else is a `NciEvsError`; `ensure_downloaded`/`list_codelists`/`get_codelist_terms`/`to_ct_csv` all resolve first, so the cache is always keyed by a real date. A `.versions.json` written by an older build (which still carries the retired `"current"` entry) is filtered on read. Confirmed live: 61 SDTM releases, 59 SEND, 28 ADaM, back to 2011. Cached to `~/.cache/defineyaml/cdisc/nci-evs/{standard}.versions.json` for 24h; "check for updates" forces a re-fetch.
- **Per-version download.** Each `(standard, YYYY-MM-DD)` is downloaded once (`ensure_downloaded`) to `{standard}@{date}.odm.xml` and **cached on disk indefinitely** - a published quarterly release's content never changes, so re-downloading a ~25MB file (SDTM; ADaM ~97KB, SEND smaller) would be pure waste. `downloaded_versions(standard)` scans the cache dir; nothing re-fetches except on explicit `force`.
- **The XML dialect is NCI's own, not plain Define-XML.** Confirmed live against a real SDTM file (1208 codelists): *every* term is an `EnumeratedItem`, never `CodeListItem`+`Decode`. Human-readable content is in `nciodm:`-namespaced children (`http://ncicb.nci.nih.gov/xml/odm/EVS/CDISC`) - `PreferredTerm`, `CDISCSynonym`, `CDISCDefinition` - and NCI Concept ID / extensibility are plain attributes (`nciodm:ExtCodeID`, `nciodm:CodeListExtensible`), not a `def:Alias`. The codelist's own CDISC submission value is a `nciodm:CDISCSubmissionValue` child element (`_submission_value()` reads it, falling back to the trailing OID segment - `CL.C66742.NY` → `NY`). `_term_from_item()` keeps a `CodeListItem`/`Decode` branch defensively but it's never been observed. Parsing is `lxml.etree.iterparse` with `el.clear()`/sibling-pruning (bounded memory over the ~25MB file); `_build_index` records just each `CodeList`'s own attributes (incl. `submission_value`) to `{standard}@{date}.index.json` so "what codelists are there" doesn't re-stream the file (an index without `submission_value`, from an older build, is rebuilt once on read), and `get_codelist_terms` early-exits the moment its target OID is found.
- **`to_ct_csv(standard, version)`** re-serialises a cached release as a CDISC-Data-Standards-Browser-style CT CSV - `_CT_CSV_COLUMNS` (`Code, Codelist Code, Codelist Extensible (Yes/No), Codelist Name, CDISC Submission Value, CDISC Synonym(s), CDISC Definition, NCI Preferred Term, Standard and Date`), one header row per codelist (empty `Codelist Code`) then one row per term (`Codelist Code` = parent C-code). `cdisc.standard_csv` reads the output back unchanged (`is_ct_file` / `codelist_detail`), so a saved file scaffolds datasets/codelists exactly like a hand-downloaded DSB export. `webui/standard_scaffold.save_nci_evs_ct(root, standard, version)` writes it into the tree's Standards folder at `terminology/<standard>/<STANDARD>_CT_<date>.csv` (`POST /api/cdisc/nci-evs/{standard}/save-to-folder`); the Standards Viewer shows a "Save to standards folder" button on a browsed release whenever a folder is configured. `test_nci_evs.py::test_to_ct_csv_round_trips_through_standard_csv` is the guarantee.

### 9.2 Local standards folder (`cdisc/local_standards.py`)

A directory of CDISC CSV exports - the kind the Data Standards Browser produces: variable tables (`SDTMIG_v3.4.csv`, `ADaMIG_v1.3.csv`, …), CT term lists (`SDTM_CT_2026-03-27.csv`), CDASH, QRS supplements. Each standard's CSV has its own column schema; this module treats them all generically. **This tool never downloads them** - the user drops new versions into the folder by hand as CDISC publishes them, per the request.

- **The folder is per-tree, not a global app setting** - it's `standards.yaml`'s `standards_folder:` (models/study.py's `StandardsFile.standards_folder`), so two define projects can draw from different CSV export folders (different SDTMIG vintages, different clients' bundles). A local editor pointer only: never emitted to define.xml, never read by the importer. Absolute, or relative to the `define/` tree root (`webui/standard_scaffold.py`'s `resolve_folder`). There is **no default** - the editor and Standards Viewer both show it unset until set. `local_standards` itself is now purely functional: every entry point takes the resolved folder `Path` as its first argument; it doesn't know or care where the path came from.
- `list_files(folder)` walks `*.csv` recursively and groups by the folder's own subdirectory layout (`data_analysis`, `terminology/sdtm`, …), parsing `_vX.Y` / trailing `YYYY-MM-DD` out of each filename for a version label.
- `read_file(folder, relpath, q, limit, offset)` streams one CSV via `csv.DictReader`, optionally filtering rows by a case-insensitive substring across all cells, and paginates (`total_matched` counts all matches, `rows` is the page). `search(folder, q, limit)` does the same across every CSV in the folder at once, capped. `rows(folder, relpath)` is the shared read primitive (columns + every row as a `''`-filled dict). All go through `_safe_csv(folder, relpath)` - `resolve()` then confirm the target is inside `folder` - so `path=../../etc/passwd` is rejected, not served.
- `raw_path(folder, relpath)` backs `GET /api/standards/raw`, a `FileResponse` for downloading a CSV as-is.

**DuckDB query cache (`cdisc/csv_db.py`).** Re-streaming a multi-MB CT export per keystroke is wasteful, so browse/search (and the scaffold layer's repeated CT scans) go through **one DuckDB database at `<tree>/.cache/standards.duckdb`** (the webui passes `app.state.root` as `cache_root`; the module itself is folder-agnostic). Tables:

- **`csv_<hash>` per CSV** - what `rows` and `read_file` (single-file browse) query. A changed/new CSV is `DROP`+`CREATE TABLE ... read_csv(?, all_varchar=true, null_padding=true, ignore_errors=true)`, a vanished one's table dropped, an unchanged one untouched (`_manifest` holds each file's `size`+`mtime_ns`).
- **`_search_index(relpath, category, blob, row)`** - one row per CSV row across the whole folder, kept in lockstep with the `csv_<hash>` tables. `blob` is a pre-lowercased `concat_ws(chr(31), *cols)` for matching; `row` is a `MAP(VARCHAR,VARCHAR)` of the original cells (compresses well - the whole index is ~10-15% on top of the folder's CSV bytes). `search` is then one `blob LIKE` scan of this table, not a per-file loop (~30 ms for a common term over a folder totalling 200k rows, vs ~110 ms before); `read_file`'s *filtered* path uses it too, seeking via an ART index on `relpath` (~16 ms vs ~76 ms for the 40k-row SDTM CT export).
- **`_meta`** carries a `schema_version` (`_SCHEMA_VERSION`); a bump wipes the derived tables so an older cache rebuilds itself.

**The connection is kept open per database path** (`_CONNECTIONS`, guarded by the one process-wide `threading.RLock` - sync FastAPI routes run in a threadpool, DuckDB is single-writer) rather than reconnected per call: `connect`+`close` is ~12 ms, the queries sub-ms. `close_all()` runs on the FastAPI lifespan shutdown and (via `tests/conftest.py`) after every test; `_adopt_tree` calls it when "open another tree" switches `app.state.root`. A stale connection whose `.cache/` was deleted underneath notices (`path.exists()`) and reconnects; a corrupt db file is unlinked and recreated. The cache is disposable and self-ignoring (`.cache/.gitignore` with `*`). If `duckdb` isn't installed (it's in the `ui` extra) or a specific CSV won't parse, every function falls back to streaming via `local_standards` (and drops the possibly-wedged connection). `server.py`'s `/api/standards/file` + `/api/standards/search` route through `csv_db`; `standard_csv._rows` takes an optional `cache_root=` and `standard_scaffold` passes the tree root at every call site (so `_ccode_index`, `codelist_reference`, `missing_referenced_codelists` - which each scan every CT file - hit the cache too).
- The webui resolves the folder once per request (`server.py`'s `_std_folder`, from `standards.yaml`), and `PUT /api/standards/config` writes `standards_folder:` back through `tree.save_object`. `GET /api/standards/config` returns `{folder, resolved, exists, creatable, error}` - `creatable` is true when the path is set but simply isn't on disk (a hand-edited `standards.yaml`, a moved/cloned tree), and `POST /api/standards/config/create-folder` (`standard_scaffold.create_folder`) `mkdir -p`s exactly that path (absolute, or relative to the tree root) and returns the refreshed status. Both the editor's standards panel and the Standards Viewer show a **"Create this folder"** button next to the ⚠ when `creatable`. In the editor the folder value is also a plain field of the standards object, saved with the normal Save button (the config panel's live "N files found" status catches up after that save).

### 9.2a Scaffolding from a standard's CSV

A `standards.yaml` entry gains an optional `standards_file:` - the path (relative to the
Standards folder) of the CSV that standard's content comes from, e.g.
`data_tabulation/SDTMIG_v3.4.csv`. It's a **local editor pointer only**: declared on `StandardDef`
(models/study.py) because `DefineBaseModel` is `extra="forbid"`, but never emitted to define.xml
and never read by the importer - the round-trip tests are untouched. The editor's
"+ Add standard from local folder" picker sets it automatically.

`cdisc/standard_csv.py` maps one such CSV into this tool's shapes - pure functions, no tree
access. It tells the two file families apart by their columns:
- **IG variable tables**: the "unit" column is `Dataset Name` (SDTMIG/SENDIG), `Domain` (CDASHIG),
  or `Data Structure Name` (ADaM + extensions - ADaM datasets are user-named instances of a
  structure, so the picker offers the structure and the user names the dataset). `unit_variables`
  maps `Char`→`text` / `Num`→`integer` (a documented default - the user refines float/date/datetime),
  `Core ∈ {Req, HR}`→`mandatory`, and the CT codelist column to `codelist:`. SDTMIG populates only
  the codelist *C-code*, not its submission value, so those come back as `codelist_ccode` for the
  scaffold layer to resolve.
- **CT term lists**: a row with an empty `Codelist Code` is a codelist header; rows whose
  `Codelist Code` matches its `Code` are its terms. `codelist_detail` builds an `EnumeratedCodeList`
  with `name`←submission value, `nci_code`←C-code, `decode`←NCI Preferred Term (dropped from every
  term if any term lacks one - the model requires all-or-none). Its optional `codes=[...]` keeps only
  that subset of terms (a sponsor-narrowed list - e.g. a `NY` codelist reduced to just `Y`); the
  parent's C-code is retained, and `create_codelists` leaves `extended:`/`def:IsNonStandard` for the
  user (the "new codelist" dialog nudges them to tick it).

`webui/standard_scaffold.py` orchestrates over `tree.py` (same shape as `copy_variables.py`):
- `create_dataset(root, standard, unit, name, key)` - writes a schema-valid dataset with every
  standard variable, `class` from the CSV, `standard:` pointing back at the entry, `label`/
  `structure` left blank for the user. `_resolve_codelists` turns each `codelist_ccode` into a
  `codelist:` name by looking it up in *any* configured CT `standards_file` (dropped if unresolvable).
- `create_codelists(root, standard, items)` - one codelist file per item; an item is a plain
  submission-value string (whole list, standard name) or `{value, name?, codes?}` - `name` renames
  the codelist (the file key + OID follow), `codes` keeps only that term subset. Skips any whose
  target name already exists (slug-compared); a `codes` set that matches nothing lands in `skipped`,
  not fatal. `ct_codelist_terms(root, standard, value)` backs the dialog's per-codelist term picker.
- `missing_referenced_codelists(root)` / `create_missing_codelists(root)` - every `codelist:` ref in
  datasets and value lists that has no file yet, annotated with which configured CT file provides it;
  the second creates all the resolvable ones in one go.
- `codelist_reference(root, name, nci_code)` - one codelist's full standard term list (matched across
  every attached CT file, on the codelist's own C-code first, then its submission value). Backs the
  editor's CT-aware term editor, not scaffolding.
- `ig_catalog(root)` / `search_ig_variables(root, standards, units, q, limit)` - every variable of
  every attached IG standard, for the **"+ Add variable(s) from standards"** overlay: the catalog
  lists standards + their units (SDTM domains / ADaM structures) for the filter selects; the search
  returns rows (each carrying `standard`, `unit`, resolved `codelist`, `role`, `description` from the
  CSV's notes column) filtered by standard/unit/substring, capped at `limit` with a `truncated` flag.
  This flow is **client-side add** (like "+ Add variable"): the frontend appends the picked, cleaned
  variable dicts to `working.variables` and the user saves - no server write, no other files touched
  (unlike `copy_variables.py`). Each added variable also gets `sas_field_name` set to its own name
  (the standard's SAS name is the variable name - skipped for a templated pick the user will rename)
  and `role` from the standard when it has one. `_resolve_codelists` strips `description` (not a
  `Variable` field - `extra="forbid"`).
- `dataset_standard_hints(root, dataset_key)` - the attached-standard units that *describe* the open
  dataset (SDTM/CDASH match on name/domain, ADaM on `class` = the structure name, via
  `_dataset_matches_unit` with a slug fallback), plus `variables[VARNAME] = {codelist: [...],
  role: [...], sources: [{standard, unit, name, label, type, mandatory, role, codelist, description,
  template}]}` - everything each matching standard says about that name. `codelist`/`role` (unioned)
  drive the datalist on the variables list's Codelist and Role fields; `sources` backs the per-row
  **"ⓘ Standard" info field** (`standardInfoField` → `openStandardVariableOverlay`), a chip that
  opens an overlay with the full standard definition(s). ADaM templated names are matched via
  `_template_regex`: every run of lowercase letters is digits - a 2-letter run (`xx`/`yy`/`zz`) is
  exactly two, any other (`y`/`z`/`w`) is one or more - so `TRT01PN` resolves to `TRTxxPN`
  (`sources[].template: true`, `name` = the template string). `renderDatasetVariables` re-renders
  the list with the hint-aware specs once the fetch lands.

Routes under `/api/standards/scaffold/` (`standards`, `units`, `unit-variables`, `POST dataset`,
`ct-codelists`, `ct-codelist`, `ct-codelist-terms`, `POST codelists`, `GET`/`POST missing-codelists`,
`ig-catalog`, `ig-variables`, `variable-hints`) - thin wrappers,
`ValueError`/`StandardCsvError`/`LocalStandardsError`→400, `NotFoundError`→404. In the editor, the
datasets and codelists sidebar "+" open a dialog offering *Blank* or *From standard* (the codelist
one lets you rename each picked CT codelist and keep only a term subset before creating);
the codelist dialog also carries the one-click "add referenced-but-missing
codelists"; the datasets editor's variables list carries "+ Add variable(s) from standards" (the
filterable multi-add overlay) alongside "Copy variables from…".

**The codelist term editor is CT-aware** (`renderCodelistTerms` in `app.js`). When an attached CT
`standards_file` has the open codelist, its terms drive: `<datalist>` suggestions on Code and Decode;
entering a standard Code (or Decode) auto-fills the rest of that row; entering a Code the standard
doesn't have blanks and disables that row's NCI Code and ticks its per-term `extended:`
(`def:ExtendedValue`, not the codelist-wide `def:IsNonStandard` - CLAUDE.md §8's confirmed-independent
pair). Existing rows are aligned to the standard once on open (marking the object dirty). Both the
CT match and the "two terms can't share a code" check are **case-sensitive** (`ckey` = trim only):
`CodedValue` is case-sensitive per ODM, so `PA` and `Pa` are different terms - the model's
`EnumeratedCodeList` validator and `codelist_detail(codes=...)` agree. This needed
one generic addition to the field-spec system: a text spec can carry `suggest(item)` (datalist),
`disabled(item)`, and `onCommit(item, value)` (mutate siblings, then the list re-renders) - consumed
by `buildFieldFromSpec`/`buildCellFromSpec` via `textOpts`, so it works in both card and table view.
`suggest(item)` also works on a `ref` spec now (`refControl`/`textControl` share a `withDatalist`
helper), which is how the datasets variables list gets Codelist suggestions from
`dataset_standard_hints` above - a `ref` field, unlike `role` which is plain text.

**The codelist editor's "Codelist kind" selector is three-way** - *Coded values with Decode
(CodeListItem)*, *Coded values only, no Decode (EnumeratedItem)*, *External dictionary reference
(ExternalCodeList)*. The model still discriminates the first two purely on whether the terms carry
`decode:` (`EnumeratedCodeList._check_decode_uniform`), so switching between them just adds/strips
`decode` on every term (with a confirm when that drops real values); `external` is the
`ExternalCodeListDef` branch. `renderCodelistTerms` takes `{withDecode}` - the Decode column and its
CT auto-fill vanish for an EnumeratedItem list. Every term row also has a **Rank** column
(`Term.rank`, §3): a live validator nudges toward all-or-none + distinct, the `EnumeratedCodeList`
model is the real gate. The External branch's Dictionary field is the C66788 datalist (§7.2).

**Every `def:DocumentRef` in the editor edits its `def:PDFPageRef` too.** `documentRefListEditor(viewKey, list)`
(`app.js`) is the shared list-of-`{ref, pages, title}` editor - used by the methods editor's new
"Documentation references" section (`MethodDef.documents`, §8) and the comments editor's Documents
section (`CommentDef.documents`), replacing the earlier ref-only list. `pages` is edited through
`pagesField` / `pagesControl`: one text input parsing `"4 5"` → `[4, 5]` (PhysicalRef), `"112-114"` →
`{first, last}`, `"section2.1"` → `["section2.1"]` (NamedDestination) - the same shapes the `Pages`
union and `xml_emit`'s Type inference already round-trip. The Origin overlay (`originFields`) grew the
same `pages:` / `pages_title:` inputs (plus the previously missing `description:` field), with a hint
that a CRF page is required for a `Collected` / Investigator-or-Subject origin - the condition
`define lint`'s `collected-origin-page-ref` flags.

### 9.3 The webui

`/cdisc-viewer` (`webui/static/cdisc-viewer.{html,js,css}`), still opened from the main editor's `#sidebar-actions` row via a *named* window target (repeat clicks focus one window), still a separate window because both sources are global per-machine, not tied to one `define/` tree. Two panels:

1. **NCI EVS CT** - one card per standard showing which versions are on disk. "List versions" fetches the version list (an explicit action - it's a network call); the resulting `<select>` is dated releases newest-first (no "current" pseudo-entry), each labelled with its size and a ✓ if downloaded; "Download & browse" fetches it if needed then loads a search-filterable codelist browser (client-side filter, capped at 300 shown) with a term-detail table on click. "Check for updates" force-refreshes the version list. When the tree has a Standards folder configured, a browsed release also gets a **"Save to standards folder"** button (`to_ct_csv` → `terminology/<standard>/<STD>_CT_<date>.csv`, §9.1).
2. **Local standards folder** - a folder-path setting (shown until set), a global search box over every CSV, and a grouped file browser; picking a file opens a paginated, in-file-searchable table with a "download raw CSV" link.

`server.py`'s routes are all thin wrappers over the two plain modules (`ValueError`/`LocalStandardsError` → 400, `FileNotFoundError` → 404, `NciEvsError` → 502/404), matching the split every other endpoint in that file uses:
`GET /api/cdisc/nci-evs/standards`, `GET /api/cdisc/nci-evs/{standard}/versions`, `POST /api/cdisc/nci-evs/{standard}/download?version=`, `POST /api/cdisc/nci-evs/{standard}/save-to-folder?version=`, `GET /api/cdisc/nci-evs/{standard}/codelists?version=`, `GET /api/cdisc/nci-evs/{standard}/codelists/{oid}?version=`; `GET`/`PUT /api/standards/config`, `POST /api/standards/config/create-folder`, `GET /api/standards/files`, `GET /api/standards/file`, `GET /api/standards/search`, `GET /api/standards/raw`. The `/static/` `Cache-Control: no-store` middleware stays (this file is edited and re-served within a live browser session far more than a deployed app would be).
