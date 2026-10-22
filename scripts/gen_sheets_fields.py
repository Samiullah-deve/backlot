#!/usr/bin/env python3
"""Regenerate backlot/data/sheets_fields.json from the Sheets v4 discovery document.

    python scripts/gen_sheets_fields.py            # rewrite the file
    python scripts/gen_sheets_fields.py --check    # exit 1 if the file is stale, 2 if unreadable

The file holds every message a Sheets read answers with, from the four ``ROOTS`` down through each
``$ref``, as the fields it declares: a field names the message it holds, or is ``null`` for a
scalar, an enum, a list of lists and a map. ``backlot.routers.google`` checks a ``fields`` mask
against it. A map is a leaf because real refuses a key under one: measured 2026-10-22,
``sheets.filterViews.criteria`` answered 200 and ``sheets.filterViews.criteria.foo`` the 400 naming
that path. `.github/workflows/fidelity.yml` runs ``--check`` on its schedule, which is where a
change to the document shows.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from backlot.fidelity.errors import FidelityError  # noqa: E402
from backlot.fidelity.fetch import fetch_json  # noqa: E402

OUT = REPO / "backlot" / "data" / "sheets_fields.json"
DOCUMENT = "https://sheets.googleapis.com/$discovery/rest?version=v4"
# What `spreadsheets.get` and `:getByDataFilter`, `values.get`, `values:batchGet` and
# `values:batchGetByDataFilter` answer with.
ROOTS = (
    "Spreadsheet",
    "ValueRange",
    "BatchGetValuesResponse",
    "BatchGetValuesByDataFilterResponse",
)


def _ref(prop: dict) -> str | None:
    """The message a field holds, itself or in a list; ``None`` for anything else."""
    if "$ref" in prop:
        return prop["$ref"]
    items = prop.get("items")
    if isinstance(items, dict) and "$ref" in items:
        return items["$ref"]
    return None


def build(document: dict | None = None) -> dict:
    schemas = (document or fetch_json(DOCUMENT)).get("schemas")
    if not isinstance(schemas, dict) or not all(r in schemas for r in ROOTS):
        raise FidelityError(f"{DOCUMENT} declares no {', '.join(ROOTS)}")
    out: dict[str, dict] = {}
    todo = list(ROOTS)
    while todo:
        name = todo.pop()
        if name in out:
            continue
        fields = {f: _ref(p) for f, p in (schemas[name].get("properties") or {}).items()}
        out[name] = dict(sorted(fields.items()))
        todo += [r for r in fields.values() if r]
    return {
        "about": (
            "The fields each message a Sheets read answers with declares. Written by "
            "scripts/gen_sheets_fields.py; do not edit by hand."
        ),
        "document": DOCUMENT,
        "schemas": dict(sorted(out.items())),
    }


def render(table: dict) -> str:
    return json.dumps(table, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if the file is stale")
    args = parser.parse_args()
    try:
        text = render(build())
    except FidelityError as e:
        # 2, as `backlot diff` exits for a document it could not ask for: not a finding
        print(e, file=sys.stderr)
        return 2
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT.relative_to(REPO)} is stale; run scripts/gen_sheets_fields.py")
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)}: {len(json.loads(text)['schemas'])} messages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
