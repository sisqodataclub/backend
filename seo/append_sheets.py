#!/usr/bin/env python3
"""
Sheets -> SQLite append pipeline for the seo/ folder.

Library choice: google-auth (AuthorizedSession) hitting the Google Sheets
v4 REST API directly. This avoids requiring gspread or
google-api-python-client, which are not installed in this environment.

Behavior:
  1. Read sheet ids from seo/sheet_ids.txt (one per line, '#' comments and
     blank lines skipped).
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

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"


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
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if not parts:
            continue
        ids.append(parts[-1])
    return ids


def _tab_name_variants(tab_name):
    """Yield plausible casings for a tab name.

    The Sheets API is case-sensitive on tab names but the exact casing
    returned by the API can differ from what callers assume. We try the
    requested name first, then common variants (Title Case, lower, upper).
    """
    seen = set()
    for cand in (tab_name, tab_name.capitalize(), tab_name.lower(),
                 tab_name.upper(), tab_name.title()):
        if cand and cand not in seen:
            seen.add(cand)
            yield cand


def fetch_tab(session, sheet_id, tab_name):
    """Return list of rows (list of lists) for a tab, or [] if missing.

    Tries the requested tab name first, then casing variants, so a
    mismatch like 'chart' vs 'Chart' does not silently return zero rows.
    """
    for cand in _tab_name_variants(tab_name):
        rng = f"'{cand}'!A:Z"
        url = f"{SHEETS_API}/{sheet_id}/values/{rng}"
        resp = session.get(url, params={"majorDimension": "ROWS"})
        if resp.status_code in (400, 404):
            continue
        resp.raise_for_status()
        payload = resp.json()
        values = payload.get("values", []) or []
        if values:
            print(f"  tab '{cand}': {len(values)} rows")
            return values
        # Tab exists but is empty; keep trying variants in case another
        # casing is the populated one.
    return []


def normalize_header(row):
    return [str(c).strip().lower() for c in row]


def extract_chart_rows(rows):
    """Return list of dicts with date, clicks, impressions, ctr, position."""
    if not rows:
        return []
    header = normalize_header(rows[0])
    try:
        idx = {name: header.index(name) for name in
               ("date", "clicks", "impressions", "ctr", "position")}
    except ValueError:
        return []
    out = []
    for r in rows[1:]:
        if not r or all((c is None or str(c).strip() == "") for c in r):
            continue

        def get(name):
            i = idx[name]
            return r[i] if i < len(r) else ""

        out.append({
            "date": get("date"),
            "clicks": get("clicks"),
            "impressions": get("impressions"),
            "ctr": get("ctr"),
            "position": get("position"),
        })
    return out


def extract_pages(rows):
    """Return list of page URLs from the pages tab (excluding header)."""
    if not rows:
        return []
    header = normalize_header(rows[0])
    candidates = ["top_pages", "page url", "page_url", "page", "url", "pages"]
    col = None
    for c in candidates:
        if c in header:
            col = header.index(c)
            break
    if col is None:
        col = 0
    out = []
    for r in rows[1:]:
        if not r or col >= len(r):
            continue
        val = r[col]
        if isinstance(val, str):
            val = val.strip()
        if val:
            out.append(str(val))
    return out


def determine_page_url(pages):
    if len(pages) == 1:
        return pages[0]
    return "Overall"


def ensure_page_url_column(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(chart)")
    cols = [row[1] for row in cur.fetchall()]
    if "page_url" not in cols:
        cur.execute("ALTER TABLE chart ADD COLUMN page_url TEXT")
        conn.commit()
        return True
    return False


def existing_keys(conn):
    cur = conn.cursor()
    cur.execute("SELECT date, page_url FROM chart")
    return {(row[0], row[1]) for row in cur.fetchall()}


def append_rows(conn, chart_rows, page_url):
    cur = conn.cursor()
    seen = existing_keys(conn)
    inserted = 0
    skipped = 0
    for row in chart_rows:
        key = (row["date"], page_url)
        if key in seen:
            skipped += 1
            continue
        cur.execute(
            "INSERT INTO chart (date, clicks, impressions, ctr, position, "
            "page_url) VALUES (?, ?, ?, ?, ?, ?)",
            (row["date"], row["clicks"], row["impressions"],
             row["ctr"], row["position"], page_url),
        )
        seen.add(key)
        inserted += 1
    conn.commit()
    return inserted, skipped


def main():
    sheet_ids = read_sheet_ids(IDS_PATH)
    if not sheet_ids:
        print(f"No sheet ids found in {IDS_PATH}")
        return 0

    session = build_session()
    conn = sqlite3.connect(str(DB_PATH))
    try:
        added = ensure_page_url_column(conn)
        if added:
            print("Migration: added page_url column to chart table.")
        else:
            print("Migration: page_url column already present.")

        total_in = total_ins = total_skip = 0
        for sid in sheet_ids:
            chart_raw = fetch_tab(session, sid, "chart")
            pages_raw = fetch_tab(session, sid, "pages")
            chart_rows = extract_chart_rows(chart_raw)
            pages = extract_pages(pages_raw)
            page_url = determine_page_url(pages)
            ins, skip = append_rows(conn, chart_rows, page_url)
            print(
                f"sheet={sid} page_url={page_url!r} "
                f"rows_read={len(chart_rows)} rows_inserted={ins} "
                f"rows_skipped_duplicates={skip}"
            )
            total_in += len(chart_rows)
            total_ins += ins
            total_skip += skip
        print(
            f"TOTAL rows_read={total_in} rows_inserted={total_ins} "
            f"rows_skipped_duplicates={total_skip}"
        )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
