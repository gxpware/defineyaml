from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import DefineBaseModel, Ref
from .documents import Document


class OdmHeader(DefineBaseModel):
    file_oid: str
    creation_datetime: str | None = None
    as_of_datetime: str | None = None
    originator: str | None = None
    source_system: str | None = None
    source_system_version: str | None = None
    # -> the <?xml-stylesheet type="text/xsl" href="..."?> processing instruction between the
    # XML declaration and <ODM> (Define-XML spec §5.3.2). Purely presentational - lets a
    # browser render the define.xml directly - not part of the ODM/def content model at all,
    # so it's optional and has no bearing on validation.
    stylesheet: str | None = None


class Study(DefineBaseModel):
    oid: str
    name: str
    description: str | None = None
    protocol_name: str


class MetaDataVersion(DefineBaseModel):
    oid: str
    name: str
    description: str | None = None
    define_version: str = "2.1.0"


class StudyFile(DefineBaseModel):
    odm: OdmHeader
    study: Study
    metadata_version: MetaDataVersion
    expression_contexts: list[str] = Field(default_factory=list)
    # ItemGroupDef sequence in the emitted document - the define.html reading order a
    # reviewer actually walks top to bottom, e.g. ADSL before every other ADaM dataset.
    # Not derivable (CLAUDE.md §3's rule covers ordering *within* one object - ItemRef/
    # OrderNumber, KeySequence, CodeListItem/OrderNumber - datasets are separate files
    # with no natural sequence of their own, unlike a YAML list, so this is the one
    # ordering concern in the whole model that has to be stored explicitly, in one
    # place, rather than derived from file layout or list position). Dataset name:
    # values, not file keys - the same identity every other reference in this model
    # uses. Optional: a dataset not listed here sorts after every listed one, by name -
    # so a study that never touches this stays exactly as alphabetical as it is today.
    dataset_order: list[str] = Field(default_factory=list)


class StandardDef(DefineBaseModel):
    name: str
    type: Literal["IG", "CT"]
    version: str
    publishing_set: str | None = None
    status: Literal["Final", "Draft"] = "Final"
    comment: Ref | None = None  # -> def:CommentOID
    oid: str | None = None
    # A local editor pointer only - the path (relative to the configured Standards
    # folder, CLAUDE.md §9.2) of the CDISC CSV export this standard's content is
    # scaffolded from, e.g. "data_tabulation/SDTMIG_v3.4.csv". Never emitted to
    # define.xml and never read by the importer; it only drives the editor's
    # "new dataset / codelists from standard" actions.
    standards_file: str | None = None


class StandardsFile(DefineBaseModel):
    standards: list[StandardDef]
    # Local editor pointer only - the folder of CDISC CSV exports that this tree's
    # `standards_file:` paths are relative to (CLAUDE.md §9.2). Per-tree, not a global
    # app setting: two define projects can draw from different CSV export folders.
    # Absolute, or relative to the define/ tree root. Never emitted to define.xml,
    # never read by the importer.
    standards_folder: str | None = None


class DocumentsFile(DefineBaseModel):
    documents: list[Document]
    annotated_crf: list[Ref] = Field(
        default_factory=list
    )  # -> def:AnnotatedCRF/def:DocumentRef*
    supplemental_docs: list[Ref] = Field(
        default_factory=list
    )  # -> def:SupplementalDoc/def:DocumentRef*
