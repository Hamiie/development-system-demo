from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / "downloads"
VERSION_FILE = ROOT / "latest_version.json"

st.set_page_config(page_title="Pathmark", page_icon="PM", layout="wide")

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
  --warm: #A66A43;
  --shadow: rgba(31,34,33,.10);
}
html, body, [data-testid="stAppViewContainer"] {
  background: radial-gradient(circle at 12% 0%, rgba(51,78,104,.16), transparent 26rem), radial-gradient(circle at 92% 8%, rgba(122,78,122,.14), transparent 24rem), linear-gradient(180deg, #FBFAF7 0%, var(--bg) 100%);
  color: var(--ink);
}
.block-container { max-width: 1180px; padding-top: 2.2rem; padding-bottom: 4rem; }
h1, h2, h3 { letter-spacing: -0.035em; }
p, li { font-size: 1.02rem; line-height: 1.62; }
.hero { padding: 3.2rem 0 2rem 0; }
.eyebrow { display: inline-flex; padding: .42rem .72rem; border-radius: 999px; background: var(--accent-soft); color: var(--accent); font-weight: 760; font-size: .92rem; margin-bottom: 1.1rem; }
.hero h1 { font-size: clamp(3.7rem, 8.2vw, 7.2rem); line-height: .84; margin: 0 0 1rem 0; letter-spacing: -.085em; }
.lead { color: var(--ink); font-size: clamp(1.45rem, 3vw, 2.3rem); line-height: 1.18; max-width: 920px; font-weight: 680; margin: 0; }
.sublead { color: var(--muted); font-size: 1.18rem; max-width: 820px; margin-top: 1.15rem; }
.hero-actions { margin-top: 1.4rem; display: flex; gap: .8rem; flex-wrap: wrap; }
.grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; margin: 1.2rem 0 2rem; }
.card { background: rgba(255,255,255,.88); border: 1px solid var(--line); border-radius: 1.35rem; padding: 1.25rem; box-shadow: 0 14px 34px var(--shadow); }
.card h3 { margin-top: 0; margin-bottom: .55rem; }
.card p { margin-bottom: 0; color: var(--muted); }
.notice { background: #E8F4EA; color: #255833; border: 1px solid #C7E3CC; border-radius: 1rem; padding: 1rem 1.1rem; margin: 1rem 0 1.5rem; }
.path-box { background: #151817; color: #EEE9E0; border-radius: 1.15rem; padding: 1.05rem 1.2rem; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; line-height: 1.65; overflow-x: auto; }
.download-card { background: rgba(255,255,255,.92); border: 1px solid var(--line); border-radius: 1.3rem; padding: 1.2rem; height: 100%; box-shadow: 0 10px 28px var(--shadow); }
.small { color: var(--muted); font-size: .95rem; }
.safe-rule { background: var(--surface-2); border: 1px solid var(--line); border-radius: 1.1rem; padding: 1rem 1.1rem; }
.stDownloadButton button, .stButton button { border-radius: .85rem !important; min-height: 3rem; font-weight: 700 !important; }
[data-testid="stHeader"] { background: transparent; }
@media (max-width: 860px) { .grid-3 { grid-template-columns: 1fr; } }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def load_version() -> dict:
    if VERSION_FILE.exists():
        return json.loads(VERSION_FILE.read_text(encoding="utf-8"))
    return {"app_name": "Pathmark", "version": "unknown", "release_date": "unknown", "notes": []}


def bytes_for(name: str) -> bytes:
    path = DOWNLOADS / name
    return path.read_bytes() if path.exists() else b""


version = load_version()
windows_name = version.get("windows_package", "")
mac_name = version.get("mac_package", "")

st.markdown("""
<div class="hero">
  <div class="eyebrow">Routines, prompts, and goal progress</div>
  <h1>Pathmark</h1>
  <p class="lead">Make time for routines. Reduce friction with prompts. Keep goals moving.</p>
  <p class="sublead">Pathmark helps you plan goals, recurring routines, tasklists, calendar blocks, and starting prompts in one practical system.</p>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="grid-3">
  <div class="card"><h3>Make time for routines</h3><p>Plan recurring routines and the activities inside them, from exercise and journalling to house resets, study, weekly planning, or creative practice.</p></div>
  <div class="card"><h3>Reduce friction with prompts</h3><p>Create Google Tasks prompts that help you begin. A prompt can tell you the first small action to take and link back to the calendar block it belongs with.</p></div>
  <div class="card"><h3>Keep goals moving</h3><p>Break goals into visible next actions, review what needs attention, and archive work with a short closing review when it reaches an endpoint.</p></div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
Pathmark can group related goals and routines under broad themes and more specific areas, such as **Making and Craft → Pottery** or **Body and Stability → Exercise**. Those groupings can carry through to tasklists, calendar exports, Google Tasks prompts, and planning files.
""")

st.header("Download Pathmark")
st.write(f"Latest version: **{version.get('version', 'unknown')}** · Released **{version.get('release_date', 'unknown')}**")

win_col, mac_col = st.columns(2)
with win_col:
    st.markdown("<div class='download-card'>", unsafe_allow_html=True)
    st.subheader("Windows")
    st.write("Download the Windows package, extract it, then run the launcher builder once to create `Pathmark.exe`.")
    if windows_name and (DOWNLOADS / windows_name).exists():
        st.download_button(
            "Download Pathmark for Windows",
            data=bytes_for(windows_name),
            file_name=windows_name,
            mime="application/zip",
            use_container_width=True,
            key="download_windows",
        )
    else:
        st.error("The Windows package is missing from this release hub.")
    st.caption("If the executable cannot be built, use `Start Pathmark.cmd` as the fallback launcher.")
    st.markdown("</div>", unsafe_allow_html=True)

with mac_col:
    st.markdown("<div class='download-card'>", unsafe_allow_html=True)
    st.subheader("Mac")
    st.write("Download the Mac package, extract it, then open `Start Pathmark.command` from the `local_app` folder.")
    if mac_name and (DOWNLOADS / mac_name).exists():
        st.download_button(
            "Download Pathmark for Mac",
            data=bytes_for(mac_name),
            file_name=mac_name,
            mime="application/zip",
            use_container_width=True,
            key="download_mac",
        )
    else:
        st.error("The Mac package is missing from this release hub.")
    st.caption("The Mac package also includes an optional builder for creating a `Start Pathmark.app` launcher.")
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("""
<div class="notice">Pathmark runs on your computer so it can create tasklists, backups, calendar exports, Google Tasks exports, and planning files in the folder you choose.</div>
""", unsafe_allow_html=True)

st.header("New installation")
st.markdown("""
1. Download the package for your computer.
2. Extract the zip file.
3. Start Pathmark from the extracted folder.
4. On first launch, choose where Pathmark should keep your system.
5. Pathmark creates missing folders and files only. Existing files are not deleted.
""")

st.header("Updating safely")
st.markdown("""
<div class="safe-rule"><strong>The app folder is replaceable. Your Pathmark folder is not.</strong><br>Before updating, open your current local app and create an update backup. Then replace only the <code>local_app</code> folder.</div>
""", unsafe_allow_html=True)

st.header("Suggested organisation")
st.markdown("""
<div class="path-box">Pathmark/
  00_System/
    pathmark.db
    Backups/
    Tasklists/
    Google Calendar Exports/
    Google Tasks Exports/
  01_Body_And_Stability/
  02_Home_And_Garden/
  03_Making_And_Craft/
  ...
  local_app/   ← replace this when updating</div>
""", unsafe_allow_html=True)

st.header("Release notes")
for note in version.get("notes", []):
    st.write(f"- {note}")

st.caption("Pathmark release hub. User files stay on the user's computer.")
