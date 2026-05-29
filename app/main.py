from __future__ import annotations

import json
from pathlib import Path
from datetime import date

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / "downloads"
VERSION_FILE = ROOT / "latest_version.json"

st.set_page_config(
    page_title="Development System",
    page_icon="DS",
    layout="centered",
)


def load_version() -> dict:
    if VERSION_FILE.exists():
        return json.loads(VERSION_FILE.read_text(encoding="utf-8"))
    return {"latest_version": "unknown", "release_date": str(date.today()), "package_name": "", "notes": []}


def package_path(version: dict) -> Path:
    name = version.get("package_name") or "Development_System_Local_App_v0_5_18.zip"
    return DOWNLOADS / name


def download_bytes(path: Path) -> bytes:
    return path.read_bytes() if path.exists() else b""


version = load_version()
local_package = package_path(version)

st.title("Development System")
st.caption("Local-first planning, routines, tasklists, Markdown, backups, Google Calendar exports, and Google Tasks exports.")

st.info(
    "This page is the release hub. The real app runs locally on your computer so it can work with your own Development folder."
)

col1, col2 = st.columns([1, 1])
with col1:
    st.metric("Latest local app", version.get("latest_version", "unknown"))
with col2:
    st.metric("Release date", version.get("release_date", "unknown"))

st.divider()

st.header("Choose your path")
new_tab, update_tab = st.tabs(["New installation", "Update existing installation"])

with new_tab:
    st.subheader("Install the local app")
    st.write(
        "Use this if you have not installed Development System on this computer before. "
        "The downloaded package contains the app files only. On first run, the local app asks where your Development folder should live."
    )
    if local_package.exists():
        st.download_button(
            "Download local app for Windows",
            data=download_bytes(local_package),
            file_name=local_package.name,
            mime="application/zip",
            use_container_width=True,
            key="download_new_installation",
        )
    else:
        st.error("The local app package is missing from the downloads folder in this release hub.")

    with st.expander("First-time setup steps", expanded=True):
        st.markdown(
            """
1. Download the local app zip.
2. Extract the zip.
3. Double-click **Start Development System.exe**. If Windows blocks the executable, use **Start Development System.cmd** as the fallback.
4. The launcher shows progress while it prepares the local Streamlit app.
5. The app opens in your browser at a local address such as `localhost`.
6. On first run, choose where your Development folder should live.

The local app can then create and update local folders, Markdown files, backups, tasklists, Google Calendar exports, and Google Tasks CSV exports.
            """
        )

with update_tab:
    st.subheader("Update an existing local app")
    st.warning(
        "Before updating, open your current local app and create an update backup from Settings. "
        "Then replace only the local_app folder. Do not replace your main Development folder."
    )
    st.markdown(
        """
**The app folder is replaceable. The Development folder is not.**

Your personal data and generated outputs should live outside the replaceable app folder, for example:

```text
Development/
    00_System/
        Backups/
        Google Calendar Exports/
        Google Tasks Exports/
        Tasklists/
    01_Body_And_Stability/
    02_Home_And_Garden/
    ...
```

The update package contains only application files. It should not contain your live database, backups, Markdown folders, calendar exports, Google Tasks exports, tasklists, or area folders.
        """
    )
    if local_package.exists():
        st.download_button(
            "Download latest local app update",
            data=download_bytes(local_package),
            file_name=local_package.name,
            mime="application/zip",
            use_container_width=True,
            key="download_update_package",
        )
    else:
        st.error("The update package is missing from the downloads folder in this release hub.")

    with st.expander("Safe update steps", expanded=True):
        st.markdown(
            """
1. Open the local app you already have installed.
2. Go to **Settings → Data safety and updates**.
3. Click **Create update backup**.
4. Close the local app.
5. Download the latest update from this page.
6. Extract the zip.
7. Replace the old **local_app** folder with the new **local_app** folder.
8. Start the app again.
9. Restore from backup only if something has gone wrong.
            """
        )

st.divider()

st.header("Why the real app runs locally")
st.write(
    "The hosted release hub cannot write directly to your Documents or OneDrive folders. "
    "The local app can, because it runs on your own computer."
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
        Google Calendar Exports/
        Google Tasks Exports/
        Tasklists/
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

st.header("Release notes")
notes = version.get("notes", [])
if notes:
    for note in notes:
        st.write(f"- {note}")
else:
    st.write("No release notes found.")

st.divider()
st.caption("Hosted release hub. Local files remain on the user's computer.")
