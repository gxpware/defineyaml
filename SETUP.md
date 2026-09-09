# SETUP - development environment & building binaries

## Prerequisites

- **Python 3.12** - pinned in `.python-version`; CI and every release binary use
  the same version. `pyproject.toml` still declares `>=3.11` as the library floor,
  but only 3.12 is exercised.
- **[uv](https://docs.astral.sh/uv/)** - the only tool you need to install by hand.
  It manages the virtualenv, the lockfile, and Python itself.
  ```sh
  curl -LsSf https://astral.sh/uv/install.sh | sh      # macOS / Linux
  # or:  pipx install uv  /  brew install uv  /  winget install astral-sh.uv
  ```
- A C toolchain is **not** required - `lxml`, `pydantic-core` and `duckdb` install as
  wheels on all common platforms.

## Development environment

```sh
git clone <this repo> && cd defineyaml

uv sync --all-extras          # venv + every dependency (runtime, dev, ui)
uv run pre-commit install     # ruff + ruff-format + whitespace hooks on commit
```

`uv sync --all-extras` installs:

| Group | What | Why |
|---|---|---|
| runtime | `ruamel.yaml`, `pydantic`, `lxml`, `typer` | `define build` / `import` / `fmt` / `lint` |
| `ui` extra | `fastapi`, `uvicorn`, `duckdb` | `define edit` (the local web editor) and the CT CSV cache |
| `dev` extra | `pytest`, `pyinstaller` | tests and binary builds |
| `dev` group | `pre-commit` | the commit hooks |

For a runtime-only install (no editor, no build tooling): `uv sync` with no flags
still pulls the `dev` **group** (`pre-commit`); use `uv sync --no-dev` for the leanest
possible tree.

### Everyday commands

```sh
uv run define --help                       # the CLI
uv run define                              # web editor launcher (recent trees / browse / create)
uv run define edit --source path/to/define  # web editor on an explicit tree, 127.0.0.1:8765
uv run pytest                               # 370-odd tests, ~1 min
uv run pytest tests/test_roundtrip.py -q    # the import→build hard gate
uv run pre-commit run --all-files           # lint/format everything now
uvx ruff check src tests                    # ad-hoc lint without the hook
uvx ruff format src tests                   # ad-hoc format
```

The test suite is self-contained: every fixture it needs is committed under
`tests/fixtures/` - the two CDISC example submissions plus XSD tree under
`definexml/`, a small example YAML tree under `define/`, and trimmed CDISC CSV
exports under `cl-dsb/` - so it runs in a fresh clone with nothing else. The CDISC
prose specs (*Define-XML v2.1*, *Analysis Results Metadata v1.0*) are worth keeping
a local copy of for design questions the XSD won't answer, but nothing in the repo
depends on them.

### Editor autocomplete (optional)

The pydantic model exports to JSON Schema. Generate it once and point the YAML
language server at it for autocomplete / inline validation while hand-editing files:

```sh
uv run python -c "import json, defineyaml.models as m; \
  print(json.dumps(m.Dataset.model_json_schema(), indent=2))" > dataset.schema.json
```

then add `# yaml-language-server: $schema=./dataset.schema.json` to a dataset file.

---

## Building OS-specific binaries

The goal (per `CLAUDE.md` §5) is a **single self-contained executable** so a user on a
locked-down CRO laptop can run `define` without getting Python approved by IT.

`pyinstaller` (in the `dev` extra) does this. It does **not** cross-compile - you get
a Linux binary by building on Linux, a macOS binary on macOS, a Windows `.exe` on
Windows. Use a CI matrix or a VM/container per target.

### 1. Entry-point script

PyInstaller needs a plain script to analyse. The repo ships
[`packaging/define_entry.py`](packaging/define_entry.py) - it's two lines:

```python
from defineyaml.cli import main

main()
```

### 2. Build

```sh
uv sync --all-extras     # PyInstaller must see the full dependency tree

uv run pyinstaller \
  --name define \
  --onefile \
  --console \
  --collect-data defineyaml \
  --collect-submodules uvicorn \
  packaging/define_entry.py
```

The binary lands in `dist/define` (`dist/define.exe` on Windows).

Flags that matter:

- **`--collect-data defineyaml`** - bundles the non-Python files the package loads at
  runtime (`webui/static/*.{html,js,css}`, `stylesheets/define2-1.xsl`). Both are
  found via `Path(__file__).parent / …`, which resolves correctly inside the bundle
  *only* if the data is collected into the mirrored `defineyaml/…` layout - which this
  flag does.
- **`--collect-submodules uvicorn`** - uvicorn imports its protocol/loop backends
  lazily by string; without this, `define edit` fails at runtime with a missing
  module. (`fastapi`, `lxml`, `pydantic-core`, `duckdb` are handled by PyInstaller's
  built-in hooks.)
- **`--onefile`** - one executable that unpacks to a temp dir on launch (slightly
  slower cold start). Drop it for a `dist/define/` folder that starts instantly.
- No XSD is bundled: schema validation only runs in the test suite, never in the
  shipped CLI.

### 3. Reproducible builds - commit a `.spec`

A ready-to-use spec lives at [`packaging/define.spec`](packaging/define.spec) - build
from it so options don't drift between machines and CI:

```sh
uv run pyinstaller packaging/define.spec        # run from the repo root
```

```python
# packaging/define.spec
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

a = Analysis(
    ["define_entry.py"],           # PyInstaller resolves this relative to the spec dir
    binaries=[],
    datas=collect_data_files("defineyaml"),
    hiddenimports=collect_submodules("uvicorn"),
    excludes=["pytest", "PyInstaller"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,                    # binaries + datas in EXE(...)  ->  onefile
    a.datas,
    [],
    name="define",
    console=True,
    upx=False,
)
```

### 4. Verify

```sh
./dist/define --help
./dist/define build --source some/define --output /tmp/out.xml
./dist/define edit --source some/define        # then open http://127.0.0.1:8765
```

`define edit` is the real smoke test - it exercises the bundled static assets and the
XSLT stylesheet.

### 5. Per-OS notes

| OS | Watch out for |
|---|---|
| **Linux** | Build the **glibc** binary in `debian:12` (or a `manylinux` container) - the oldest glibc you support; newer distros (Ubuntu, Arch) run it fine because glibc is backward compatible. One binary covers Debian, Ubuntu and Arch. Alpine/musl is **not** built (a glibc PyInstaller executable won't run there); Alpine users install from source, see §7. |
| **macOS** | The binary is unsigned, so Gatekeeper quarantines a downloaded copy - recipients run `xattr -dr com.apple.quarantine ./define` or you `codesign`/notarize. Build separately for `arm64` and `x86_64` (or `--target-arch universal2` on a universal Python). |
| **Windows** | SmartScreen / some AV flag unsigned onefile PyInstaller binaries (the temp-dir self-extraction pattern). Sign the `.exe`, or ship the `--onedir` folder build, which trips fewer heuristics. Use `;` not `:` if you pass `--add-data` manually. The release also wraps `define.exe` in an MSI - see `packaging/windows/define.wxs`. |

### 6. CI/CD

Two workflows under [`.github/workflows/`](.github/workflows/):

Both pin **Python 3.12** (`.python-version`, and `PYTHON_VERSION` in each workflow).

**`ci.yml`** - on every push to `main` and every PR:

- `lint` - `uv run pre-commit run --all-files`, i.e. exactly the hooks in
  `.pre-commit-config.yaml` (`ruff`, `ruff-format`, whitespace/EOF/YAML checks).
- `test` - `uv run pytest` on 3.12, on Linux + macOS + Windows.

**`release.yml`** - on a **published GitHub Release** (or a manual
`workflow_dispatch` for a dry run that builds everything and publishes nothing):

| Job | Runner | Produces |
|---|---|---|
| `linux` (x86_64, aarch64) | `ubuntu-latest` / `ubuntu-24.04-arm`, in a `debian:12` container | `define-linux-<arch>.tar.gz`, `defineyaml_<v>_<arch>.deb` (Debian + Ubuntu), `defineyaml-<v>-<arch>.pkg.tar.zst` (Arch) |
| `macos` (arm64, x86_64) | `macos-14` / `macos-13` | `define-macos-<arch>.tar.gz` |
| `windows` (x86_64) | `windows-latest` | `define-windows-x86_64.zip` (standalone `define.exe`) and `DefineYAML-<v>-x64.msi` (WiX installer) |
| `release` | `ubuntu-latest` | gathers all of the above, writes `SHA256SUMS`, attaches every file to the triggering Release |

The glibc binary is built in `debian:12` (glibc 2.36) so it also runs on older
hosts; a newer-glibc distro (Arch, recent Ubuntu) runs it fine because glibc is
backward compatible. Alpine/musl is not built - a glibc PyInstaller executable
will not run there at all (see §7).

`aarch64` uses the free `ubuntu-24.04-arm` runner (public repos only - private
repos need a paid ARM runner or QEMU).

The MSI (`packaging/windows/define.wxs`, built with the `wix` dotnet tool)
installs `define.exe` to `%ProgramFiles%\DefineYAML` and adds it to the system
`PATH`; `ProductVersion` must be strictly numeric, so any pre-release suffix on
the tag is stripped for the MSI only.

### 7. Linux distribution packages

Built by `release.yml` with **[nfpm](https://nfpm.goreleaser.com/)** from one
config, [`packaging/nfpm.yaml`](packaging/nfpm.yaml). Each package just drops the
self-contained binary at `/usr/bin/define` plus docs under
`/usr/share/doc/defineyaml/` - there are no distro-level runtime dependencies
(the binary bundles its own Python).

| Distro | Artifact | Install |
|---|---|---|
| Debian / Ubuntu | `defineyaml_<v>_<arch>.deb` | `sudo apt install ./defineyaml_<v>_<arch>.deb` |
| Arch (bundled binary) | `defineyaml-<v>-<arch>.pkg.tar.zst` | `sudo pacman -U ./defineyaml-<v>-<arch>.pkg.tar.zst` |
| Arch (AUR, builds from the release) | - | `packaging/PKGBUILD` → `defineyaml-bin`; per release run `updpkgsums` then `makepkg --printsrcinfo > .SRCINFO` |

One `.deb` covers Debian and every supported Ubuntu - it's built against the
`debian:12` glibc and declares no dependencies. `<arch>` is `amd64` or `arm64`.

**Alpine is not packaged.** A glibc PyInstaller binary can't run on musl, and
`duckdb` (needed by the `ui` extra / `define edit`) has no guaranteed musl wheel,
so an Alpine build risks a multi-hour source compile in CI. Alpine users run
`pipx install "defineyaml[ui] @ git+https://github.com/gxpware/defineyaml"` or use
the glibc binary under `gcompat`.

To build a package locally against a binary you already have in `dist/define`:

```sh
VERSION=0.1.0 ARCH=amd64 nfpm package -f packaging/nfpm.yaml -p deb       -t dist/
VERSION=0.1.0 ARCH=amd64 nfpm package -f packaging/nfpm.yaml -p archlinux -t dist/
```

### Troubleshooting

| Symptom | Fix |
|---|---|
| `FileNotFoundError: …/defineyaml/webui/static/index.html` at runtime | `--collect-data defineyaml` was missing, or the entry script imports `defineyaml` before PyInstaller can trace it - keep the entry script minimal. |
| `define edit` → `ModuleNotFoundError: uvicorn.protocols…` | add `--collect-submodules uvicorn`, or `--collect-all uvicorn` as a bigger hammer. |
| `ModuleNotFoundError: fastapi` when running the binary | you built from an env without `--all-extras`; re-run `uv sync --all-extras` first. |
| Binary is large (~45–60 MB onefile) | expected - `lxml` + `duckdb` + `uvicorn` + the CPython runtime. Drop the `ui` extra before building if you only need `build`/`import`/`lint`/`fmt`. |
| macOS: "define" is damaged and can't be opened | quarantine attribute - `xattr -dr com.apple.quarantine ./define`. |
