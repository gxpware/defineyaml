"""Hard-coded CDISC-controlled terminology for ARM 1.0 (CLAUDE.md §7.1 / §8, "smart mode"
CDISC Library lookup deferred). Not enforced by the pydantic models: both `AnalysisReason`
and `AnalysisPurpose` are XSD unions of this enumerated set with unrestricted free text
(cdisc-arm-1.0/arm-ns.xsd), i.e. CDISC itself defines these as *extensible* - a sponsor value
outside this list is schema-valid, so rejecting it at parse time would be wrong. `define lint`
is where these belong: flag a value outside the set as a warning, not a build-blocking error.
"""

from __future__ import annotations

ANALYSIS_REASON_CT = (
    "SPECIFIED IN PROTOCOL",
    "SPECIFIED IN SAP",
    "DATA DRIVEN",
    "REQUESTED BY REGULATORY AGENCY",
)

ANALYSIS_PURPOSE_CT = (
    "PRIMARY OUTCOME MEASURE",
    "SECONDARY OUTCOME MEASURE",
    "EXPLORATORY OUTCOME MEASURE",
)
