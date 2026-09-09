# PyInstaller onefile build for the `define` CLI.
# Build from the repo root:  uv run pyinstaller packaging/define.spec
# See SETUP.md for the full guide (per-OS notes, CI matrix, troubleshooting).

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

a = Analysis(
    ["define_entry.py"],  # resolved relative to this spec file (packaging/)
    binaries=[],
    # webui/static/*.{html,js,css} and stylesheets/define2-1.xsl - loaded at runtime
    # via Path(__file__).parent, so they must land in the mirrored defineyaml/ layout.
    datas=collect_data_files("defineyaml"),
    # uvicorn imports its protocol/loop backends lazily by string.
    hiddenimports=collect_submodules("uvicorn"),
    excludes=["pytest", "PyInstaller"],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,  # binaries + datas passed into EXE(...) -> onefile
    a.datas,
    [],
    name="define",
    console=True,
    upx=False,
)
