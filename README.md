# Pathmark release hub

This repository hosts the Streamlit download page for Pathmark.

This release is Windows-only while the local app workflow is stabilised.

## Structure

```text
app/
  main.py
  assets/pathmark.png
downloads/
  Pathmark_Local_App_Windows_v0_5_51.zip
latest_version.json
requirements.txt
.streamlit/config.toml
```

## Installation model

Pathmark separates the replaceable app files from the user's workspace:

```text
Documents\Workspace_app       ← app files; replace on update
Documents\Workspace          ← default workspace; keep user projects and exports here
```

The launcher creates or points to the workspace folder on first launch. The workspace is used for area folders, exports, tasklists, backups, and the local database. Users can choose an existing folder if they already have one.

## Updating a release

1. Replace the Windows package in `downloads/`.
2. Update `latest_version.json`.
3. Keep `app/main.py` aligned with the file name and installation instructions.

Mac support has been removed for now.

## v0.5.51 focus

This release stabilises the Windows setup workflow: Pathmark.exe defaults to Documents\Workspace but lets the user choose an existing workspace before first launch; the app files live directly in Documents\Workspace_app; the homepage instructions no longer show raw HTML or redundant suggested-organisation text.
