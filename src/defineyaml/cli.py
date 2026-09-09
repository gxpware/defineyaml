from __future__ import annotations

from pathlib import Path

import typer

from .lint import run_lint
from .linker import LinkError
from .scaffold import ScaffoldError, scaffold_tree
from .xml_emit import write_define_xml
from .xml_import import ImportError_, import_define_xml

app = typer.Typer(
    name="define",
    help="define.xml v2.1 distributed editor",
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context) -> None:
    """Run with no subcommand: open the web editor to a launcher screen - reopen a
    recently used tree, browse to a folder, or create a new one. Use `define edit`
    for an explicit --source / --host / --port, or `define --help` for the full
    command list.
    """
    if ctx.invoked_subcommand is not None:
        return
    _serve_editor(None, "127.0.0.1", 8765, open_browser=True)


def _serve_editor(
    source: Path | None, host: str, port: int, *, open_browser: bool
) -> None:
    """Start the local editor server. `source` None starts it on the launcher screen -
    the frontend then opens a recent tree, browses to one, or creates one, and the
    server adopts it. A real tree (from `define edit`) is added to the recent list so
    the launcher offers it next time.
    """
    try:
        import uvicorn

        from .webui import config as editor_config
        from .webui.server import create_app
    except ModuleNotFoundError as exc:
        typer.echo(
            "error: the editor needs the 'ui' extra - install with: uv pip install -e '.[ui]'"
        )
        raise typer.Exit(code=1) from exc

    root = source.resolve() if source is not None and source.is_dir() else None
    if root is not None:
        editor_config.remember_tree(root)

    url = f"http://{host}:{port}"
    if open_browser:
        import threading
        import webbrowser

        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    if root is None:
        typer.echo(f"visit {url} to open a recent tree, browse to one, or create one")
    else:
        typer.echo(f"serving {root} at {url}")
    uvicorn.run(create_app(root), host=host, port=port, log_level="warning")


@app.command()
def init(
    destination: Path = typer.Option(
        Path("define"), "--destination", help="Root of the file tree to create"
    ),
) -> None:
    """Scaffold a new define/ file tree (build order step 0, CLAUDE.md §2).

    Creates a subdirectory for every object kind, plus a minimal study.yaml. Prompts
    only for the fields Define-XML actually requires (an ODM file OID, the Study's own
    OID/name/protocol name, and the MetaDataVersion's OID/name) - everything else stays
    hand-editable in study.yaml afterward, same as any other file in the tree.
    """
    if destination.exists():
        typer.echo(f"error: {destination} already exists - refusing to overwrite")
        raise typer.Exit(code=1)

    file_oid = typer.prompt("ODM file OID")
    study_oid = typer.prompt("Study OID")
    study_name = typer.prompt("Study name")
    protocol_name = typer.prompt("Protocol name")
    metadata_version_oid = typer.prompt("MetaDataVersion OID")
    metadata_version_name = typer.prompt("MetaDataVersion name")

    try:
        scaffold_tree(
            destination,
            file_oid=file_oid,
            study_oid=study_oid,
            study_name=study_name,
            protocol_name=protocol_name,
            metadata_version_oid=metadata_version_oid,
            metadata_version_name=metadata_version_name,
        )
    except ScaffoldError as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"created {destination}")


@app.command()
def build(
    source: Path = typer.Option(
        Path("define"), "--source", help="Root of the define/ file tree"
    ),
    output: Path = typer.Option(
        Path("define.xml"), "--output", help="Path to write the generated define.xml"
    ),
) -> None:
    """File tree -> define.xml (build order step 2). Runs the linker pass, then emits XML."""
    try:
        write_define_xml(source, output)
    except LinkError as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"wrote {output}")


@app.command()
def fmt(
    source: Path = typer.Option(
        Path("define"), "--source", help="Root of the define/ file tree to reformat"
    ),
) -> None:
    """Canonical formatting: normalised key order, 2-space indent, consistent quoting. Not yet implemented."""
    typer.echo("fmt: not yet implemented")
    raise typer.Exit(code=1)


@app.command()
def lint(
    source: Path = typer.Option(
        Path("define"), "--source", help="Root of the define/ file tree to lint"
    ),
) -> None:
    """Xref integrity, orphans, and CLAUDE.md's documented conventions (build order step 4)."""
    findings = run_lint(source)
    for finding in findings:
        typer.echo(str(finding))
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    infos = sum(1 for f in findings if f.severity == "info")
    typer.echo(f"{errors} error(s), {warnings} warning(s), {infos} info")
    if errors:
        raise typer.Exit(code=1)


@app.command()
def edit(
    source: Path = typer.Option(
        Path("define"), "--source", help="Root of the define/ file tree to edit"
    ),
    host: str = typer.Option(
        "127.0.0.1", "--host", help="Interface to bind the local editor server to"
    ),
    port: int = typer.Option(
        8765, "--port", help="Port to bind the local editor server to"
    ),
    open_browser: bool = typer.Option(
        True, "--open/--no-open", help="Open the editor in a browser on startup"
    ),
) -> None:
    """Start the local web editor over the define/ file tree."""
    if not source.is_dir():
        typer.echo(
            f"note: {source} is not a directory - opening the launcher "
            "to pick a recent tree, browse to one, or create one"
        )
        source = None
    _serve_editor(source, host, port, open_browser=open_browser)


@app.command(name="import")
def import_(
    define_xml: Path = typer.Argument(
        ..., help="Existing define.xml v2.1 to explode into the file tree"
    ),
    destination: Path = typer.Option(
        Path("define"), "--destination", help="Root of the file tree to write"
    ),
    force_lang_en: bool = typer.Option(
        False,
        "--force-lang-en",
        help="Discard non-English/duplicate TranslatedText instead of hard-failing",
    ),
) -> None:
    """Parse an existing define.xml and explode it into the file tree (build order step 1)."""
    try:
        import_define_xml(define_xml, destination, force_lang_en=force_lang_en)
    except ImportError_ as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"wrote {destination}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
