# **DefineYAML**
### define.xml v2.1 editor - Define, But in YAML (Yet Another Metadata Liability)

*A modern metadata authoring platform for turning one perfectly good XML file into
several hundred perfectly auditable problems.*

---

## What it is

`define.xml` is a deeply nested, namespace-encrusted XML document that a submission
team maintains by hand in a spreadsheet, pastes into a vendor tool, and then argues
about in email. DefineYAML replaces the spreadsheet with a tree of small YAML files -
one per codelist, method, comment, value list - so that:

- **version control actually works.** A one-line change to a derivation is a one-line
  diff in `methods/adsl/trtsdt.yaml` - not a mystery somewhere inside a 40,000-line
  XML file that your reviewer has to `xmllint --format` and eyeball. Each object lives
  in its own file, so `git blame`, `git log -p`, code review, and merge all operate
  at the granularity a human thinks in. Two people editing different codelists don't
  even touch the same file; two people editing the *same* variable get a real,
  legible conflict instead of a corrupted document.
- cross-references are written by **name**, not by a hand-assigned `OID` counter that
  two people always increment to the same number in different branches;
- derivation code lives in a `|` block scalar that `git diff` can actually read,
  instead of one Excel cell with smuggled newlines;
- every object gets a comment explaining *why*, and the comment **never** leaks into
  the generated XML;
- `define build` turns the tree back into a byte-faithful `define.xml`, and
  `define import` goes the other way, so you can adopt this on a submission that
  already exists and bail out later if you hate it.

There's also a local web editor (`define edit`, or just `define` with no arguments -
a launcher to reopen a recent tree, browse to one, or create a new one) and a
define.html preview, because apparently that's the bar now.

## Many hands, one define.xml, zero screaming

A `define.xml` is produced by a crowd of people who would rather not be in the same
room: the CT owner, four statistical programmers, whoever "owns ADSL," a reviewer,
and the person who inherited the SDRG. In the spreadsheet-and-vendor-tool workflow
they take turns holding the file, and the project's status is a description of whose
inbox it is currently sitting in.

DefineYAML makes it a normal software repo instead:

- **Everyone works at once.** The person rewriting a MedDRA codelist and the person
  adding six ADAE variables are editing different files. Git merges that without
  being asked. "Can you send me the latest define" stops being a sentence anyone has
  to say.
- **Every change has a name attached.** `git blame methods/adsl/trtsdt.yaml` tells
  you who last touched that derivation, when, in which commit, alongside which other
  changes, and - commit message permitting - why. That is an audit log you got for
  free, not a 21 CFR Part 11 feature you licensed.
- **Diffs a human can review.** A derivation change is a two-line diff in a fifty-line
  file, in a pull request, with review comments - not a mystery buried in line 31,204
  of an XML document the reviewer has to `xmllint --format` before they can see it.
- **Conflicts are real, or they don't happen.** Two people on different variables:
  clean merge, nobody interrupted. Two people on the *same* variable: a legible
  conflict on those six lines, which is exactly the conversation those two people
  were going to have to have anyway.
- **`define fmt` removes the rest.** One canonical layout - key order, indent,
  quoting - so the only conflicts git ever reports are semantic. (`fmt` is not built
  yet. The badgers 🦡 are digging. It's step 5. We are on step 7. Do not ask.)

The 🦡 badgers regard this as the entire reason the project exists. The 🦝 raccoons
regard "distributed version control for regulatory metadata" as a phrase with too
many words in it and have wandered back to the CT files, one of which is now missing.

**Specs:** [`XMLYAML.md`](XMLYAML.md) (the define.xml ⟷ YAML mapping),
[`LOCALCT.md`](LOCALCT.md) (Controlled Terminology, local-first),
[`CLI.md`](CLI.md) (commands). [`CLAUDE.md`](CLAUDE.md) is the design log - roughly
nine thousand words of decisions nobody asked for.

## "Smart mode" and the CDISC Library API

DefineYAML briefly integrated with the **CDISC Library API** - the official,
member-gated REST service for Controlled Terminology and standards metadata - and it
was a genuinely enriching experience, in the sense that CDISC's revenue was enriched
and our experience was not.

The pitch is beautiful: one canonical, versioned, machine-readable source of truth
for every standard, behind a tidy HATEOAS tree. The reality is that the *interesting*
half of that tree returns `403` unless your organisation holds a paid membership, the
free half is reachable mostly by knowing which undocumented endpoint shape happens to
work this quarter, the API key onboarding involves a portal, and the whole thing
exists to sell you access to spreadsheets that the U.S. government already publishes
for free. It is a masterclass in taking a public good, adding a login page, and
calling the login page "the platform."

So we retired it. The client modules are still in the tree as a small museum exhibit.
In its place:

- **NCI EVS Controlled Terminology** - the *exact same* CDISC CT, published by NCI as
  free, no-key ODM-XML, one file per standard per quarter, back to 2011. Downloaded
  on demand, cached forever, because a shipped quarterly release does not change.
- **A local folder of CDISC CSV exports** - the ones you download by hand from the
  Data Standards Browser and drop in a directory. DefineYAML reads them. It does not
  phone anyone.

Turns out you can have the metadata without the membership. Who knew. (CDISC knew.)

## Install

Grab a self-contained binary from the [Releases](https://github.com/gxpware/defineyaml/releases)
page - no Python needed:

| Platform | Asset |
|---|---|
| Debian / Ubuntu | `defineyaml_<v>_<arch>.deb` → `sudo apt install ./defineyaml_<v>_<arch>.deb` |
| Arch | `defineyaml-<v>-<arch>.pkg.tar.zst` → `sudo pacman -U ./…` |
| Windows | `DefineYAML-<v>-x64.msi` (installer) or `define-windows-x86_64.zip` (standalone) |
| macOS | `define-macos-<arch>.tar.gz` (then `xattr -dr com.apple.quarantine ./define`) |
| Other Linux | `define-linux-<arch>.tar.gz` |

Or from source:

```sh
uv venv
uv pip install -e ".[dev,ui]"
```

Then `uv run define --help`. [`SETUP.md`](SETUP.md) has the full development-environment
setup and how to build a self-contained per-OS binary (so a locked-down CRO laptop can
run `define` without an approved Python).

## Contributing

PRs welcome. Bug reports welcome. Strong opinions about YAML anchor syntax also
welcome, though less likely to be actioned.

This project is maintained by a small nocturnal committee of **badgers 🦡 and
raccoons 🦝**:

- 🦡 the **badgers** do the digging - schema archaeology, XSD edge cases, the
  round-trip test suite, the load-bearing sentence in `CLAUDE.md` you weren't supposed
  to read. A badger has never once been talked out of a business rule it found in an
  errata document. Do not try.
- 🦝 the **raccoons** handle acquisitions (whatever CT files were left unattended on a
  shared drive) and QA, which they perform by knocking things off the counter to see
  what breaks and then filing the resulting stack trace as a feature request.

Division of labour: the badgers 🦡 write the tests, the raccoons 🦝 find out what the
tests didn't cover, usually in production, usually at 2 a.m., usually by touching it.
If your PR is rejected it was probably a 🦝 raccoon, and if it's merged without review
it was definitely a 🦝 raccoon. If it's merged *after* a 400-comment thread about
whether `OrderNumber` should really be positional, that was a 🦡 badger, and it was
right. Be kind to both; they work for scraps.

## Licence

MIT. See [`LICENSE`](LICENSE). Do what you want; don't blame us; the badgers 🦡 are
not liable and the raccoons 🦝 cannot be served.
