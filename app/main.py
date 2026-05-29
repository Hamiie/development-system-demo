from __future__ import annotations

import json
from pathlib import Path
from datetime import date

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / "downloads"
VERSION_FILE = ROOT / "latest_version.json"

st.set_page_config(
    page_title="Clearway",
    page_icon="CW",
    layout="wide",
)

CSS = """
<style>
:root {
    --bg: #F7F6F2;
    --ink: #1F2221;
    --muted: #626966;
    --soft: #848B88;
    --surface: #FFFFFF;
    --surface-2: #EDEBE5;
    --line: #D4D1C8;
    --accent: #3E6E75;
    --accent-2: #496B55;
    --accent-soft: #DCEAE9;
    --warm: #A87A4D;
    --dark: #121514;
    --shadow: rgba(32, 35, 33, 0.10);
}

html, body, [data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at top left, rgba(62,110,117,0.13), transparent 36rem),
        linear-gradient(180deg, #FBFAF7 0%, var(--bg) 100%);
    color: var(--ink);
}

.block-container {
    max-width: 1180px;
    padding-top: 2.4rem;
    padding-bottom: 4rem;
}

h1, h2, h3 {
    letter-spacing: -0.025em;
}

p, li {
    font-size: 1.03rem;
    line-height: 1.65;
}

.hero-wrap {
    display: grid;
    grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
    gap: 2rem;
    align-items: stretch;
    margin-top: 0.5rem;
    margin-bottom: 2.4rem;
}

.eyebrow {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.42rem 0.72rem;
    border-radius: 999px;
    background: var(--accent-soft);
    color: #244F55;
    font-weight: 700;
    font-size: 0.92rem;
    margin-bottom: 1.1rem;
}

.hero h1 {
    font-size: clamp(3rem, 6vw, 5.7rem);
    line-height: 0.95;
    margin: 0 0 1.1rem 0;
    letter-spacing: -0.075em;
}

.hero .lead {
    color: var(--muted);
    font-size: 1.35rem;
    max-width: 780px;
    margin-bottom: 1.5rem;
}

.hero-actions {
    display: flex;
    gap: 0.85rem;
    flex-wrap: wrap;
    align-items: center;
}

.product-panel {
    background: rgba(255,255,255,0.78);
    border: 1px solid var(--line);
    border-radius: 1.7rem;
    padding: 1.2rem;
    box-shadow: 0 18px 40px var(--shadow);
    backdrop-filter: blur(8px);
}

.panel-top {
    background: var(--dark);
    color: #F5F1E8;
    border-radius: 1.25rem;
    padding: 1.25rem;
    min-height: 210px;
}

.panel-top h3 {
    margin-top: 0;
    font-size: 1.45rem;
}

.panel-top p {
    color: #CFC8BE;
    margin-bottom: 1.5rem;
}

.mini-list {
    display: grid;
    gap: 0.55rem;
}

.mini-row {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.72rem 0.85rem;
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 0.8rem;
    font-size: 0.94rem;
}

.panel-bottom {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.8rem;
    margin-top: 0.8rem;
}

.stat-card {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 1rem;
    padding: 1rem;
}

.stat-card span {
    display: block;
    color: var(--soft);
    font-size: 0.86rem;
    margin-bottom: 0.3rem;
}

.stat-card strong {
    font-size: 1.35rem;
}

.notice {
    background: #E8F4EA;
    color: #255833;
    border: 1px solid #C7E3CC;
    border-radius: 1rem;
    padding: 1rem 1.1rem;
    margin: 1rem 0 0 0;
}

.grid-3 {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 1rem;
    margin: 1rem 0 2rem 0;
}

.feature-card {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 1.2rem;
    padding: 1.25rem;
    min-height: 180px;
    box-shadow: 0 10px 26px rgba(32,35,33,0.055);
}

.feature-card h3 {
    margin-top: 0;
    margin-bottom: 0.6rem;
    font-size: 1.2rem;
}

.feature-card p {
    color: var(--muted);
    margin: 0;
}

.path-box {
    background: #151817;
    color: #EEE9E0;
    border-radius: 1.25rem;
    padding: 1.15rem 1.25rem;
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
    line-height: 1.6;
    overflow-x: auto;
    border: 1px solid #323936;
}

.split {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.2rem;
}

.step-card {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 1.25rem;
    padding: 1.25rem;
}

.step-number {
    width: 2.3rem;
    height: 2.3rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    background: var(--accent);
    color: white;
    font-weight: 800;
    margin-bottom: 0.8rem;
}

.safe-rule {
    background: var(--surface-2);
    border: 1px solid var(--line);
    border-radius: 1.25rem;
    padding: 1.2rem;
}

.small-muted {
    color: var(--muted);
    font-size: 0.95rem;
}

.stDownloadButton button, .stButton button {
    border-radius: 0.85rem !important;
    min-height: 3.1rem;
    font-weight: 700 !important;
}

[data-testid="stMetricValue"] {
    font-size: 1.7rem;
}

@media (max-width: 860px) {
    .hero-wrap, .grid-3, .split { grid-template-columns: 1fr; }
    .panel-bottom { grid-template-columns: 1fr; }
}
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)


def load_version() -> dict:
    if VERSION_FILE.exists():
        return json.loads(VERSION_FILE.read_text(encoding="utf-8"))
    return {"latest_version": "unknown", "release_date": str(date.today()), "package_name": "", "notes": []}


def package_path(version: dict) -> Path:
    name = version.get("package_name") or "Clearway_Local_App.zip"
    return DOWNLOADS / name


def download_bytes(path: Path) -> bytes:
    return path.read_bytes() if path.exists() else b""


version = load_version()
local_package = package_path(version)

st.markdown(
    """
<div class="hero-wrap">
  <div class="hero">
    <div class="eyebrow">Local-first planning system</div>
    <h1>Clearway</h1>
    <p class="lead">Create time for healthy routines, reduce friction with useful prompts, and keep meaningful goals moving without losing your local folder system.</p>
  </div>
  <div class="product-panel">
    <div class="panel-top">
      <h3>Your work stays local.</h3>
      <p>Clearway runs in your browser, but the real app lives on your computer so it can write Markdown, backups, tasklists, and Google export files where you choose.</p>
      <div class="mini-list">
        <div class="mini-row"><span>Routines</span><strong>time + prompts</strong></div>
        <div class="mini-row"><span>Goals</span><strong>next actions</strong></div>
        <div class="mini-row"><span>Files</span><strong>Markdown + backups</strong></div>
      </div>
    </div>
    <div class="panel-bottom">
      <div class="stat-card"><span>Latest version</span><strong>{version}</strong></div>
      <div class="stat-card"><span>Release date</span><strong>{release}</strong></div>
    </div>
  </div>
</div>
""".format(version=version.get("latest_version", "unknown").split()[0], release=version.get("release_date", "unknown")),
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="notice">
This page is the release hub. Use it to download or update the local app. The hosted page cannot manage your local files; the downloaded local app does that on your computer.
</div>
""",
    unsafe_allow_html=True,
)

st.header("What Clearway helps with")

st.markdown(
    """
<div class="grid-3">
  <div class="feature-card"><h3>Make time visible</h3><p>Turn routines and goal actions into calendar blocks, tasklists, and local notes so the work has a place to happen.</p></div>
  <div class="feature-card"><h3>Lower the starting cost</h3><p>Create Google Tasks prompts that cue the first step, rather than acting as another vague reminder.</p></div>
  <div class="feature-card"><h3>Keep the system yours</h3><p>Generate Markdown, backups, exports, and folders locally, with the app code kept separate from your persistent files.</p></div>
</div>
""",
    unsafe_allow_html=True,
)

st.header("How the local system is organised")

left, right = st.columns([0.95, 1.05])
with left:
    st.write(
        "Clearway separates replaceable app files from your lasting system files. "
        "When you update, you replace the app. You do not replace your Clearway folder, database, Markdown, backups, or exports."
    )
    st.markdown(
        """
<div class="safe-rule"><strong>The app folder is replaceable.</strong><br>The Clearway folder is not.</div>
""",
        unsafe_allow_html=True,
    )
with right:
    st.markdown(
        """
<div class="path-box">Clearway/
  00_System/
    clearway.db
    Backups/
    Tasklists/
    Google Calendar Exports/
    Google Tasks Exports/
  01_Body_And_Stability/
  02_Home_And_Garden/
  ...
  local_app/   ← replace this when updating</div>
""",
        unsafe_allow_html=True,
    )

st.divider()

st.header("Choose your path")
new_tab, update_tab, learn_tab = st.tabs(["New installation", "Update existing installation", "Understand first"])

with new_tab:
    st.subheader("Install Clearway locally")
    st.write("Use this if Clearway has not been installed on this computer before.")
    if local_package.exists():
        st.download_button(
            "Download Clearway local app source",
            data=download_bytes(local_package),
            file_name=local_package.name,
            mime="application/zip",
            use_container_width=True,
            key="download_new_installation",
        )
    else:
        st.error("The local app package is missing from this release hub.")
    st.markdown(
        """
<div class="split">
  <div class="step-card"><div class="step-number">1</div><h3>Download and extract</h3><p>Download the local app source and extract it somewhere sensible.</p></div>
  <div class="step-card"><div class="step-number">2</div><h3>Build the launcher</h3><p>Run <code>build_launcher_exe.bat</code> before publishing a friend-facing package. Use <code>Start Clearway.cmd</code> as the fallback.</p></div>
  <div class="step-card"><div class="step-number">3</div><h3>Choose a folder</h3><p>On first run, Clearway asks where to keep the local system. The recommended default is Documents\Clearway.</p></div>
  <div class="step-card"><div class="step-number">4</div><h3>Start using it</h3><p>The local app creates missing folders and files only. Existing files are not deleted.</p></div>
</div>
""",
        unsafe_allow_html=True,
    )

with update_tab:
    st.subheader("Update safely")
    st.markdown(
        """
<div class="safe-rule"><strong>Before updating:</strong> open your current local app and create an update backup. Then replace only <code>local_app</code>.</div>
""",
        unsafe_allow_html=True,
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
        st.error("The update package is missing from this release hub.")
    st.markdown(
        """
1. Open your current local app.
2. Go to **Settings → Data safety and updates**.
3. Create an update backup.
4. Close the local app.
5. Download the latest local app source from this page.
6. Replace only the old `local_app` folder.
7. Start Clearway again.
8. Restore from backup only if something has gone wrong.
"""
    )

with learn_tab:
    st.subheader("Why Clearway runs locally")
    st.write(
        "The hosted page is a polished front door, but a cloud app cannot write to your Documents folder or OneDrive. "
        "Clearway's main benefit is local file integration, so the real app runs locally and opens in the browser at localhost."
    )
    st.markdown("### Included in the local app")
    st.markdown(
        """
- Goals and projects with next actions.
- Routines with timed activities and shared repeat patterns.
- Printable tasklists.
- Google Calendar `.ics` exports.
- Google Tasks `.csv` exports and Apps Script setup guide.
- Markdown generation into the chosen Clearway folder.
- Local database backups and restore options.
- Seasonal appearance plus curated theme presets.
"""
    )

st.divider()

st.header("Safety rules")
s1, s2 = st.columns(2)
with s1:
    st.markdown(
        """
<div class="feature-card"><h3>Clearway may</h3><p>Create missing folders, generate Markdown, make backups, and write exports into <code>00_System</code>.</p></div>
""",
        unsafe_allow_html=True,
    )
with s2:
    st.markdown(
        """
<div class="feature-card"><h3>Clearway should not</h3><p>Delete files, empty folders, replace your Clearway folder during updates, or overwrite Markdown without a backup.</p></div>
""",
        unsafe_allow_html=True,
    )

st.divider()

st.header("Release notes")
notes = version.get("notes", [])
if notes:
    for note in notes:
        st.write(f"- {note}")
else:
    st.write("No release notes found.")

st.caption("Clearway release hub. Local files stay on the user's computer.")
