"""`define init`: scaffold a new define/ file tree (CLAUDE.md §2) - a subdirectory for
every object kind, plus a study.yaml carrying the fields Define-XML requires plus the
ODM-header housekeeping every submission needs (creation/as-of timestamps, originator,
source system, the rendering stylesheet, the Define-XML version). Separated from cli.py's
interactive prompting so the scaffolding itself (what gets created, and with what content)
is testable without faking stdin.
"""

from __future__ import annotations

import getpass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .io.yaml_io import dump
from .models import MetaDataVersion, OdmHeader, Study, StudyFile
from .tree_time import now_iso

# Every subdirectory a collection kind lives under (CLAUDE.md §2). standards.yaml and
# documents.yaml aren't created - both are optional (linker.load_tree defaults to an
# empty StandardsFile/DocumentsFile when the file is absent), so there's nothing minimal
# to put in them until there's real content for either.
SCAFFOLD_SUBDIRS = (
    "datasets",
    "codelists",
    "methods",
    "comments",
    "valuelists",
    "whereclauses",
    "analysis-results",
)

SOURCE_SYSTEM = "DefineYAML"
# The rendering stylesheet's href (Define-XML spec §5.3.2's <?xml-stylesheet?> PI). Matches
# the file vendored at src/defineyaml/stylesheets/define2-1.xsl and html_render's default;
# a submission ships the .xsl alongside define.xml so a browser can render it directly.
STYLESHEET_HREF = "define2-1.xsl"


class ScaffoldError(Exception):
    """The destination already exists, or the given study fields don't validate."""


def _tool_version() -> str:
    # Normal install: read the version hatch-vcs computed from the git tag.
    try:
        return version("defineyaml")
    except PackageNotFoundError:
        pass
    # Frozen build (PyInstaller) has no dist metadata - fall back to the
    # generated _version.py bundled at build time.
    try:
        from ._version import __version__

        return __version__
    except Exception:
        return "0"


def _current_user() -> str:
    try:
        return getpass.getuser()
    except Exception:  # no password entry / no USER env - rare, but don't crash init
        return "unknown"


def scaffold_tree(
    destination: Path,
    *,
    file_oid: str,
    study_oid: str,
    study_name: str,
    protocol_name: str,
    metadata_version_oid: str,
    metadata_version_name: str,
) -> StudyFile:
    """Create `destination` with every object-kind subdirectory and a study.yaml.

    The ODM header is pre-filled: `as_of_datetime` to now (local time, ISO 8601),
    `originator` to the current OS user, `source_system` / `source_system_version` to
    this tool, `stylesheet` to `define2-1.xsl`, and `metadata_version.define_version`
    to 2.1.0 - all editable in study.yaml afterward. `creation_datetime` is left blank
    on purpose: `define build` / the define.html render fill `CreationDateTime` with
    the tree's latest modification (`tree_time.latest_modification` - git history when
    version-controlled, else the newest YAML file's mtime) whenever it's empty.

    Raises ScaffoldError, touching nothing on disk, if `destination` already exists or
    the given fields don't satisfy StudyFile's own validation.
    """
    if destination.exists():
        raise ScaffoldError(f"{destination} already exists - refusing to overwrite")

    try:
        study = StudyFile(
            odm=OdmHeader(
                file_oid=file_oid,
                as_of_datetime=now_iso(),
                originator=_current_user(),
                source_system=SOURCE_SYSTEM,
                source_system_version=_tool_version(),
                stylesheet=STYLESHEET_HREF,
            ),
            study=Study(oid=study_oid, name=study_name, protocol_name=protocol_name),
            metadata_version=MetaDataVersion(
                oid=metadata_version_oid, name=metadata_version_name
            ),
        )
    except Exception as exc:  # pydantic.ValidationError
        raise ScaffoldError(str(exc)) from exc

    data = study.model_dump(exclude_none=True, exclude_defaults=True)
    # define_version equals its model default (2.1.0), so exclude_defaults drops it -
    # but it's a spec-significant field a submission preparer should see and confirm,
    # so write it back explicitly.
    data["metadata_version"]["define_version"] = study.metadata_version.define_version

    destination.mkdir(parents=True)
    for subdir in SCAFFOLD_SUBDIRS:
        (destination / subdir).mkdir()
    dump(data, destination / "study.yaml")
    return study
