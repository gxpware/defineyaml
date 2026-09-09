# XMLYAML - the define.xml ⟷ YAML specification

How DefineYAML represents a Define-XML v2.1 submission as a tree of YAML files, and
how `define build` / `define import` convert between the two without losing content.

This is the normative spec. [`CLAUDE.md`](CLAUDE.md) is the design log - the *why*, the
alternatives rejected, and the evidence behind each decision. [`CLI.md`](CLI.md) is the
command reference.

---

## 1. Scope of the mapping

- **`define build`**: YAML tree → `define.xml`, then XSD-validated against
  `arm1-0-0.xsd` (which transitively pulls in the full ODM → define-extension →
  arm-extension chain).
- **`define import`**: an existing `define.xml` v2.1 → YAML tree.
- **Round-trip guarantee**: `import` then `build` reproduces the source's content -
  every OID, every cross-reference, every `TranslatedText` / `Decode` /
  `FormalExpression` body, element ordering, and each OID-bearing object's
  canonicalised XML subtree. Attribute order and insignificant whitespace differ;
  compare canonicalised XML, not raw bytes. Top-level children are re-ordered to the
  XSD's mandated sequence.

Analysis Results Metadata (`arm:` namespace) is in scope - it is native to
Define-XML 2.1, not an extension.

---

## 2. File format: YAML 1.2 via `ruamel.yaml`

YAML 1.2 in round-trip mode. Two hard requirements drive both choices:

1. **Comments and key order survive a load–modify–dump cycle.** A save rewrites only
   what changed; explanatory comments, key order, and block/flow style are preserved.
   (`ruamel.yaml` does this; `PyYAML` discards all of it.)
2. **YAML 1.2 boolean semantics.** Under YAML 1.1, bare `NO`, `Y`, `N`, `ON`, `OFF`
   parse as booleans - and Define-XML is saturated with them (`Mandatory="No"`, `NY`
   codelists with codes `Y`/`N`, ISO-3166 country code `NO` for Norway). YAML 1.2
   restricts booleans to `true`/`false`, removing the class of bug.

### Quoting

The serialiser **always** emits values in *code positions* as double-quoted strings,
regardless of whether YAML would require it: `code:`, `name:`, `nci_code:`, `oid:`,
plus leading-zero codes (`"01"`) and version strings (`"2.1"`). This protects against
a non-`ruamel` reader (`yq` in CI, a contractor's editor, a future non-Python tool).

### Canonical formatting

`define fmt` (and the matching pre-commit hook) rewrites every file with normalised
key order, 2-space indent, and the quoting rules above. Any conflict git reports
after `fmt` is a real semantic conflict, not whitespace.

### Schema-driven editing

The pydantic model exports to JSON Schema; generated files may carry a
`# yaml-language-server: $schema=…` header, giving autocomplete, inline validation,
and hover docs in an editor with no plugin install.

---

## 3. File layout

```
define/
  study.yaml                    # Study, MetaDataVersion, ODM header attributes
  standards.yaml                # def:Standards - CT versions, IG versions   (optional)
  documents.yaml                # def:leaf for aCRF, SAP, SDRG/ADRG, ...     (optional)
  datasets/
    adsl.yaml                   # ItemGroupDef + inline variable list (ItemRef + ItemDef)
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
  valuelists/
    adlb__aval.yaml             # ValueListDef + inline WhereClauseDefs + value-level ItemDefs
  whereclauses/
    alt-week4.yaml              # named, shared across value lists and/or ARM
  analysis-results/
    t14-2-1.yaml                # one arm:ResultDisplay, results as entries
```

An absent `standards.yaml` / `documents.yaml` loads as empty.

### Granularity: one file per unit of *ownership and sharing*

| Object | File | Why |
|---|---|---|
| Codelist | one each | Shared across datasets; highest-contention object in a define. |
| Method | one each | Long free text, per-variable, frequently rewritten. |
| Comment, value list, ARM display | one each | Same argument. |
| Named where clause | one each | Shared across value lists and ARM. |
| Variable | **inline** in the dataset file | ~6 lines each; a dataset is one programmer's ownership unit. Two people editing different variables merge cleanly; editing the *same* variable is a real conflict that should surface. |

**Escape hatch for a monster domain:** `datasets/adsl/` as a directory with
`_dataset.yaml` + one file per variable. The loader accepts either shape.

---

## 4. OIDs are derived, not stored

By default no file contains an OID. Cross-references are written by
**human-meaningful name**; the linker resolves names to OIDs at build time.

- No shared counter → two contributors adding objects in parallel branches never
  collide on an identifier.
- Derived OIDs are legible in the output (`IT.ADSL.TRTSDT`, not `IT.000147`).
- Renaming an object = rename one file + find-replace its name; the OID follows.

### Derivation table

| Object | OID pattern | Example |
|---|---|---|
| Standard | `STD.<name>` | `STD.ADAMIG.1.3` |
| ItemGroupDef | `IG.<DATASET>` | `IG.ADSL` |
| ItemDef | `IT.<DATASET>.<VARIABLE>` | `IT.ADSL.TRTSDT` |
| ItemDef (value-level) | `IT.<DATASET>.<VARIABLE>.<ENTRY>` | `IT.ADLB.AVAL.ALT` |
| CodeList | `CL.<NAME>` | `CL.RACE` |
| MethodDef | `MT.<PATH>` (path under `methods/`) | `MT.ADSL.TRTSDT` |
| CommentDef | `COM.<PATH>` (path under `comments/`) | `COM.ADSL.USUBJID` |
| ValueListDef | `VL.<DATASET>.<VARIABLE>` | `VL.ADLB.AVAL` |
| WhereClauseDef (inline) | `WC.<DATASET>.<VARIABLE>.<ENTRY>` | `WC.ADLB.AVAL.ALT` |
| WhereClauseDef (named) | `WC.<PATH>` (path under `whereclauses/`) | `WC.ALT.WEEK4` |
| def:leaf (dataset) | `LF.<DATASET>` | `LF.ADSL` |
| def:leaf (document) | `LF.<NAME>` | `LF.ACRF` |
| arm:ResultDisplay | `RD.<PATH>` (path under `analysis-results/`) | `RD.T14.2.1` |
| arm:AnalysisResult | `AR.<PATH>.<ENTRY>` | `AR.T14.2.1.ANCOVA` |

`<ENTRY>` is the `name:` key of a value-list / result entry - **not** a where-clause
condition value (a clause may have two conditions and no single value to name it
after).

**Slug rule:** uppercase; `[^A-Z0-9._]` → `.`; collapse repeats; strip leading /
trailing separators. Derivation is a pure function of `(kind, path-or-name)` - same
inputs, same OID, on any machine, in any branch.

**Shared objects derive from path, not from a referencing variable.** One method can
serve `ADSL.TRTSDT` and `ADSL.TRTEDT`; deriving its OID from one consumer would name
it after an arbitrary one. Only objects genuinely owned by one parent - ItemDef,
ValueListDef, inline WhereClauseDef, dataset leaf - derive from the parent.

**Collisions hard-fail the build**, naming both source files. No auto-disambiguating
suffix (it would make OIDs order-dependent and merge-unstable). A collision is a
naming problem for a human to fix.

**Standard is a partial exception:** a submission may legitimately carry two
`def:Standard` elements with the same `Name` (two CT vintages differing in
`PublishingSet`, or two IG versions differing only in `Version`). A bare `name:` is
the reference key while it is unique in `standards.yaml`. When ambiguous, those
entries are keyed by `name` + `PublishingSet` + `Version` and are reachable only via
`{oid: …}`.

**`dataset.standard:` and `codelist.standard:` are optional** - `def:StandardOID` is
optional on both `ItemGroupDef` and `CodeList`. Omit the field; do not write an empty
reference.

### The `oid:` override (definition side)

Any object may carry an explicit `oid:` instead of a derived one. Two legitimate
uses: importing a define.xml whose OIDs were assigned elsewhere (resubmission
continuity), and a sponsor OID convention. `define import` writes `oid:` only where
the existing OID differs from what would be derived - a clean file set stays clean.
`define lint` reports every override (visibility, not restriction).

### The `{oid: …}` reference form (reference side)

Every reference field that resolves to an OID accepts a literal `{oid: …}` instead of
a name: `codelist:`, `method:`, `comment:`, `valuelist:`, `same_as:`,
`origin.document:`, `standard:`, `where:` (named, or on a `RangeCheck.variable:`), ARM
`dataset:` / `variables:` / `parameter:` / `join_comment:`, and a `def:DocumentRef`'s
`ref:`.

```yaml
codelist: race                    # resolved by name through the symbol table
codelist: {oid: CL.RACE_LEGACY}   # literal OID; no lookup
```

A bare string is the normal, preferred, hand-authored form. `{oid: …}` exists for
round-tripping a define.xml this tool did not generate - most importantly
`def:WhereClauseDef`, which has **no `Name` attribute in Define-XML**, so an imported
clause has nothing to name it by. Both escape hatches together - `oid:` on the target,
`{oid: …}` at each use site - are what let `define.xml → yaml → define.xml` preserve
OIDs and references regardless of the source tool's naming.

`origin.source:` is **not** a reference. For a `Predecessor` origin it is free
descriptive text (`DM.STUDYID`) that the emitter writes into `def:Origin/Description`;
Define-XML has no OID slot for it.

---

## 5. Ordering: positional by default, stored only where there is no positional signal

Derived from YAML list position, never stored:

| Attribute | Source |
|---|---|
| `ItemRef/@OrderNumber` | index in the dataset's `variables:` list |
| `ItemRef/@KeySequence` | position in the dataset's `keys:` list |
| `CodeListItem/@OrderNumber` | index in `terms:` |

`ItemRef/@Role`, `@Mandatory`, etc. stay explicit fields.

Stored explicitly (no positional signal to derive from):

- **`study.yaml`'s `dataset_order: [ADSL, ADAE, …]`** - the `ItemGroupDef` sequence in
  the emitted XML (which `define.html` is read top-to-bottom in). Datasets are
  separate files with no shared list. Optional and additive: an unlisted dataset
  sorts after every listed one, alphabetically. `define import` captures a source's
  actual sequence only when it is not already alphabetical. `define lint`'s
  `dataset-order` rule errors on a listed name matching no dataset.
- **`Term.rank` → `CodeListItem`/`EnumeratedItem/@Rank`** (`int | float | None`).
  Per Define-XML, `@Rank` "does not imply a display order" - it is the numeric
  significance of a term relative to its siblings (severity 1/2/3). Optional, but
  **all-or-none across a codelist and distinct** when set. `@OrderNumber` stays
  positional; `define import` captures `@Rank` verbatim and drops `@OrderNumber`.

---

## 6. The linker pass

Reference resolution is a distinct build stage before any XML is emitted:

1. Load every file; validate each against its pydantic model.
2. Build the symbol table: `name → derived OID`, per object kind.
3. Resolve every reference. `{oid: …}` resolves with no lookup; a name resolves
   through the symbol table (its derived OID, or the target's own `oid:` override).
4. **Unresolved reference → hard error**, with file and line from the ruamel node.
5. **Orphan object → warning** (a codelist / method / named where clause nothing
   references).
6. Emit.

Broken hyperlinks are the most common `define.html` defect and almost always trace to
a method or codelist referenced but never defined. Making that a build-time error is
most of this tool's value.

---

## 7. Where-clause rules

- **Multiple `values:` require `IN` / `NOTIN`.** `EQ` with two check values → error.
- **Cross-dataset conditions require a comment.** `def:WhereClauseDef/@def:CommentOID`
  must point at a CommentDef describing the join whenever the clause references
  variables in more than one dataset. Missing → error.
- **Duplicate inline clauses → warning** (promote to a named clause under
  `whereclauses/`). Never auto-merged - content-addressed dedup produces unreadable
  OIDs like `WC.SUPPCL.QNAM.EQ.1ea50245…`, exactly what the naming scheme exists to
  avoid.
- **No `OR`.** Define-XML has no representation for it. Disjunction = multiple
  ItemRefs against one ItemDef via `same_as:`.

**ARM parallel:** `arm:AnalysisDatasets` requires a `def:CommentOID` when a result
spans more than one dataset (`join_comment:`). Missing with ≥2 datasets → error.

---

## 8. Text and `xml:lang`

Descriptive text is a plain string; the emitter wraps it in
`<TranslatedText xml:lang="en">`. There is **no language field** anywhere in the file
format. Multi-language `TranslatedText` is effectively unused in regulatory
submissions.

**The importer fails loudly.** If an incoming define.xml has any `TranslatedText`
with `lang` other than `en`, or more than one per parent, importing would silently
discard content. The importer errors, lists every offending element with its XPath,
and offers `--force-lang en` for a user who has looked and decided the non-`en` text
is disposable.

---

## 9. `FormalExpression` and code blocks

`MethodDef` carries a human-readable `Description` and zero or more `FormalExpression`
elements. `Context` is required and must be distinct per expression within a method.

```yaml
name: Treatment Start Date
type: Computation
description: |
  Date part of the earliest non-missing EXSTDTC in EX where EXDOSE > 0 ...
expressions:
  - context: SAS 9.4
    code: |
      trtsdt = datepart(min(of _exstdtc[*]));
  - context: R
    code: |
      trtsdt <- min(ex$EXSTDTC[ex$EXDOSE > 0], na.rm = TRUE)
```

Handling rules:

- **Block scalars only.** `fmt` rewrites every `code:` value as `|` - never `>`
  (destroys line structure), never a quoted scalar (turns newlines into escapes).
- **Whitespace fidelity is a hard requirement.** Relative indentation inside the code
  must survive a load–dump cycle byte-for-byte; chomping is normalised to `|` (one
  trailing newline). This is the one field where a formatter bug silently corrupts a
  submission - the round-trip suite asserts byte-equality of every `code:` value.
- **Let `lxml` escape; never emit CDATA.** `<`, `>`, `&` are common in derivation
  code; the entities are what a conformant reader expects, and most parsers do not
  preserve CDATA (making import lossy).
- **`Context` needs a project convention.** Declare the permitted set in `study.yaml`
  (`expression_contexts: ["SAS 9.4", "R 4.4"]`); `define lint` warns on any `context:`
  not in it (silent until a study opts in).
- **Duplicate `Context` in one method → error.**
- **`expressions:` without `description:` → error** - a consumer that cannot interpret
  the expression falls back to the `TranslatedText`.
- **Element order comes from the XSD**, not the YAML key order.
- **Not in where clauses by default.** `FormalExpression` inside a `RangeCheck` is
  XSD-valid but outside Define-XML's `Comparator`+`CheckValue` business rules and most
  validators; opt-in only.

`arm:ProgrammingCode` has the same `context` + `code` shape but different semantics
(it documents the program that produced a TFL). The `expression_contexts` lint list
applies to both. `programming_code:` accepts an inline `code:` **or** a `document:`
reference, not both.

---

## 10. Element-level mapping notes

Attributes and elements that are modeled but not obvious from the shape above. Each is
confirmed against the two bundled CDISC example submissions and gated by the
round-trip suite.

| Define-XML | YAML field | Notes |
|---|---|---|
| `ItemDef/@SASFieldName` | `Variable.sas_field_name` | Defaults to `name:`; always emitted. |
| `ItemGroupDef/@Domain` | `Dataset.domain` | |
| `ItemGroupDef` `def:Class` / `def:SubClass` | `Dataset.class` / `Dataset.subclasses` | `SubClass.name` is a closed 2-value enum (`TIME-TO-EVENT`, `ADVERSE EVENT`); `parent_class` is free text (union of class + subclass names). |
| `ItemGroupDef/Alias` | `Dataset.aliases` (`list[{context, name}]`) | e.g. `Context="DomainDescription"` on `SUPPxx`. |
| `CodeList/@SASFormatName` | `codelist.sas_format_name` | |
| `def:CommentOID` (on Standard / ItemGroupDef / ItemDef / CodeList / CommentDef) | `comment:` on each | |
| `def:StandardOID` (on ItemGroupDef / CodeList) | `standard:` - `| None` | Optional in the schema; omit rather than empty. |
| `ItemRef/@Role` | `Variable.role` | Also on the value-list and `same_as` paths. |
| `ItemDef/@SignificantDigits` | `Variable.significant_digits` | |
| `def:Origin/@Source` | `origin.data_source` (`Investigator`/`Sponsor`/`Subject`/`Vendor`) | A fixed vocabulary, not a reference. |
| `def:Origin/Description` | `origin.source` (Predecessor only, a `dataset.variable` mnemonic) **or** `origin.description` (every other type, free prose) | A `model_validator` enforces exactly one per type. |
| `def:IsNonStandard` / `def:HasNoData` (on ItemGroupDef / ItemRef) | `.is_non_standard` / `.has_no_data` (`bool = False`) | `odm:YesOnly` - emitted only when true. |
| `CodeListItem`/`EnumeratedItem/@def:ExtendedValue` | `Term.extended` | Per-*term* flag, independent of the codelist-wide `extended:` (`def:IsNonStandard`). |
| `CodeList` / `Term` sponsor `Alias` | `.aliases` (`list[{context, name}]`) | Any `Context` except `nci:ExtCodeID`, which is `nci_code:`. |
| `def:PDFPageRef` under **any** `def:DocumentRef` | `pages:` + `title:` (nested `DocumentRef`) or `pages:` + `pages_title:` (flat, on `Origin` / `CommentDef`) | See §11. |
| `MethodDef/def:DocumentRef` | `MethodDef.documents` (`list[DocumentRef]`) | Emitted last in `MethodDef`'s child sequence (`Description, FormalExpression*, Alias*, def:DocumentRef*`). |
| `CommentDef/def:DocumentRef` (`maxOccurs="unbounded"`) | `CommentDef.documents` (`list[DocumentRef]`) | |
| `def:AnnotatedCRF` / `def:SupplementalDoc` | `documents.yaml`'s `annotated_crf:` / `supplemental_docs:` (plain name lists) | No per-ref `def:PDFPageRef` here. |
| `<?xml-stylesheet …?>` PI | `study.yaml`'s `odm.stylesheet` | Sits outside the ODM content model. |

### External codelists

An `ExternalCodeList` is a dictionary reference, not a membership list. The model is a
**discriminated union on the presence of `external:`**:

```yaml
# codelists/meddra.yaml
name: MEDDRA
label: MedDRA
type: text
external:
  dictionary: MedDRA
  version: "26.1"
```

External and enumerated codelists share one `codelists/` directory and one symbol
table - an `ItemDef` references either kind identically via `CodeListRef`. The model
**rejects** `terms:`, `extended:`, `nci_code:`, `standard:`, `comment:` on an external
codelist. CT lint rules (term coverage, NCI code presence) skip external codelists.
`ExternalCodeList/@Dictionary` should be a CT C66788 ("CodeList Dictionary Name")
value - the editor offers those as a datalist (see [`LOCALCT.md`](LOCALCT.md)) but the
field stays free text, and a dictionary name is never a `def:Standard` entry.

### Enumerated codelists - three shapes

ODM's `CodeList` content model is a three-way choice, never mixed:

- **`CodeListItem*`** - every term has a `decode:` (a human label).
- **`EnumeratedItem*`** - no term has a `decode:` (a self-explanatory coded value:
  age groups, arm labels).
- **`ExternalCodeList`** - the dictionary reference above.

`terms:` must be uniform (every entry has `decode:`, or none do) - enforced by a
`model_validator`. `CodedValue` is **case-sensitive** per ODM: `PA` and `Pa` are
distinct terms, and two terms sharing a code is invalid.

### `def:leaf`

Datasets carry an explicit `leaf:` block (a wrong `xlink:href` produces a
define.html that links nowhere and looks fine):

```yaml
leaf:
  href: adsl.xpt
  title: adsl.xpt      # optional; defaults to basename(href)
```

The leaf `ID` is still derived (`LF.ADSL`) - a dataset leaf has exactly one owner.
Documents in `documents.yaml` are explicit throughout (they have no owning dataset).

---

## 11. `def:PDFPageRef` on a `def:DocumentRef`

Every `def:DocumentRef` DefineYAML emits - under `Origin`, `MethodDef`, `CommentDef`,
and ARM `ResultDisplay` / `Documentation` / `ProgrammingCode` - round-trips its
optional `def:PDFPageRef`. The page value is a union:

```yaml
pages: [4, 5]           # list of integers  -> Type="PhysicalRef", PageRefs="4 5"
pages: [section2.1]     # list of strings   -> Type="NamedDestination", PageRefs="section2.1"
pages: {first: 112, last: 114}   # a range  -> FirstPage / LastPage (integers only)
```

`@Type` is **not stored** - the emitter infers `PhysicalRef` vs `NamedDestination`
from whether the `pages:` value parsed as integers or strings (YAML already keeps them
apart). `@Title` is `title:` on the nested `DocumentRef` model, or `pages_title:` on
the flat `Origin` / `CommentDef` shape.

**Business rule (lint, not schema):** `def:PDFPageRef` is *required* when
`def:Origin/@Type="Collected"` and `@Source ∈ {Investigator, Subject}` - an annotated
CRF page is assumed to exist. `define lint`'s `collected-origin-page-ref` warns on an
origin that fits the condition but cites no page.

---

## 12. What the round-trip deliberately does *not* preserve

These are design choices, scrubbed equally from both sides of the round-trip
comparison - not gaps:

- **`@OrderNumber`** on `ItemRef` / `CodeListItem` / `EnumeratedItem` - always
  re-derived from list position. Relative order *is* checked; the absolute number is
  not meant to survive.
- **Attribute order** and pretty-print whitespace.
- **Top-level child order** - re-ordered to the XSD's mandated sequence.
- **`def:IsNonStandard` / `def:StandardOID` / `def:CommentOID` / `ExternalCodeList/@href`
  on an *external* codelist** - deliberately outside the narrow `ExternalCodeListDef`
  model.
- **`SASFieldName`** when it equals `Name` and the source omitted it - the tool always
  emits it explicitly.

Anything else that differs is a real regression.

---

## 13. Worked example

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
  href: adsl.xpt                          # ID derived as LF.ADSL
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

Everything after `#`, and every word of a `description:` block, is preserved on save
and **never reaches the XML**.
