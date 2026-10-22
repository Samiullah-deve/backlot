"""The Sheets half of the `google_drive` types comparison: which reads to make, over which corpus.

Which method answers which message is the discovery document's to say (a method's `response`), so
unlike Graph's walk this one names methods, not types. What it has to know is how to make each read
carry everything it can: a grid holding each kind of cell a corpus states, a range that starts past
the first row and column, a second sheet for a grid range to name, and a prose spreadsheet beside
it. A field none of these reads carries is reported missing, which is what the baseline records.
"""

from __future__ import annotations

from typing import Any

import httpx

from backlot.fidelity.errors import FidelityError

CORPUS = [
    {
        "source_type": "google_drive",
        "doc_id": "walk-grid",
        "subtype": "spreadsheet",
        "title": "Walk grid",
        "folder": "walk",
        "author_email": "walker@acme.com",
        "created": "2026-01-10T08:00:00Z",
        "updated": "2026-01-11T08:00:00Z",
        "sheets": [
            {"title": "Data", "grid": [["Region", "Deals", "Won"], ["EMEA", 12, True]]},
            {"title": "More", "grid": [["a", None, "c"], [None, 2.5, False]]},
        ],
    },
    {
        "source_type": "google_drive",
        "doc_id": "walk-prose",
        "subtype": "spreadsheet",
        "title": "Walk prose",
        "folder": "walk",
        "author_email": "walker@acme.com",
        "created": "2026-01-10T08:00:00Z",
        "updated": "2026-01-10T08:00:00Z",
        "content": "month,revenue\nJan,1",
    },
]


def run(timeout: float) -> list[tuple[str, Any]]:
    """Each read as the discovery method it is, with what Backlot answered, as the service account
    so every spreadsheet answers."""
    import backlot

    with backlot.serve(CORPUS, telemetry=False) as server:
        headers = {"Authorization": f"Bearer {server.token}"}
        with httpx.Client(base_url=server.base_url, headers=headers, timeout=timeout) as client:
            return list(_reads(client))


def _reads(client: httpx.Client):
    files = _ok(
        client.get(
            "/drive/v3/files",
            params={"q": "mimeType='application/vnd.google-apps.spreadsheet'", "fields": "*"},
        )
    )["files"]
    for book in (f["id"] for f in files):
        base = f"/sheets/v4/spreadsheets/{book}"
        get = "sheets.spreadsheets.get"
        yield get, _ok(client.get(base, params={"includeGridData": "true"}))
        yield get, _ok(client.get(base, params={"includeGridData": "true", "ranges": "B2:C3"}))
        yield (
            "sheets.spreadsheets.getByDataFilter",
            _ok(
                client.post(
                    f"{base}:getByDataFilter",
                    json={"includeGridData": True, "dataFilters": [{"a1Range": "A1:C2"}]},
                )
            ),
        )
        yield "sheets.spreadsheets.values.get", _ok(client.get(f"{base}/values/A1:C2"))
        yield (
            "sheets.spreadsheets.values.batchGet",
            _ok(client.get(f"{base}/values:batchGet", params={"ranges": ["A1:B2", "B1"]})),
        )
    grid = next(f["id"] for f in files if f["name"] == "Walk grid")
    more = _ok(client.get(f"/sheets/v4/spreadsheets/{grid}"))["sheets"][1]["properties"]["sheetId"]
    yield (
        "sheets.spreadsheets.values.batchGetByDataFilter",
        _ok(
            client.post(
                f"/sheets/v4/spreadsheets/{grid}/values:batchGetByDataFilter",
                json={
                    "dataFilters": [
                        {"a1Range": "Data!A1:B2"},
                        {
                            "gridRange": {
                                "sheetId": more,
                                "startRowIndex": 0,
                                "endRowIndex": 2,
                                "startColumnIndex": 1,
                                "endColumnIndex": 3,
                            }
                        },
                    ]
                },
            )
        ),
    )


def _ok(response: httpx.Response) -> Any:
    if response.status_code != 200:
        raise FidelityError(
            f"Backlot answered {response.status_code} for {response.request.url}: {response.text}"
        )
    return response.json()
