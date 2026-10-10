#!/usr/bin/env python3
"""
Sheets -> SQLite append pipeline for the seo/ folder.

Library choice: google-auth (AuthorizedSession) hitting the Google Sheets
v4 REST API directly. This avoids requiring gspread or
google-api-python-client, which are not installed in this environment.

Behavior:
  1. Resolve sheet ids:
       a. Read seo/sheet_ids.txt (one per line, '#' comments and blank
          lines skipped).
       b. If that yields nothing, fall back to the Drive API: list all
          files with mimeType='application/vnd.google-apps.spreadsheet'
          whose name contains 'Performance-on-Search'. This makes the
          pipeline self-maintaining -- no manual id tracking needed.
  2. For each sheet id, fetch the 'chart' tab and the 'pages' tab via the
     Sheets v4 API using a service account.
  3. Determine page_url for the sheet:
       - pages tab has exactly 1 data row -> that page URL
       - pages tab empty or >1 rows      -> 'Overall'
  4. Ensure the `chart` table has a `page_url` column (ALTER TABLE ... ADD
     COLUMN if missing). Append-only: never drop/recreate.
  5. Insert chart rows with page_url populated, skipping any row whose
     (date, page_url) already exists in the chart table (idempotent).
  6. Print a per-sheet summary: rows read / inserted / skipped.

Credentials resolution order (env var FIRST, file only for local dev):
  1. $GCP_CREDENTIALS  -- JSON string of the service account key.
  2. $GOOGLE_APPLICATION_CREDENTIALS -- path to a service account JSON.
  3. seo/service_account.json -- local dev fallback next to this script.
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account


HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "sheets_extract.sqlite3"
IDS_PATH = HERE / "sheet_ids.txt"
SA_FALLBACK = HERE / "service_account.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
DRIVE_API = "https://www.googleapis.com/drive/v3/files"

# Name filter used by the Drive fallback. All three Performance-on-Search
# spreadsheets match this substring.
DRIVE_NAME_FILTER = "Performance-on-Search"


def build_credentials():
    """Resolve service account credentials.

    Priority:
      1. GCP_CREDENTIALS env var (JSON string) -- GitHub Actions path.
      2. GOOGLE_APPLICATION_CREDENTIALS env var (file path) -- local dev.
      3. seo/service_account.json (file) -- local dev fallback.
    """
    raw = os.environ.get("GCP_CREDENTIALS")
    if raw:
        info = json.loads(raw)
        return service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )

    env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path and Path(env_path).is_file():
        return service_account.Credentials.from_service_account_file(
            env_path, scopes=SCOPES
        )

    if SA_FALLBACK.is_file():
        return service_account.Credentials.from_service_account_file(
            str(SA_FALLBACK), scopes=SCOPES
        )

    raise SystemExit(
        "No service account credentials found. Set GCP_CREDENTIALS (JSON "
        "string) or GOOGLE_APPLICATION_CREDENTIALS (file path), or place "
        f"service_account.json in {HERE}."
    )


def build_session():
    return AuthorizedSession(build_credentials())


def read_sheet_ids(path):
    """Return sheet ids from a file.

    Each non-comment line may be either a bare sheet id or a
    '<YYYY-MM> <sheet_id>' pair (the format used by sheet_ids.txt).
    We take the last whitespace-separated token so the month prefix is
    stripped and only the sheet id is passed to the Sheets API.
    """
    ids = []
    if not path.is_file():
        return ids
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        ids.append(parts[-1])
    return ids


def discover_sheet_ids(session):
    """Fallback: list Performance-on-Search spreadsheets via Drive API.

    Returns a list of spreadsheet ids. Uses a name-contains filter so it
    keeps working as new monthly spreadsheets are added, as long as they
    follow the 'Performance-on-Search' naming convention.
    """
    params = {
        "q": (
            "mimeType='application/vnd.google-apps.spreadsheet' "
            f"and name contains '{DRIVE_NAME_FILTER}' "
            "and trashed=false"
        ),
        "fields": "files(id,name)",
        "pageSize": "100",
        "orderBy": "name",
    }
    resp = session.get(DRIVE_API, params=params, timeout=60)
    resp.raise_for_status()
    files = resp.json().get("files", [])
    for f in files:
        print(f"[drive] matched: {f.get('name')} -> {f.get('id')}")
    return [f["id"] for f in files if f.get("id")]


def resolve_sheet_ids(session):
    """Resolve sheet ids: file first, Drive fallback if file is empty."""
    ids = read_sheet_ids(IDS_PATH)
    if ids:
        print(f"[ids] using {len(ids)} id(s) from {IDS_PATH.name}")
        return ids
    print(f"[ids] {IDS_PATH.name} empty -- falling back to Drive API")
    ids = discover_sheet_ids(session)
    print(f"[ids] Drive returned {len(ids)} sheet id(s)")
    return ids


def fetch_values(session, sheet_id, tab):
    """Fetch a tab's values via the Sheets v4 API."""
    url = f"{SHEETS_API}/{sheet_id}/values/{tab}"
    resp = session.get(url, timeout=60)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    return resp.json().get("values", [])


def page_url_for_sheet(session, sheet_id):
    """Determine page_url from the 'pages' tab.

    - exactly 1 data row  -> that page URL
    - empty or >1 rows    -> 'Overall'
    """
    values = fetch_values(session, sheet_id, "pages")
    if not values:
        return "Overall"
    # Drop a header row if the first cell looks like a header.
    body = values
    if body and str(body[0][0]).strip().lower() in {"page", "page_url", "url", "pages"}:
        body = body[1:]
    if len(body) == 1 and body[0]:
        return str(body[0][0]).strip() or "Overall"
    return "Overall"


def ensure_page_url_column(conn):
    cur = conn.execute("PRAGMA table_info(chart)")
    cols = [r[1] for r in cur.fetchall()]
    if not cols:
        raise SystemExit("chart table does not exist in the database")
    if "page_url" not in cols:
        conn.execute("ALTER TABLE chart ADD COLUMN page_url TEXT")
        conn.commit()
        print("[db] added page_url column to chart")


def existing_keys(conn):
    cur = conn.execute("SELECT date, page_url FROM chart")
    return {(r[0], r[1]) for r in cur.fetchall()}


def insert_rows(conn, rows, page_url, seen):
    """Insert chart rows for one sheet, skipping (date, page_url) dupes."""
    inserted = 0
    skipped = 0
    for row in rows:
        if not row:
            continue
        date = str(row[0]).strip()
        if not date:
            continue
        key = (date, page_url)
        if key in seen:
            skipped += 1
            continue
        # Remaining columns after date are stored as-is.
        values = row[1:] if len(row) > 1 else []
        cols = ["date", "page_url"] + [f"c{i}" for i in range(len(values))]
        placeholders = ",".join(["?"] * len(cols))
        conn.execute(
            f"INSERT INTO chart ({','.join(cols)}) VALUES ({placeholders})",
            [date, page_url, *values],
        )
        seen.add(key)
        inserted += 1
    conn.commit()
    return inserted, skipped


def main():
    session = build_session()
    sheet_ids = resolve_sheet_ids(session)
    if not sheet_ids:
        print("[ids] no sheet ids resolved -- nothing to do")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS chart (date TEXT, clicks INTEGER, impressions INTEGER, ctr REAL, position REAL, page_url TEXT)')  # table-creation step
    conn.commit()
    try:
        ensure_page_url_column(conn)
        seen = existing_keys(conn)
        total_read = total_inserted = total_skipped = 0
        for sid in sheet_ids:
            page_url = page_url_for_sheet(session, sid)
            rows = fetch_values(session, sid, "chart")
            body = rows[1:] if rows else []
            total_read += len(body)
            ins, skp = insert_rows(conn, body, page_url, seen)
            total_inserted += ins
            total_skipped += skp
            print(
                f"[sheet {sid}] page_url={page_url!r} "
                f"read={len(body)} inserted={ins} skipped={skp}"
            )
        print(
            f"[done] read={total_read} inserted={total_inserted} "
            f"skipped={total_skipped}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
