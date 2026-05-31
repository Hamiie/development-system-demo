# Pathmark release hub

This repository hosts the Streamlit download page for Pathmark.

This release is Windows-only while the local app workflow is stabilised.

## Structure

```text
app/
  main.py
  assets/pathmark.png
downloads/
  Pathmark_Local_App_Windows_v0_5_72.zip
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

The hosted login uses a Pathmark-managed Google OAuth flow rather than Streamlit `st.login()`. This avoids the Streamlit Authlib route issue while still keeping password entry with Google. Pathmark receives the verified Google email claim; it does not collect or store passwords.

Expected Streamlit secrets for hosted login:

```toml
[auth]
client_id = "YOUR_GOOGLE_WEB_CLIENT_ID"
client_secret = "YOUR_GOOGLE_WEB_CLIENT_SECRET"
login_redirect_uri = "https://pathmark.streamlit.app"
cookie_secret = "A_LONG_RANDOM_SECRET_USED_TO_SIGN_OAUTH_STATE"

[pathmark_access]
developer_emails = ["you@example.com"]
# Optional fallback while Supabase is being configured:
beta_tester_emails = []
disabled_emails = []
```

For backward compatibility, if `login_redirect_uri` is not provided, Pathmark will use `[google_oauth].redirect_uri` or strip `/oauth2callback` from `[auth].redirect_uri`.

The Google Cloud OAuth client should be a **Web application**. Add this authorised redirect URI for hosted login:

```text
https://pathmark.streamlit.app
```

Developer access should be bootstrapped through Streamlit secrets, not hard-coded into the public repository.

## Supabase access layer

From v0.5.72, persistent role management is designed to use Supabase rather than a Google Sheet service-account key.

Supabase is used only for hosted Pathmark access control:

- user email
- role
- status
- last login
- feature flags
- audit logs

It should **not** store Pathmark goals, routines, Google Tasks prompts, calendar blocks, Workspace files, backups, Markdown files, or on-the-go planning entries.

Add these Streamlit secrets when Supabase is configured:

```toml
[supabase]
url = "https://YOUR_PROJECT_ID.supabase.co"
service_role_key = "YOUR_SUPABASE_SERVICE_ROLE_KEY"
```

Then run this SQL in the Supabase SQL editor:

```sql
create table if not exists pathmark_users (
  email text primary key,
  role text not null default 'standard' check (role in ('standard', 'beta_tester', 'developer')),
  status text not null default 'active' check (status in ('active', 'disabled')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_login timestamptz,
  notes text
);

create table if not exists pathmark_feature_flags (
  key text primary key,
  enabled boolean not null default true,
  minimum_role text not null default 'standard' check (minimum_role in ('standard', 'beta_tester', 'developer')),
  updated_at timestamptz not null default now(),
  notes text
);

create table if not exists pathmark_audit_log (
  id uuid primary key default gen_random_uuid(),
  actor_email text,
  action text not null,
  target_email text,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

insert into pathmark_feature_flags (key, enabled, minimum_role, notes)
values
  ('on_the_go_beta', true, 'beta_tester', 'Shows the On-the-go beta tab.'),
  ('developer_panel', true, 'developer', 'Shows the Developer settings tab.')
on conflict (key) do nothing;
```

Keep `[pathmark_access].developer_emails` in Streamlit secrets as an emergency bootstrap route even after Supabase is configured.

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

## v0.5.72 focus

This release introduces the Supabase access layer for hosted role management, feature flags, and audit logs. It removes the Google Sheet service-account role-store model while preserving Google login, Streamlit-secret bootstrap developer access, and user-owned Google Sheets for on-the-go sync.
