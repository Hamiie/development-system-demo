# Pathmark release hub

This repository hosts the Streamlit download page for Pathmark.

This release is Windows-only while the local app workflow is stabilised.

## Structure

```text
app/
  main.py
  assets/pathmark.png
downloads/
  Pathmark_Local_App_Windows_v0_5_66.zip
latest_version.json
requirements.txt
.streamlit/config.toml
```

## Installation model

Pathmark separates the replaceable app files from the user's workspace:

```text
Documents\Pathmark            ← app files; replace on update
Documents\Workspace           ← default workspace; keep user projects and exports here
```

The launcher creates or points to the workspace folder on first launch. The workspace is used for area folders, exports, tasklists, backups, and the local database. Users can choose an existing folder if they already have one.


## Hosted login and role setup

Visitors can download Pathmark without logging in. Beta and developer features are hidden unless the user signs in and has an allowed role. Unknown signed-in users default to `standard`.

Developer access should be bootstrapped through Streamlit secrets, not hard-coded into the public repository:

```toml
[pathmark_access]
developer_emails = ["you@example.com"]
```

Optional persistent role management uses a private app-owned role store. This stores access records only: email address, role, status, last login, and update timestamps. It does not contain Pathmark goals, routines, tasks, Workspace files, or on-the-go planning entries.

```toml
[pathmark_access]
developer_emails = ["you@example.com"]
role_store_sheet_id = "YOUR_PRIVATE_ROLE_SHEET_ID"
service_account_json = '''{"type":"service_account", "client_email":"...", "private_key":"..."}'''
```

## On-the-go OAuth setup

The hosted **On the go** tab can work in two modes:

1. CSV download/import, which requires no credentials.
2. User-authorised Google Sheets OAuth, which requires Streamlit secrets for a Google OAuth web client.

Expected Streamlit secrets:

```toml
[google_oauth]
client_id = "..."
client_secret = "..."
redirect_uri = "https://your-pathmark-app.streamlit.app"
```

The Google Cloud OAuth client should be a **Web application** with the Streamlit app URL added as an authorised redirect URI. The requested scope is the narrower Google `drive.file` permission. Private on-the-go entries are written to the Pathmark sync sheet authorised by the signed-in user, not to this public repository.

## Updating a release

1. Replace the Windows package in `downloads/`.
2. Update `latest_version.json`.
3. Keep `app/main.py` aligned with the file name and installation instructions.

Mac support has been removed for now.

## v0.5.68 focus

This release tightens the hosted login and beta-access model before wider testing. Developer bootstrap emails now live in Streamlit secrets rather than source code, beta/developer access requires a verified email claim, and Google Sheets sync is centred on app-created Pathmark sync sheets.


## On-the-go Google Sheets sync

Pathmark uses user-authorised OAuth for Google Sheets sync. The hosted app and desktop app request the narrower Google `drive.file` permission so they can work with the Pathmark sync sheet used by the app, rather than asking for access to every spreadsheet in the user's Google account. CSV import remains available as the safest fallback.


## Hosted login setup

The download homepage remains available without signing in. Beta and developer tools appear only after Streamlit OIDC login is configured in deployment secrets and the signed-in user has the appropriate role. If `[auth]` is not configured, the page shows a visible disabled login control and remains in download-only mode.

Required Streamlit authentication settings include `[auth]` values such as `redirect_uri`, `cookie_secret`, `client_id`, `client_secret`, and `server_metadata_url`. Developer bootstrap emails should be stored under `[pathmark_access]`, not hard-coded in the repository.


## v0.5.68 focus

This release fixes hosted login installation by using `streamlit[auth]` in `requirements.txt`, removes the misleading empty bar above the account panel, and changes the logged-out label from `public` to `download only`.
