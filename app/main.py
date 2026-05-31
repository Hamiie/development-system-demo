from __future__ import annotations

import csv
import io
import importlib.util
import json
import re
import uuid
import secrets
import hmac
import hashlib
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

try:
    from PIL import Image
except Exception:
    Image = None

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / "downloads"
VERSION_FILE = ROOT / "latest_version.json"
ICON_PATH = ROOT / "app" / "assets" / "pathmark.png"
SYNC_COLUMNS = [
    "sync_id", "status", "record_type", "action", "title", "area_name", "specific_area",
    "details", "calendar_start", "calendar_end", "recurrence", "created_at", "updated_at",
    "imported_at", "source",
]


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
.hero { padding: 2.6rem 0 1.2rem 0; }
.eyebrow { display: inline-flex; padding: .42rem .72rem; border-radius: 999px; background: var(--accent-soft); color: var(--accent); font-weight: 760; font-size: .92rem; margin-bottom: 1.1rem; }
.hero h1 { font-size: clamp(3.7rem, 8.2vw, 7.2rem); line-height: .84; margin: 0 0 1rem 0; letter-spacing: -.085em; }
.lead { color: var(--ink); font-size: clamp(1.28rem, 2.4vw, 1.9rem); line-height: 1.22; max-width: 920px; font-weight: 680; margin: 0; }
.sublead { color: var(--muted); font-size: 1.12rem; max-width: 850px; margin-top: 1rem; }
.grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; margin: 1.2rem 0 2rem; }
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; margin: 1.2rem 0 2rem; }
.card { background: rgba(255,255,255,.88); border: 1px solid var(--line); border-radius: 1.35rem; padding: 1.25rem; box-shadow: 0 14px 34px var(--shadow); }
.card h3 { margin-top: 0; margin-bottom: .55rem; }
.card p { margin-bottom: 0; color: var(--muted); }
.meta-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; margin: .9rem 0 2.1rem; }
.meta-card { background: rgba(255,255,255,.80); border: 1px solid var(--line); border-radius: 1.25rem; padding: 1rem 1.15rem; box-shadow: 0 10px 26px var(--shadow); }
.meta-label { color: var(--muted); font-size: .92rem; font-weight: 700; margin-bottom: .35rem; }
.meta-value { color: var(--ink); font-size: 1.9rem; line-height: 1.05; font-weight: 780; letter-spacing: -.045em; }
.download-panel { background: rgba(255,255,255,.70); border: 1px solid var(--line); border-radius: 1.25rem; padding: 1rem 1.1rem; margin-bottom: .75rem; }
.safe-rule { background: var(--surface-2); border: 1px solid var(--line); border-radius: 1.1rem; padding: 1rem 1.1rem; }
.profile-pill { display: inline-flex; gap: .45rem; align-items: center; padding: .46rem .72rem; border-radius: 999px; background: rgba(255,255,255,.78); border: 1px solid var(--line); color: var(--muted); font-weight: 700; }
.beta-note { background: #FFF8E6; border: 1px solid #E7D49B; border-radius: 1.1rem; padding: 1rem 1.1rem; color: #3B3325; }
.stDownloadButton button, .stButton button { border-radius: .85rem !important; min-height: 3rem; font-weight: 700 !important; }
[data-testid="stHeader"] { background: transparent; }
@media (max-width: 860px) { .grid-3, .grid-2, .meta-grid { grid-template-columns: 1fr; } }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

ROLE_VALUES = ["standard", "beta_tester", "developer"]
STATUS_VALUES = ["active", "disabled"]
ROLE_COLUMNS = ["email", "role", "status", "last_login", "updated_at"]


def _secret_section(name: str):
    try:
        return st.secrets.get(name, {})
    except Exception:
        return {}


def login_config() -> dict[str, str] | None:
    """Return Google login settings for Pathmark's own OIDC flow.

    This deliberately avoids Streamlit's built-in st.login route so the hosted
    page does not depend on the streamlit[auth]/Authlib extra being installed.
    Users still sign in with Google; Pathmark never receives a password.
    """
    auth = _secret_section("auth")
    if not auth:
        return None
    client_id = str(auth.get("client_id", "")).strip()
    client_secret = str(auth.get("client_secret", "")).strip()
    # Prefer an explicit app callback URL. If only the old Streamlit callback is
    # configured, fall back to the app root so this custom flow can complete in
    # Streamlit's normal page code.
    redirect_uri = str(auth.get("login_redirect_uri", "")).strip()
    if not redirect_uri:
        google_cfg = _secret_section("google_oauth")
        redirect_uri = str(google_cfg.get("redirect_uri", "")).strip() if google_cfg else ""
    if not redirect_uri:
        old_uri = str(auth.get("redirect_uri", "")).strip()
        redirect_uri = old_uri[:-len("/oauth2callback")] if old_uri.endswith("/oauth2callback") else old_uri
    if not (client_id and client_secret and redirect_uri):
        return None
    return {"client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri}


def login_configured() -> bool:
    return login_config() is not None

def _user_claim(user: Any, key: str, default: Any = "") -> Any:
    """Read a claim from Streamlit's OIDC user object defensively."""
    try:
        value = getattr(user, key)
        if value is not None:
            return value
    except Exception:
        pass
    try:
        return user.get(key, default)
    except Exception:
        return default


def current_user() -> dict[str, Any]:
    """Return the Google identity stored in this Streamlit session."""
    user = st.session_state.get("pathmark_user")
    if not isinstance(user, dict):
        return {"email": "", "name": "", "email_verified": False}
    email = str(user.get("email", "") or "").strip().lower()
    if not email:
        return {"email": "", "name": "", "email_verified": False}
    return {
        "email": email,
        "name": str(user.get("name", "") or "").strip(),
        "email_verified": bool(user.get("email_verified", False)),
    }


def oauth_state_secret() -> str:
    """Return a stable secret for signing OAuth state values.

    The hosted page cannot rely on Streamlit session_state surviving a full
    external Google redirect in every deployment. Signed state values let
    Pathmark verify that the callback originated from this app without storing
    the state only in the in-memory session.
    """
    auth = _secret_section("auth")
    secret = str(auth.get("cookie_secret", "") or auth.get("client_secret", "")).strip() if auth else ""
    if not secret:
        google_cfg = _secret_section("google_oauth")
        secret = str(google_cfg.get("client_secret", "")).strip() if google_cfg else ""
    return secret or "pathmark-development-only-state-secret"


def make_signed_oauth_state(kind: str) -> str:
    ts = str(int(datetime.now(timezone.utc).timestamp()))
    nonce = secrets.token_urlsafe(24)
    payload = f"{kind}:{ts}:{nonce}"
    sig = hmac.new(oauth_state_secret().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_signed_oauth_state(state: str | None, kind: str, max_age_seconds: int = 900) -> bool:
    if not state:
        return False
    parts = str(state).split(":")
    if len(parts) != 4 or parts[0] != kind:
        return False
    payload = ":".join(parts[:3])
    expected = hmac.new(oauth_state_secret().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, parts[3]):
        return False
    try:
        age = int(datetime.now(timezone.utc).timestamp()) - int(parts[1])
    except Exception:
        return False
    return 0 <= age <= max_age_seconds


def login_auth_url() -> str | None:
    cfg = login_config()
    if not cfg:
        return None
    state = make_signed_oauth_state("login")
    # Also store it in session when possible. The signed value is the fallback
    # used after the browser returns from Google.
    st.session_state["pathmark_login_state"] = state
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def handle_login_redirect() -> bool:
    """Complete Pathmark login when returning from Google.

    Returns True if this callback belonged to the login flow. Google Sheets OAuth
    uses a different state value and is handled separately.
    """
    params = st.query_params
    code = params.get("code")
    state = params.get("state")
    error = params.get("error")
    if isinstance(code, list):
        code = code[0] if code else None
    if isinstance(state, list):
        state = state[0] if state else None
    if isinstance(error, list):
        error = error[0] if error else None
    expected_state = st.session_state.get("pathmark_login_state")
    if not (state and str(state).startswith("login:")):
        return False
    if error:
        st.session_state.pop("pathmark_login_state", None)
        st.query_params.clear()
        st.warning(f"Google login was not completed: {error}")
        return True
    if not code:
        return False
    session_match = bool(expected_state and secrets.compare_digest(str(expected_state), str(state)))
    signed_match = verify_signed_oauth_state(str(state), "login")
    if not (session_match or signed_match):
        st.session_state.pop("pathmark_login_state", None)
        st.query_params.clear()
        st.error("Google login could not be verified. Please try again.")
        return True
    cfg = login_config()
    if not cfg:
        st.session_state.pop("pathmark_login_state", None)
        st.query_params.clear()
        st.error("Google login is not configured yet.")
        return True
    try:
        data = urllib.parse.urlencode({
            "code": code,
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "redirect_uri": cfg["redirect_uri"],
            "grant_type": "authorization_code",
        }).encode("utf-8")
        request = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            token_info = json.loads(response.read().decode("utf-8"))
        raw_id_token = token_info.get("id_token")
        if not raw_id_token:
            raise ValueError("Google did not return an ID token.")
        from google.auth.transport import requests as google_requests  # type: ignore
        from google.oauth2 import id_token as google_id_token  # type: ignore
        claims = google_id_token.verify_oauth2_token(raw_id_token, google_requests.Request(), cfg["client_id"])
        email = str(claims.get("email", "") or "").strip().lower()
        if not email:
            raise ValueError("Google login did not return an email address.")
        email_verified = bool(claims.get("email_verified", False))
        st.session_state["pathmark_user"] = {
            "email": email,
            "name": str(claims.get("name", "") or ""),
            "email_verified": email_verified,
        }
        st.session_state.pop("pathmark_login_state", None)
        st.query_params.clear()
        st.success("Signed in with Google.")
        st.rerun()
        return True
    except Exception as exc:
        st.session_state.pop("pathmark_login_state", None)
        st.query_params.clear()
        st.error(f"Could not complete Google login: {exc}")
        return True

def configured_developer_emails() -> set[str]:
    access = _secret_section("pathmark_access")
    values: list[str] = []
    raw = access.get("developer_emails", []) if access else []
    if isinstance(raw, str):
        values = [item.strip() for item in raw.split(",")]
    elif isinstance(raw, list):
        values = [str(item).strip() for item in raw]
    return {item.lower() for item in values if item}


def role_store_config() -> dict[str, Any] | None:
    """Return optional app-owned role store settings.

    This store is separate from user planning data. If configured, it stores
    only access records: email, role, status, and login/update times.
    """
    access = _secret_section("pathmark_access")
    if not access:
        return None
    sheet_id = str(access.get("role_store_sheet_id", "")).strip()
    sa_json = access.get("service_account_json", "")
    if not sheet_id or not sa_json:
        return None
    return {"sheet_id": sheet_id, "service_account_json": sa_json}


def role_store_client():
    cfg = role_store_config()
    if not cfg:
        return None
    try:
        import gspread  # type: ignore
        raw = cfg["service_account_json"]
        info = json.loads(raw) if isinstance(raw, str) else dict(raw)
        return gspread.service_account_from_dict(info)
    except Exception as exc:
        st.warning(f"Developer role store is not available: {exc}")
        return None


def read_role_records() -> list[dict[str, str]]:
    client = role_store_client()
    cfg = role_store_config()
    if client is None or cfg is None:
        return []
    try:
        sh = client.open_by_key(cfg["sheet_id"])
        try:
            ws = sh.worksheet("users")
        except Exception:
            ws = sh.add_worksheet(title="users", rows=100, cols=len(ROLE_COLUMNS))
            ws.append_row(ROLE_COLUMNS)
        records = ws.get_all_records()
        out: list[dict[str, str]] = []
        for rec in records:
            email = str(rec.get("email", "")).strip().lower()
            if not email:
                continue
            role = str(rec.get("role", "standard")).strip()
            status = str(rec.get("status", "active")).strip()
            out.append({
                "email": email,
                "role": role if role in ROLE_VALUES else "standard",
                "status": status if status in STATUS_VALUES else "active",
                "last_login": str(rec.get("last_login", "")).strip(),
                "updated_at": str(rec.get("updated_at", "")).strip(),
            })
        return out
    except Exception as exc:
        st.warning(f"Could not read developer role store: {exc}")
        return []


def upsert_role_record(email: str, role: str, status: str = "active", update_login: bool = False) -> tuple[bool, str]:
    email = (email or "").strip().lower()
    role = role if role in ROLE_VALUES else "standard"
    status = status if status in STATUS_VALUES else "active"
    if not email or "@" not in email:
        return False, "Enter a valid email address."
    if email in configured_developer_emails() and role != "developer":
        return False, "A developer account listed in Streamlit secrets cannot be downgraded from the hosted UI."
    client = role_store_client()
    cfg = role_store_config()
    if client is None or cfg is None:
        return False, "Persistent role management is not configured yet. Add a private role-store Google Sheet in Streamlit secrets."
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        sh = client.open_by_key(cfg["sheet_id"])
        try:
            ws = sh.worksheet("users")
        except Exception:
            ws = sh.add_worksheet(title="users", rows=100, cols=len(ROLE_COLUMNS))
            ws.append_row(ROLE_COLUMNS)
        values = ws.get_all_values()
        if not values:
            ws.append_row(ROLE_COLUMNS)
            values = [ROLE_COLUMNS]
        if values[0][:len(ROLE_COLUMNS)] != ROLE_COLUMNS:
            ws.update("A1:E1", [ROLE_COLUMNS])
            values[0] = ROLE_COLUMNS
        target_row = None
        for idx, row in enumerate(values[1:], start=2):
            if row and row[0].strip().lower() == email:
                target_row = idx
                break
        existing_last_login = ""
        if target_row:
            current = values[target_row - 1]
            if len(current) >= 4:
                existing_last_login = current[3]
        last_login = now if update_login else existing_last_login
        row_values = [email, role, status, last_login, now]
        if target_row:
            ws.update(f"A{target_row}:E{target_row}", [row_values])
        else:
            ws.append_row(row_values)
        return True, "Role saved."
    except Exception as exc:
        return False, f"Could not update role store: {exc}"


def resolve_role(email: str, email_verified: bool = False) -> tuple[str, str]:
    """Return (role, status), defaulting unknown logged-in users to standard.

    Developer and beta access require a verified email claim from the identity
    provider. This prevents unverified identities from being granted protected
    hosted features.
    """
    email = (email or "").strip().lower()
    if not email:
        return "public", "active"
    if not email_verified:
        return "standard", "active"
    if email in configured_developer_emails():
        return "developer", "active"
    for record in read_role_records():
        if record["email"] == email:
            return record["role"], record["status"]
    return "standard", "active"

def maybe_record_login(email: str, role: str, status: str) -> None:
    if not email or status != "active":
        return
    key = f"login_recorded_{email}"
    if st.session_state.get(key):
        return
    if role_store_config() is not None:
        upsert_role_record(email, role, status, update_login=True)
    st.session_state[key] = True


def render_account_bar(role: str, user: dict[str, str]) -> None:
    """Render minimal account controls without a status bar."""
    configured = login_configured()
    cols = st.columns([3.5, 1.15, 1.15])
    with cols[0]:
        if user.get("email"):
            verified_note = "verified" if user.get("email_verified") else "email not verified"
            st.caption(f"Signed in as {user.get('email')} ({verified_note}). Role: {role}.")
        elif configured:
            st.caption("Sign in with Google to access beta or developer features. You can download Pathmark without signing in.")
        else:
            st.caption("Login is not configured yet. Download Pathmark below.")
    with cols[1]:
        if user.get("email"):
            st.markdown(f"<span class='profile-pill'>{role}</span>", unsafe_allow_html=True)
    with cols[2]:
        if user.get("email"):
            if st.button("Log out", use_container_width=True):
                st.session_state.pop("pathmark_user", None)
                st.session_state.pop("pathmark_login_state", None)
                st.rerun()
        elif configured:
            auth_url = login_auth_url()
            if auth_url:
                st.link_button("Log in with Google", auth_url, use_container_width=True)
            else:
                st.button("Log in unavailable", use_container_width=True, disabled=True)
        else:
            st.button("Log in not configured", use_container_width=True, disabled=True)

def role_can_use_on_the_go(role: str, status: str) -> bool:
    return status == "active" and role in {"beta_tester", "developer"}


def role_can_develop(role: str, status: str) -> bool:
    return status == "active" and role == "developer"


def row_to_csv_bytes(row: dict[str, str]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=SYNC_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerow({col: row.get(col, "") for col in SYNC_COLUMNS})
    return buffer.getvalue().encode("utf-8")


def load_version() -> dict:
    if VERSION_FILE.exists():
        return json.loads(VERSION_FILE.read_text(encoding="utf-8"))
    return {"app_name": "Pathmark", "version": "unknown", "release_date": "unknown", "notes": []}


def find_windows_package(configured_name: str | None) -> Path | None:
    if configured_name:
        configured_path = DOWNLOADS / configured_name
        if configured_path.exists():
            return configured_path
    candidates = sorted(DOWNLOADS.glob("Pathmark_Local_App_Windows*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def extract_google_sheet_id(value: str) -> str:
    text = (value or "").strip()
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", text)
    if match:
        return match.group(1)
    return text.split("?")[0].strip().strip("/")


def blank_sync_row() -> dict[str, str]:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {key: "" for key in SYNC_COLUMNS} | {
        "sync_id": f"otg-{uuid.uuid4().hex}",
        "status": "pending",
        "action": "create",
        "created_at": now,
        "updated_at": now,
        "source": "streamlit_on_the_go",
    }




GOOGLE_SHEETS_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def google_oauth_config() -> dict[str, Any] | None:
    """Return a Google OAuth web-client config from Streamlit secrets when configured.

    Expected secrets format:

    [google_oauth]
    client_id = "..."
    client_secret = "..."
    redirect_uri = "https://your-app.streamlit.app"
    """
    try:
        cfg = st.secrets.get("google_oauth", None)
    except Exception:
        cfg = None
    if not cfg:
        return None
    client_id = str(cfg.get("client_id", "")).strip()
    client_secret = str(cfg.get("client_secret", "")).strip()
    redirect_uri = str(cfg.get("redirect_uri", "")).strip()
    if not (client_id and client_secret and redirect_uri):
        return None
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "client_config": {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
    }


def web_oauth_available() -> bool:
    return google_oauth_config() is not None


def google_credentials_from_session():
    """Return short-lived Google credentials stored only in Streamlit session state.

    The hosted page deliberately avoids requesting offline access. If the access
    token expires, the user reconnects rather than Pathmark storing a refresh
    token on the hosted app.
    """
    raw = st.session_state.get("google_sheets_credentials")
    if not raw:
        return None
    try:
        from google.oauth2.credentials import Credentials  # type: ignore
        credentials = Credentials.from_authorized_user_info(json.loads(raw), GOOGLE_SHEETS_SCOPES)
        if credentials.expired:
            st.session_state.pop("google_sheets_credentials", None)
            return None
        return credentials if credentials and credentials.valid else None
    except Exception:
        st.session_state.pop("google_sheets_credentials", None)
        return None


def revoke_google_session_token() -> None:
    raw = st.session_state.get("google_sheets_credentials")
    token = ""
    try:
        if raw:
            token = json.loads(raw).get("token", "")
    except Exception:
        token = ""
    if token:
        try:
            data = urllib.parse.urlencode({"token": token}).encode("utf-8")
            urllib.request.urlopen("https://oauth2.googleapis.com/revoke", data=data, timeout=5)
        except Exception:
            pass
    st.session_state.pop("google_sheets_credentials", None)
    st.session_state.pop("sync_sheet_id", None)
    st.session_state.pop("google_oauth_state", None)

def handle_google_oauth_redirect() -> None:
    """Complete OAuth callback only when the returned state matches exactly."""
    cfg = google_oauth_config()
    if not cfg:
        return
    params = st.query_params
    code = params.get("code")
    state = params.get("state")
    error = params.get("error")
    if isinstance(code, list):
        code = code[0] if code else None
    if isinstance(state, list):
        state = state[0] if state else None
    if isinstance(error, list):
        error = error[0] if error else None
    if error:
        st.warning(f"Google authorisation was not completed: {error}")
        st.query_params.clear()
        return
    if not code:
        return
    expected_state = st.session_state.get("google_oauth_state")
    # Only handle callbacks that were started by Pathmark's Google Sheets connector.
    if not (state and str(state).startswith("sheets:")):
        return
    session_match = bool(expected_state and secrets.compare_digest(str(expected_state), str(state)))
    signed_match = verify_signed_oauth_state(str(state), "sheets")
    if not (session_match or signed_match):
        st.session_state.pop("google_oauth_state", None)
        st.query_params.clear()
        st.error("Google authorisation could not be verified. Please reconnect from the On the go tab.")
        return
    try:
        from google_auth_oauthlib.flow import Flow  # type: ignore
        flow = Flow.from_client_config(cfg["client_config"], scopes=GOOGLE_SHEETS_SCOPES, redirect_uri=cfg["redirect_uri"])
        flow.fetch_token(code=code)
        # Do not keep a refresh token in the hosted app session.
        cred_info = json.loads(flow.credentials.to_json())
        cred_info.pop("refresh_token", None)
        st.session_state["google_sheets_credentials"] = json.dumps(cred_info)
        st.session_state.pop("google_oauth_state", None)
        st.query_params.clear()
        st.success("Google Sheets is connected for this session.")
    except Exception as exc:
        st.session_state.pop("google_oauth_state", None)
        st.query_params.clear()
        st.warning(f"Could not complete Google authorisation: {exc}")

def google_auth_url() -> str | None:
    cfg = google_oauth_config()
    if not cfg:
        return None
    try:
        from google_auth_oauthlib.flow import Flow  # type: ignore
        flow = Flow.from_client_config(cfg["client_config"], scopes=GOOGLE_SHEETS_SCOPES, redirect_uri=cfg["redirect_uri"])
        state_seed = make_signed_oauth_state("sheets")
        auth_url, state = flow.authorization_url(
            access_type="online",
            include_granted_scopes="true",
            prompt="select_account",
            state=state_seed,
        )
        st.session_state["google_oauth_state"] = state
        return auth_url
    except Exception as exc:
        st.warning(f"Could not prepare Google authorisation: {exc}")
        return None

def sheets_service():
    credentials = google_credentials_from_session()
    if not credentials:
        return None
    try:
        from googleapiclient.discovery import build  # type: ignore
        return build("sheets", "v4", credentials=credentials, cache_discovery=False)
    except Exception as exc:
        st.warning(f"Could not connect to Google Sheets: {exc}")
        return None


def ensure_pending_changes_sheet(service: Any, sheet_id: str) -> None:
    metadata = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    sheet_titles = [sheet.get("properties", {}).get("title") for sheet in metadata.get("sheets", [])]
    if "pending_changes" not in sheet_titles:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": "pending_changes"}}}]},
        ).execute()
    values = service.spreadsheets().values().get(spreadsheetId=sheet_id, range="pending_changes!1:1").execute().get("values", [])
    if not values or values[0] != SYNC_COLUMNS:
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"pending_changes!A1:{chr(64 + len(SYNC_COLUMNS))}1",
            valueInputOption="RAW",
            body={"values": [SYNC_COLUMNS]},
        ).execute()


def create_user_sync_sheet() -> tuple[bool, str, str]:
    service = sheets_service()
    if service is None:
        return False, "", "Connect Google Sheets first."
    try:
        spreadsheet = service.spreadsheets().create(
            body={
                "properties": {"title": "Pathmark Sync"},
                "sheets": [{"properties": {"title": "pending_changes"}}],
            },
            fields="spreadsheetId,spreadsheetUrl",
        ).execute()
        sheet_id = spreadsheet.get("spreadsheetId", "")
        ensure_pending_changes_sheet(service, sheet_id)
        st.session_state["sync_sheet_id"] = sheet_id
        return True, sheet_id, spreadsheet.get("spreadsheetUrl", "")
    except Exception as exc:
        return False, "", f"Could not create a Pathmark sync sheet: {exc}"


def append_to_user_oauth_sheet(sheet_id: str, row: dict[str, str]) -> tuple[bool, str]:
    sheet_id = extract_google_sheet_id(sheet_id)
    if not sheet_id:
        return False, "No Google Sheet ID was provided."
    service = sheets_service()
    if service is None:
        return False, "Connect Google Sheets before saving to a sync sheet."
    try:
        ensure_pending_changes_sheet(service, sheet_id)
        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range="pending_changes!A:O",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [[row.get(col, "") for col in SYNC_COLUMNS]]},
        ).execute()
        st.session_state["sync_sheet_id"] = sheet_id
        return True, "Saved to your Google Sheet."
    except Exception as exc:
        return False, f"Could not write to the sync sheet: {exc}"

def download_tab() -> None:
    version = load_version()
    windows_package = find_windows_package(version.get("windows_package", ""))
    if ICON_PATH.exists():
        st.image(str(ICON_PATH), width=54)
    st.markdown("""
    <div class="hero">
      <div class="eyebrow">Routines. Prompts. Progress.</div>
      <h1>Pathmark</h1>
      <p class="lead">Make space for goals and routines in your calendar, then export Google Tasks prompts that make the next action easier to start.</p>
      <p class="sublead">Use Pathmark to plan recurring work as calendar blocks, keep related projects grouped in Areas, and generate task prompts that still point back to the goal, routine, or Area they support.</p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("""
    <div class="grid-3">
      <div class="card"><h3>Make time visible</h3><p>Prepare calendar blocks for routines, goals, and project work, then export them as ICS files for Google Calendar.</p></div>
      <div class="card"><h3>Prompt the action</h3><p>Generate Google Tasks prompts alongside calendar exports, so each prompt is easier to understand and edit later.</p></div>
      <div class="card"><h3>Keep work grouped</h3><p>Organise goals, routines, tasklists, exports, and project files under broad Areas in your Workspace.</p></div>
    </div>
    """, unsafe_allow_html=True)
    st.header("Download Pathmark")
    st.markdown(f"""
    <div class="meta-grid">
      <div class="meta-card"><div class="meta-label">Latest version</div><div class="meta-value">{version.get('version', 'unknown')}</div></div>
      <div class="meta-card"><div class="meta-label">Release date</div><div class="meta-value">{version.get('release_date', 'unknown')}</div></div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("""
    <div class="download-panel">
      <h3>Windows app</h3>
      <p>Download the package, extract it, move the extracted <strong>Pathmark</strong> app folder into <strong>Documents</strong>, then run <strong>build_launcher_exe.bat</strong> once. The launcher lets you set the Workspace before opening the app.</p>
    </div>
    """, unsafe_allow_html=True)
    if windows_package is not None:
        st.download_button("Download Pathmark for Windows", data=windows_package.read_bytes(), file_name=windows_package.name, mime="application/zip", use_container_width=True, key="download_windows")
    else:
        st.error("The Windows package is missing from this release hub. Check that a file named Pathmark_Local_App_Windows_v*.zip exists in the downloads folder.")
    st.caption("This release is Windows-only for now. Mac package support has been removed while the Windows workflow is stabilised.")
    st.header("How the folders work")
    st.markdown("""
    <div class="grid-2">
      <div class="card"><h3>App folder</h3><p><strong>Documents\\Pathmark</strong> contains the replaceable app files and launcher. This is the folder you replace when updating.</p></div>
      <div class="card"><h3>Workspace folder</h3><p><strong>Documents\\Workspace</strong> is the default place for your projects, numbered Areas, exports, tasklists, backups, and database. You can choose another Workspace in the launcher.</p></div>
    </div>
    """, unsafe_allow_html=True)
    st.header("Install")
    st.markdown("""
    1. Download the Windows package.
    2. Extract the zip file.
    3. Move the extracted `Pathmark` app folder into your Documents folder.
    4. Open the `Pathmark` app folder and run `build_launcher_exe.bat` once to create `Pathmark.exe`.
    5. Open `Pathmark.exe`, review or change the Workspace field, then open Pathmark.

    The default Workspace is `Documents\\Workspace`. Pathmark will create it if needed, or you can choose an existing folder before opening the app.
    """)
    st.header("Update")
    st.markdown("""
    <div class="safe-rule"><strong>Replace the app folder only.</strong><br>Open <strong>Pathmark.exe</strong> and choose <strong>Check for updates</strong>. Then replace only <code>Documents\\Pathmark</code>. Do not replace <code>Documents\\Workspace</code> or whichever Workspace folder you selected.</div>
    """, unsafe_allow_html=True)
    st.header("Release notes")
    for note in version.get("notes", []):
        st.write(f"- {note}")



def on_the_go_tab() -> None:
    handle_google_oauth_redirect()
    st.header("On the go beta")
    st.markdown("<div class='beta-note'><strong>Beta feature.</strong> Capture goal ideas, routine changes, task prompts, or calendar block ideas while away from your main Workspace. The desktop app can review and import these updates later. Do not use this for sensitive information during testing.</div>", unsafe_allow_html=True)

    with st.expander("How on-the-go updates work", expanded=False):
        st.markdown("""
        **CSV mode** keeps everything offline until you import the file into desktop Pathmark.

        **Google Sheets mode** uses your own Google account and the narrow Google `drive.file` permission. For the safest workflow, create the Pathmark sync sheet from this page and use that sheet for on-the-go captures. Pathmark does not ask for access to all of your Google Sheets and it does not store your entries in this hosted app.
        """)

    st.subheader("1. Choose where to save this capture")
    auth_ready = web_oauth_available()
    credentials = google_credentials_from_session()
    if not auth_ready:
        st.info("Google Sheets OAuth is not configured on this hosted deployment yet. Use the CSV download workflow below.")
    else:
        if credentials:
            st.success("Google Sheets is connected for this session.")
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("Create Pathmark sync sheet", use_container_width=True):
                    ok, sheet_id, message = create_user_sync_sheet()
                    if ok:
                        st.success("Created Pathmark Sync sheet.")
                        st.link_button("Open sync sheet", message, use_container_width=True)
                    else:
                        st.warning(message)
            with c2:
                current_sheet = st.session_state.get("sync_sheet_id", "")
                if current_sheet:
                    st.link_button("Open current sync sheet", f"https://docs.google.com/spreadsheets/d/{current_sheet}", use_container_width=True)
            with c3:
                if st.button("Disconnect", use_container_width=True):
                    revoke_google_session_token()
                    st.rerun()
            if not st.session_state.get("sync_sheet_id"):
                st.info("Create a Pathmark sync sheet above before saving captures to Google Sheets, or use the CSV download below.")
        else:
            auth_url = google_auth_url()
            if auth_url:
                st.link_button("Connect Google Sheets", auth_url, use_container_width=True)
            st.caption("You will be asked by Google to allow Pathmark to create and update the specific Google Drive files used by this app. Access is kept for this browser session only.")

    with st.expander("Advanced: use an existing Pathmark sync sheet", expanded=False):
        sheet_url_input = st.text_input("Google Sheet URL or ID", value=st.session_state.get("sync_sheet_id", ""), help="Use a Pathmark sync sheet that belongs to your Google account. With the safer drive.file permission, Pathmark can only use files it created or files you have explicitly opened with the app.")
        if sheet_url_input:
            st.session_state["sync_sheet_id"] = extract_google_sheet_id(sheet_url_input)
    sheet_url = st.session_state.get("sync_sheet_id", "")

    st.subheader("2. Capture the update")
    c1, c2 = st.columns(2)
    with c1:
        record_type = st.selectbox("Update type", ["new_goal", "new_routine", "new_task_prompt", "new_calendar_block", "update_note"])
        title = st.text_input("Title")
        area = st.text_input("Area", placeholder="For example, Body and Stability")
        specific = st.text_input("Specific area", placeholder="For example, Exercise")
    with c2:
        calendar_start = st.text_input("Optional start date/time", placeholder="2026-06-01 09:00")
        calendar_end = st.text_input("Optional end date/time", placeholder="2026-06-01 10:00")
        recurrence = st.text_input("Optional recurrence", placeholder="Weekly, daily, or RRULE text")
    details = st.text_area("Details", height=160)
    row = blank_sync_row()
    row.update({
        "record_type": record_type,
        "title": title.strip(),
        "area_name": area.strip(),
        "specific_area": specific.strip(),
        "details": details.strip(),
        "calendar_start": calendar_start.strip(),
        "calendar_end": calendar_end.strip(),
        "recurrence": recurrence.strip(),
    })

    st.subheader("3. Save for desktop review")
    save_col, dl_col = st.columns(2)
    with save_col:
        disabled = not bool(credentials and st.session_state.get("sync_sheet_id"))
        if st.button("Save to my Pathmark sync sheet", use_container_width=True, disabled=disabled):
            if not title.strip():
                st.error("Add a title before saving.")
            else:
                ok, message = append_to_user_oauth_sheet(sheet_url, row)
                if ok:
                    st.success(message)
                else:
                    st.warning(message)
        if disabled:
            st.caption("Connect Google Sheets and create/select a Pathmark sync sheet first, or use the CSV download.")
    with dl_col:
        st.download_button("Download pending update CSV", data=row_to_csv_bytes(row), file_name="pathmark_on_the_go_update.csv", mime="text/csv", use_container_width=True)

def developer_tab() -> None:
    st.header("Developer settings")
    st.write("Manage hosted access roles for beta features. Unknown signed-in users default to standard access.")
    st.markdown("""
    Roles:
    - **standard**: download homepage only.
    - **beta_tester**: On-the-go beta access.
    - **developer**: beta access plus this developer panel.
    """)
    if role_store_config() is None:
        st.info("Persistent role management is not configured yet. Developer access must be bootstrapped from Streamlit secrets, and role assignments cannot be saved until a private role-store Google Sheet is configured.")
        with st.expander("Role store setup", expanded=False):
            st.markdown("""
            Configure a private app-owned role store in Streamlit secrets. This stores access records only: email address, role, status, last login, and update timestamps. It does not contain Pathmark goals, routines, tasks, Workspace files, or on-the-go planning entries.

            ```toml
            [pathmark_access]
            developer_emails = ["you@example.com"]
            role_store_sheet_id = "YOUR_PRIVATE_ROLE_SHEET_ID"
            service_account_json = '''{"type":"service_account", "client_email":"...", "private_key":"..."}'''
            ```

            The role sheet should be private and shared only with the service-account email. Pathmark will create or update a `users` worksheet with columns: `email`, `role`, `status`, `last_login`, `updated_at`.
            """)
    records = read_role_records()
    if records:
        st.subheader("Current role records")
        st.dataframe(pd.DataFrame(records), use_container_width=True, hide_index=True)
    else:
        st.caption("No role records found. Initial developer emails are still treated as developer accounts.")

    st.subheader("Assign or update a user role")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        email = st.text_input("User email").strip().lower()
    with c2:
        role = st.selectbox("Role", ROLE_VALUES, index=0)
    with c3:
        status = st.selectbox("Status", STATUS_VALUES, index=0)
    if st.button("Save user access", use_container_width=True):
        ok, msg = upsert_role_record(email, role, status)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.warning(msg)


def render_app() -> None:
    # Complete Google login before Google Sheets OAuth handles its own callback.
    handle_login_redirect()
    user = current_user()
    role, status = resolve_role(user.get("email", ""), bool(user.get("email_verified", False)))
    maybe_record_login(user.get("email", ""), role, status)
    render_account_bar(role, user)
    if status == "disabled":
        st.error("This account has been disabled for the hosted Pathmark page.")
        return

    tabs = ["Download Pathmark"]
    if role_can_use_on_the_go(role, status):
        tabs.append("On the go beta")
    if role_can_develop(role, status):
        tabs.append("Developer")
    created_tabs = st.tabs(tabs)
    with created_tabs[0]:
        download_tab()
    idx = 1
    if role_can_use_on_the_go(role, status):
        with created_tabs[idx]:
            on_the_go_tab()
        idx += 1
    if role_can_develop(role, status):
        with created_tabs[idx]:
            developer_tab()


render_app()

st.caption("Pathmark release hub. Beta and developer tools are visible only to signed-in accounts with a verified email and the appropriate role. On-the-go entries are saved only to a downloaded CSV or to the Pathmark sync sheet authorised by the user with the drive.file scope.")
