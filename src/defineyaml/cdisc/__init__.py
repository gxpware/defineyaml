"""CDISC Library integration ("smart mode", CLAUDE.md §8 - deferred at the project's
outset, now started). Everything here is read-only lookup against an external API: it
has no bearing on the define/ file tree's own correctness, and nothing in linker.py,
xml_emit.py or xml_import.py depends on any of it. First slice, per the explicit
request that started this package: configure which server to query (the official CDISC
Library, or a sponsor-run proxy), confirm it's reachable, query it, and cache the
result locally for a while - not yet wired into the editor's own field-level
autocomplete/validation, which is the eventual point of having this at all.
"""
