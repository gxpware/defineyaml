"""`define lint`: xref integrity, orphans, and the project conventions from CLAUDE.md
that neither the XSD nor the pydantic models enforce on their own. Each test builds the
smallest file tree that exercises exactly one rule, rather than importing a bundled
fixture - these are project-specific conventions invented for this tool, not Define-XML
spec rules a real submission would already demonstrate.
"""

from __future__ import annotations

from pathlib import Path


from defineyaml.lint import LintFinding, run_lint

_STUDY_YAML = """\
odm:
  file_oid: "FILE.1"
study:
  oid: "STUDY.1"
  name: "Test Study"
  protocol_name: "PROTO-1"
metadata_version:
  oid: "MDV.1"
  name: "MDV"
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _minimal_tree(
    root: Path,
    *,
    expression_contexts: list[str] | None = None,
    dataset_order: list[str] | None = None,
) -> None:
    study = _STUDY_YAML
    if expression_contexts:
        ctx_lines = "\n".join(f'  - "{c}"' for c in expression_contexts)
        study += f"expression_contexts:\n{ctx_lines}\n"
    if dataset_order:
        order_lines = "\n".join(f'  - "{n}"' for n in dataset_order)
        study += f"dataset_order:\n{order_lines}\n"
    _write(root / "study.yaml", study)


def _minimal_dataset(root: Path, name: str, *, variables: str = "[]") -> None:
    _write(
        root / "datasets" / f"{name.lower()}.yaml",
        f"""\
name: "{name}"
label: "{name} label"
class: "SUBJECT LEVEL ANALYSIS DATASET"
structure: "One record per subject"
variables: {variables}
""",
    )


def by_rule(findings: list[LintFinding], rule: str) -> list[LintFinding]:
    return [f for f in findings if f.rule == rule]


def test_clean_minimal_tree_has_no_errors(tmp_path):
    _minimal_tree(tmp_path)
    _minimal_dataset(tmp_path, "DM")
    findings = run_lint(tmp_path)
    assert not [f for f in findings if f.severity == "error"]


def test_xref_error_on_unresolved_reference(tmp_path):
    _minimal_tree(tmp_path)
    _write(
        tmp_path / "datasets" / "dm.yaml",
        """\
name: "DM"
label: DM
class: "SUBJECT LEVEL ANALYSIS DATASET"
structure: s
variables:
  - name: "TRTSDT"
    label: Treatment Start Date
    type: integer
    method: does-not-exist
""",
    )
    findings = run_lint(tmp_path)
    xref = by_rule(findings, "xref")
    assert len(xref) == 1
    assert xref[0].severity == "error"
    assert "does-not-exist" in xref[0].message


def test_orphan_warning_for_unreferenced_method(tmp_path):
    _minimal_tree(tmp_path)
    _minimal_dataset(tmp_path, "DM")
    _write(
        tmp_path / "methods" / "unused.yaml",
        """\
name: Unused Method
type: Computation
description: Nothing calls this.
""",
    )
    findings = run_lint(tmp_path)
    orphans = by_rule(findings, "orphan")
    assert any("UNUSED" in f.message for f in orphans)


def test_slug_collision_within_same_kind(tmp_path):
    _minimal_tree(tmp_path)
    # "A-E" and "A E" both slugify to "A.E" - a real, if contrived, build_symbol_table
    # collision (CLAUDE.md §3's slugify: non [A-Z0-9._] -> '.', collapsed).
    _minimal_dataset(tmp_path, "A-E")
    _write(
        tmp_path / "datasets" / "a e.yaml",
        """\
name: "A E"
label: also AE
class: "SUBJECT LEVEL ANALYSIS DATASET"
structure: s
variables: []
""",
    )
    findings = run_lint(tmp_path)
    collisions = by_rule(findings, "slug-collision")
    assert len(collisions) == 1
    assert collisions[0].severity == "error"
    # xref also hard-fails on the same underlying collision via build_symbol_table.
    assert by_rule(findings, "xref")


def test_duplicate_name_across_kinds(tmp_path):
    _minimal_tree(tmp_path)
    _minimal_dataset(tmp_path, "SHARED")
    _write(
        tmp_path / "codelists" / "shared.yaml",
        """\
name: "SHARED"
label: Shared Name Codelist
terms:
  - code: "X"
""",
    )
    findings = run_lint(tmp_path)
    dupes = by_rule(findings, "duplicate-name")
    assert len(dupes) == 1
    assert dupes[0].severity == "warning"


def test_analysis_ct_warning_for_nonstandard_reason_and_purpose(tmp_path):
    _minimal_tree(tmp_path)
    _minimal_dataset(tmp_path, "DM")
    _write(
        tmp_path / "documents.yaml",
        """\
documents:
  - name: t1
    href: t1.pdf
    title: Table 1
""",
    )
    _write(
        tmp_path / "analysis-results" / "t1.yaml",
        """\
name: "Table 1"
title: Table 1
document:
  ref: t1
results:
  - name: "R1"
    description: A result.
    reason: "SPONSOR DEFINED REASON"
    purpose: "SPONSOR DEFINED PURPOSE"
    datasets:
      - dataset: DM
        variables: []
""",
    )
    findings = run_lint(tmp_path)
    ct_findings = by_rule(findings, "analysis-ct")
    assert len(ct_findings) == 2
    assert all(f.severity == "warning" for f in ct_findings)


def test_expression_context_warning_when_undeclared(tmp_path):
    _minimal_tree(tmp_path, expression_contexts=["SAS 9.4"])
    _minimal_dataset(tmp_path, "DM")
    _write(
        tmp_path / "methods" / "m1.yaml",
        """\
name: M1
type: Computation
description: text
expressions:
  - context: "R 4.4"
    code: "x <- 1"
""",
    )
    findings = run_lint(tmp_path)
    ctx_findings = by_rule(findings, "expression-context")
    assert len(ctx_findings) == 1
    assert "R 4.4" in ctx_findings[0].message


def test_no_expression_context_warning_when_study_has_not_opted_in(tmp_path):
    _minimal_tree(tmp_path)  # no expression_contexts: at all
    _minimal_dataset(tmp_path, "DM")
    _write(
        tmp_path / "methods" / "m1.yaml",
        """\
name: M1
type: Computation
description: text
expressions:
  - context: "whatever"
    code: "x <- 1"
""",
    )
    findings = run_lint(tmp_path)
    assert not by_rule(findings, "expression-context")


def test_undocumented_method_warning(tmp_path):
    _minimal_tree(tmp_path)
    _minimal_dataset(tmp_path, "DM")
    _write(tmp_path / "methods" / "empty.yaml", "name: Empty\ntype: Computation\n")
    findings = run_lint(tmp_path)
    undocumented = by_rule(findings, "undocumented-method")
    assert len(undocumented) == 1
    assert "empty" in undocumented[0].message


def test_documented_method_has_no_warning(tmp_path):
    _minimal_tree(tmp_path)
    _minimal_dataset(tmp_path, "DM")
    _write(
        tmp_path / "methods" / "ok.yaml",
        "name: Ok\ntype: Computation\ndescription: explains it\n",
    )
    findings = run_lint(tmp_path)
    assert not by_rule(findings, "undocumented-method")


def test_collected_origin_without_page_ref_warns(tmp_path):
    _minimal_tree(tmp_path)
    _minimal_dataset(
        tmp_path,
        "DM",
        variables="""
  - name: BRTHDTC
    label: Date of Birth
    type: text
    origin:
      type: Collected
      data_source: Investigator
""",
    )
    findings = run_lint(tmp_path)
    hits = by_rule(findings, "collected-origin-page-ref")
    assert len(hits) == 1 and hits[0].severity == "warning"
    assert "BRTHDTC" in hits[0].message


def test_collected_origin_with_page_ref_has_no_warning(tmp_path):
    _minimal_tree(tmp_path)
    _write(
        tmp_path / "documents.yaml",
        "documents:\n  - name: acrf\n    href: acrf.pdf\n    title: CRF\n",
    )
    _minimal_dataset(
        tmp_path,
        "DM",
        variables="""
  - name: BRTHDTC
    label: Date of Birth
    type: text
    origin:
      type: Collected
      data_source: Subject
      document: acrf
      pages: [4, 5]
""",
    )
    findings = run_lint(tmp_path)
    assert not by_rule(findings, "collected-origin-page-ref")


def test_derived_origin_never_warns_about_page_ref(tmp_path):
    _minimal_tree(tmp_path)
    _minimal_dataset(
        tmp_path,
        "DM",
        variables="""
  - name: AGE
    label: Age
    type: integer
    origin:
      type: Derived
      data_source: Sponsor
""",
    )
    findings = run_lint(tmp_path)
    assert not by_rule(findings, "collected-origin-page-ref")


def test_valuelist_where_shape_mismatch_warning(tmp_path):
    _minimal_tree(tmp_path)
    _minimal_dataset(tmp_path, "ADLB")
    _write(
        tmp_path / "whereclauses" / "alt.yaml",
        """\
conditions:
  - variable: ADLB.PARAMCD
    comparator: EQ
    values: ["ALT"]
""",
    )
    _write(
        tmp_path / "valuelists" / "adlb__aval.yaml",
        """\
dataset: ADLB
variable: AVAL
entries:
  - name: "ALT"
    where: alt
    item:
      name: "AVAL1"
      label: ALT Result
      type: float
  - name: "AST"
    where:
      - variable: ADLB.PARAMCD
        comparator: EQ
        values: ["AST"]
    item:
      name: "AVAL2"
      label: AST Result
      type: float
""",
    )
    findings = run_lint(tmp_path)
    shape_findings = by_rule(findings, "valuelist-where-shape")
    assert len(shape_findings) == 1


def test_valuelist_uniform_where_shape_has_no_warning(tmp_path):
    _minimal_tree(tmp_path)
    _minimal_dataset(tmp_path, "ADLB")
    _write(
        tmp_path / "valuelists" / "adlb__aval.yaml",
        """\
dataset: ADLB
variable: AVAL
entries:
  - name: "ALT"
    where:
      - variable: ADLB.PARAMCD
        comparator: EQ
        values: ["ALT"]
    item:
      name: "AVAL1"
      label: ALT Result
      type: float
  - name: "AST"
    where:
      - variable: ADLB.PARAMCD
        comparator: EQ
        values: ["AST"]
    item:
      name: "AVAL2"
      label: AST Result
      type: float
""",
    )
    findings = run_lint(tmp_path)
    assert not by_rule(findings, "valuelist-where-shape")


def test_oid_visibility_reports_override_and_literal_ref(tmp_path):
    _minimal_tree(tmp_path)
    _write(
        tmp_path / "datasets" / "dm.yaml",
        """\
name: "DM"
label: DM
class: "SUBJECT LEVEL ANALYSIS DATASET"
structure: s
oid: "IG.CUSTOM"
variables:
  - name: "STUDYID"
    label: Study ID
    type: text
    comment: {oid: "COM.LEGACY"}
""",
    )
    findings = run_lint(tmp_path)
    overrides = by_rule(findings, "oid-override")
    literal_refs = by_rule(findings, "literal-oid-ref")
    assert any("IG.CUSTOM" in f.message for f in overrides)
    assert any("COM.LEGACY" in f.message for f in literal_refs)
    assert all(f.severity == "info" for f in overrides + literal_refs)


def test_schema_error_in_one_file_does_not_block_other_checks(tmp_path):
    _minimal_tree(tmp_path)
    _minimal_dataset(tmp_path, "DM")
    # Missing required `structure:` - a genuine pydantic ValidationError.
    _write(
        tmp_path / "datasets" / "broken.yaml",
        """\
name: "BROKEN"
label: Broken
class: "SUBJECT LEVEL ANALYSIS DATASET"
variables: []
""",
    )
    _write(tmp_path / "methods" / "empty.yaml", "name: Empty\ntype: Computation\n")
    findings = run_lint(tmp_path)
    schema_errors = by_rule(findings, "schema")
    assert len(schema_errors) == 1
    assert "broken" in schema_errors[0].path
    # DM still gets checked despite BROKEN failing to validate.
    assert by_rule(findings, "undocumented-method")


def test_dataset_order_error_on_stale_name(tmp_path):
    _minimal_tree(tmp_path, dataset_order=["ADSL", "RENAMED-AWAY"])
    _minimal_dataset(tmp_path, "ADSL")
    findings = run_lint(tmp_path)
    order_findings = by_rule(findings, "dataset-order")
    assert len(order_findings) == 1
    assert order_findings[0].severity == "error"
    assert "RENAMED-AWAY" in order_findings[0].message


def test_dataset_order_matching_real_names_has_no_warning(tmp_path):
    _minimal_tree(tmp_path, dataset_order=["ADSL", "DM"])
    _minimal_dataset(tmp_path, "ADSL")
    _minimal_dataset(tmp_path, "DM")
    findings = run_lint(tmp_path)
    assert not by_rule(findings, "dataset-order")


def test_no_dataset_order_check_when_study_has_not_opted_in(tmp_path):
    _minimal_tree(tmp_path)  # no dataset_order: at all
    _minimal_dataset(tmp_path, "ADSL")
    findings = run_lint(tmp_path)
    assert not by_rule(findings, "dataset-order")


def test_lint_finding_str_includes_severity_rule_and_path():
    finding = LintFinding(
        "warning", "orphan", "method 'x' is never referenced", "methods/x.yaml"
    )
    text = str(finding)
    assert "warning" in text
    assert "orphan" in text
    assert "methods/x.yaml" in text
