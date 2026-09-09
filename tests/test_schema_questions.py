"""CLAUDE.md §8's four open schema questions, answered against the actual vendored XSD
rather than assumption - each test is the evidence, not just a comment citing it. If CDISC
ever revises the 2.1/ARM 1.0 schema, these fail and say exactly what changed.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from defineyaml.ct import ANALYSIS_PURPOSE_CT, ANALYSIS_REASON_CT
from defineyaml.models import Origin

FIXTURES = Path(__file__).parent / "fixtures" / "definexml"
SCHEMA_PATH = FIXTURES / "schema" / "cdisc-arm-1.0" / "arm1-0-0.xsd"
ARM_NS_XSD_PATH = FIXTURES / "schema" / "cdisc-arm-1.0" / "arm-ns.xsd"

_SCHEMA = etree.XMLSchema(etree.parse(str(SCHEMA_PATH)))

_ODM_HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<ODM xmlns="http://www.cdisc.org/ns/odm/v1.3"
     xmlns:def="http://www.cdisc.org/ns/def/v2.1"
     xmlns:xlink="http://www.w3.org/1999/xlink"
     FileOID="PROBE.1" ODMVersion="1.3.2" FileType="Snapshot"
     CreationDateTime="2026-01-01T00:00:00" def:Context="Submission">
  <Study OID="STUDY.1">
    <GlobalVariables>
      <StudyName>Probe</StudyName>
      <StudyDescription>Probe</StudyDescription>
      <ProtocolName>Probe</ProtocolName>
    </GlobalVariables>
    <MetaDataVersion OID="MDV.1" Name="MDV" def:DefineVersion="2.1.0">
{body}
    </MetaDataVersion>
  </Study>
</ODM>
"""


def _validate(body: str) -> tuple[bool, str]:
    doc = etree.fromstring(_ODM_HEADER.format(body=body).encode())
    ok = _SCHEMA.validate(doc)
    return ok, "\n".join(str(e) for e in _SCHEMA.error_log)


# ---------------------------------------------------------------------------
# 3A. MethodDef child element order
# ---------------------------------------------------------------------------


def test_methoddef_correct_order_is_description_formalexpression_alias_documentref():
    # ODM1-3-2-foundation.xsd's ODMcomplexTypeDefinition-MethodDef sequence is
    # Description, FormalExpression*, Alias*, MethodDefElementExtension - and
    # define-extension.xsd's redefine of MethodDefElementExtension appends
    # def:DocumentRef* at the END of that, not after Description. CLAUDE.md §8 previously
    # guessed (Description, def:DocumentRef, FormalExpression, Alias) - this is not that.
    body = """
      <MethodDef OID="MT.PROBE" Name="Probe" Type="Computation">
        <Description><TranslatedText xml:lang="en">Probe</TranslatedText></Description>
        <FormalExpression Context="SAS 9.4">x = 1;</FormalExpression>
        <Alias Context="probe" Name="probe"/>
        <def:DocumentRef leafID="LF.PROBE"/>
      </MethodDef>
      <def:leaf ID="LF.PROBE" xlink:href="probe.pdf"><def:title>probe.pdf</def:title></def:leaf>
    """
    ok, errors = _validate(body)
    assert ok, errors


def test_methoddef_documentref_before_formalexpression_is_invalid():
    # The order CLAUDE.md §8 previously guessed at - proves that guess wrong, not just
    # that the correct order (above) happens to also work.
    body = """
      <MethodDef OID="MT.PROBE" Name="Probe" Type="Computation">
        <Description><TranslatedText xml:lang="en">Probe</TranslatedText></Description>
        <def:DocumentRef leafID="LF.PROBE"/>
        <FormalExpression Context="SAS 9.4">x = 1;</FormalExpression>
      </MethodDef>
      <def:leaf ID="LF.PROBE" xlink:href="probe.pdf"><def:title>probe.pdf</def:title></def:leaf>
    """
    ok, _errors = _validate(body)
    assert not ok


# ---------------------------------------------------------------------------
# 3B. FormalExpression inside a def:WhereClauseDef's RangeCheck
# ---------------------------------------------------------------------------


def test_formal_expression_in_wc_rangecheck_is_schema_valid():
    # def:WhereClauseDef references plain odm:RangeCheck unmodified (define-ns.xsd), and
    # ODMcomplexTypeDefinition-RangeCheck's content model is a choice of
    # CheckValue+ | FormalExpression+ - so this is XSD-valid. CLAUDE.md §7.5 was right not
    # to take that on faith: P21 conformance is a separate question this environment has no
    # way to check (no P21 CLI/service available here), and the stylesheet/most validators
    # assume the Comparator+CheckValue form regardless of what the XSD alone permits. This
    # test settles only the XSD half - the opt-in-only stance (no ordinary authoring path)
    # stands until real evidence of a submission that needs it shows up.
    body = """
      <def:WhereClauseDef OID="WC.PROBE">
        <RangeCheck def:ItemOID="IT.PROBE" SoftHard="Soft">
          <FormalExpression Context="SAS 9.4">PARAMCD = 'ALT' and AVISITN = 4</FormalExpression>
        </RangeCheck>
      </def:WhereClauseDef>
      <ItemGroupDef OID="IG.PROBE" Name="PROBE" SASDatasetName="PROBE" Repeating="No"
                    IsReferenceData="No" Purpose="Tabulation" def:Structure="one record per subject">
        <ItemRef ItemOID="IT.PROBE" OrderNumber="1" Mandatory="No"/>
        <def:Class Name="SPECIAL PURPOSE"/>
      </ItemGroupDef>
      <ItemDef OID="IT.PROBE" Name="PROBE" DataType="text" SASFieldName="PROBE"/>
    """
    ok, errors = _validate(body)
    assert ok, errors


# ---------------------------------------------------------------------------
# 3C. def:Origin/@Type is not standard-dependent at the schema level
# ---------------------------------------------------------------------------


def test_origin_type_enumeration_has_no_standard_dependent_restriction():
    # define-enumerations.xsd's OriginType is one flat enumeration (Assigned, Collected,
    # Derived, Not Available, Predecessor, Protocol) with no SEND-vs-other-standard split -
    # "COLLECTED only in a SEND context" is a Define-XML business rule, not an XSD one. So
    # the model is right to leave Origin.type unconstrained by standard: (see below) and any
    # such check belongs in `define lint` (context-dependent: it needs the dataset's
    # standard:, which the model layer doesn't have visibility into per-field), never as a
    # global Literal restriction on Origin.type itself.
    for origin_type in (
        "Assigned",
        "Collected",
        "Derived",
        "Not Available",
        "Predecessor",
        "Protocol",
    ):
        Origin(type=origin_type)


# ---------------------------------------------------------------------------
# 3D. arm:AnalysisResult/@AnalysisReason and @AnalysisPurpose are extensible CT
# ---------------------------------------------------------------------------


def _xsd_enum_values(xsd_path: Path, simple_type_name: str) -> set[str]:
    ns = {"xs": "http://www.w3.org/2001/XMLSchema"}
    tree = etree.parse(str(xsd_path))
    (simple_type,) = tree.xpath(
        f".//xs:simpleType[@name='{simple_type_name}']", namespaces=ns
    )
    return {
        e.get("value") for e in simple_type.findall(".//xs:enumeration", namespaces=ns)
    }


def test_analysis_reason_and_purpose_ct_matches_the_vendored_xsd():
    # arm-ns.xsd defines both as a union of unrestricted odm:text with this enumerated
    # subset - i.e. CDISC itself made these *extensible* CT, not a closed set. A sponsor
    # value outside the list is schema-valid, so ct.py's lists are for `define lint` to warn
    # on (CLAUDE.md's errors-vs-warnings split), not for the pydantic model to reject.
    assert _xsd_enum_values(ARM_NS_XSD_PATH, "AnalysisReason") == set(
        ANALYSIS_REASON_CT
    )
    assert _xsd_enum_values(ARM_NS_XSD_PATH, "AnalysisPurpose") == set(
        ANALYSIS_PURPOSE_CT
    )
