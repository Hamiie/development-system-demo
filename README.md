# Pathmark release hub

This repository hosts the Streamlit download page for Pathmark.

This release is Windows-only while the local app workflow is stabilised.

## Structure

```text
app/
  main.py
  assets/pathmark.png
downloads/
  Pathmark_Local_App_Windows_v0_5_74.zip
supabase/
  migrations/
    20260531000000_create_pathmark_access_tables.sql
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

From v0.5.74, the Supabase access-control schema is versioned in `supabase/migrations/` so a GitHub-linked Supabase project can track the database structure safely. Persistent role management uses Supabase rather than a Google Sheet service-account key. This version prefers Supabase Secret API keys (`sb_secret_...`) rather than legacy JWT-based `service_role` keys.

Supabase is used only for hosted Pathmark access control:

- user email
- role
- status
- last login
- feature flags
- audit logs

It should **not** store Pathmark goals, routines, Google Tasks prompts, calendar blocks, Workspace files, backups, Markdown files, or on-the-go planning entries.

Add these Streamlit secrets when Supabase is configured. New setups should use a Supabase Secret API key from **Settings → API Keys**:

```toml
[supabase]
url = "https://YOUR_PROJECT_ID.supabase.co"
secret_key = "sb_secret_YOUR_SUPABASE_SECRET_API_KEY"
```

`service_role_key` is still accepted as a migration fallback for older projects, but it is not recommended for new setups.

The schema is versioned in `supabase/migrations/20260531000000_create_pathmark_access_tables.sql`. For a new project, either let Supabase apply the migration through the GitHub integration, or run the same SQL manually in the Supabase SQL editor:

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

alter table pathmark_users enable row level security;
alter table pathmark_feature_flags enable row level security;
alter table pathmark_audit_log enable row level security;

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

## v0.5.74 focus

This release adds a versioned Supabase migration structure for the hosted access-control database. The migration creates only the access tables, enables RLS, inserts the default feature flags, and deliberately excludes personal developer rows and secrets. This makes the GitHub-linked Supabase setup safer and easier to reproduce while keeping private data out of the repository.

## Google Sheets On-the-go OAuth checks

Pathmark v0.5.75 adds a safe diagnostics panel in the hosted On-the-go beta tab. The panel shows only non-secret values: whether Google OAuth is configured, the OAuth client ID prefix, the redirect URI, the requested scope, and the Google authorisation endpoint.

For Google Sheets sync, configure the same Google Cloud project used by Streamlit secrets:

```toml
[google_oauth]
client_id = "YOUR_GOOGLE_WEB_CLIENT_ID"
client_secret = "YOUR_GOOGLE_WEB_CLIENT_SECRET"
redirect_uri = "https://pathmark.streamlit.app"
```

Google Cloud checklist:

1. Use an OAuth 2.0 **Web application** client.
2. Add the exact authorised redirect URI: `https://pathmark.streamlit.app`.
3. If the Google Auth Platform app is in Testing, add the developer/beta Google accounts as test users.
4. Add the scope `https://www.googleapis.com/auth/drive.file` under Data Access.
5. Enable both **Google Sheets API** and **Google Drive API** for the same project.

The hosted app requests `drive.file` only. It should create and update user-authorised Pathmark sync files, not read all of a user’s Google Sheets.
