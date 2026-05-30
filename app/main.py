from __future__ import annotations

import csv
import io
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    from PIL import Image
except Exception:
    Image = None

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / "downloads"
VERSION_FILE = ROOT / "latest_version.json"
ICON_PATH = ROOT / "app" / "assets" / "pathmark.png"
SYNC_COLUMNS = [
    "sync_id", "status", "record_type", "action", "title", "area_name", "specific_area",
    "details", "calendar_start", "calendar_end", "recurrence", "created_at", "updated_at",
    "imported_at", "source",
]


def page_icon():
    if Image is not None and ICON_PATH.exists():
        try:
            return Image.open(ICON_PATH)
        except Exception:
            pass
    return "PM"


st.set_page_config(page_title="Pathmark", page_icon=page_icon(), layout="wide")

CSS = """
<style>
:root {
  --bg: #F7F6F2;
  --ink: #1F2221;
  --muted: #626966;
  --surface: #FFFFFF;
  --surface-2: #EFEEE8;
  --line: #D8D4CB;
  --accent: #334E68;
  --accent-2: #7A4E7A;
  --accent-soft: #E7EEF4;
  --shadow: rgba(31,34,33,.10);
}
html, body, [data-testid="stAppViewContainer"] {
  background: radial-gradient(circle at 12% 0%, rgba(51,78,104,.16), transparent 26rem), radial-gradient(circle at 92% 8%, rgba(122,78,122,.14), transparent 24rem), linear-gradient(180deg, #FBFAF7 0%, var(--bg) 100%);
  color: var(--ink);
}
.block-container { max-width: 1180px; padding-top: 2.2rem; padding-bottom: 4rem; }
h1, h2, h3 { letter-spacing: -0.035em; }
p, li { font-size: 1.02rem; line-height: 1.62; }
.hero { padding: 2.6rem 0 1.2rem 0; }
.eyebrow { display: inline-flex; padding: .42rem .72rem; border-radius: 999px; background: var(--accent-soft); color: var(--accent); font-weight: 760; font-size: .92rem; margin-bottom: 1.1rem; }
.hero h1 { font-size: clamp(3.7rem, 8.2vw, 7.2rem); line-height: .84; margin: 0 0 1rem 0; letter-spacing: -.085em; }
.lead { color: var(--ink); font-size: clamp(1.28rem, 2.4vw, 1.9rem); line-height: 1.22; max-width: 920px; font-weight: 680; margin: 0; }
.sublead { color: var(--muted); font-size: 1.12rem; max-width: 850px; margin-top: 1rem; }
.grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; margin: 1.2rem 0 2rem; }
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; margin: 1.2rem 0 2rem; }
.card { background: rgba(255,255,255,.88); border: 1px solid var(--line); border-radius: 1.35rem; padding: 1.25rem; box-shadow: 0 14px 34px var(--shadow); }
.card h3 { margin-top: 0; margin-bottom: .55rem; }
.card p { margin-bottom: 0; color: var(--muted); }
.meta-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; margin: .9rem 0 2.1rem; }
.meta-card { background: rgba(255,255,255,.80); border: 1px solid var(--line); border-radius: 1.25rem; padding: 1rem 1.15rem; box-shadow: 0 10px 26px var(--shadow); }
.meta-label { color: var(--muted); font-size: .92rem; font-weight: 700; margin-bottom: .35rem; }
.meta-value { color: var(--ink); font-size: 1.9rem; line-height: 1.05; font-weight: 780; letter-spacing: -.045em; }
.download-panel { background: rgba(255,255,255,.70); border: 1px solid var(--line); border-radius: 1.25rem; padding: 1rem 1.1rem; margin-bottom: .75rem; }
.safe-rule { background: var(--surface-2); border: 1px solid var(--line); border-radius: 1.1rem; padding: 1rem 1.1rem; }
.stDownloadButton button, .stButton button { border-radius: .85rem !important; min-height: 3rem; font-weight: 700 !important; }
[data-testid="stHeader"] { background: transparent; }
@media (max-width: 860px) { .grid-3, .grid-2, .meta-grid { grid-template-columns: 1fr; } }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def load_version() -> dict:
    if VERSION_FILE.exists():
        return json.loads(VERSION_FILE.read_text(encoding="utf-8"))
    return {"app_name": "Pathmark", "version": "unknown", "release_date": "unknown", "notes": []}


def find_windows_package(configured_name: str | None) -> Path | None:
    if configured_name:
        configured_path = DOWNLOADS / configured_name
        if configured_path.exists():
            return configured_path
    candidates = sorted(DOWNLOADS.glob("Pathmark_Local_App_Windows*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def extract_google_sheet_id(value: str) -> str:
    text = (value or "").strip()
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", text)
    if match:
        return match.group(1)
    return text.split("?")[0].strip().strip("/")


def blank_sync_row() -> dict[str, str]:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {key: "" for key in SYNC_COLUMNS} | {
        "sync_id": f"otg-{uuid.uuid4().hex}",
        "status": "pending",
        "action": "create",
        "created_at": now,
        "updated_at": now,
        "source": "streamlit_on_the_go",
    }


def row_to_csv_bytes(row: dict[str, str]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=SYNC_COLUMNS)
    writer.writeheader()
    writer.writerow({key: row.get(key, "") for key in SYNC_COLUMNS})
    return output.getvalue().encode("utf-8")


def append_to_private_sheet(sheet_id: str, row: dict[str, str]) -> tuple[bool, str]:
    """Append a row to pending_changes using a Streamlit service account secret.

    The user must share their sync sheet with the service-account email configured
    in Streamlit secrets. If credentials are not configured, the page falls back to
    a downloadable CSV row that can be imported from the desktop app later.
    """
    sheet_id = extract_google_sheet_id(sheet_id)
    if not sheet_id:
        return False, "No Google Sheet ID was provided."
    try:
        service_info = st.secrets.get("gcp_service_account", None)
    except Exception:
        service_info = None
    if not service_info:
        return False, "No service-account credentials are configured for this hosted app yet."
    try:
        import gspread  # type: ignore
        from google.oauth2.service_account import Credentials  # type: ignore
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        credentials = Credentials.from_service_account_info(dict(service_info), scopes=scopes)
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(sheet_id)
        try:
            worksheet = spreadsheet.worksheet("pending_changes")
        except Exception:
            worksheet = spreadsheet.add_worksheet(title="pending_changes", rows=1000, cols=len(SYNC_COLUMNS))
            worksheet.append_row(SYNC_COLUMNS)
        worksheet.append_row([row.get(col, "") for col in SYNC_COLUMNS], value_input_option="USER_ENTERED")
        return True, "Saved to your Pathmark sync sheet."
    except Exception as exc:
        return False, f"Could not write to the sync sheet: {exc}"


def download_tab() -> None:
    version = load_version()
    windows_package = find_windows_package(version.get("windows_package", ""))
    if ICON_PATH.exists():
        st.image(str(ICON_PATH), width=54)
    st.markdown("""
    <div class="hero">
      <div class="eyebrow">Routines. Prompts. Progress.</div>
      <h1>Pathmark</h1>
      <p class="lead">Make space for goals and routines in your calendar, then export Google Tasks prompts that make the next action easier to start.</p>
      <p class="sublead">Use Pathmark to plan recurring work as calendar blocks, keep related projects grouped in Areas, and generate task prompts that still point back to the goal, routine, or Area they support.</p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("""
    <div class="grid-3">
      <div class="card"><h3>Make time visible</h3><p>Prepare calendar blocks for routines, goals, and project work, then export them as ICS files for Google Calendar.</p></div>
      <div class="card"><h3>Prompt the action</h3><p>Generate Google Tasks prompts alongside calendar exports, so each prompt is easier to understand and edit later.</p></div>
      <div class="card"><h3>Keep work grouped</h3><p>Organise goals, routines, tasklists, exports, and project files under broad Areas in your Workspace.</p></div>
    </div>
    """, unsafe_allow_html=True)
    st.header("Download Pathmark")
    st.markdown(f"""
    <div class="meta-grid">
      <div class="meta-card"><div class="meta-label">Latest version</div><div class="meta-value">{version.get('version', 'unknown')}</div></div>
      <div class="meta-card"><div class="meta-label">Release date</div><div class="meta-value">{version.get('release_date', 'unknown')}</div></div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("""
    <div class="download-panel">
      <h3>Windows app</h3>
      <p>Download the package, extract it, move the extracted <strong>Pathmark</strong> app folder into <strong>Documents</strong>, then run <strong>build_launcher_exe.bat</strong> once. The launcher lets you set the Workspace before opening the app.</p>
    </div>
    """, unsafe_allow_html=True)
    if windows_package is not None:
        st.download_button("Download Pathmark for Windows", data=windows_package.read_bytes(), file_name=windows_package.name, mime="application/zip", use_container_width=True, key="download_windows")
    else:
        st.error("The Windows package is missing from this release hub. Check that a file named Pathmark_Local_App_Windows_v*.zip exists in the downloads folder.")
    st.caption("This release is Windows-only for now. Mac package support has been removed while the Windows workflow is stabilised.")
    st.header("How the folders work")
    st.markdown("""
    <div class="grid-2">
      <div class="card"><h3>App folder</h3><p><strong>Documents\\Pathmark</strong> contains the replaceable app files and launcher. This is the folder you replace when updating.</p></div>
      <div class="card"><h3>Workspace folder</h3><p><strong>Documents\\Workspace</strong> is the default place for your projects, numbered Areas, exports, tasklists, backups, and database. You can choose another Workspace in the launcher.</p></div>
    </div>
    """, unsafe_allow_html=True)
    st.header("Install")
    st.markdown("""
    1. Download the Windows package.
    2. Extract the zip file.
    3. Move the extracted `Pathmark` app folder into your Documents folder.
    4. Open the `Pathmark` app folder and run `build_launcher_exe.bat` once to create `Pathmark.exe`.
    5. Open `Pathmark.exe`, review or change the Workspace field, then open Pathmark.

    The default Workspace is `Documents\\Workspace`. Pathmark will create it if needed, or you can choose an existing folder before opening the app.
    """)
    st.header("Update")
    st.markdown("""
    <div class="safe-rule"><strong>Replace the app folder only.</strong><br>Open <strong>Pathmark.exe</strong> and choose <strong>Check for updates</strong>. Then replace only <code>Documents\\Pathmark</code>. Do not replace <code>Documents\\Workspace</code> or whichever Workspace folder you selected.</div>
    """, unsafe_allow_html=True)
    st.header("Release notes")
    for note in version.get("notes", []):
        st.write(f"- {note}")


def on_the_go_tab() -> None:
    st.header("On the go")
    st.write("Capture a goal idea, routine change, task prompt, or calendar block idea while away from your main Workspace. The desktop app can review and import these updates later.")
    st.info("For the first sync version, the hosted page writes only pending updates. Your desktop Workspace remains the place where changes are reviewed and applied.")
    with st.expander("How to connect a user-owned Google Sheet", expanded=False):
        st.markdown("""
        1. Create a Google Sheet for Pathmark sync.
        2. Add a tab named `pending_changes` with the columns used below.
        3. Share the sheet with the Pathmark service-account email configured for this hosted app, or use the CSV fallback until credentials are configured.
        4. In the desktop app, open **On-the-go Updates** and use the same Sheet URL or ID.
        """)
        st.code(", ".join(SYNC_COLUMNS), language="text")
    sheet_url = st.text_input("Google Sheet URL or ID", help="Use your own Pathmark sync sheet. Private sheet writing requires service-account credentials configured in the hosted app.")
    c1, c2 = st.columns(2)
    with c1:
        record_type = st.selectbox("Update type", ["new_goal", "new_routine", "new_task_prompt", "new_calendar_block", "update_note"])
        title = st.text_input("Title")
        area = st.text_input("Area", placeholder="For example, Body and Stability")
        specific = st.text_input("Specific area", placeholder="For example, Exercise")
    with c2:
        calendar_start = st.text_input("Optional start date/time", placeholder="2026-06-01 09:00")
        calendar_end = st.text_input("Optional end date/time", placeholder="2026-06-01 10:00")
        recurrence = st.text_input("Optional recurrence", placeholder="Weekly, daily, or RRULE text")
    details = st.text_area("Details", height=160)
    row = blank_sync_row()
    row.update({
        "record_type": record_type,
        "title": title.strip(),
        "area_name": area.strip(),
        "specific_area": specific.strip(),
        "details": details.strip(),
        "calendar_start": calendar_start.strip(),
        "calendar_end": calendar_end.strip(),
        "recurrence": recurrence.strip(),
    })
    save_col, dl_col = st.columns(2)
    with save_col:
        if st.button("Save to sync sheet", use_container_width=True):
            if not title.strip():
                st.error("Add a title before saving.")
            else:
                ok, message = append_to_private_sheet(sheet_url, row)
                if ok:
                    st.success(message)
                else:
                    st.warning(message)
                    st.caption("Use the CSV fallback below, or configure the hosted service-account access before using direct sheet writes.")
    with dl_col:
        st.download_button("Download pending update CSV", data=row_to_csv_bytes(row), file_name="pathmark_on_the_go_update.csv", mime="text/csv", use_container_width=True)


tab_download, tab_go = st.tabs(["Download Pathmark", "On the go"])
with tab_download:
    download_tab()
with tab_go:
    on_the_go_tab()

st.caption("Pathmark release hub. User files stay in the user's chosen Workspace; on-the-go updates are only saved to a user-owned sync sheet when configured.")
