from defineyaml import oid


def test_slugify_basic():
    assert oid.slugify("adsl") == "ADSL"
    assert oid.slugify("adamig-1-3") == "ADAMIG.1.3"


def test_slugify_collapses_repeats_and_strips_separators():
    assert oid.slugify("--foo bar--") == "FOO.BAR"


def test_slugify_preserves_underscore_as_allowed_char():
    assert oid.slugify("foo__bar") == "FOO__BAR"


def test_derivation_table_examples():
    assert oid.standard_oid("adamig-1-3") == "STD.ADAMIG.1.3"
    assert oid.itemgroup_oid("ADSL") == "IG.ADSL"
    assert oid.item_oid("ADSL", "TRTSDT") == "IT.ADSL.TRTSDT"
    assert oid.item_value_level_oid("ADLB", "AVAL", "ALT") == "IT.ADLB.AVAL.ALT"
    assert oid.codelist_oid("RACE") == "CL.RACE"
    assert oid.method_oid("adsl/trtsdt") == "MT.ADSL.TRTSDT"
    assert oid.comment_oid("adsl/usubjid") == "COM.ADSL.USUBJID"
    assert oid.valuelist_oid("ADLB", "AVAL") == "VL.ADLB.AVAL"
    assert oid.whereclause_inline_oid("ADLB", "AVAL", "ALT") == "WC.ADLB.AVAL.ALT"
    assert oid.whereclause_named_oid("alt-week4") == "WC.ALT.WEEK4"
    assert oid.leaf_dataset_oid("ADSL") == "LF.ADSL"
    assert oid.leaf_document_oid("acrf") == "LF.ACRF"
    assert oid.result_display_oid("t14-2-1") == "RD.T14.2.1"
    assert oid.analysis_result_oid("t14-2-1", "ANCOVA") == "AR.T14.2.1.ANCOVA"


def test_shared_object_oid_derives_from_path_not_from_consumer():
    assert oid.method_oid("shared/last-dose-date") == "MT.SHARED.LAST.DOSE.DATE"


def test_resolve_oid_prefers_explicit_override():
    assert oid.resolve_oid("CL.CUSTOM", "CL.RACE") == "CL.CUSTOM"
    assert oid.resolve_oid(None, "CL.RACE") == "CL.RACE"
