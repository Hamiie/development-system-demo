# Pathmark release hub

This repository hosts the Streamlit download page for Pathmark.

This release is Windows-only while the local app workflow is stabilised.

## Structure

```text
app/
  main.py
  assets/pathmark.png
downloads/
  Pathmark_Local_App_Windows_v0_5_71.zip
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

Visitors can download Pathmark without logging in. Beta and developer features are hidden unless the user signs in with Google and has an allowed role. Unknown signed-in users default to `standard`.

The hosted login now uses a Pathmark-managed Google OAuth flow rather than Streamlit `st.login()`. This avoids the Streamlit Authlib route error while still keeping password entry with Google. Pathmark receives the verified Google email claim; it does not collect or store passwords.

Expected Streamlit secrets for hosted login:

```toml
[auth]
client_id = "YOUR_GOOGLE_WEB_CLIENT_ID"
client_secret = "YOUR_GOOGLE_WEB_CLIENT_SECRET"
login_redirect_uri = "https://pathmark.streamlit.app"

[pathmark_access]
developer_emails = ["you@example.com"]
```

For backward compatibility, if `login_redirect_uri` is not provided, Pathmark will use `[google_oauth].redirect_uri` or strip `/oauth2callback` from `[auth].redirect_uri`.

The Google Cloud OAuth client should be a **Web application**. Add this authorised redirect URI for hosted login:

```text
https://pathmark.streamlit.app
```

Developer access should be bootstrapped through Streamlit secrets, not hard-coded into the public repository.

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

Expected Streamlit secrets for Google Sheets sync:

```toml
[google_oauth]
client_id = "YOUR_GOOGLE_WEB_CLIENT_ID"
client_secret = "YOUR_GOOGLE_WEB_CLIENT_SECRET"
redirect_uri = "https://pathmark.streamlit.app"
```

The requested scope is the narrower Google `drive.file` permission. Private on-the-go entries are written to the Pathmark sync sheet authorised by the signed-in user, not to this public repository.

## Updating a release

1. Replace the Windows package in `downloads/`.
2. Update `latest_version.json`.
3. Keep `app/main.py` aligned with the file name and installation instructions.

Mac support has been removed for now.

## v0.5.71 focus

This release replaces Streamlit `st.login()` with a Pathmark-managed Google OAuth login flow, removing the dependency on Streamlit's Authlib auth route. It also removes the unnecessary download-only/status bar from the top of the hosted homepage while keeping beta/developer tools behind verified Google sign-in and role checks.
