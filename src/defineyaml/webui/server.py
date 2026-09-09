"""`define edit`'s backend: a small FastAPI app over tree.py's read/save functions,
plus the static frontend. Runs entirely on localhost, against one file tree passed
at startup - there's no auth, and it's not meant to be exposed beyond that.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .. import html_render
from .. import oid as oidmod
from ..cdisc import csv_db, local_standards, nci_evs, standard_csv
from ..linker import LinkError
from ..scaffold import ScaffoldError, scaffold_tree
from ..xml_emit import render_xml_bytes
from . import config as editor_config
from . import copy_variables as copy_variables_module
from . import standard_scaffold
from . import state as state_module
from . import tree
from . import usages as usages_module

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def _lifespan(app: FastAPI):
    yield
    csv_db.close_all()  # release the per-tree standards.duckdb connections on shutdown


def create_app(source: Path | None) -> FastAPI:
    """`source` may be None (or, from the CLI, is only ever a real directory): a None
    root starts the editor in first-run setup mode - every content route is unused
    until the frontend calls /api/setup/open or /api/setup/init and the server adopts
    a tree.
    """
    app = FastAPI(title="define edit", lifespan=_lifespan)
    app.state.root = source

    @app.middleware("http")
    async def no_cache_static(request, call_next):
        # A named window.open() target (the sidebar's "CDISC Standards Viewer" link,
        # app.js) navigates rather than reloading from scratch, and browsers apply
        # heuristic freshness to a static response with no explicit Cache-Control at
        # all - either can serve a stale app.js/cdisc-viewer.js after this tool's own
        # source changes underneath it, on a machine that's just built it from source
        # and iterates on it, not a deployed app with a real release cadence to key
        # cache invalidation off of. Simplest fix for a localhost-only, single-user
        # tool: never let the browser cache anything under /static/ at all.
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/info")
    def get_info():
        # The frontend uses this to put the tree's absolute path (and, alongside a read
        # of study.yaml, the study/protocol name) in the tab title and sidebar header -
        # the only way to tell two `define edit` tabs on different studies apart, since
        # otherwise both just say "define edit".
        root = app.state.root
        return {"source": str(root.resolve()) if root is not None else None}

    @app.get("/api/tree/last-modified")
    def get_tree_last_modified():
        # What an empty odm.creation_datetime becomes on the next build - shown as the
        # ghost/placeholder value of the study editor's Creation Date/Time field.
        from ..tree_time import latest_modification

        root = app.state.root
        if root is None:
            return {"datetime": None, "source": "none"}
        stamp, src = latest_modification(root)
        return {"datetime": stamp, "source": src}

    # Launcher: `define` with no arguments starts the server with app.state.root == None
    # and the frontend drives this flow - reopen a recent tree, browse to one, or
    # scaffold a new one - after which the server adopts the choice in place (no
    # restart) and moves it to the front of the recent list.

    @app.get("/api/setup/status")
    def setup_status():
        root = app.state.root
        return {
            "needs_setup": root is None or not root.is_dir(),
            "source": str(root.resolve()) if root is not None else None,
        }

    @app.get("/api/setup/recent")
    def setup_recent():
        # Up to 10 recently opened trees, most-recent first, already filtered by
        # config.get_recent_trees() to the ones that are still a directory. Each
        # carries a best-effort study/protocol label read straight from study.yaml.
        return {
            "recent": [
                {"path": str(p), **_tree_label(p)}
                for p in editor_config.get_recent_trees()
            ]
        }

    @app.get("/api/setup/browse")
    def setup_browse(path: str | None = None):
        # A server-side directory picker: a browser can't hand back a real filesystem
        # path, and this is a localhost single-user tool, so listing directories the
        # user could already `ls` is not a disclosure concern. Directories only, never
        # file contents.
        start = _resolve_browse_start(path, app.state.root)
        try:
            entries = sorted(
                (
                    p
                    for p in start.iterdir()
                    if p.is_dir() and not p.name.startswith(".")
                ),
                key=lambda p: p.name.lower(),
            )
        except (PermissionError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "path": str(start),
            "parent": str(start.parent) if start.parent != start else None,
            "is_tree": (start / "study.yaml").is_file(),
            "writable": _is_writable(start),
            "entries": [
                {
                    "name": p.name,
                    "path": str(p),
                    "is_tree": (p / "study.yaml").is_file(),
                }
                for p in entries
            ],
        }

    @app.post("/api/setup/open")
    def setup_open(body: dict):
        target = Path(body.get("path") or "").expanduser()
        if not target.is_dir():
            raise HTTPException(status_code=400, detail=f"{target} is not a directory")
        return _adopt_tree(app, target)

    @app.post("/api/setup/init")
    def setup_init(body: dict):
        parent = Path(body.get("parent") or "").expanduser()
        name = (body.get("name") or "").strip()
        if not parent.is_dir():
            raise HTTPException(status_code=400, detail=f"{parent} is not a directory")
        if not name or "/" in name or name in (".", ".."):
            raise HTTPException(status_code=400, detail="give a folder name")
        if not (body.get("study_name") or "").strip():
            raise HTTPException(status_code=400, detail="a study name is required")
        fields = _study_fields(body)
        try:
            scaffold_tree(parent / name, **fields)
        except ScaffoldError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _adopt_tree(app, parent / name)

    @app.get("/api/kinds")
    def get_kinds():
        return tree.list_kinds()

    @app.get("/api/kinds/{kind}/items")
    def get_items(kind: str):
        _require_kind(kind)
        items = tree.list_items(app.state.root, kind)
        orphans = usages_module.orphan_keys(app.state.root, kind)
        for item in items:
            item["orphan"] = item["key"] in orphans
        return items

    @app.get("/api/kinds/{kind}/search")
    def search_items_route(kind: str, q: str = "", limit: int = 200):
        # Backs the double-click ref picker (codelist/method/comment on a variable):
        # a name/label/key match plus a full-text pass over each file's contents, so
        # searching "male" turns up the SEX codelist. See tree.search_items.
        _require_kind(kind)
        return tree.search_items(app.state.root, kind, q, limit=limit)

    @app.put("/api/datasets/order")
    def put_dataset_order(body: dict):
        # study.yaml's dataset_order: (models/study.py) - names, not file keys, so the
        # frontend sends whatever list_items("datasets") gave it back for each item's
        # `name`. Routed through tree.save_object like any other save, so this gets the
        # same comment-preserving merge and pydantic validation every other write does -
        # there's nothing dataset-order-specific about *writing* it, only about which
        # field of which object a sidebar reorder ends up touching.
        order = body.get("order")
        if not isinstance(order, list):
            raise HTTPException(
                status_code=400, detail="body must be {'order': [dataset names, ...]}"
            )
        try:
            study_data = tree.read_object(app.state.root, "study", "study")
        except tree.NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        study_data["dataset_order"] = order
        try:
            tree.save_object(app.state.root, "study", "study", study_data)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422, detail=_validation_errors(exc)
            ) from exc
        return {"ok": True}

    @app.get("/api/kinds/{kind}/items/{key:path}")
    def get_item(kind: str, key: str):
        _require_kind(kind)
        try:
            data = tree.read_object(app.state.root, kind, key)
        except tree.NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "data": data,
            "schema": tree.schema_for(kind),
            "usages": usages_module.usages_for(app.state.root, kind, key),
        }

    @app.put("/api/kinds/{kind}/items/{key:path}")
    def put_item(kind: str, key: str, data: dict):
        _require_kind(kind)
        try:
            tree.save_object(app.state.root, kind, key, data)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422, detail=_validation_errors(exc)
            ) from exc
        return {"ok": True}

    @app.delete("/api/kinds/{kind}/items/{key:path}")
    def delete_item(kind: str, key: str):
        _require_kind(kind)
        try:
            tree.delete_object(app.state.root, kind, key)
        except tree.NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True}

    @app.post("/api/kinds/datasets/items/{key:path}/copy-variables")
    def copy_variables(key: str, body: dict):
        try:
            result = copy_variables_module.copy_variables(
                app.state.root,
                target_key=key,
                source_key=body["source_key"],
                variable_names=body["variable_names"],
                reference_mode=body.get("reference_mode", "share"),
                set_predecessor=bool(body.get("set_predecessor", False)),
            )
        except tree.NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(
                status_code=422, detail=_validation_errors(exc)
            ) from exc
        return result

    @app.get("/api/state")
    def get_editor_state():
        return state_module.get_state(app.state.root)

    @app.put("/api/state")
    def put_editor_state(data: dict):
        return state_module.update_state(app.state.root, data)

    @app.get("/api/render/xml")
    def render_xml():
        # The same linker pass + XML emission `define build` runs (xml_emit.py's
        # build_document_tree) - a tree with an unresolved reference or a naming
        # collision fails this exactly like it would fail a real build, not a
        # separately-weaker validation path.
        try:
            data = render_xml_bytes(app.state.root)
        except LinkError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return Response(content=data, media_type="application/xml")

    @app.get("/api/render/stylesheets")
    def render_stylesheets():
        # Every *.xsl in defineyaml/stylesheets/. The frontend shows a picker only
        # when there's more than one; with just the bundled stylesheet the "View
        # define.html" link stays a plain link.
        return [
            {
                "name": name,
                "label": html_render.stylesheet_label(name),
                "default": name == html_render.DEFAULT_STYLESHEET,
            }
            for name in html_render.available_stylesheets()
        ]

    @app.get("/api/render/html")
    def render_html_route(stylesheet: str | None = None):
        try:
            data = html_render.render_html(
                app.state.root, stylesheet or html_render.DEFAULT_STYLESHEET
            )
        except LinkError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(content=data, media_type="text/html")

    # Controlled Terminology + standards lookup (CLAUDE.md §9). Entirely independent of
    # app.state.root - external/local reference data, not something that reads or writes
    # the define/ file tree. The CDISC Library API integration (defineyaml/cdisc/client.py
    # etc.) is dormant: those modules are still in the tree but nothing routes to them.

    # NCI EVS (nci_evs.py) - the primary CT source. One .odm.xml file per (standard,
    # version); version is "current" or a YYYY-MM-DD archived quarterly release. Each is
    # downloaded once and cached on disk indefinitely (a published release never changes).

    @app.get("/api/cdisc/nci-evs/standards")
    def get_nci_evs_standards():
        return [
            {"standard": name, "downloaded": nci_evs.downloaded_versions(name)}
            for name in nci_evs.STANDARDS
        ]

    @app.get("/api/cdisc/nci-evs/{standard}/versions")
    def get_nci_evs_versions(standard: str, force: bool = False):
        _require_nci_standard(standard)
        try:
            return nci_evs.list_available_versions(standard, force=force)
        except nci_evs.NciEvsError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/cdisc/nci-evs/{standard}/download")
    def post_nci_evs_download(
        standard: str, version: str = nci_evs.CURRENT, force: bool = False
    ):
        _require_nci_standard(standard)
        try:
            resolved = nci_evs.resolve_version(standard, version)
            nci_evs.ensure_downloaded(standard, resolved, force=force)
        except nci_evs.NciEvsError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"version": resolved, "cache": nci_evs.cache_info(standard, resolved)}

    @app.post("/api/cdisc/nci-evs/{standard}/save-to-folder")
    def post_nci_evs_save_to_folder(standard: str, version: str = nci_evs.CURRENT):
        # Convert a cached (downloading first if needed) NCI EVS CT release to a
        # DSB-style CT CSV and drop it into this tree's Standards folder, so it
        # scaffolds datasets/codelists like any hand-downloaded export.
        _require_nci_standard(standard)
        try:
            return standard_scaffold.save_nci_evs_ct(app.state.root, standard, version)
        except local_standards.LocalStandardsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except nci_evs.NciEvsError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/api/cdisc/nci-evs/{standard}/codelists")
    def get_nci_evs_codelists(standard: str, version: str = nci_evs.CURRENT):
        _require_nci_standard(standard)
        try:
            return nci_evs.list_codelists(standard, version)
        except nci_evs.NciEvsError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/api/cdisc/nci-evs/{standard}/codelists/{oid}")
    def get_nci_evs_codelist_terms(
        standard: str, oid: str, version: str = nci_evs.CURRENT
    ):
        _require_nci_standard(standard)
        try:
            return nci_evs.get_codelist_terms(standard, version, oid)
        except nci_evs.NciEvsError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Local standards folder - a directory of CDISC CSV exports, scanned/browsed/searched
    # in place. Per-tree: the path is `standards.yaml`'s `standards_folder:` (not a global
    # app setting), resolved by standard_scaffold.resolve_folder against app.state.root.

    def _std_folder():
        try:
            return standard_scaffold.resolve_folder(app.state.root)
        except local_standards.LocalStandardsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/standards/config")
    def get_standards_config():
        return standard_scaffold.folder_status(app.state.root)

    @app.post("/api/standards/config/create-folder")
    def create_standards_folder():
        # Backs the editor's "create the missing folder" button: the path is set in
        # standards.yaml but doesn't exist on disk (a moved/cloned tree, a folder the
        # user hasn't made yet). mkdir -p it, then return the refreshed status.
        try:
            return standard_scaffold.create_folder(app.state.root)
        except local_standards.LocalStandardsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.put("/api/standards/config")
    def put_standards_config(body: dict):
        try:
            return standard_scaffold.set_folder(app.state.root, body.get("folder"))
        except local_standards.LocalStandardsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except tree.NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(
                status_code=422, detail=_validation_errors(exc)
            ) from exc

    @app.get("/api/standards/files")
    def get_standards_files():
        return local_standards.list_files(_std_folder())

    @app.get("/api/standards/file")
    def get_standards_file(
        path: str, q: str | None = None, limit: int = 500, offset: int = 0
    ):
        try:
            return csv_db.read_file(
                app.state.root, _std_folder(), path, q=q, limit=limit, offset=offset
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"no such file: {exc}") from exc
        except local_standards.LocalStandardsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/standards/search")
    def get_standards_search(q: str, limit: int = 200):
        try:
            return csv_db.search(app.state.root, _std_folder(), q, limit=limit)
        except local_standards.LocalStandardsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/standards/raw")
    def get_standards_raw(path: str):
        try:
            target = local_standards.raw_path(_std_folder(), path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"no such file: {exc}") from exc
        except local_standards.LocalStandardsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return FileResponse(target, media_type="text/csv", filename=target.name)

    # Scaffold datasets / codelists from a standards.yaml entry's standards_file
    # (standard_scaffold.py). Writes into app.state.root, unlike the read-only routes
    # above - the same server-orchestrated shape as /copy-variables.

    def _scaffold_call(fn, *args):
        try:
            return fn(app.state.root, *args)
        except tree.NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (
            ValueError,
            standard_csv.StandardCsvError,
            local_standards.LocalStandardsError,
        ) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(
                status_code=422, detail=_validation_errors(exc)
            ) from exc

    @app.get("/api/standards/scaffold/standards")
    def scaffold_standards():
        return standard_scaffold.standards_with_files(app.state.root)

    @app.get("/api/standards/scaffold/units")
    def scaffold_units(standard: str):
        return _scaffold_call(standard_scaffold.standard_units, standard)

    @app.get("/api/standards/scaffold/unit-variables")
    def scaffold_unit_variables(standard: str, unit: str):
        return _scaffold_call(standard_scaffold.standard_unit_variables, standard, unit)

    @app.post("/api/standards/scaffold/dataset")
    def scaffold_dataset(body: dict):
        return _scaffold_call(
            standard_scaffold.create_dataset,
            body.get("standard"),
            body.get("unit"),
            body.get("name"),
            body.get("key"),
        )

    @app.get("/api/standards/scaffold/ig-catalog")
    def scaffold_ig_catalog():
        return _scaffold_call(standard_scaffold.ig_catalog)

    @app.get("/api/standards/scaffold/ig-variables")
    def scaffold_ig_variables(
        standard: str | None = None,
        unit: str | None = None,
        q: str | None = None,
        limit: int = 800,
    ):
        return _scaffold_call(
            standard_scaffold.search_ig_variables,
            standard.split(",") if standard else None,
            unit.split(",") if unit else None,
            q,
            limit,
        )

    @app.get("/api/standards/scaffold/variable-hints")
    def scaffold_variable_hints(dataset: str):
        return _scaffold_call(standard_scaffold.dataset_standard_hints, dataset)

    @app.get("/api/standards/scaffold/ct-codelists")
    def scaffold_ct_codelists(standard: str, q: str | None = None):
        return _scaffold_call(standard_scaffold.list_ct_codelists, standard, q)

    @app.get("/api/standards/scaffold/ct-codelist")
    def scaffold_ct_codelist(name: str | None = None, nci_code: str | None = None):
        return _scaffold_call(standard_scaffold.codelist_reference, name, nci_code)

    @app.get("/api/standards/scaffold/ct-codelist-terms")
    def scaffold_ct_codelist_terms(standard: str, value: str):
        return _scaffold_call(standard_scaffold.ct_codelist_terms, standard, value)

    @app.post("/api/standards/scaffold/codelists")
    def scaffold_codelists(body: dict):
        # `items` (new: {value, name?, codes?}) or `values` (plain strings, still accepted)
        return _scaffold_call(
            standard_scaffold.create_codelists,
            body.get("standard"),
            body.get("items") or body.get("values") or [],
        )

    @app.get("/api/standards/external-dictionaries")
    def external_dictionaries():
        # CT C66788 "CodeList Dictionary Name" values for the ExternalCodeList editor's
        # Dictionary field - from an attached CT CSV if one carries it, else a sample list.
        return _scaffold_call(standard_scaffold.external_dictionary_names)

    @app.get("/api/standards/scaffold/missing-codelists")
    def scaffold_missing_codelists():
        return _scaffold_call(standard_scaffold.missing_referenced_codelists)

    @app.post("/api/standards/scaffold/missing-codelists")
    def scaffold_create_missing_codelists():
        return _scaffold_call(standard_scaffold.create_missing_codelists)

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/cdisc-viewer")
    def cdisc_viewer_page():
        return FileResponse(STATIC_DIR / "cdisc-viewer.html")

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app


def _require_kind(kind: str) -> None:
    if kind not in tree.KIND_SPECS:
        raise HTTPException(status_code=404, detail=f"unknown kind {kind!r}")


def _resolve_browse_start(path: str | None, root: Path | None) -> Path:
    """Where /api/setup/browse opens: an explicit `path` if it's a real directory,
    else the last-used tree's parent, else the user's home directory.
    """
    if path:
        candidate = Path(path).expanduser()
        if candidate.is_dir():
            return candidate.resolve()
    last = editor_config.get_last_tree()
    if last is not None:
        return last.parent
    return Path.home()


def _is_writable(directory: Path) -> bool:
    import os

    return os.access(directory, os.W_OK)


def _tree_label(root: Path) -> dict:
    """A friendly name for a recent tree - study name / protocol from its study.yaml
    if that reads, else just the folder name. Best-effort: a missing or malformed
    study.yaml just yields {"name": <folder>, "protocol": None}.
    """
    name, protocol = root.name, None
    try:
        study = (tree.read_object(root, "study", "study") or {}).get("study") or {}
        name = str(study.get("name") or "") or root.name
        protocol = str(study["protocol_name"]) if study.get("protocol_name") else None
    except Exception:
        pass
    return {"name": name, "protocol": protocol}


def _adopt_tree(app: FastAPI, target: Path) -> dict:
    """Point a running server at `target` (from the launcher flow) and move it to the
    front of the recent list a bare `define` offers.
    """
    resolved = target.resolve()
    csv_db.close_all()  # the old tree's standards.duckdb handle is no longer needed
    app.state.root = resolved
    editor_config.remember_tree(resolved)
    return {"source": str(resolved)}


def _study_fields(body: dict) -> dict:
    """The six fields scaffold_tree needs, from whatever the setup form sent - the
    frontend only asks for a study name and protocol name; the OIDs default off a slug
    of the study name (all overridable if the form sends them explicitly).
    """
    study_name = (body.get("study_name") or "").strip()
    protocol_name = (body.get("protocol_name") or study_name).strip()
    try:
        slug = oidmod.slugify(study_name)
    except ValueError:
        slug = "STUDY"
    return {
        "study_name": study_name,
        "protocol_name": protocol_name,
        "file_oid": (body.get("file_oid") or f"ODM.{slug}").strip(),
        "study_oid": (body.get("study_oid") or f"SDY.{slug}").strip(),
        "metadata_version_oid": (
            body.get("metadata_version_oid") or f"MDV.{slug}"
        ).strip(),
        "metadata_version_name": (
            body.get("metadata_version_name") or study_name or "MDV"
        ).strip(),
    }


def _require_nci_standard(standard: str) -> None:
    if standard not in nci_evs.STANDARDS:
        raise HTTPException(status_code=400, detail=f"unknown standard {standard!r}")


def _validation_errors(exc: ValidationError) -> list[dict]:
    return [
        {"loc": [str(p) for p in e["loc"]], "msg": e["msg"], "type": e["type"]}
        for e in exc.errors()
    ]
