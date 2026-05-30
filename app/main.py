from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

try:
    from PIL import Image
except Exception:  # Streamlit can still fall back to a text favicon.
    Image = None

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / "downloads"
VERSION_FILE = ROOT / "latest_version.json"
ICON_PATH = ROOT / "app" / "assets" / "pathmark.png"


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
.hero { padding: 3.2rem 0 2rem 0; }
.eyebrow { display: inline-flex; padding: .42rem .72rem; border-radius: 999px; background: var(--accent-soft); color: var(--accent); font-weight: 760; font-size: .92rem; margin-bottom: 1.1rem; }
.hero h1 { font-size: clamp(3.7rem, 8.2vw, 7.2rem); line-height: .84; margin: 0 0 1rem 0; letter-spacing: -.085em; }
.lead { color: var(--ink); font-size: clamp(1.45rem, 3vw, 2.3rem); line-height: 1.18; max-width: 920px; font-weight: 680; margin: 0; }
.sublead { color: var(--muted); font-size: 1.18rem; max-width: 820px; margin-top: 1.15rem; }
.grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; margin: 1.2rem 0 2rem; }
.card { background: rgba(255,255,255,.88); border: 1px solid var(--line); border-radius: 1.35rem; padding: 1.25rem; box-shadow: 0 14px 34px var(--shadow); }
.card h3 { margin-top: 0; margin-bottom: .55rem; }
.card p { margin-bottom: 0; color: var(--muted); }
.notice { background: #E8F4EA; color: #255833; border: 1px solid #C7E3CC; border-radius: 1rem; padding: 1rem 1.1rem; margin: 1rem 0 1.5rem; }
.path-box { background: #151817; color: #EEE9E0; border-radius: 1.15rem; padding: 1.05rem 1.2rem; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; line-height: 1.65; overflow-x: auto; }
.meta-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; margin: .9rem 0 2.1rem; }
.meta-card { background: rgba(255,255,255,.80); border: 1px solid var(--line); border-radius: 1.25rem; padding: 1rem 1.15rem; box-shadow: 0 10px 26px var(--shadow); }
.meta-label { color: var(--muted); font-size: .92rem; font-weight: 700; margin-bottom: .35rem; }
.meta-value { color: var(--ink); font-size: 1.9rem; line-height: 1.05; font-weight: 780; letter-spacing: -.045em; }
.download-panel { background: rgba(255,255,255,.70); border: 1px solid var(--line); border-radius: 1.25rem; padding: 1rem 1.1rem; margin-bottom: .75rem; }
.download-panel h3 { margin: 0 0 .45rem 0; }
.download-panel p { color: var(--muted); margin-bottom: 0; }
.safe-rule { background: var(--surface-2); border: 1px solid var(--line); border-radius: 1.1rem; padding: 1rem 1.1rem; }
.stDownloadButton button, .stButton button { border-radius: .85rem !important; min-height: 3rem; font-weight: 700 !important; }
[data-testid="stHeader"] { background: transparent; }
@media (max-width: 860px) { .grid-3, .meta-grid { grid-template-columns: 1fr; } }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def load_version() -> dict:
    if VERSION_FILE.exists():
        return json.loads(VERSION_FILE.read_text(encoding="utf-8"))
    return {"app_name": "Pathmark", "version": "unknown", "release_date": "unknown", "notes": []}


def find_windows_package(configured_name: str | None) -> Path | None:
    """Find the Windows package safely.

    The configured filename is used first. If it is missing, the release hub falls
    back to the newest-looking Windows package in downloads/. This prevents the
    public download page from showing a false missing-package warning when only
    the package filename has changed.
    """
    if configured_name:
        configured_path = DOWNLOADS / configured_name
        if configured_path.exists():
            return configured_path

    candidates = sorted(
        DOWNLOADS.glob("Pathmark_Local_App_Windows*.zip"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


version = load_version()
windows_package = find_windows_package(version.get("windows_package", ""))

if ICON_PATH.exists():
    st.image(str(ICON_PATH), width=54)

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
st.markdown(f"""
<div class="meta-grid">
  <div class="meta-card">
    <div class="meta-label">Latest version</div>
    <div class="meta-value">{version.get('version', 'unknown')}</div>
  </div>
  <div class="meta-card">
    <div class="meta-label">Release date</div>
    <div class="meta-value">{version.get('release_date', 'unknown')}</div>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="download-panel">
  <h3>Windows</h3>
  <p>Download the Windows package, extract it, move <strong>Pathmark_app</strong> directly into <strong>Documents</strong>, then run the launcher builder once to create the updated <strong>Pathmark.exe</strong> launcher. The launcher uses the separate <strong>Documents\\Workspace</strong> folder for projects and exports by default, or you can choose an existing workspace folder before opening the app.</p>
</div>
""", unsafe_allow_html=True)

if windows_package is not None:
    st.download_button(
        "Download Pathmark for Windows",
        data=windows_package.read_bytes(),
        file_name=windows_package.name,
        mime="application/zip",
        use_container_width=True,
        key="download_windows",
    )
else:
    st.error("The Windows package is missing from this release hub. Check that a file named Pathmark_Local_App_Windows_v*.zip exists in the downloads folder.")

st.caption("This release is Windows-only for now. Mac package support has been removed while the Windows folder, backup, and update workflow is stabilised.")

st.markdown("""
<div class="notice">Pathmark runs on your computer so it can create tasklists, backups, calendar exports, Google Tasks exports, and planning files in the folder you choose.</div>
""", unsafe_allow_html=True)

st.header("New installation")
st.markdown("""
1. Download the Windows package.
2. Extract the zip file.
3. Move the extracted `Pathmark_app` folder into your Documents folder. Avoid leaving the app in Downloads for normal use.
4. Open `Pathmark_app` and run `build_launcher_exe.bat` once to create `Pathmark.exe`.
5. Open `Pathmark.exe`. Review the workspace field before opening the app. The default workspace is `Documents\\Workspace`, or you can choose an existing folder.
6. This workspace folder is where Pathmark keeps projects, area folders, calendar exports, Google Tasks exports, tasklists, backups, and the local database.
""")

st.header("Updating safely")
st.markdown("""
<div class="safe-rule"><strong>The app folder is replaceable. Your Workspace folder is not.</strong><br>Before updating, open the launcher and choose <strong>Update</strong>. Then replace only the <code>Pathmark_app</code> folder in Documents. Do not replace your <code>Documents\\Workspace</code> folder or the workspace folder you selected.</div>
""", unsafe_allow_html=True)


st.header("Release notes")
for note in version.get("notes", []):
    st.write(f"- {note}")

st.caption("Pathmark release hub. User files stay on the user's computer.")
