from __future__ import annotations

import json
from pathlib import Path
from datetime import date

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / "downloads"
VERSION_FILE = ROOT / "latest_version.json"
LOCAL_PACKAGE = DOWNLOADS / "Development_System_Local_App_v0_5_15_launcher_v3_with_exe.zip"

st.set_page_config(
    page_title="Development System",
    page_icon="DS",
    layout="centered",
)


def load_version() -> dict:
    if VERSION_FILE.exists():
        return json.loads(VERSION_FILE.read_text(encoding="utf-8"))
    return {"latest_version": "unknown", "release_date": str(date.today()), "notes": []}


def download_bytes(path: Path) -> bytes:
    return path.read_bytes() if path.exists() else b""


version = load_version()

st.title("Development System")
st.caption("A local-first app for goals, routines, tasklists, Markdown, backups, Google Calendar exports, and Google Tasks exports.")

st.info(
    "This page is the update hub. The real app runs locally on your computer so it can work with your own Development folder."
)

col1, col2 = st.columns([1, 1])
with col1:
    st.metric("Latest local app", version.get("latest_version", "unknown"))
with col2:
    st.metric("Release date", version.get("release_date", "unknown"))

st.divider()

st.header("Download the local app")
st.write(
    "Download the Windows package, extract it, then start the local app. The launcher executable shows a progress bar and plain-language status updates, then opens the app in your browser at a local address such as `localhost`."
)

if LOCAL_PACKAGE.exists():
    st.download_button(
        "Download Development System for Windows",
        data=download_bytes(LOCAL_PACKAGE),
        file_name=LOCAL_PACKAGE.name,
        mime="application/zip",
        use_container_width=True,
    )
else:
    st.error("The local app package is missing from the downloads folder in this release hub.")

with st.expander("How to use the local app", expanded=True):
    st.markdown(
        """
1. Download the local app zip.
2. Extract the zip somewhere sensible, such as Documents.
3. Double-click **Start Development System.exe**. If Windows blocks the executable or it does not start, use **Start Development System.cmd** as the fallback.
4. A friendly launcher opens with a progress bar and status updates while it checks Python, prepares the local environment, installs requirements if needed, and opens the app locally in your browser.
5. On first run, choose where your Development folder should live.

The local app can then create and update folders, Markdown files, backups, Google Calendar exports, and Google Tasks CSV exports on your computer.
        """
    )

st.divider()

st.header("Why this is local")
st.write(
    "The hosted page cannot write directly to your Documents or OneDrive folders. The local app can, because it runs on your own computer."
)

st.markdown(
    """
The local app is designed to create and maintain a structure like:

```text
Development/
    00_System/
        DEV_DASHBOARD.md
        SYSTEM_GUIDE.md
        Backups/
    CalendarExports/
    GoogleTasksExports/
    01_Body_And_Stability/
    02_Home_And_Garden/
    03_Making_And_Craft/
    04_Expression_And_Culture/
    05_Work_And_Admin/
    06_Finance/
```

Safety rules:

```text
Creates missing folders only.
Does not delete files.
Does not empty existing folders.
Backs up Markdown before updating it.
Keeps backups local.
```
    """
)

st.divider()

st.header("Updates")
st.write(
    "Return to this page to download newer local app packages. Before updating, create a backup from Settings inside the local app."
)

notes = version.get("notes", [])
if notes:
    st.subheader("Current release notes")
    for note in notes:
        st.write(f"- {note}")

st.divider()
st.caption("Hosted demo/update hub. Local files remain on the user's computer.")
