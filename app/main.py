from __future__ import annotations

import csv
import json
import calendar as py_calendar
import os
import re
import shutil
import sqlite3
import sys
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import streamlit as st

try:
    from PIL import Image
except Exception:
    Image = None
import yaml
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

APP_TITLE = "Pathmark Local App v0.5.47"
APP_VERSION = "v0.5.53-local"
ROOT = Path(__file__).resolve().parents[1]
OLD_DATA_DIR = ROOT / "data"
OLD_DB_PATH = OLD_DATA_DIR / "development_system.db"
LEGACY_SYSTEM_DB_NAME = "development_system.db"
CONFIG_DIR = ROOT / "config"
def default_workspace_folder() -> Path:
    """Return the best default Documents\\Pathmark location for this Windows user."""
    candidates: list[Path] = []
    for key in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        value = os.environ.get(key)
        if value:
            candidates.append(Path(value) / "Documents" / "Workspace")
    candidates.append(Path.home() / "OneDrive" / "Documents" / "Workspace")
    candidates.append(Path.home() / "Documents" / "Workspace")
    for candidate in candidates:
        try:
            if candidate.parent.exists():
                return candidate
        except Exception:
            pass
    return Path.home() / "Documents" / "Workspace"


def default_development_root() -> Path:
    """Suggest a user-specific Pathmark workspace without hard-coded personal paths.

    The replaceable application folder may live in Downloads, Desktop, or another
    temporary location. User data and exports should not default to that location.
    The Windows launcher passes PATHMARK_ROOT after the user has chosen their
    workspace on first launch; that value takes priority. Only when the app is
    installed inside a folder literally named Pathmark do we treat that parent
    folder as the persistent project root; otherwise the default is the user's
    Documents\\Workspace folder.
    """
    env_root = os.environ.get("PATHMARK_ROOT", "").strip()
    if env_root:
        return Path(env_root).expanduser()
    try:
        if ROOT.name.lower() in ("pathmark", "local_app") and ROOT.parent.name.lower() == "pathmark" and ROOT.parent.exists():
            return ROOT.parent
    except Exception:
        pass
    return default_workspace_folder()



def launcher_initial_theme_preset() -> str:
    value = os.environ.get("PATHMARK_INITIAL_THEME_PRESET", "Default").strip() or "Default"
    if value == "Pathmark":
        value = "Default"
    return value if value in ["Default", "Seasonal", "Persimmon", "Marigold", "Moss", "Lagoon", "Iris", "Rosewood", "Custom"] else "Default"


def launcher_initial_theme_mode() -> str:
    value = os.environ.get("PATHMARK_INITIAL_THEME_MODE", "Light").strip() or "Light"
    return value if value in ["Light", "Dark"] else "Light"


def launcher_root_supplied() -> bool:
    return bool(os.environ.get("PATHMARK_ROOT", "").strip())


def launcher_theme_sync_requested() -> bool:
    return os.environ.get("PATHMARK_SYNC_THEME_FROM_LAUNCHER", "").strip() == "1"


def launcher_config_path() -> Path | None:
    raw = os.environ.get("PATHMARK_LAUNCHER_CONFIG", "").strip()
    return Path(raw).expanduser() if raw else None


def sync_launcher_theme_file(preset: str, mode: str) -> None:
    path = launcher_config_path()
    if not path:
        return
    try:
        data = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8")) or {}
        data["theme_preset"] = "Default" if preset == "Pathmark" else preset
        data["theme_mode"] = mode
        if get_setting("root_folder", ""):
            data["workspace_root"] = get_setting("root_folder", "")
            data["pathmark_root"] = get_setting("root_folder", "")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


DEFAULT_DEVELOPMENT_ROOT = default_development_root()
DEFAULT_SYSTEM_FOLDER = DEFAULT_DEVELOPMENT_ROOT / "00_System"
DATA_DIR = DEFAULT_SYSTEM_FOLDER
DB_PATH = DATA_DIR / "pathmark.db"
OUTPUT_DIR = DEFAULT_SYSTEM_FOLDER
DEFAULT_CALENDAR_EXPORT_FOLDER = DEFAULT_SYSTEM_FOLDER / "Google Calendar Exports"
DEFAULT_GOOGLE_TASKS_EXPORT_FOLDER = DEFAULT_SYSTEM_FOLDER / "Google Tasks Exports"
DEFAULT_TASKLIST_EXPORT_FOLDER = DEFAULT_SYSTEM_FOLDER / "Tasklists"
DEFAULT_BACKUP_FOLDER = DEFAULT_SYSTEM_FOLDER / "Backups"
ICON_PATH = ROOT / "assets" / "pathmark.png"
ACCIDENTAL_APP_PARENT = ROOT.parent if ROOT.name.lower() in ("pathmark", "local_app") and ROOT.parent.name.lower() != "pathmark" else None


def migrate_accidental_app_parent_database() -> None:
    """Copy data from the old accidental parent-root location to Documents\\Pathmark.

    v0.5.36 could treat the folder containing Pathmark as the user's Pathmark
    root. If the app was extracted in Downloads, data could be written to
    Downloads\\00_System. This copies that database to the safer Documents\\Pathmark
    default the first time v0.5.39 runs. It does not delete the old database.
    """
    try:
        if ACCIDENTAL_APP_PARENT is None or DB_PATH.exists():
            return
        old_db = ACCIDENTAL_APP_PARENT / "00_System" / "pathmark.db"
        if not old_db.exists():
            return
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_db, DB_PATH)
    except Exception:
        pass


migrate_accidental_app_parent_database()


def page_icon():
    if Image is not None and ICON_PATH.exists():
        try:
            return Image.open(ICON_PATH)
        except Exception:
            pass
    return "PM"



GOOGLE_TASKS_APPS_SCRIPT_CODE = r"""
/**
 * Pathmark Google Tasks importer
 *
 * Paste this script into Google Sheets Extensions > Apps Script.
 * Enable the Advanced Google service named "Tasks API" before running.
 *
 * Expected sheet columns:
 * Task ID, Task List, Title, Notes, Due Date, Reminder Time, Status
 */
function importPathmarkTasksToGoogleTasks() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const values = sheet.getDataRange().getValues();

  if (values.length < 2) {
    SpreadsheetApp.getUi().alert("No task rows found.");
    return;
  }

  const headers = values[0].map(String);
  const col = name => headers.indexOf(name);

  const requiredColumns = [
    "Task ID",
    "Task List",
    "Title",
    "Notes",
    "Due Date",
    "Reminder Time",
    "Status"
  ];

  for (const name of requiredColumns) {
    if (col(name) === -1) {
      throw new Error("Missing required column: " + name);
    }
  }

  let created = 0;
  let skipped = 0;

  for (let r = 1; r < values.length; r++) {
    const row = values[r];

    const title = String(row[col("Title")] || "").trim();
    const taskId = String(row[col("Task ID")] || "").trim();
    const notes = String(row[col("Notes")] || "").trim();
    const dueDate = row[col("Due Date")];
    const reminderTime = row[col("Reminder Time")];
    const status = String(row[col("Status")] || "needsAction").trim();
    const taskListName = String(row[col("Task List")] || "Pathmark").trim() || "Pathmark";

    if (!title) {
      skipped++;
      continue;
    }

    const fullNotes = [
      notes,
      "",
      taskId ? "Source Task ID: " + taskId : "",
      reminderTime ? "Reference time from Pathmark: " + formatTime_(reminderTime) : ""
    ].filter(Boolean).join("\n");

    const task = {
      title: title,
      notes: fullNotes,
      status: status === "completed" ? "completed" : "needsAction"
    };

    if (dueDate) {
      task.due = formatDueDateForTasks_(dueDate);
    }

    const taskListId = getOrCreateTaskList_(taskListName);
    Tasks.Tasks.insert(task, taskListId);
    created++;
  }

  SpreadsheetApp.getUi().alert(
    "Google Tasks import complete.\n\nCreated: " + created + "\nSkipped: " + skipped
  );
}

// Backwards-compatible alias for older Pathmark/Development System guides.
function importDevelopmentTasksToGoogleTasks() {
  importPathmarkTasksToGoogleTasks();
}

function getOrCreateTaskList_(taskListName) {
  const existing = Tasks.Tasklists.list();

  if (existing.items) {
    for (const list of existing.items) {
      if (list.title === taskListName) {
        return list.id;
      }
    }
  }

  const created = Tasks.Tasklists.insert({
    title: taskListName
  });

  return created.id;
}

function formatDueDateForTasks_(value) {
  let date;

  if (Object.prototype.toString.call(value) === "[object Date]") {
    date = value;
  } else {
    date = new Date(value);
  }

  if (isNaN(date.getTime())) {
    throw new Error("Invalid due date: " + value);
  }

  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");

  // Google Tasks requires RFC3339 timestamp format.
  // The API stores only the date portion for due dates.
  return `${yyyy}-${mm}-${dd}T00:00:00.000Z`;
}

function formatTime_(value) {
  if (Object.prototype.toString.call(value) === "[object Date]") {
    return Utilities.formatDate(value, Session.getScriptTimeZone(), "HH:mm");
  }

  return String(value);
}
""".strip()


def google_tasks_setup_readme() -> str:
    return """# Pathmark Google Tasks import setup

Pathmark exports Google Tasks prompts as a CSV file. Google Tasks does not provide a normal CSV import button, so the import is done through a small Google Apps Script attached to a Google Sheet.

This setup is only needed once per Google account.

## What Pathmark exports

Pathmark creates a CSV file with these required columns:

- Task ID
- Task List
- Title
- Notes
- Due Date
- Reminder Time
- Status

Extra columns may appear after these. The import script ignores extra columns.

## First-time setup

1. Open Google Drive.
2. Create a new Google Sheet called `Pathmark Task Import`.
3. In the Google Sheet, go to **Extensions > Apps Script**.
4. Delete any starter code.
5. Open the file `pathmark_google_tasks_import.gs` from this folder.
6. Copy the whole script into Apps Script.
7. In Apps Script, enable the advanced Google Tasks service:
   - Click **Services** on the left.
   - Click **Add a service**.
   - Choose **Tasks API**.
   - Click **Add**.
8. Save the project.
9. Run `importPathmarkTasksToGoogleTasks` once.
10. Google will ask you to authorise the script. Approve it for your own account.

## Each time you want to import tasks

1. Export Google Tasks from Pathmark.
2. Open the CSV file.
3. Copy the rows into your `Pathmark Task Import` Google Sheet.
4. Keep the header row exactly as exported.
5. Go to **Extensions > Apps Script**.
6. Run `importPathmarkTasksToGoogleTasks`.

The script creates tasks in the task list named in the `Task List` column. If the task list does not already exist, it creates it.

## Important notes

- Google Tasks due dates store the date only. The reference time from Pathmark is kept in the task notes.
- Repeating routine prompts are exported as individual CSV rows, not as true repeating Google Tasks.
- Google Calendar remains the main place for recurring time blocks.
- Google Tasks prompts are intended to reduce friction to begin the work.

## Troubleshooting

If you see `Tasks is not defined`, the Tasks API service has not been enabled in Apps Script.

If the script says a required column is missing, make sure the header row still contains:

`Task ID, Task List, Title, Notes, Due Date, Reminder Time, Status`
"""

GOAL_STATUSES = ["Captured", "Active", "On hold", "Closed", "Abandoned"]
ACTION_STATUSES = ["Planned", "Next", "Scheduled", "Waiting", "Done", "Deferred"]
ROUTINE_STATUSES = ["Captured", "Active", "Retired"]
CORE_AREAS = [
    "Food and nutrition",
    "Movement and exercise",
    "Sleep and recovery",
    "Household reset",
    "Planning and admin",
    "Social connection",
    "Creative maintenance",
    "Financial admin",
]
FREQUENCIES = [
    "Daily",
    "Weekdays",
    "Weekly",
    "Fortnightly",
    "Monthly",
    "First Monday of each month",
    "First Tuesday of each month",
    "First Wednesday of each month",
    "First Thursday of each month",
    "First Friday of each month",
    "First Saturday of each month",
    "First Sunday of each month",
    "Second Monday of each month",
    "Second Tuesday of each month",
    "Second Wednesday of each month",
    "Second Thursday of each month",
    "Second Friday of each month",
    "Second Saturday of each month",
    "Second Sunday of each month",
    "Third Monday of each month",
    "Third Tuesday of each month",
    "Third Wednesday of each month",
    "Third Thursday of each month",
    "Third Friday of each month",
    "Third Saturday of each month",
    "Third Sunday of each month",
    "Fourth Monday of each month",
    "Fourth Tuesday of each month",
    "Fourth Wednesday of each month",
    "Fourth Thursday of each month",
    "Fourth Friday of each month",
    "Fourth Saturday of each month",
    "Fourth Sunday of each month",
    "Last Monday of each month",
    "Last Tuesday of each month",
    "Last Wednesday of each month",
    "Last Thursday of each month",
    "Last Friday of each month",
    "Last Saturday of each month",
    "Last Sunday of each month",
    "As needed",
]
GOOGLE_CALENDAR_COLOURS = {
    "Graphite": {"bg": "#5F6368", "text": "#FFFFFF"},
    "Tomato": {"bg": "#D93025", "text": "#FFFFFF"},
    "Tangerine": {"bg": "#F4511E", "text": "#FFFFFF"},
    "Banana": {"bg": "#F6BF26", "text": "#241A05"},
    "Sage": {"bg": "#33B679", "text": "#FFFFFF"},
    "Basil": {"bg": "#0B8043", "text": "#FFFFFF"},
    "Peacock": {"bg": "#039BE5", "text": "#FFFFFF"},
    "Blueberry": {"bg": "#3F51B5", "text": "#FFFFFF"},
    "Lavender": {"bg": "#7986CB", "text": "#FFFFFF"},
    "Grape": {"bg": "#8E24AA", "text": "#FFFFFF"},
    "Flamingo": {"bg": "#E67C73", "text": "#241A05"},
}
DEFAULT_AREA_COLOURS = {
    "Body And Stability": "Sage",
    "Home And Garden": "Basil",
    "Making And Craft": "Tangerine",
    "Expression And Culture": "Peacock",
    "Work And Admin": "Graphite",
    "Finance": "Grape",
}
STATUS_COLOURS = {
    "Next": {"bg": "#2f6f5e", "text": "#ffffff"},
    "Planned": {"bg": "#8b6f47", "text": "#ffffff"},
    "Scheduled": {"bg": "#4f6f8b", "text": "#ffffff"},
    "Waiting": {"bg": "#80624c", "text": "#ffffff"},
    "Done": {"bg": "#4f6b4a", "text": "#ffffff"},
    "Captured": {"bg": "#b98a5d", "text": "#211c18"},
    "Active": {"bg": "#2f6f5e", "text": "#ffffff"},
    "On hold": {"bg": "#80624c", "text": "#ffffff"},
    "Closed": {"bg": "#5f6368", "text": "#ffffff"},
    "Abandoned": {"bg": "#684b55", "text": "#ffffff"},
}

# -----------------------------------------------------------------------------
# Config and styling
# -----------------------------------------------------------------------------


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    value = (value or "").strip().lstrip("#")
    if len(value) != 6:
        return None
    try:
        return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return None


def _relative_luminance(hex_colour: str) -> float:
    rgb = _hex_to_rgb(hex_colour)
    if rgb is None:
        return 0.0
    vals = []
    for channel in rgb:
        c = channel / 255
        vals.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]


def _contrast_ratio(a: str, b: str) -> float:
    l1 = _relative_luminance(a)
    l2 = _relative_luminance(b)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _best_text_for(background: str, *, prefer_light: bool = False) -> str:
    candidates = ["#FFFFFF", "#FFFDF7", "#151917", "#0F1412"] if prefer_light else ["#151917", "#0F1412", "#FFFFFF", "#FFFDF7"]
    return max(candidates, key=lambda c: _contrast_ratio(c, background))


def ensure_theme_contrast(palette: dict[str, str]) -> dict[str, str]:
    """Normalise theme colours so labels remain readable on their backdrop.

    Some theme families use bright accents in dark mode. This helper keeps the
    visual feel of the palette, but swaps text colours where a selected text colour
    would not meet practical contrast against its actual background.
    """
    out = dict(palette or {})
    bg = out.get("background", "#FAF9F5")
    surface = out.get("surface", bg)
    input_bg = out.get("input_bg", surface)
    primary = out.get("primary", "#0F2D44")
    tag_bg = out.get("tag_bg", out.get("surface_alt", surface))

    if _contrast_ratio(out.get("text", "#151917"), bg) < 4.5:
        out["text"] = _best_text_for(bg)
    if _contrast_ratio(out.get("muted_text", out.get("text", "#151917")), bg) < 3.8:
        out["muted_text"] = out.get("text", _best_text_for(bg))
    if _contrast_ratio(out.get("soft_text", out.get("muted_text", "#151917")), bg) < 3.2:
        out["soft_text"] = out.get("muted_text", out.get("text", _best_text_for(bg)))
    if _contrast_ratio(out.get("button_text", "#FFFFFF"), primary) < 4.5:
        out["button_text"] = _best_text_for(primary, prefer_light=True)
    if _contrast_ratio(out.get("text", "#151917"), input_bg) < 4.5:
        out["input_text"] = _best_text_for(input_bg)
    else:
        out["input_text"] = out.get("text", "#151917")
    if _contrast_ratio(out.get("tag_text", out.get("text", "#151917")), tag_bg) < 4.0:
        out["tag_text"] = _best_text_for(tag_bg)
    return out


def current_season(value: date | None = None) -> str:
    value = value or date.today()
    if value.month in {12, 1, 2}:
        return "Summer"
    if value.month in {3, 4, 5}:
        return "Autumn"
    if value.month in {6, 7, 8}:
        return "Winter"
    return "Spring"


def seasonal_theme(mode: str) -> dict[str, str]:
    # Elegant seasonal palettes. These are deliberately restrained and update automatically
    # when the selected preset is Seasonal.
    palettes = {
        "Autumn": {
            "light": {
                "background": "#f4efe6", "surface": "#fffaf2", "surface_alt": "#eadcc9", "border": "#c2a98d",
                "text": "#211c18", "muted_text": "#5c5148", "soft_text": "#786a60",
                "primary": "#9a704a", "primary_hover": "#815c3d", "button_text": "#fffaf2", "secondary": "#d6bea2",
                "input_bg": "#fffdf8", "input_border": "#b59a7e", "table_header": "#e5d2ba", "table_body": "#fffaf2",
                "tag_bg": "#ead9c4", "tag_text": "#2f271f"
            },
            "dark": {
                # Warm autumn dark mode: espresso, walnut, mushroom and muted brass.
                # This is intended to read as autumnal rather than black UI with orange accents.
                "background": "#241D17", "surface": "#302821", "surface_alt": "#3A3027", "border": "#7C674F",
                "text": "#F5EDE2", "muted_text": "#D8C7B3", "soft_text": "#BCA891",
                "primary": "#B9855A", "primary_hover": "#C9976A", "button_text": "#1E1813", "secondary": "#4B3D30",
                "input_bg": "#2A221C", "input_border": "#8C7358", "table_header": "#3E3329", "table_body": "#302821",
                "tag_bg": "#46372A", "tag_text": "#F5EDE2"
            },
        },
        "Winter": {
            "light": {"background":"#eef2f2","surface":"#fbfdfc","surface_alt":"#dde6e6","border":"#aebbbb","text":"#1e2828","muted_text":"#4d5a5a","soft_text":"#687575","primary":"#55706f","primary_hover":"#455f5e","button_text":"#ffffff","secondary":"#d6e0df","input_bg":"#ffffff","input_border":"#9eafae","table_header":"#dbe6e5","table_body":"#fbfdfc","tag_bg":"#d9e5e4","tag_text":"#1e2828"},
            "dark": {"background":"#101515","surface":"#1b2222","surface_alt":"#242d2d","border":"#4c5d5d","text":"#ecf3f2","muted_text":"#c5d1d0","soft_text":"#a4b2b1","primary":"#8eaaaa","primary_hover":"#a0bbbb","button_text":"#101515","secondary":"#2d3939","input_bg":"#161d1d","input_border":"#566969","table_header":"#263131","table_body":"#1b2222","tag_bg":"#2b3838","tag_text":"#ecf3f2"},
        },
        "Spring": {
            "light": {"background":"#f3f7ee","surface":"#fffefa","surface_alt":"#e2ecd9","border":"#b9c9a8","text":"#20281b","muted_text":"#53604a","soft_text":"#6d785f","primary":"#6d855b","primary_hover":"#5a7149","button_text":"#ffffff","secondary":"#d9e6ce","input_bg":"#fffefa","input_border":"#aebf9f","table_header":"#dce9d1","table_body":"#fffefa","tag_bg":"#e0ead8","tag_text":"#20281b"},
            "dark": {"background":"#11160f","surface":"#1d241a","surface_alt":"#253020","border":"#536348","text":"#eff5e8","muted_text":"#c9d4bf","soft_text":"#a9b79d","primary":"#9ab684","primary_hover":"#abc894","button_text":"#11160f","secondary":"#303b2a","input_bg":"#171e14","input_border":"#5d704f","table_header":"#2a3625","table_body":"#1d241a","tag_bg":"#2d3927","tag_text":"#eff5e8"},
        },
        "Summer": {
            "light": {"background":"#f7f3e6","surface":"#fffdf4","surface_alt":"#efe7c8","border":"#c8b879","text":"#24210f","muted_text":"#5e5734","soft_text":"#7b7146","primary":"#8a7b3e","primary_hover":"#736632","button_text":"#fffdf4","secondary":"#e2d7a9","input_bg":"#fffdf4","input_border":"#b6a768","table_header":"#eee3ba","table_body":"#fffdf4","tag_bg":"#eadfae","tag_text":"#24210f"},
            "dark": {"background":"#151408","surface":"#22200f","surface_alt":"#2b2815","border":"#6a612d","text":"#f2ecd0","muted_text":"#d4c99a","soft_text":"#b9ad78","primary":"#c0ae62","primary_hover":"#d1c177","button_text":"#151408","secondary":"#3b351b","input_bg":"#1b190c","input_border":"#746a36","table_header":"#302b15","table_body":"#22200f","tag_bg":"#36301a","tag_text":"#f2ecd0"},
        },
    }
    season = current_season()
    return ensure_theme_contrast(dict(palettes.get(season, palettes["Autumn"]).get("dark" if mode == "Dark" else "light")))


def theme() -> dict[str, str]:
    config = load_yaml(CONFIG_DIR / "theme.yaml")
    mode = get_setting("theme_mode", "Light")
    preset = get_setting("theme_preset", "Default")
    if preset == "Pathmark":
        preset = "Default"
    if preset == "Seasonal":
        return seasonal_theme(mode)
    if preset == "Default":
        return default_theme(mode)
    presets = config.get("themes", {})
    if preset == "Custom":
        return custom_theme(mode)
    selected = presets.get(preset) or presets.get("Lagoon") or {}
    return ensure_theme_contrast(selected.get("dark" if mode == "Dark" else "light", {}))

def default_theme(mode: str) -> dict[str, str]:
    """Default product-page aligned Pathmark theme.

    This is intentionally quiet and continuous with the public download page
    and launcher. Seasonal and custom themes remain available.
    """
    light = {
        "background": "#FAF9F5", "surface": "#FFFFFF", "surface_alt": "#F1EFE8", "border": "#D8D4CB",
        "text": "#151917", "muted_text": "#626966", "soft_text": "#7A817E",
        "primary": "#0F2D44", "primary_hover": "#1F4A66", "button_text": "#FFFDF7", "secondary": "#E7EEF4",
        "input_bg": "#FFFFFF", "input_border": "#BDB7AD", "table_header": "#EFEEE8", "table_body": "#FFFFFF",
        "tag_bg": "#E7EEF4", "tag_text": "#17324A"
    }
    dark = {
        "background": "#141816", "surface": "#1E2421", "surface_alt": "#29302C", "border": "#4B5650",
        "text": "#F6F4EF", "muted_text": "#CCD2CF", "soft_text": "#AAB2AE",
        "primary": "#87A6BF", "primary_hover": "#A1BBD0", "button_text": "#141816", "secondary": "#334E68",
        "input_bg": "#191F1C", "input_border": "#5B6760", "table_header": "#29302C", "table_body": "#1E2421",
        "tag_bg": "#263B4F", "tag_text": "#E7EEF4"
    }
    return ensure_theme_contrast(dark if mode == "Dark" else light)


def custom_theme(mode: str) -> dict[str, str]:
    base = load_yaml(CONFIG_DIR / "theme.yaml").get("themes", {}).get("Lagoon", {})
    palette = dict(base.get("dark" if mode == "Dark" else "light", {}))
    for key in ["background", "surface", "surface_alt", "border", "text", "muted_text", "primary", "primary_hover", "input_bg", "input_border"]:
        val = get_setting(f"custom_{key}", "")
        if val:
            palette[key] = val
    if "primary" in palette and not get_setting("custom_primary_hover", ""):
        palette["primary_hover"] = palette["primary"]
    return ensure_theme_contrast(palette)


def apply_css() -> None:
    t = theme()
    css = f"""
    <style>
    :root {{
        --bg: {t.get('background', '#f7f1e8')};
        --surface: {t.get('surface', '#fffaf2')};
        --surface-alt: {t.get('surface_alt', '#f0e3d3')};
        --border: {t.get('border', '#c9ad8e')};
        --text: {t.get('text', '#211c18')};
        --muted: {t.get('muted_text', '#5e5249')};
        --soft: {t.get('soft_text', '#77675d')};
        --primary: {t.get('primary', '#8b6042')};
        --primary-hover: {t.get('primary_hover', '#724e36')};
        --button-text: {t.get('button_text', '#fffdf8')};
        --secondary: {t.get('secondary', '#d9c3aa')};
        --input-bg: {t.get('input_bg', '#fffdf8')};
        --input-border: {t.get('input_border', '#b99a7a')};
        --input-text: {t.get('input_text', t.get('text', '#211c18'))};
        --tag-bg: {t.get('tag_bg', '#ead9c4')};
        --tag-text: {t.get('tag_text', '#3d3028')};
    }}

    .stApp {{ background: var(--bg); color: var(--text); }}
    header[data-testid="stHeader"] {{ background: var(--bg) !important; color: var(--text) !important; box-shadow: none !important; height: 0.25rem !important; }}
    header[data-testid="stHeader"] * {{ color: var(--text) !important; }}
    div[data-testid="stToolbar"], div[data-testid="stDecoration"], div[data-testid="stStatusWidget"], div[data-testid="stDeployButton"], button[title="Deploy"], a[title="Deploy"] {{ display: none !important; visibility: hidden !important; }}
    #MainMenu {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}
    section[data-testid="stSidebar"] {{ background: var(--surface); border-right: 1px solid var(--border); }}
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label {{ color: var(--text) !important; }}
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{ color: var(--muted) !important; }}
    .block-container {{ padding-top: 2rem; padding-bottom: 4rem; max-width: 1280px; }}

    h1 {{ color: var(--text); font-size: 2.15rem !important; line-height: 1.05 !important; letter-spacing: 0.01em; margin-bottom: 0.45rem !important; }}
    h2 {{ color: var(--text); font-size: 1.8rem !important; margin-top: 1.4rem !important; }}
    h3 {{ color: var(--text); font-size: 1.25rem !important; }}
    p, li, label {{ color: var(--text); }}
    .muted {{ color: var(--muted); font-size: 0.98rem; line-height: 1.55; }}
    .small-muted {{ color: var(--soft); font-size: 0.88rem; line-height: 1.45; }}

    .metric-card {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 16px 18px;
        min-height: 86px;
        margin-bottom: 12px;
    }}
    .metric-label {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 6px; }}
    .metric-value {{ color: var(--text); font-size: 1.65rem; font-weight: 700; }}

    .panel {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 18px 20px;
        margin: 10px 0 16px 0;
    }}

    .card {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 18px 20px;
        margin: 12px 0 16px 0;
        line-height: 1.55;
    }}
    .row-card {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 13px 15px;
        margin: 10px 0;
    }}
    .source-heading {{
        color: var(--muted);
        font-size: 0.92rem;
        text-transform: uppercase;
        letter-spacing: 0.055em;
        margin-top: 18px;
        margin-bottom: 8px;
        border-bottom: 1px solid var(--border);
        padding-bottom: 5px;
    }}
    .tag {{
        display: inline-block;
        background: var(--tag-bg);
        color: var(--tag-text);
        border: 1px solid var(--border);
        border-radius: 999px;
        padding: 3px 10px;
        margin: 7px 6px 4px 0;
        font-size: 0.78rem;
        line-height: 1.25;
        font-weight: 600;
    }}

    .stButton > button, div[data-testid="stDownloadButton"] button, div[data-testid="stFormSubmitButton"] button {{
        background: var(--primary) !important;
        color: var(--button-text) !important;
        border: 1px solid var(--primary) !important;
        border-radius: 9px !important;
        padding: 0.52rem 0.9rem !important;
        font-weight: 600 !important;
        box-shadow: none !important;
    }}
    .stButton > button:hover, div[data-testid="stDownloadButton"] button:hover, div[data-testid="stFormSubmitButton"] button:hover {{
        background: var(--primary-hover) !important;
        border-color: var(--primary-hover) !important;
        color: var(--button-text) !important;
    }}
    .stButton > button *, div[data-testid="stDownloadButton"] button *, div[data-testid="stFormSubmitButton"] button * {{
        color: var(--button-text) !important;
    }}
    button[data-testid^="baseButton"], button[data-testid^="baseButton"] *,
    button[data-testid^="baseButton"] p, button[data-testid^="baseButton"] span,
    [data-testid="stButton"] button, [data-testid="stButton"] button *,
    [data-testid="stButton"] button p, [data-testid="stButton"] button span,
    [data-testid="stDownloadButton"] button, [data-testid="stDownloadButton"] button *,
    [data-testid="stFormSubmitButton"] button, [data-testid="stFormSubmitButton"] button * {{
        color: var(--button-text) !important;
        -webkit-text-fill-color: var(--button-text) !important;
        text-shadow: 0 1px 1px rgba(0,0,0,.18);
    }}
    .stButton > button:disabled, div[data-testid="stFormSubmitButton"] button:disabled {{
        background: var(--secondary) !important;
        color: var(--muted) !important;
        border-color: var(--border) !important;
        opacity: 0.78 !important;
    }}
    .stButton > button:disabled *, div[data-testid="stFormSubmitButton"] button:disabled * {{
        color: var(--muted) !important;
    }}

    input, textarea, div[data-baseweb="select"] > div {{
        background: var(--input-bg) !important;
        color: var(--text) !important;
        border-color: var(--input-border) !important;
        border-radius: 9px !important;
    }}
    input:focus, textarea:focus, div[data-baseweb="select"] > div:focus-within {{
        border-color: var(--primary) !important;
        box-shadow: none !important;
    }}
    div[data-baseweb="select"] span {{ color: var(--text) !important; }}
    [data-testid="stDataFrame"] {{ background: var(--surface); border-radius: 10px; }}



    /* Pathmark polish layer */
    .block-container {{ max-width: 1180px; padding-top: 1.6rem; }}
    h1 {{ font-size: clamp(2.1rem, 4vw, 3.6rem) !important; letter-spacing: -0.055em !important; font-weight: 780 !important; }}
    h2 {{ letter-spacing: -0.035em !important; font-weight: 730 !important; }}
    h3 {{ letter-spacing: -0.02em !important; font-weight: 720 !important; }}
    .metric-card, .panel, .card, .row-card {{
        border-radius: 18px !important;
        border-color: color-mix(in srgb, var(--border) 78%, transparent) !important;
        box-shadow: 0 14px 34px rgba(0,0,0,.07);
    }}
    .row-card:hover, .card:hover {{ transform: translateY(-1px); transition: transform .16s ease, box-shadow .16s ease; box-shadow: 0 18px 40px rgba(0,0,0,.10); }}
    .source-heading {{ text-transform: none !important; letter-spacing: 0 !important; font-weight: 700 !important; color: var(--text) !important; border-bottom: 1px solid var(--border); }}
    .stButton > button, div[data-testid="stDownloadButton"] button, div[data-testid="stFormSubmitButton"] button {{
        border-radius: 999px !important;
        min-height: 2.75rem !important;
        padding-left: 1.05rem !important;
        padding-right: 1.05rem !important;
        box-shadow: 0 8px 18px rgba(0,0,0,.08) !important;
    }}
    .stButton > button:hover, div[data-testid="stDownloadButton"] button:hover, div[data-testid="stFormSubmitButton"] button:hover {{
        transform: translateY(-1px);
        box-shadow: 0 12px 24px rgba(0,0,0,.12) !important;
    }}
    input, textarea, div[data-baseweb="select"] > div {{ border-radius: 14px !important; }}
    [data-testid="stExpander"] {{ border-radius: 18px !important; border-color: var(--border) !important; background: var(--surface) !important; }}
    [data-testid="stTabs"] button {{ font-weight: 650 !important; }}

    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

def page_title(title: str, subtitle: str | None = None) -> None:
    st.title(title)
    if subtitle:
        st.markdown(f"<div class='muted'>{subtitle}</div>", unsafe_allow_html=True)


def tag_markup(tag: Any) -> str:
    if isinstance(tag, dict):
        label = str(tag.get("label", ""))
        bg = tag.get("bg") or "var(--tag-bg)"
        text = tag.get("text") or "var(--tag-text)"
        return f"<span class='tag' style='background:{bg}; color:{text};'>{escape_html(label)}</span>"
    label = str(tag)
    colour = STATUS_COLOURS.get(label)
    if colour:
        return f"<span class='tag' style='background:{colour['bg']}; color:{colour['text']};'>{escape_html(label)}</span>"
    return f"<span class='tag'>{escape_html(label)}</span>"


def area_tag(area_name: str | None, google_colour: str | None = None) -> dict[str, str]:
    label = area_name or "No area"
    colour_name = google_colour or DEFAULT_AREA_COLOURS.get(label) or "Graphite"
    colour = GOOGLE_CALENDAR_COLOURS.get(colour_name, GOOGLE_CALENDAR_COLOURS["Graphite"])
    return {"label": label, "bg": colour["bg"], "text": colour["text"]}


def card(title: str, body: str, tags: Iterable[Any] | None = None) -> None:
    tag_html = "".join(tag_markup(t) for t in (tags or []))
    st.markdown(
        f"<div class='card'><h3>{escape_html(title)}</h3>{tag_html}<div class='muted'>{body}</div></div>",
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: Any) -> None:
    st.markdown(
        f"<div class='metric-card'><div class='metric-label'>{escape_html(label)}</div><div class='metric-value'>{value}</div></div>",
        unsafe_allow_html=True,
    )


def help_note(text: str) -> None:
    st.markdown(f"<div class='section-note'>{escape_html(text)}</div>", unsafe_allow_html=True)


def escape_html(value: Any) -> str:
    import html
    return html.escape("" if value is None else str(value))

# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------


def migrate_database_out_of_app_folder() -> None:
    """Copy an older database into 00_System without deleting the original.

    New Pathmark installs use 00_System/pathmark.db. Older development builds used
    Pathmark/data/development_system.db or 00_System/development_system.db. If an
    older database is found and pathmark.db does not exist yet, copy it forward.
    """
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        legacy_system_db = DATA_DIR / LEGACY_SYSTEM_DB_NAME
        if not DB_PATH.exists() and legacy_system_db.exists():
            shutil.copy2(legacy_system_db, DB_PATH)
        elif not DB_PATH.exists() and OLD_DB_PATH.exists():
            shutil.copy2(OLD_DB_PATH, DB_PATH)
    except Exception:
        # If migration fails, normal database creation/error handling will continue.
        pass


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def execute(sql: str, params: tuple = ()) -> None:
    with connect() as con:
        con.execute(sql, params)
        # Lightweight migrations for v0.4.12. Existing local databases keep working.
        existing = {row[1] for row in con.execute("PRAGMA table_info(routines)").fetchall()}
        routine_columns = {
            "calendar_block": "INTEGER DEFAULT 0",
            "reminder": "INTEGER DEFAULT 0",
            "calendar_start_time": "TEXT DEFAULT '09:00'",
            "calendar_end_time": "TEXT DEFAULT '10:00'",
            "calendar_location": "TEXT DEFAULT ''",
            "task_reminder_time": "TEXT DEFAULT '09:00'",
            "starting_prompt": "TEXT DEFAULT ''",
        }
        for col, definition in routine_columns.items():
            if col not in existing:
                con.execute(f"ALTER TABLE routines ADD COLUMN {col} {definition}")
        con.commit()


def executemany(sql: str, params: list[tuple]) -> None:
    with connect() as con:
        con.executemany(sql, params)
        con.commit()


def query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with connect() as con:
        return [dict(row) for row in con.execute(sql, params).fetchall()]


def scalar(sql: str, params: tuple = ()) -> Any:
    with connect() as con:
        row = con.execute(sql, params).fetchone()
        return None if row is None else row[0]


def df(sql: str, params: tuple = ()) -> pd.DataFrame:
    return pd.DataFrame(query(sql, params))


def init_db() -> None:
    with connect() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS areas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT DEFAULT '',
                folder_path TEXT DEFAULT '',
                markdown_path TEXT DEFAULT '',
                default_calendar TEXT DEFAULT '',
                default_task_list TEXT DEFAULT '',
                google_color TEXT DEFAULT 'Graphite',
                status TEXT DEFAULT 'Active',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                area_id INTEGER,
                status TEXT DEFAULT 'Captured',
                subarea TEXT DEFAULT '',
                purpose TEXT DEFAULT '',
                desired_outcome TEXT DEFAULT '',
                closure_criteria TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                closed_at TEXT,
                archived_at TEXT,
                FOREIGN KEY(area_id) REFERENCES areas(id)
            );
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_id INTEGER,
                routine_id INTEGER,
                area_id INTEGER,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT DEFAULT 'Planned',
                priority TEXT DEFAULT 'Medium',
                subarea TEXT DEFAULT '',
                due_date TEXT,
                scheduled_date TEXT,
                activity_days TEXT DEFAULT '',
                estimated_minutes INTEGER,
                calendar_block INTEGER DEFAULT 0,
                reminder INTEGER DEFAULT 0,
                include_tasklist INTEGER DEFAULT 1,
                notes TEXT DEFAULT '',
                completed_at TEXT,
                archived_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(goal_id) REFERENCES goals(id),
                FOREIGN KEY(routine_id) REFERENCES routines(id),
                FOREIGN KEY(area_id) REFERENCES areas(id)
            );
            CREATE TABLE IF NOT EXISTS routines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                area_id INTEGER,
                core_area TEXT DEFAULT '',
                subarea TEXT DEFAULT '',
                purpose TEXT DEFAULT '',
                frequency TEXT DEFAULT 'Weekly',
                next_due TEXT,
                last_completed TEXT,
                status TEXT DEFAULT 'Active',
                notes TEXT DEFAULT '',
                checklist TEXT DEFAULT '',
                calendar_block INTEGER DEFAULT 0,
                reminder INTEGER DEFAULT 0,
                task_reminder_time TEXT DEFAULT '09:00',
                starting_prompt TEXT DEFAULT '',
                calendar_start_time TEXT DEFAULT '09:00',
                calendar_end_time TEXT DEFAULT '10:00',
                calendar_location TEXT DEFAULT '',
                archived_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(area_id) REFERENCES areas(id)
            );
            CREATE TABLE IF NOT EXISTS calendar_blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_id INTEGER,
                goal_id INTEGER,
                routine_id INTEGER,
                area_id INTEGER,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                start_datetime TEXT,
                end_datetime TEXT,
                location TEXT DEFAULT '',
                calendar_name TEXT DEFAULT 'Google Calendar',
                recurrence_rule TEXT DEFAULT '',
                alarm_minutes INTEGER DEFAULT 10,
                export_status TEXT DEFAULT 'Staged',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                exported_at TEXT,
                removed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS reminder_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_id INTEGER,
                goal_id INTEGER,
                routine_id INTEGER,
                area_id INTEGER,
                title TEXT NOT NULL,
                notes TEXT DEFAULT '',
                due_date TEXT,
                reminder_time TEXT,
                task_list TEXT DEFAULT 'Pathmark',
                export_status TEXT DEFAULT 'Staged',
                linked_calendar_block_id INTEGER,
                repeat_pattern TEXT DEFAULT '',
                linked_calendar_summary TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                exported_at TEXT,
                removed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS review_issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                priority TEXT DEFAULT 'Medium',
                type TEXT DEFAULT '',
                source TEXT DEFAULT '',
                entity_type TEXT DEFAULT '',
                entity_id INTEGER,
                message TEXT DEFAULT '',
                suggested_step TEXT DEFAULT '',
                status TEXT DEFAULT 'Open',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                resolved_at TEXT
            );
            CREATE TABLE IF NOT EXISTS archive_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id INTEGER,
                title TEXT NOT NULL,
                final_status TEXT DEFAULT '',
                summary TEXT DEFAULT '',
                went_well TEXT DEFAULT '',
                did_not_go_well TEXT DEFAULT '',
                carried_forward TEXT DEFAULT '',
                snapshot_json TEXT DEFAULT '',
                archived_at TEXT DEFAULT CURRENT_TIMESTAMP,
                promoted_at TEXT
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                focus_type TEXT DEFAULT '',
                focus_id INTEGER,
                focus_title TEXT DEFAULT '',
                intended_action TEXT DEFAULT '',
                started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                ended_at TEXT,
                went_well TEXT DEFAULT '',
                did_not_go_well TEXT DEFAULT '',
                changed TEXT DEFAULT '',
                next_step TEXT DEFAULT '',
                decision TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS export_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                export_type TEXT NOT NULL,
                file_path TEXT NOT NULL,
                row_count INTEGER DEFAULT 0,
                scope TEXT DEFAULT '',
                status TEXT DEFAULT 'Created',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        con.commit()


def column_exists(table: str, column: str) -> bool:
    with connect() as con:
        cols = [row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()]
    return column in cols


def ensure_schema_updates() -> None:
    # v0.4.18: export logs are used to record generated ICS/CSV/PDF/Markdown files.
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS export_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            export_type TEXT NOT NULL,
            file_path TEXT NOT NULL,
            row_count INTEGER DEFAULT 0,
            scope TEXT DEFAULT '',
            status TEXT DEFAULT 'Created',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        con.commit()
    if not column_exists("areas", "google_color"):
        execute("ALTER TABLE areas ADD COLUMN google_color TEXT DEFAULT 'Graphite'")
    if not column_exists("routines", "checklist"):
        execute("ALTER TABLE routines ADD COLUMN checklist TEXT DEFAULT ''")
    routine_columns = {
        "calendar_block": "INTEGER DEFAULT 0",
        "reminder": "INTEGER DEFAULT 0",
        "task_reminder_time": "TEXT DEFAULT '09:00'",
        "calendar_start_time": "TEXT DEFAULT '09:00'",
        "calendar_end_time": "TEXT DEFAULT '10:00'",
        "calendar_location": "TEXT DEFAULT ''",
        "starting_prompt": "TEXT DEFAULT ''",
    }
    for column, definition in routine_columns.items():
        if not column_exists("routines", column):
            execute(f"ALTER TABLE routines ADD COLUMN {column} {definition}")
    action_columns = {
        "first_step": "TEXT DEFAULT ''",
        "task_reminder_time": "TEXT DEFAULT '09:00'",
        "calendar_start_time": "TEXT DEFAULT '09:00'",
        "calendar_end_time": "TEXT DEFAULT '10:00'",
        "calendar_location": "TEXT DEFAULT ''",
        "recurrence_rule": "TEXT DEFAULT ''",
        "include_tasklist": "INTEGER DEFAULT 1",
        "activity_days": "TEXT DEFAULT ''",
    }
    for column, definition in action_columns.items():
        if not column_exists("actions", column):
            execute(f"ALTER TABLE actions ADD COLUMN {column} {definition}")
    # v0.5.5: top-level Area + specific subarea. Keep old routine.core_area only as a migration source.
    for table in ["goals", "actions", "routines"]:
        if not column_exists(table, "subarea"):
            execute(f"ALTER TABLE {table} ADD COLUMN subarea TEXT DEFAULT ''")
    if column_exists("routines", "core_area"):
        execute("UPDATE routines SET subarea = COALESCE(NULLIF(subarea,''), core_area) WHERE COALESCE(subarea,'') = ''")
    # v0.5.10: routine child rows are recurring activities, not once-off actions.
    # Preserve archived rows, but normalise active routine children away from Done/Planned semantics.
    execute("UPDATE actions SET status='Included' WHERE routine_id IS NOT NULL AND archived_at IS NULL AND status IN ('Done','Planned','Next','Scheduled','Waiting')")
    execute("UPDATE actions SET status='Paused' WHERE routine_id IS NOT NULL AND archived_at IS NULL AND status IN ('On hold','Retired')")
    execute("UPDATE actions SET include_tasklist=1 WHERE routine_id IS NOT NULL AND include_tasklist IS NULL")
    # v0.5.12: infer routine activity days from old imports where possible.
    # Existing data is not overwritten once activity_days has been set.
    for row in query("SELECT id, scheduled_date, due_date, title, notes, description FROM actions WHERE routine_id IS NOT NULL AND archived_at IS NULL AND COALESCE(activity_days,'')=''"):
        inferred = infer_activity_days_from_import(dict(row))
        if inferred:
            execute("UPDATE actions SET activity_days=? WHERE id=?", (inferred, row["id"]))
    # Carry legacy routine-level export flags onto activity rows where no activity setting exists yet.
    execute("""UPDATE actions
               SET calendar_block = COALESCE(NULLIF(calendar_block,0), (SELECT calendar_block FROM routines WHERE routines.id = actions.routine_id)),
                   reminder = COALESCE(NULLIF(reminder,0), (SELECT reminder FROM routines WHERE routines.id = actions.routine_id))
               WHERE routine_id IS NOT NULL AND archived_at IS NULL""")
    if not column_exists("reminder_tasks", "repeat_pattern"):
        execute("ALTER TABLE reminder_tasks ADD COLUMN repeat_pattern TEXT DEFAULT ''")
    if not column_exists("reminder_tasks", "linked_calendar_summary"):
        execute("ALTER TABLE reminder_tasks ADD COLUMN linked_calendar_summary TEXT DEFAULT ''")
    if not column_exists("calendar_blocks", "recurrence_rule"):
        execute("ALTER TABLE calendar_blocks ADD COLUMN recurrence_rule TEXT DEFAULT ''")
    if not column_exists("archive_entries", "promoted_at"):
        execute("ALTER TABLE archive_entries ADD COLUMN promoted_at TEXT")
    for name, colour in DEFAULT_AREA_COLOURS.items():
        execute("UPDATE areas SET google_color = COALESCE(NULLIF(google_color,''), ?) WHERE name = ?", (colour, name))
    valid_colours = tuple(GOOGLE_CALENDAR_COLOURS.keys())
    placeholders = ",".join("?" for _ in valid_colours)
    execute(f"UPDATE areas SET google_color = 'Sage' WHERE google_color IS NULL OR google_color = '' OR google_color NOT IN ({placeholders})", valid_colours)


def table_count(table: str) -> int:
    return int(scalar(f"SELECT COUNT(*) FROM {table}") or 0)


def get_setting(key: str, default: str = "") -> str:
    try:
        value = scalar("SELECT value FROM app_settings WHERE key = ?", (key,))
        return default if value in (None, "") else str(value)
    except Exception:
        return default


def set_setting(key: str, value: str) -> None:
    execute("INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def root_folder() -> Path:
    value = get_setting("root_folder", "")
    if not value:
        return DEFAULT_DEVELOPMENT_ROOT
    return Path(value).expanduser()


def setup_complete() -> bool:
    return get_setting("setup_complete", "No") == "Yes"


def backup_database(reason: str = "manual") -> Path | None:
    if not DB_PATH.exists():
        return None
    backup_dir = backup_folder() / "Database"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"pathmark_{reason}_{stamp}.db"
    shutil.copy2(DB_PATH, backup)
    log_export("Database backup", backup, 1, reason)
    return backup


def log_export(export_type: str, path: Path, row_count: int = 0, scope: str = "", status: str = "Created") -> None:
    execute(
        "INSERT INTO export_logs (export_type, file_path, row_count, scope, status) VALUES (?,?,?,?,?)",
        (export_type, str(path), int(row_count or 0), scope, status),
    )


def ensure_default_settings() -> None:
    defaults = {
        "theme_mode": launcher_initial_theme_mode(),
        "theme_preset": launcher_initial_theme_preset(),
        "weekly_focus": "No main focus",
        "system_name": "Pathmark",
        "root_folder": str(DEFAULT_DEVELOPMENT_ROOT),
        "system_folder": str(DEFAULT_SYSTEM_FOLDER),
        "calendar_export_folder": str(DEFAULT_CALENDAR_EXPORT_FOLDER),
        "google_tasks_export_folder": str(DEFAULT_GOOGLE_TASKS_EXPORT_FOLDER),
        "tasklist_export_folder": str(DEFAULT_TASKLIST_EXPORT_FOLDER),
        "backup_folder": str(DEFAULT_BACKUP_FOLDER),
        "default_task_list": "Pathmark",
        "default_calendar": "Pathmark",
        "release_hub_url": "",
    }
    for key, value in defaults.items():
        if get_setting(key, "") == "":
            set_setting(key, value)

    # v0.5.43: when Pathmark is launched from Pathmark.exe, the launcher is the
    # source of truth for the selected workspace. This prevents exports being
    # written to a newly-created Documents\Workspace folder when the user has
    # chosen an existing development/workspace folder in the launcher.
    if launcher_root_supplied():
        set_setting("root_folder", str(DEFAULT_DEVELOPMENT_ROOT))
        set_setting("system_folder", str(DEFAULT_SYSTEM_FOLDER))
        set_setting("calendar_export_folder", str(DEFAULT_CALENDAR_EXPORT_FOLDER))
        set_setting("google_tasks_export_folder", str(DEFAULT_GOOGLE_TASKS_EXPORT_FOLDER))
        set_setting("tasklist_export_folder", str(DEFAULT_TASKLIST_EXPORT_FOLDER))
        set_setting("backup_folder", str(DEFAULT_BACKUP_FOLDER))

    if launcher_theme_sync_requested() and not st.session_state.get("_launcher_theme_synced_once", False):
        # The launcher provides the initial theme at app start, but it should not
        # overwrite an in-app theme change on every Streamlit rerun.
        set_setting("theme_mode", launcher_initial_theme_mode())
        set_setting("theme_preset", launcher_initial_theme_preset())
        st.session_state["_launcher_theme_synced_once"] = True

    # v0.5.35: rename older visible system names from the prototype era.
    if get_setting("system_name", "") in ("Development System", "Clearway", "Wayline"):
        set_setting("system_name", "Pathmark")
    if get_setting("default_task_list", "") in ("Development System", "Clearway", "Wayline"):
        set_setting("default_task_list", "Pathmark")
    if get_setting("default_calendar", "") in ("Development System", "Clearway", "Wayline"):
        set_setting("default_calendar", "Pathmark")

    # v0.5.39: if v0.5.36 accidentally used the folder containing Pathmark
    # as the user root, move settings back to Documents\Workspace while leaving
    # the old folders untouched.
    if ACCIDENTAL_APP_PARENT is not None:
        current_root = Path(get_setting("root_folder", "") or "").expanduser()
        try:
            if current_root.resolve() == ACCIDENTAL_APP_PARENT.resolve():
                safe_root = default_workspace_folder()
                set_setting("root_folder", str(safe_root))
                set_setting("system_folder", str(safe_root / "00_System"))
                set_setting("calendar_export_folder", str(safe_root / "00_System" / "Google Calendar Exports"))
                set_setting("google_tasks_export_folder", str(safe_root / "00_System" / "Google Tasks Exports"))
                set_setting("tasklist_export_folder", str(safe_root / "00_System" / "Tasklists"))
                set_setting("backup_folder", str(safe_root / "00_System" / "Backups"))
        except Exception:
            pass

    # v0.5.19: generated files live in 00_System, not inside Pathmark/output.
    persistent_calendar = system_folder() / "Google Calendar Exports"
    persistent_tasks = system_folder() / "Google Tasks Exports"
    persistent_tasklists = system_folder() / "Tasklists"
    persistent_backups = system_folder() / "Backups"
    current_calendar = get_setting("calendar_export_folder", "")
    current_tasks = get_setting("google_tasks_export_folder", "")
    current_tasklists = get_setting("tasklist_export_folder", "")
    current_backups = get_setting("backup_folder", "")
    def _is_old_or_app_output(path_text: str, old_suffixes: tuple[str, ...]) -> bool:
        text = (path_text or "").replace("\\", "/").lower()
        return (not text) or "/pathmark/output/" in text or "/local_app/output/" in text or text.endswith("/pathmark/output") or text.endswith("/local_app/output") or any(text.endswith(s.lower()) for s in old_suffixes)

    if _is_old_or_app_output(current_calendar, ("/CalendarExports",)):
        set_setting("calendar_export_folder", str(persistent_calendar))
    if _is_old_or_app_output(current_tasks, ("/GoogleTasksExports",)):
        set_setting("google_tasks_export_folder", str(persistent_tasks))
    if _is_old_or_app_output(current_tasklists, ("/weekly",)):
        set_setting("tasklist_export_folder", str(persistent_tasklists))
    if _is_old_or_app_output(current_backups, ("/backups",)):
        set_setting("backup_folder", str(persistent_backups))


def seed_data() -> None:
    if table_count("areas") > 0:
        return
    create_development_root()
    areas = [
        ("Body And Stability", "Movement, sleep, food, recovery, and sustainable capacity", "01_Body_And_Stability", "README", "Body And Stability", "Pathmark", "Sage"),
        ("Home And Garden", "Household reset, garden, houseplants, and domestic environment", "02_Home_And_Garden", "README", "Home And Garden", "Pathmark", "Basil"),
        ("Making And Craft", "Pottery, design, glaze, clay, and making projects", "03_Making_And_Craft", "README", "Making And Craft", "Pathmark", "Tangerine"),
        ("Expression And Culture", "Language, music, art practice, reading, and cultural work", "04_Expression_And_Culture", "README", "Expression And Culture", "Pathmark", "Peacock"),
        ("Work And Admin", "Professional work, planning, administration, and system maintenance", "05_Work_And_Admin", "README", "Work And Admin", "Pathmark", "Graphite"),
        ("Finance", "Budgeting, forecasting, savings, and financial administration", "06_Finance", "README", "Finance", "Pathmark", "Grape"),
    ]
    for name, desc, folder, md, cal, task, colour in areas:
        folder_path = root_folder() / folder
        markdown_path = folder_path / f"{slug(name)}.md"
        execute(
            "INSERT INTO areas (name, description, folder_path, markdown_path, default_calendar, default_task_list, google_color, notes) VALUES (?,?,?,?,?,?,?,?)",
            (name, desc, str(folder_path), str(markdown_path), cal, task, colour, "Starter area. Edit to match your folder system."),
        )
        ensure_area_folder(name)

    area_ids = {r["name"]: r["id"] for r in query("SELECT id, name FROM areas")}
    goals = [
        ("Set up the development system", "Work And Admin", "Active", "Build a practical local system for goals, routines, review, and exports.", "A usable app that supports daily focus, weekly planning, and clean archiving.", "The first version can be used for one full planning week without returning to the spreadsheet.", "Use the app and note where it still feels clunky."),
        ("Prepare next work milestone", "Work And Admin", "Captured", "Hold a defined work outcome without it becoming a vague open loop.", "A clear set of actions and calendar time for the next milestone.", "The milestone has a completed summary and any carry-forward actions are defined.", "Starter example. Rename or replace this with a real work goal."),
        ("Develop a seasonal creative practice", "Making And Craft", "Active", "Create regular space for pottery/design observations and development.", "A small repeatable creative practice that can survive busy weeks.", "There is a simple routine and at least one completed output or observation note.", "Connect this to folder and Markdown exports."),
        ("Plan the garden for the current season", "Home And Garden", "On hold", "Choose seasonal garden priorities without trying to do everything at once.", "A short list of seasonal tasks and plant decisions.", "Current season priorities are confirmed and scheduled or deliberately deferred.", "Review when ready to plan garden tasks."),
    ]
    for g in goals:
        execute(
            "INSERT INTO goals (title, area_id, subarea, status, purpose, desired_outcome, closure_criteria, notes) VALUES (?,?,?,?,?,?,?,?)",
            (g[0], area_ids[g[1]], "", g[2], g[3], g[4], g[5], g[6]),
        )

    goal_ids = {r["title"]: r["id"] for r in query("SELECT id, title FROM goals")}
    actions = [
        ("Review Home page wording and spacing", "Set up the development system", "Work And Admin", "Next", "High", 45, 1, 1, "Check whether labels are clear and user-facing."),
        ("Test Google Calendar export by area", "Set up the development system", "Work And Admin", "Planned", "Medium", 30, 1, 0, "Confirm each exported ICS maps to the intended Google Calendar."),
        ("Draft design criteria from observation notes", "Develop a seasonal creative practice", "Making And Craft", "Next", "Medium", 60, 1, 1, "Use a small set of observations and convert them to testable design criteria."),
        ("Confirm seasonal garden priorities", "Plan the garden for the current season", "Home And Garden", "Waiting", "Low", 30, 0, 1, "Decide what is genuinely current-season rather than future planning."),
        ("Define next milestone outcome", "Prepare next work milestone", "Work And Admin", "Planned", "High", 30, 0, 1, "Write the desired outcome in one sentence."),
    ]
    for title, goal, area, status, priority, mins, cal, rem, notes in actions:
        execute(
            """INSERT INTO actions (goal_id, area_id, title, status, priority, estimated_minutes, calendar_block, reminder, notes, due_date, scheduled_date)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (goal_ids[goal], area_ids[area], title, status, priority, mins, cal, rem, notes, str(date.today()+timedelta(days=3)), str(date.today()+timedelta(days=1))),
        )

    routines = [
        ("Plan the week", "Work And Admin", "Planning and admin", "Decide the week’s main focus, routines, and planned actions.", "Weekly", str(next_monday()), "Active", "Review active goals\nChoose main focus\nPrepare weekly checklist"),
        ("Prepare work lunches", "Body And Stability", "Food and nutrition", "Make weekdays easier by preparing reliable lunches in advance.", "Weekly", str(next_monday()-timedelta(days=1)), "Active", "Choose lunches\nShop ingredients\nPrepare containers"),
        ("Exercise", "Body And Stability", "Movement and exercise", "Maintain strength, mood, and cardiovascular fitness.", "Weekdays", str(date.today()+timedelta(days=1)), "Active", "Choose session\nPrepare clothes\nLog completion"),
        ("Reset the house", "Home And Garden", "Household reset", "Keep the home functional enough that project work does not crowd out basic maintenance.", "Weekly", str(next_monday()-timedelta(days=1)), "Active", "Clear surfaces\nLaundry reset\nKitchen reset\nBins and recycling"),
        ("Review meals, movement, sleep, and stress", "Body And Stability", "Planning and admin", "Check whether the week is supporting energy and balance.", "Weekly", str(next_monday()), "Active", "Meals\nMovement\nSleep\nStress"),
        ("Choose tomorrow’s focus", "Work And Admin", "Planning and admin", "Decide the next day’s first useful action before the evening ends.", "Daily", str(date.today()), "Active", "Check calendar\nChoose first action\nPrepare anything needed"),
    ]
    for title, area, core, purpose, frequency, next_due, status, checklist in routines:
        execute(
            "INSERT INTO routines (title, area_id, subarea, core_area, purpose, frequency, next_due, status, notes, checklist) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (title, area_ids[area], core, core, purpose, frequency, next_due, status, "Starter routine. Edit or retire if it does not fit.", checklist),
        )
    stage_exports_from_actions()
    generate_review_issues()


def next_monday() -> date:
    today = date.today()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


def migrate_routine_checklists_to_tasks() -> None:
    """Convert legacy routine checklist lines into routine activities.

    The earlier prototype stored printable checklist lines on the routine itself.
    The current model treats these as routine activities so they can appear in the
    Tasklist and can be exported to Google Calendar / Google Tasks when useful.
    This migration is intentionally non-destructive: it creates missing tasks but
    leaves the original checklist text in place for reference.
    """
    if not column_exists("routines", "checklist"):
        return
    for routine in query("SELECT id, area_id, next_due, checklist FROM routines WHERE COALESCE(checklist,'') != ''"):
        items = []
        for raw in str(routine.get("checklist") or "").splitlines():
            item = raw.strip().lstrip("-•□☐").strip()
            if item:
                items.append(item)
        for item in items:
            exists = scalar("SELECT COUNT(*) FROM actions WHERE routine_id = ? AND title = ? AND archived_at IS NULL", (routine["id"], item))
            if not exists:
                execute(
                    """INSERT INTO actions (routine_id, area_id, title, status, priority, first_step, due_date, scheduled_date, notes)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (routine["id"], routine.get("area_id"), item, "Planned", "Medium", item, routine.get("next_due"), routine.get("next_due"), "Created from routine checklist item."),
                )

# -----------------------------------------------------------------------------
# Data helpers
# -----------------------------------------------------------------------------


def areas_df(active_only: bool = False) -> pd.DataFrame:
    where = "WHERE status = 'Active'" if active_only else ""
    return df(f"SELECT * FROM areas {where} ORDER BY name")


def goals_df(include_archived: bool = False) -> pd.DataFrame:
    where = "" if include_archived else "WHERE archived_at IS NULL"
    return df(
        f"""
        SELECT g.*, a.name AS area_name, a.google_color AS area_color
        FROM goals g LEFT JOIN areas a ON a.id = g.area_id
        {where}
        ORDER BY CASE g.status WHEN 'Active' THEN 1 WHEN 'Captured' THEN 2 WHEN 'On hold' THEN 3 WHEN 'Closed' THEN 4 WHEN 'Abandoned' THEN 5 ELSE 6 END,
                 g.updated_at DESC, g.title
        """
    )


def actions_df(extra_where: str = "", params: tuple = ()) -> pd.DataFrame:
    return df(
        f"""
        SELECT ac.*, g.title AS goal_title, ar.name AS area_name, ar.google_color AS area_color, r.title AS routine_title
        FROM actions ac
        LEFT JOIN goals g ON g.id = ac.goal_id
        LEFT JOIN routines r ON r.id = ac.routine_id
        LEFT JOIN areas ar ON ar.id = ac.area_id
        {extra_where}
        ORDER BY CASE ac.status WHEN 'Next' THEN 1 WHEN 'Scheduled' THEN 2 WHEN 'Planned' THEN 3 WHEN 'Waiting' THEN 4 WHEN 'Done' THEN 5 ELSE 6 END,
                 ac.due_date IS NULL, ac.due_date, ac.title
        """,
        params,
    )


def weekly_focus_goal_id() -> int | None:
    focus = get_setting("weekly_focus", "No main focus")
    rows = query("SELECT id FROM goals WHERE title=? AND archived_at IS NULL", (focus,))
    return int(rows[0]["id"]) if rows else None


def planned_actions_df(source: str = "all") -> pd.DataFrame:
    """Return planned goal actions and included routine activities."""
    if source == "routines":
        return df(
            """
            SELECT ac.*, g.title AS goal_title, ar.name AS area_name, ar.google_color AS area_color, r.title AS routine_title
            FROM actions ac
            LEFT JOIN goals g ON g.id = ac.goal_id
            LEFT JOIN routines r ON r.id = ac.routine_id
            LEFT JOIN areas ar ON ar.id = ac.area_id
            WHERE ac.routine_id IS NOT NULL
              AND ac.archived_at IS NULL
              AND COALESCE(ac.status,'Included') != 'Paused'
              AND COALESCE(ac.include_tasklist,1) = 1
            ORDER BY r.title, ac.calendar_start_time IS NULL, ac.calendar_start_time, ac.title
            """
        )

    extra = ""
    if source == "goals":
        extra = " AND ac.goal_id IS NOT NULL"
    elif source == "unlinked":
        extra = " AND ac.goal_id IS NULL AND ac.routine_id IS NULL"

    return df(
        f"""
        SELECT ac.*, g.title AS goal_title, ar.name AS area_name, ar.google_color AS area_color, r.title AS routine_title
        FROM actions ac
        LEFT JOIN goals g ON g.id = ac.goal_id
        LEFT JOIN routines r ON r.id = ac.routine_id
        LEFT JOIN areas ar ON ar.id = ac.area_id
        WHERE ac.routine_id IS NULL AND ac.status IN ('Next','Scheduled','Planned') AND ac.archived_at IS NULL {extra}
        ORDER BY CASE ac.priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 WHEN 'Low' THEN 3 ELSE 4 END,
                 CASE ac.status WHEN 'Next' THEN 1 WHEN 'Scheduled' THEN 2 WHEN 'Planned' THEN 3 ELSE 4 END,
                 ac.due_date IS NULL, ac.due_date, ac.title
        """
    )

def weekly_actions_df(source: str = "all") -> pd.DataFrame:
    """Rows shown on the printable tasklist. Routine activities are ordered by time."""
    if source == "routines":
        return planned_actions_df("routines")

    focus_id = weekly_focus_goal_id()
    source_filter = ""
    if source == "goals":
        source_filter = " AND ac.goal_id IS NOT NULL"
    elif source == "unlinked":
        source_filter = " AND ac.goal_id IS NULL AND ac.routine_id IS NULL"

    if focus_id:
        return df(
            f"""
            SELECT ac.*, g.title AS goal_title, ar.name AS area_name, ar.google_color AS area_color, r.title AS routine_title
            FROM actions ac
            LEFT JOIN goals g ON g.id = ac.goal_id
            LEFT JOIN routines r ON r.id = ac.routine_id
            LEFT JOIN areas ar ON ar.id = ac.area_id
            WHERE ac.routine_id IS NULL AND ac.status IN ('Next','Scheduled','Planned') AND ac.archived_at IS NULL {source_filter}
            ORDER BY CASE WHEN ac.goal_id = ? THEN 0 ELSE 1 END,
                     CASE ac.priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 WHEN 'Low' THEN 3 ELSE 4 END,
                     CASE ac.status WHEN 'Next' THEN 1 WHEN 'Scheduled' THEN 2 WHEN 'Planned' THEN 3 ELSE 4 END,
                     ac.due_date IS NULL, ac.due_date, ac.title
            """,
            (focus_id,),
        )
    return planned_actions_df(source)

def select_rows_table(table: pd.DataFrame, key: str) -> list[int]:
    """Render a table that supports row selection when the installed Streamlit version allows it."""
    try:
        event = st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
            key=key,
            on_select="rerun",
            selection_mode="multi-row",
        )
        selected = getattr(event, "selection", None)
        if selected is None and isinstance(event, dict):
            selected = event.get("selection", {})
        rows = selected.rows if hasattr(selected, "rows") else selected.get("rows", []) if isinstance(selected, dict) else []
        return [int(i) for i in rows]
    except TypeError:
        st.dataframe(table, use_container_width=True, hide_index=True)
        return []


def routines_df(active_only: bool = False) -> pd.DataFrame:
    where = "WHERE r.status = 'Active'" if active_only else ""
    return df(
        f"""
        SELECT r.*, a.name AS area_name, a.google_color AS area_color
        FROM routines r LEFT JOIN areas a ON a.id = r.area_id
        {where}
        ORDER BY r.status, r.next_due IS NULL, r.next_due, r.title
        """
    )


def review_df(open_only: bool = True) -> pd.DataFrame:
    where = "WHERE status = 'Open'" if open_only else ""
    return df(f"SELECT * FROM review_issues {where} ORDER BY CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, created_at DESC")


def calendar_df(extra_where: str = "", params: tuple = ()) -> pd.DataFrame:
    return df(
        f"""
        SELECT cb.*, ar.name AS area_name, ar.google_color AS area_color, g.title AS goal_title, r.title AS routine_title, ac.title AS action_title
        FROM calendar_blocks cb
        LEFT JOIN areas ar ON ar.id = cb.area_id
        LEFT JOIN goals g ON g.id = cb.goal_id
        LEFT JOIN routines r ON r.id = cb.routine_id
        LEFT JOIN actions ac ON ac.id = cb.action_id
        {extra_where}
        ORDER BY cb.start_datetime IS NULL, cb.start_datetime, cb.title
        """,
        params,
    )


def reminders_df(extra_where: str = "", params: tuple = ()) -> pd.DataFrame:
    return df(
        f"""
        SELECT rt.*, ar.name AS area_name, ar.google_color AS area_color, g.title AS goal_title, r.title AS routine_title, r.frequency AS repeat_pattern, ac.title AS action_title,
               cb.title AS linked_calendar_title, cb.start_datetime AS linked_calendar_start, cb.end_datetime AS linked_calendar_end,
               CASE WHEN cb.id IS NOT NULL THEN cb.title || ' (' || COALESCE(cb.start_datetime,'') || ')' ELSE '' END AS linked_calendar_summary
        FROM reminder_tasks rt
        LEFT JOIN areas ar ON ar.id = rt.area_id
        LEFT JOIN goals g ON g.id = rt.goal_id
        LEFT JOIN routines r ON r.id = rt.routine_id
        LEFT JOIN actions ac ON ac.id = rt.action_id
        LEFT JOIN calendar_blocks cb ON cb.id = rt.linked_calendar_block_id
        {extra_where}
        ORDER BY rt.due_date IS NULL, rt.due_date, rt.title
        """,
        params,
    )


def select_options_from_df(data: pd.DataFrame, label_col: str = "title", id_col: str = "id") -> dict[str, int]:
    if data.empty:
        return {}
    return {f"{row[label_col]}": int(row[id_col]) for _, row in data.iterrows()}


def area_options(include_all: bool = False) -> list[str]:
    data = areas_df(active_only=True)
    opts = [] if not include_all else ["All areas"]
    if data.empty:
        return opts
    return opts + data["name"].dropna().sort_values().tolist()


def area_id_by_name(name: str | None) -> int | None:
    if not name or name == "All areas":
        return None
    return scalar("SELECT id FROM areas WHERE name = ?", (name,))

# -----------------------------------------------------------------------------
# Review, staging, export, archive services
# -----------------------------------------------------------------------------


def generate_review_issues() -> None:
    execute("DELETE FROM review_issues WHERE status = 'Open'")
    for goal in query("SELECT g.*, a.name AS area_name FROM goals g LEFT JOIN areas a ON a.id = g.area_id WHERE g.archived_at IS NULL"):
        if goal["status"] == "Captured":
            add_review("Medium", "Goal", goal["title"], "goal", goal["id"], "This goal has been captured but not yet planned.", "Decide whether it should become active, go on hold, or be archived as abandoned.")
        if goal["status"] == "Active" and not (goal["closure_criteria"] or "").strip():
            add_review("High", "Goal", goal["title"], "goal", goal["id"], "This active goal has no closure criteria.", "Add a short statement describing what would make it complete enough to archive.")
        next_count = scalar("SELECT COUNT(*) FROM actions WHERE goal_id = ? AND status IN ('Next','Scheduled','Planned') AND archived_at IS NULL", (goal["id"],)) or 0
        if goal["status"] == "Active" and next_count == 0:
            add_review("High", "Goal", goal["title"], "goal", goal["id"], "This active goal has no planned actions.", "Add the next action under the goal.")
        if goal["status"] == "On hold":
            add_review("Low", "Goal", goal["title"], "goal", goal["id"], "This goal is on hold.", "Confirm whether it should stay on hold, become active, or be archived.")

    for action in query("SELECT ac.*, COALESCE(g.title, r.title, ar.name) AS source FROM actions ac LEFT JOIN goals g ON g.id = ac.goal_id LEFT JOIN routines r ON r.id = ac.routine_id LEFT JOIN areas ar ON ar.id = ac.area_id WHERE ac.archived_at IS NULL"):
        if not action["goal_id"] and not action["routine_id"]:
            add_review("Medium", "Action", action["title"], "action", action["id"], "This action is not linked to a goal or routine.", "Link it to a goal, link it to a routine, or archive it if it is no longer needed.")
        if action["status"] == "Done":
            add_review("Low", "Action", action["title"], "action", action["id"], "This action is marked done but remains active.", "Archive it, or add any carry-forward action that still matters.")
        if not action.get("routine_id"):
            if action["calendar_block"] and not scalar("SELECT COUNT(*) FROM calendar_blocks WHERE action_id = ? AND export_status != 'Removed'", (action["id"],)):
                add_review("Medium", "Action", action["title"], "action", action["id"], "This action is marked for Google Calendar but has no export row.", "Run staging for Google Calendar or clear the calendar option.")
            if action["reminder"] and not scalar("SELECT COUNT(*) FROM reminder_tasks WHERE action_id = ? AND export_status != 'Removed'", (action["id"],)):
                add_review("Medium", "Action", action["title"], "action", action["id"], "This action is marked for Google Tasks but has no export row.", "Run staging for Google Tasks or clear the prompt option.")

    for action in query("SELECT ac.*, COALESCE(g.title, r.title, ar.name) AS source FROM actions ac LEFT JOIN goals g ON g.id = ac.goal_id LEFT JOIN routines r ON r.id = ac.routine_id LEFT JOIN areas ar ON ar.id = ac.area_id WHERE ac.archived_at IS NULL AND ac.routine_id IS NULL"):
        if action["reminder"] and not (action["first_step"] or "").strip():
            add_review("High", "Action", action["title"], "action", action["id"], "This action is prepared for Google Tasks but has no starting prompt.", "Add a short first cue so the Google Task reduces friction to begin.")
        if action["calendar_block"] and not (action["scheduled_date"] or action["due_date"]):
            add_review("High", "Action", action["title"], "action", action["id"], "This action is prepared for Google Calendar but has no date.", "Add a scheduled date or due date before preparing calendar export rows.")
        if action["calendar_block"] and action.get("calendar_start_time") and action.get("calendar_end_time") and str(action["calendar_end_time"]) <= str(action["calendar_start_time"]):
            add_review("High", "Action", action["title"], "action", action["id"], "This action’s Google Calendar end time is not after its start time.", "Adjust the calendar start and end times.")

    for routine in query("SELECT r.*, a.name AS area_name, a.folder_path, a.markdown_path FROM routines r LEFT JOIN areas a ON a.id = r.area_id WHERE r.status = 'Active'"):
        if not (routine["purpose"] or "").strip():
            add_review("Medium", "Routine", routine["title"], "routine", routine["id"], "This routine has no purpose recorded.", "Add a practical sentence describing what this routine maintains.")
        if routine["reminder"] and not (routine["starting_prompt"] or "").strip():
            add_review("High", "Routine", routine["title"], "routine", routine["id"], "This routine is prepared for Google Tasks but has no starting prompt.", "Add a short first cue such as ‘Put the mat out’ or ‘Open the meal plan’.")
        activity_count = scalar("SELECT COUNT(*) FROM actions WHERE routine_id=? AND archived_at IS NULL", (routine["id"],))
        if routine["status"] == "Active" and not activity_count:
            add_review("Medium", "Routine", routine["title"], "routine", routine["id"], "This active routine has no activities.", "Add the repeated activities that make up this routine.")
        if (routine["frequency"] or "") not in ("", "Does not repeat", "As needed") and not frequency_to_rrule(routine["frequency"]):
            add_review("Medium", "Routine", routine["title"], "routine", routine["id"], "This routine has a repeat pattern that may not export as an ICS recurrence rule.", "Use the Repeat tab to choose a supported daily, weekly, or monthly pattern.")

    for area in query("SELECT * FROM areas ORDER BY name"):
        folder = Path(area["folder_path"] or "")
        md = Path(area["markdown_path"] or "")
        if folder and not folder.exists():
            add_review("Low", "Area", area["name"], "area", area["id"], "This area’s folder has not been created yet.", "Create missing folders and Markdown from Settings or update the folder path.")
        if md and not md.exists():
            add_review("Low", "Area", area["name"], "area", area["id"], "This area’s Markdown file has not been created yet.", "Generate Markdown from Settings or update the Markdown path.")


def add_review(priority: str, type_: str, source: str, entity_type: str, entity_id: int, message: str, suggested: str) -> None:
    execute(
        "INSERT INTO review_issues (priority, type, source, entity_type, entity_id, message, suggested_step) VALUES (?,?,?,?,?,?,?)",
        (priority, type_, source, entity_type, entity_id, message, suggested),
    )



def frequency_to_rrule(frequency: str | None) -> str:
    """Convert Google Calendar-style repeat text into an ICS RRULE."""
    if not frequency:
        return ""
    freq = str(frequency).strip()
    if freq in {"As needed", "Does not repeat"}:
        return ""
    day_codes = {"Monday":"MO", "Tuesday":"TU", "Wednesday":"WE", "Thursday":"TH", "Friday":"FR", "Saturday":"SA", "Sunday":"SU"}
    if freq == "Daily":
        return "RRULE:FREQ=DAILY;INTERVAL=1"
    if freq == "Weekdays":
        return "RRULE:FREQ=WEEKLY;INTERVAL=1;BYDAY=MO,TU,WE,TH,FR"
    import re
    m = re.match(r"Every (\d+) days?", freq)
    if m:
        return f"RRULE:FREQ=DAILY;INTERVAL={m.group(1)}"
    m = re.match(r"Weekly on (.+)", freq)
    if m:
        day_text = m.group(1).replace(" and ", ", ")
        days = [day_codes[d.strip()] for d in day_text.split(',') if d.strip() in day_codes]
        byday = ";BYDAY=" + ",".join(days) if days else ""
        return f"RRULE:FREQ=WEEKLY;INTERVAL=1{byday}"
    m = re.match(r"Every (\d+) weeks? on (.+)", freq)
    if m:
        day_text = m.group(2).replace(" and ", ", ")
        days = [day_codes[d.strip()] for d in day_text.split(',') if d.strip() in day_codes]
        byday = ";BYDAY=" + ",".join(days) if days else ""
        return f"RRULE:FREQ=WEEKLY;INTERVAL={m.group(1)}{byday}"
    m = re.match(r"Monthly on day (\d+)", freq)
    if m:
        return f"RRULE:FREQ=MONTHLY;INTERVAL=1;BYMONTHDAY={m.group(1)}"
    m = re.match(r"Every (\d+) months? on day (\d+)", freq)
    if m:
        return f"RRULE:FREQ=MONTHLY;INTERVAL={m.group(1)};BYMONTHDAY={m.group(2)}"
    m = re.match(r"Monthly on the (first|second|third|fourth|last) (Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)", freq, re.I)
    if m:
        ord_map = {"first":"1", "second":"2", "third":"3", "fourth":"4", "last":"-1"}
        return f"RRULE:FREQ=MONTHLY;INTERVAL=1;BYDAY={ord_map[m.group(1).lower()]}{day_codes[m.group(2).title()]}"
    m = re.match(r"Every (\d+) months? on the (first|second|third|fourth|last) (Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)", freq, re.I)
    if m:
        ord_map = {"first":"1", "second":"2", "third":"3", "fourth":"4", "last":"-1"}
        return f"RRULE:FREQ=MONTHLY;INTERVAL={m.group(1)};BYDAY={ord_map[m.group(2).lower()]}{day_codes[m.group(3).title()]}"
    return ""


def normalise_activity_days(value: str | None) -> list[str]:
    if not value:
        return []
    days = []
    for part in str(value).replace(";", ",").split(","):
        day = part.strip().title()
        if day in WEEKDAY_INDEX and day not in days:
            days.append(day)
    return days


def infer_activity_days_from_import(row: dict[str, Any]) -> str:
    """Infer activity day(s) for legacy imported routine activities.

    This is deliberately conservative and only runs when activity_days is blank.
    It uses explicit weekday words first, then falls back to the scheduled/due date.
    """
    text = " ".join(str(row.get(k) or "") for k in ["title", "notes", "description"]).lower()
    if "weekday" in text or "week day" in text:
        return "Monday,Tuesday,Wednesday,Thursday,Friday"
    found: list[str] = []
    for day in WEEKDAY_INDEX:
        if day.lower() in text and day not in found:
            found.append(day)
    if found:
        return ",".join(found)
    d = parse_date(row.get("scheduled_date") or row.get("due_date"))
    if d:
        return list(WEEKDAY_INDEX.keys())[d.weekday()]
    return ""


def join_days_for_display(days: list[str]) -> str:
    if not days:
        return ""
    if len(days) == 1:
        return days[0]
    return ", ".join(days[:-1]) + " and " + days[-1]


def rrule_with_activity_days(frequency: str | None, activity_days: str | None) -> str:
    """Return an ICS RRULE for a routine activity.

    The parent routine defines the repeat interval. Weekly activities can then
    choose the day or days they happen on, as in Google Calendar.
    """
    base = frequency_to_rrule(frequency)
    days = normalise_activity_days(activity_days)
    if not days:
        return base
    codes = {"Monday":"MO", "Tuesday":"TU", "Wednesday":"WE", "Thursday":"TH", "Friday":"FR", "Saturday":"SA", "Sunday":"SU"}
    byday = ",".join(codes[d] for d in days)
    if "FREQ=WEEKLY" in base:
        if ";BYDAY=" in base:
            return re.sub(r";BYDAY=[^;]+", f";BYDAY={byday}", base)
        return base + f";BYDAY={byday}"
    # If the parent is not explicitly weekly, keep the parent rule. Activity days
    # are still shown in the UI and used for task occurrence generation only when appropriate.
    return base


WEEKDAY_INDEX = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, py_calendar.monthrange(year, month)[1])
    return date(year, month, day)


def nth_weekday_of_month(year: int, month: int, weekday: int, ordinal: str) -> date:
    days = []
    last_day = py_calendar.monthrange(year, month)[1]
    for day in range(1, last_day + 1):
        candidate = date(year, month, day)
        if candidate.weekday() == weekday:
            days.append(candidate)
    if not days:
        return date(year, month, 1)
    if ordinal.lower() == "last":
        return days[-1]
    idx = {"first": 0, "second": 1, "third": 2, "fourth": 3}.get(ordinal.lower(), 0)
    return days[min(idx, len(days) - 1)]


def routine_occurrence_dates(frequency: str | None, start: date, count: int = 8) -> list[date]:
    """Generate individual Google Tasks due dates for a repeating routine.

    Google Calendar can import one recurring VEVENT via RRULE. The Google Tasks
    Apps Script importer creates one task per CSV row, so repeated routines need
    repeated task rows.
    """
    import re
    freq = (frequency or "Does not repeat").strip()
    if freq in {"", "Does not repeat", "As needed"}:
        return [start]

    if freq == "Daily":
        return [start + timedelta(days=i) for i in range(count)]
    m = re.match(r"Every (\d+) days?", freq, re.I)
    if m:
        step = max(1, int(m.group(1)))
        return [start + timedelta(days=i * step) for i in range(count)]

    if freq == "Weekdays":
        out = []
        cur = start
        while len(out) < count:
            if cur.weekday() < 5:
                out.append(cur)
            cur += timedelta(days=1)
        return out

    weekly = re.match(r"Weekly on (.+)", freq, re.I)
    every_weeks = re.match(r"Every (\d+) weeks? on (.+)", freq, re.I)
    if weekly or every_weeks:
        interval = 1 if weekly else max(1, int(every_weeks.group(1)))
        day_text = (weekly.group(1) if weekly else every_weeks.group(2)).replace(" and ", ", ")
        wanted = [WEEKDAY_INDEX[d.strip().title()] for d in day_text.split(",") if d.strip().title() in WEEKDAY_INDEX]
        if not wanted:
            wanted = [start.weekday()]
        out = []
        cur = start
        anchor_monday = start - timedelta(days=start.weekday())
        while len(out) < count:
            weeks_since = (cur - anchor_monday).days // 7
            if weeks_since % interval == 0 and cur.weekday() in wanted and cur >= start:
                out.append(cur)
            cur += timedelta(days=1)
        return out

    monthly_day = re.match(r"Monthly on day (\d+)", freq, re.I)
    every_monthly_day = re.match(r"Every (\d+) months? on day (\d+)", freq, re.I)
    if monthly_day or every_monthly_day:
        interval = 1 if monthly_day else max(1, int(every_monthly_day.group(1)))
        wanted_day = int(monthly_day.group(1) if monthly_day else every_monthly_day.group(2))
        out = []
        month_offset = 0
        while len(out) < count:
            base = add_months(start.replace(day=1), month_offset)
            last = py_calendar.monthrange(base.year, base.month)[1]
            candidate = date(base.year, base.month, min(wanted_day, last))
            if candidate >= start:
                out.append(candidate)
            month_offset += interval
        return out

    monthly_ord = re.match(r"Monthly on the (first|second|third|fourth|last) (Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)", freq, re.I)
    every_monthly_ord = re.match(r"Every (\d+) months? on the (first|second|third|fourth|last) (Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)", freq, re.I)
    if monthly_ord or every_monthly_ord:
        interval = 1 if monthly_ord else max(1, int(every_monthly_ord.group(1)))
        ordinal = monthly_ord.group(1) if monthly_ord else every_monthly_ord.group(2)
        day_name = (monthly_ord.group(2) if monthly_ord else every_monthly_ord.group(3)).title()
        weekday = WEEKDAY_INDEX[day_name]
        out = []
        month_offset = 0
        while len(out) < count:
            base = add_months(start.replace(day=1), month_offset)
            candidate = nth_weekday_of_month(base.year, base.month, weekday, ordinal)
            if candidate >= start:
                out.append(candidate)
            month_offset += interval
        return out

    return [start]



def routine_activity_occurrence_dates(frequency: str | None, start: date, activity_days: str | None, count: int = 8) -> list[date]:
    """Generate occurrence dates for one routine activity.

    Routine repeat controls define the repeating pattern. For weekly routines,
    individual activities can choose their own day(s) within that repeat.
    """
    days = normalise_activity_days(activity_days)
    freq = (frequency or "Does not repeat").strip()
    if days and ("Weekly" in freq or "weeks" in freq or freq == "Weekdays"):
        import re
        interval = 1
        m = re.match(r"Every (\d+) weeks?", freq, re.I)
        if m:
            interval = max(1, int(m.group(1)))
        wanted = [WEEKDAY_INDEX[d] for d in days]
        out: list[date] = []
        cur = start
        anchor_monday = start - timedelta(days=start.weekday())
        while len(out) < count:
            weeks_since = (cur - anchor_monday).days // 7
            if weeks_since % interval == 0 and cur.weekday() in wanted and cur >= start:
                out.append(cur)
            cur += timedelta(days=1)
        return out
    return routine_occurrence_dates(frequency, start, count=count)


def linked_calendar_note(calendar_row: dict[str, Any] | None) -> str:
    if not calendar_row:
        return ""
    title = calendar_row.get("title") or "Calendar time"
    start = display_datetime(calendar_row.get("start_datetime")) if calendar_row.get("start_datetime") else ""
    end = display_datetime(calendar_row.get("end_datetime")) if calendar_row.get("end_datetime") else ""
    cal = calendar_row.get("calendar_name") or "Google Calendar"
    when = f"{start} to {end}" if start and end else start or end
    return f"Related Google Calendar item: {title}" + (f" ({when})" if when else "") + f" in {cal}. If the calendar time or task prompt changes, update the linked item as well."


def reminder_note(starting_prompt: str, base_note: str, calendar_row: dict[str, Any] | None) -> str:
    parts = []
    linked = linked_calendar_note(calendar_row)
    if linked:
        parts.append(linked)
    if starting_prompt:
        parts.append(f"Starting prompt: {starting_prompt}")
    if base_note:
        parts.append(str(base_note))
    return "\n\n".join(parts)


def routine_task_lines(routine_id: int, include_paused: bool = False) -> list[str]:
    where = "WHERE routine_id=? AND archived_at IS NULL"
    params: tuple[Any, ...] = (routine_id,)
    if not include_paused:
        where += " AND COALESCE(status,'Included') != 'Paused'"
    rows = query(
        f"""SELECT title, status, notes, calendar_start_time, calendar_end_time
             FROM actions {where}
             ORDER BY calendar_start_time IS NULL, calendar_start_time, title""",
        params,
    )
    out = []
    for r in rows:
        title = str(r.get("title") or "").strip()
        if not title:
            continue
        start = str(r.get("calendar_start_time") or "").strip()
        end = str(r.get("calendar_end_time") or "").strip()
        time_text = f" ({start}–{end})" if start and end else f" ({start})" if start else ""
        out.append(title + time_text)
    return out

def routine_task_note_block(routine_id: int) -> str:
    lines = routine_task_lines(routine_id)
    if not lines:
        return ""
    return "Routine activities:\n" + "\n".join(f"- {line}" for line in lines)


def parse_clock_time(value: Any, default: str = "09:00") -> time:
    """Parse a user-entered time. Accepts HH:MM, H:MM, and simple H values."""
    if value in (None, ""):
        value = default
    text = str(value).strip().lower().replace(".", ":")
    for suffix in ["am", "pm"]:
        if text.endswith(suffix):
            raw = text[:-2].strip()
            try:
                hour, minute = (raw.split(":") + ["0"])[:2]
                h = int(hour); m = int(minute)
                if suffix == "pm" and h != 12:
                    h += 12
                if suffix == "am" and h == 12:
                    h = 0
                return time(h, m)
            except Exception:
                break
    try:
        hour, minute = (text.split(":") + ["0"])[:2]
        return time(int(hour), int(minute))
    except Exception:
        h, m = default.split(":")[:2]
        return time(int(h), int(m))


def event_bounds_for_export(date_text: Any, start_text: Any, end_text: Any) -> tuple[str, str]:
    """Return start/end strings for export, preserving intended duration.

    Users often enter afternoon end times as `3:00` rather than `15:00`.
    If the end is earlier than the start and looks like afternoon shorthand,
    treat it as PM; otherwise fall back to a one-hour block.
    """
    d = parse_date(date_text) or date.today()
    start_t = parse_clock_time(start_text, "09:00")
    end_t = parse_clock_time(end_text, "10:00")
    start_dt = datetime.combine(d, start_t)
    end_dt = datetime.combine(d, end_t)
    raw_end = "" if end_text is None else str(end_text).strip().lower()
    if end_dt <= start_dt and ("am" not in raw_end and "pm" not in raw_end) and 1 <= end_t.hour <= 7:
        end_dt = datetime.combine(d, time(end_t.hour + 12, end_t.minute))
    if end_dt <= start_dt:
        end_dt = start_dt + timedelta(hours=1)
    return start_dt.strftime("%Y-%m-%d %H:%M"), end_dt.strftime("%Y-%m-%d %H:%M")

def stage_exports_from_actions(area_id: int | None = None, routine_task_occurrences: int = 1) -> None:
    """Prepare Google Calendar and Google Tasks rows.

    Goal actions are once-off work items. Routine activities are repeating activities
    that inherit the parent routine repeat pattern but keep their own time/location.
    """
    # Remove obsolete staged rows before regenerating. Exported rows are preserved as a record.
    execute("""UPDATE calendar_blocks SET export_status='Removed', removed_at=CURRENT_TIMESTAMP
               WHERE action_id IN (SELECT id FROM actions WHERE status='Done')
                 AND export_status='Staged'""")
    execute("""UPDATE reminder_tasks SET export_status='Removed', removed_at=CURRENT_TIMESTAMP
               WHERE action_id IN (SELECT id FROM actions WHERE status='Done')
                 AND export_status='Staged'""")

    # Goal actions: only active planned/next/scheduled rows, no recurrence unless explicitly stored.
    params: tuple = ()
    where = "WHERE archived_at IS NULL AND routine_id IS NULL AND status != 'Done' AND (calendar_block = 1 OR reminder = 1)"
    if area_id is not None:
        where += " AND area_id = ?"
        params = (area_id,)

    for action in query(f"SELECT * FROM actions {where}", params):
        area = query("SELECT * FROM areas WHERE id = ?", (action["area_id"],))
        cal = area[0]["default_calendar"] if area else "Google Calendar"
        task_list = area[0]["default_task_list"] if area else "Pathmark"
        start_dt = action["scheduled_date"] or action["due_date"] or str(date.today()+timedelta(days=1))
        start_time = action.get("calendar_start_time") or "09:00"
        end_time = action.get("calendar_end_time") or "10:00"
        start, end = event_bounds_for_export(start_dt, start_time, end_time)
        if action["calendar_block"] and not scalar("SELECT COUNT(*) FROM calendar_blocks WHERE action_id = ? AND export_status != 'Removed'", (action["id"],)):
            execute(
                """INSERT INTO calendar_blocks (action_id, goal_id, routine_id, area_id, title, description, start_datetime, end_datetime, location, calendar_name, recurrence_rule, alarm_minutes, export_status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'Staged')""",
                (action["id"], action["goal_id"], action["routine_id"], action["area_id"], action["title"], action["notes"] or action["description"], start, end, action.get("calendar_location") or "", cal, action.get("recurrence_rule") or "", 10),
            )
        if action["reminder"] and not scalar("SELECT COUNT(*) FROM reminder_tasks WHERE action_id = ? AND export_status != 'Removed'", (action["id"],)):
            linked = scalar("SELECT id FROM calendar_blocks WHERE action_id = ? AND export_status != 'Removed' ORDER BY id DESC LIMIT 1", (action["id"],))
            linked_row = query("SELECT * FROM calendar_blocks WHERE id = ?", (linked,))[0] if linked else None
            starting_prompt = action.get("first_step") or action["title"]
            notes_text = reminder_note(starting_prompt, action.get("notes") or action.get("description") or "", linked_row)
            execute(
                """INSERT INTO reminder_tasks (action_id, goal_id, routine_id, area_id, title, notes, due_date, reminder_time, task_list, export_status, linked_calendar_block_id, repeat_pattern, linked_calendar_summary)
                   VALUES (?,?,?,?,?,?,?,?,?, 'Staged', ?, ?, ?)""",
                (action["id"], action["goal_id"], action["routine_id"], action["area_id"], starting_prompt, notes_text, action.get("scheduled_date") or action.get("due_date"), action.get("task_reminder_time") or "09:00", task_list, linked, "", linked_calendar_note(linked_row)),
            )

    # Routine activities: each activity can create its own recurring calendar block.
    activity_where = """WHERE ac.archived_at IS NULL
                         AND ac.routine_id IS NOT NULL
                         AND COALESCE(ac.status,'Included') != 'Paused'
                         AND (COALESCE(ac.calendar_block,0)=1 OR COALESCE(ac.reminder,0)=1)"""
    activity_params: tuple = ()
    if area_id is not None:
        activity_where += " AND ac.area_id = ?"
        activity_params = (area_id,)
    activities = query(
        f"""SELECT ac.*, r.title AS routine_title, r.frequency AS routine_frequency, r.next_due AS routine_next_due, r.purpose AS routine_purpose
             FROM actions ac LEFT JOIN routines r ON r.id = ac.routine_id {activity_where}""",
        activity_params,
    )
    for activity in activities:
        area = query("SELECT * FROM areas WHERE id = ?", (activity["area_id"],))
        default_calendar = area[0]["default_calendar"] if area else "Google Calendar"
        task_list = area[0]["default_task_list"] if area else "Pathmark"
        start_seed = activity.get("scheduled_date") or activity.get("due_date") or activity.get("routine_next_due") or str(date.today()+timedelta(days=1))
        occurrence_seed = parse_date(start_seed) or date.today()
        first_occurrence = routine_activity_occurrence_dates(activity.get("routine_frequency"), occurrence_seed, activity.get("activity_days"), count=1)[0]
        start_date = str(first_occurrence)
        start_time = activity.get("calendar_start_time") or "09:00"
        end_time = activity.get("calendar_end_time") or "10:00"
        start, end = event_bounds_for_export(start_date, start_time, end_time)
        recurrence = rrule_with_activity_days(activity.get("routine_frequency"), activity.get("activity_days"))
        # Regenerate staged rows for this activity so edited times/prompts do not leave stale rows.
        execute("DELETE FROM calendar_blocks WHERE action_id=? AND export_status='Staged'", (activity["id"],))
        execute("DELETE FROM reminder_tasks WHERE action_id=? AND export_status='Staged'", (activity["id"],))
        linked = None
        if activity.get("calendar_block"):
            description = "\n\n".join(part for part in [f"Routine: {activity.get('routine_title') or ''}", activity.get("notes") or activity.get("description") or ""] if part)
            execute(
                """INSERT INTO calendar_blocks (action_id, goal_id, routine_id, area_id, title, description, start_datetime, end_datetime, location, calendar_name, recurrence_rule, alarm_minutes, export_status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'Staged')""",
                (activity["id"], None, activity["routine_id"], activity["area_id"], activity["title"], description, start, end, activity.get("calendar_location") or "", default_calendar, recurrence, 10),
            )
            linked = scalar("SELECT id FROM calendar_blocks WHERE action_id=? AND export_status='Staged' ORDER BY id DESC LIMIT 1", (activity["id"],))
        linked_row = query("SELECT * FROM calendar_blocks WHERE id=?", (linked,))[0] if linked else None
        if activity.get("reminder"):
            starting_prompt = activity.get("first_step") or activity["title"]
            occurrence_start = parse_date(start_date) or date.today()
            occurrence_count = max(1, int(routine_task_occurrences or 1))
            occurrences = routine_activity_occurrence_dates(activity.get("routine_frequency"), occurrence_start, activity.get("activity_days"), count=occurrence_count)
            for occurrence in occurrences:
                occurrence_note = reminder_note(
                    starting_prompt,
                    "\n\n".join(part for part in [
                        f"Routine: {activity.get('routine_title') or ''}",
                        activity.get("notes") or activity.get("description") or "",
                        f"Prompt occurrence: {friendly_date(occurrence)}.",
                        f"Repeat pattern: {activity.get('routine_frequency') or 'Does not repeat'}."
                    ] if part),
                    linked_row,
                )
                execute(
                    """INSERT INTO reminder_tasks (action_id, goal_id, routine_id, area_id, title, notes, due_date, reminder_time, task_list, export_status, linked_calendar_block_id, repeat_pattern, linked_calendar_summary)
                       VALUES (?,?,?,?,?,?,?,?,?, 'Staged', ?, ?, ?)""",
                    (activity["id"], None, activity["routine_id"], activity["area_id"], starting_prompt, occurrence_note, str(occurrence), activity.get("task_reminder_time") or start_time, task_list, linked, activity.get("routine_frequency") or "", linked_calendar_note(linked_row)),
                )

    # Remove legacy routine-level staged exports; routine activities now own the time blocks.
    execute("UPDATE calendar_blocks SET export_status='Removed', removed_at=CURRENT_TIMESTAMP WHERE action_id IS NULL AND routine_id IS NOT NULL AND export_status='Staged'")
    execute("UPDATE reminder_tasks SET export_status='Removed', removed_at=CURRENT_TIMESTAMP WHERE action_id IS NULL AND routine_id IS NOT NULL AND export_status='Staged'")

def archive_goal_with_review(goal_id: int, final_status: str, summary: str, went_well: str, did_not_go_well: str, carried_forward: str) -> None:
    goal = query("SELECT g.*, a.name AS area_name FROM goals g LEFT JOIN areas a ON a.id = g.area_id WHERE g.id = ?", (goal_id,))[0]
    actions = query("SELECT * FROM actions WHERE goal_id = ?", (goal_id,))
    snapshot = {"goal": goal, "actions": actions}
    execute(
        """INSERT INTO archive_entries (entity_type, entity_id, title, final_status, summary, went_well, did_not_go_well, carried_forward, snapshot_json)
           VALUES ('goal',?,?,?,?,?,?,?,?)""",
        (goal_id, goal["title"], final_status, summary, went_well, did_not_go_well, carried_forward, json.dumps(snapshot, default=str)),
    )
    execute("UPDATE goals SET status = ?, archived_at = CURRENT_TIMESTAMP, closed_at = CURRENT_TIMESTAMP WHERE id = ?", (final_status, goal_id))


def archive_routine(routine_id: int, final_status: str, summary: str) -> None:
    routine = query("SELECT r.*, a.name AS area_name FROM routines r LEFT JOIN areas a ON a.id = r.area_id WHERE r.id = ?", (routine_id,))[0]
    execute(
        """INSERT INTO archive_entries (entity_type, entity_id, title, final_status, summary, snapshot_json)
           VALUES ('routine',?,?,?,?,?)""",
        (routine_id, routine["title"], final_status, summary, json.dumps({"routine": routine}, default=str)),
    )
    execute("UPDATE routines SET status = 'Retired', archived_at = CURRENT_TIMESTAMP WHERE id = ?", (routine_id,))


def restore_archive_entry(entry_id: int) -> None:
    entry = query("SELECT * FROM archive_entries WHERE id = ?", (entry_id,))
    if not entry:
        return
    e = entry[0]
    add_review("Medium", "Archive", e["title"], e["entity_type"], e["entity_id"], "This archived item was marked for review or reconstruction.", "Open the archive detail and promote the goal, routine, or action back to its origin if needed.")


def _row_exists(table: str, row_id: int) -> bool:
    return bool(scalar(f"SELECT COUNT(*) FROM {table} WHERE id = ?", (row_id,)))


def _insert_from_snapshot(table: str, snapshot_row: dict[str, Any], allowed_fields: list[str], overrides: dict[str, Any] | None = None) -> int:
    overrides = overrides or {}
    data = {field: snapshot_row.get(field) for field in allowed_fields if field in snapshot_row}
    data.update(overrides)
    cols = list(data.keys())
    placeholders = ",".join("?" for _ in cols)
    cur = conn().execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})", tuple(data[c] for c in cols))
    conn().commit()
    return int(cur.lastrowid)


def promote_archive_entry_to_origin(entry_id: int) -> str:
    rows = query("SELECT * FROM archive_entries WHERE id = ?", (entry_id,))
    if not rows:
        return "Archive item not found."
    entry = rows[0]
    snapshot = {}
    if entry.get("snapshot_json"):
        try:
            snapshot = json.loads(entry["snapshot_json"])
        except Exception:
            snapshot = {}

    entity_type = entry["entity_type"]
    entity_id = int(entry["entity_id"] or 0)

    if entity_type == "goal":
        goal = snapshot.get("goal", {})
        if entity_id and _row_exists("goals", entity_id):
            execute("UPDATE goals SET status='Active', archived_at=NULL, closed_at=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=?", (entity_id,))
            restored_goal_id = entity_id
        else:
            restored_goal_id = _insert_from_snapshot(
                "goals",
                goal,
                ["area_id", "title", "status", "purpose", "desired_outcome", "closure_criteria", "notes"],
                {"status": "Active", "archived_at": None, "closed_at": None},
            )
        restored_actions = 0
        for action in snapshot.get("actions", []) or []:
            action_id = int(action.get("id") or 0)
            if action_id and _row_exists("actions", action_id):
                execute("UPDATE actions SET archived_at=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=?", (action_id,))
                restored_actions += 1
            else:
                _insert_from_snapshot(
                    "actions",
                    action,
                    ["area_id", "routine_id", "title", "description", "status", "priority", "due_date", "scheduled_date", "estimated_minutes", "calendar_block", "reminder", "notes"],
                    {"goal_id": restored_goal_id, "archived_at": None},
                )
                restored_actions += 1
        execute("DELETE FROM archive_entries WHERE id=?", (entry_id,))
        return f"Promoted goal to Goals with {restored_actions} action(s)."

    if entity_type == "routine":
        routine = snapshot.get("routine", {})
        if entity_id and _row_exists("routines", entity_id):
            execute("UPDATE routines SET status='Active', archived_at=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=?", (entity_id,))
        else:
            _insert_from_snapshot(
                "routines",
                routine,
                ["area_id", "title", "core_area", "purpose", "frequency", "next_due", "last_completed", "notes", "checklist"],
                {"status": "Active", "archived_at": None},
            )
        execute("DELETE FROM archive_entries WHERE id=?", (entry_id,))
        return "Promoted routine to Routines."

    if entity_type == "action":
        action = snapshot.get("action", {})
        if entity_id and _row_exists("actions", entity_id):
            execute("UPDATE actions SET archived_at=NULL, status=CASE WHEN status='Done' THEN status ELSE 'Planned' END, updated_at=CURRENT_TIMESTAMP WHERE id=?", (entity_id,))
        else:
            _insert_from_snapshot(
                "actions",
                action,
                ["goal_id", "routine_id", "area_id", "title", "description", "status", "priority", "due_date", "scheduled_date", "activity_days", "estimated_minutes", "calendar_block", "reminder", "include_tasklist", "notes"],
                {"archived_at": None},
            )
        execute("DELETE FROM archive_entries WHERE id=?", (entry_id,))
        return "Promoted action to Actions."

    add_review("Medium", "Archive", entry["title"], entity_type, entity_id, "This archived item could not be promoted automatically.", "Review the archive detail and recreate it manually if needed.")
    return "This archive item could not be promoted automatically, so a review item was created."

# -----------------------------------------------------------------------------
# Files, Markdown, exports
# -----------------------------------------------------------------------------


def write_workspace_readme() -> None:
    """Create a small human-facing guide in the selected Pathmark workspace."""
    try:
        root = root_folder()
        root.mkdir(parents=True, exist_ok=True)
        readme = root / "README - Pathmark workspace.md"
        if readme.exists():
            return
        readme.write_text("""# Pathmark workspace

This folder is your Pathmark workspace. Keep this folder when updating Pathmark.

Pathmark uses this workspace for:

- area folders
- project planning files
- Google Calendar exports
- Google Tasks exports
- tasklists
- backups
- the local Pathmark database inside `00_System`

## Area folder naming

Pathmark works best when each top-level area folder starts with a number:

```text
01_Body_And_Stability
02_Home_And_Garden
03_Making_And_Craft
04_Work_And_Admin
```

The number controls the display order and helps Pathmark know that the folder is an area. `00_System` is reserved for Pathmark's database, exports, backups, and system files.

When you add a new area inside the app, Pathmark suggests the next number automatically. For example, if the highest existing area is `06_Finance`, the next area will be created as `07_New_Area`.

You can still point Pathmark at an existing folder system. Existing folders are not deleted, emptied, or renamed.
""", encoding="utf-8")
    except Exception:
        pass


def create_development_root() -> None:
    # Kept for backwards compatibility with earlier function names. This now creates
    # the configured Pathmark root folder only. pathlib.mkdir(..., exist_ok=True)
    # is non-destructive: it never deletes, empties, or replaces existing folders.
    ensure_core_folders()


def system_folder() -> Path:
    return Path(get_setting("system_folder", str(DEFAULT_SYSTEM_FOLDER)) or str(DEFAULT_SYSTEM_FOLDER)).expanduser()


def calendar_export_folder() -> Path:
    return Path(get_setting("calendar_export_folder", str(DEFAULT_CALENDAR_EXPORT_FOLDER)) or str(DEFAULT_CALENDAR_EXPORT_FOLDER)).expanduser()


def google_tasks_export_folder() -> Path:
    return Path(get_setting("google_tasks_export_folder", str(DEFAULT_GOOGLE_TASKS_EXPORT_FOLDER)) or str(DEFAULT_GOOGLE_TASKS_EXPORT_FOLDER)).expanduser()


def tasklist_export_folder() -> Path:
    return Path(get_setting("tasklist_export_folder", str(DEFAULT_TASKLIST_EXPORT_FOLDER)) or str(DEFAULT_TASKLIST_EXPORT_FOLDER)).expanduser()


def backup_folder() -> Path:
    return Path(get_setting("backup_folder", str(DEFAULT_BACKUP_FOLDER)) or str(DEFAULT_BACKUP_FOLDER)).expanduser()


def ensure_core_folders() -> None:
    # Non-destructive folder creation only. Existing files and non-empty folders are untouched.
    for folder in [root_folder(), system_folder(), calendar_export_folder(), google_tasks_export_folder(), tasklist_export_folder(), backup_folder()]:
        folder.mkdir(parents=True, exist_ok=True)
    write_workspace_readme()
    # Keep the Google Tasks import guide with the user's Google Tasks export folder.
    try:
        write_google_tasks_setup_files()
    except Exception:
        pass


def ensure_area_folder(area_name: str) -> None:
    create_development_root()
    rows = query("SELECT * FROM areas WHERE name = ?", (area_name,))
    if not rows:
        return
    area = rows[0]
    folder = Path(area["folder_path"] or (root_folder() / slug(area_name)))
    folder.mkdir(parents=True, exist_ok=True)
    md_path = Path(area["markdown_path"] or (folder / f"{slug(area_name)}.md"))
    if not md_path.exists():
        md_path.write_text(f"# {area_name}\n\n{area['description'] or ''}\n", encoding="utf-8")


def backup_file_if_exists(path: Path) -> None:
    if not path.exists():
        return
    backup_dir = backup_folder() / "Markdown"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"{path.stem}_{stamp}{path.suffix}"
    shutil.copy2(path, backup)


def regenerate_area_markdown() -> None:
    written = 0
    for area in query("SELECT * FROM areas ORDER BY name"):
        ensure_area_folder(area["name"])
        md = Path(area["markdown_path"] or (Path(area["folder_path"]) / "README.md"))
        goals = query("SELECT * FROM goals WHERE area_id = ? AND archived_at IS NULL ORDER BY status, title", (area["id"],))
        routines = query("SELECT * FROM routines WHERE area_id = ? AND status = 'Active' ORDER BY title", (area["id"],))
        lines = [f"# {area['name']}", "", area["description"] or "", "", "## Goals", ""]
        for g in goals:
            lines += [f"- **{g['title']}** ({g['status']})", f"  - Desired outcome: {g['desired_outcome'] or g['purpose'] or ''}", f"  - Closure criteria: {g['closure_criteria'] or ''}"]
        lines += ["", "## Routines", ""]
        for r in routines:
            lines += [f"- **{r['title']}** ({r['frequency']})", f"  - {r['purpose'] or ''}"]
        backup_file_if_exists(md)
        md.write_text("\n".join(lines).strip()+"\n", encoding="utf-8")
        written += 1
    log_export("Markdown", root_folder(), written, "Area index files")


def regenerate_goal_and_routine_markdown() -> None:
    written = 0
    for area in query("SELECT * FROM areas ORDER BY name"):
        folder = Path(area["folder_path"] or (root_folder() / slug(area["name"])))
        goal_dir = folder / "Goals"
        routine_dir = folder / "Routines"
        goal_dir.mkdir(parents=True, exist_ok=True)
        routine_dir.mkdir(parents=True, exist_ok=True)
        for g in query("SELECT * FROM goals WHERE area_id = ? AND archived_at IS NULL ORDER BY title", (area["id"],)):
            path = goal_dir / f"{slug(g['title'])}.md"
            lines = [
                f"# {g['title']}", "",
                f"Area: {area['name']}",
                f"Status: {g['status']}",
                f"Updated: {display_datetime(g['updated_at'])}", "",
                "## Purpose", "", g['purpose'] or "", "",
                "## Desired outcome", "", g['desired_outcome'] or "", "",
                "## Closure criteria", "", g['closure_criteria'] or "", "",
                "## Actions", "",
            ]
            for a in query("SELECT * FROM actions WHERE goal_id = ? AND archived_at IS NULL ORDER BY status, due_date, title", (g["id"],)):
                due = display_datetime(a["due_date"]) if a["due_date"] else ""
                lines.append(f"- [{ 'x' if a['status']=='Done' else ' ' }] {a['title']} ({a['status']})" + (f" — due {due}" if due else ""))
            backup_file_if_exists(path)
            path.write_text("\n".join(lines).strip()+"\n", encoding="utf-8")
            written += 1
        for r in query("SELECT * FROM routines WHERE area_id = ? ORDER BY status, title", (area["id"],)):
            path = routine_dir / f"{slug(r['title'])}.md"
            checklist = [x.strip() for x in (r['checklist'] or '').splitlines() if x.strip()]
            lines = [
                f"# {r['title']}", "",
                f"Area: {area['name']}",
                f"Specific area: {(r['subarea'] or r['core_area'] or '')}",
                f"Status: {r['status']}",
                f"Repeat: {r['frequency'] or ''}",
                f"Repeat starts: {display_datetime(r['next_due']) if r['next_due'] else ''}", "",
                "## Purpose", "", r['purpose'] or "", "",
                "## Printable checklist", "",
            ]
            lines += [f"- {item}" for item in checklist] or ["No checklist items recorded."]
            backup_file_if_exists(path)
            path.write_text("\n".join(lines).strip()+"\n", encoding="utf-8")
            written += 1
    log_export("Markdown", root_folder(), written, "Goal and routine files")


def ensure_standard_routines() -> int:
    standard = [
        ("Plan the week", "Work And Admin", "Planning and admin", "Decide the week’s main focus, routines, and planned actions.", "Weekly on Monday", "Review active goals\nChoose main focus\nPrepare tasklist"),
        ("Check in with the week", "Work And Admin", "Planning and admin", "Check whether anything is drifting, blocked, too vague, or needs to be rescheduled.", "Weekly on Wednesday", "Open review queue\nCheck tasklist\nAdjust next actions"),
        ("Reset the house", "Home And Garden", "Household reset", "Make the house easier to live and work in next week.", "Weekly on Saturday", "Clear surfaces\nLaundry reset\nKitchen reset\nBins and recycling"),
        ("Review meals, movement, sleep, and stress", "Body And Stability", "Planning and admin", "Check whether core routines are supporting the week.", "Weekly on Sunday", "Meals\nMovement\nSleep\nStress"),
        ("Choose tomorrow’s focus", "Work And Admin", "Planning and admin", "Choose the next day’s first useful action before the evening ends.", "Daily", "Check calendar\nChoose first action\nPrepare anything needed"),
    ]
    created = 0
    areas = {r['name']: r['id'] for r in query("SELECT id, name FROM areas")}
    for title, area, core, purpose, freq, checklist in standard:
        if scalar("SELECT COUNT(*) FROM routines WHERE title=?", (title,)):
            continue
        area_id = areas.get(area) or areas.get("Work And Admin")
        execute("""INSERT INTO routines (title, area_id, subarea, core_area, purpose, frequency, next_due, status, checklist, calendar_block, reminder, starting_prompt)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (title, area_id, core, core, purpose, freq, str(next_monday()), "Active", checklist, 1, 1, title))
        created += 1
    return created


def slug(text: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text.strip()).strip("_") or "Area"

def strip_numeric_prefix(folder_name: str) -> str:
    import re
    return re.sub(r"^\d{2,3}_", "", folder_name).strip()


def is_area_candidate_folder(folder: Path) -> bool:
    import re
    """Return True only for numbered top-level folders that should become Areas.

    Pathmark treats the Workspace as a user-owned folder, so random top-level
    folders should not be imported automatically. Area folders must start with a
    numeric prefix such as 01_, 02-, or 03 . The reserved 00_System folder is
    always ignored.
    """
    if not folder.is_dir():
        return False
    name = folder.name.strip()
    if not name or name.startswith("."):
        return False
    normalised = name.lower().replace("_", " ").replace("-", " ")
    normalised = " ".join(normalised.split())
    ignored = {
        "00 system",
        "pathmark app",
        "pathmark",
        "local app",
        "local_app",
        "__pycache__",
        "venv",
        "env",
        "backups",
        "backup",
        "google calendar exports",
        "google tasks exports",
        "tasklists",
        "task lists",
    }
    if normalised in ignored:
        return False
    match = re.match(r"^(\d{2,3})[_ -]", name)
    if not match:
        return False
    return int(match.group(1)) > 0


def existing_area_folders() -> list[tuple[int | None, Path]]:
    """Return numbered top-level folders that can become Pathmark areas.

    Folders must start with a numeric prefix such as 01_Body_And_Stability.
    Unnumbered folders are ignored so downloads, app folders, and other user files
    do not accidentally appear as Areas. This is read-only and never deletes,
    renames, or empties anything.
    """
    root = root_folder()
    if not root.exists():
        return []
    import re
    out: list[tuple[int | None, Path]] = []
    for child in root.iterdir():
        if not is_area_candidate_folder(child):
            continue
        match = re.match(r"^(\d{2,3})[_ -]", child.name)
        number = int(match.group(1)) if match else None
        out.append((number, child))
    return sorted(out, key=lambda item: (item[0] is None, item[0] or 9999, item[1].name.lower()))


def existing_numbered_area_folders() -> list[tuple[int, Path]]:
    """Backward-compatible helper returning only numbered area folders."""
    return [(number, folder) for number, folder in existing_area_folders() if number is not None]


def next_area_number() -> int:
    existing = [number for number, _ in existing_numbered_area_folders()]
    return (max(existing) + 1) if existing else 1


def find_existing_area_folder(area_name: str) -> Path | None:
    """Find an existing folder that already appears to represent this area."""
    target = slug(area_name).lower()
    if not target:
        return None
    root = root_folder()
    if not root.exists():
        return None
    for _, folder in existing_area_folders():
        without_prefix = strip_numeric_prefix(folder.name)
        if slug(without_prefix).lower() == target:
            return folder
    return None


def suggested_area_folder(area_name: str) -> Path:
    """Suggest a non-destructive area folder using the existing numbered order.

    If a matching folder already exists, use it. Otherwise continue the current
    numeric sequence under the Pathmark root, e.g. 07_New_Area.
    """
    cleaned = slug(area_name or "New_Area")
    existing = find_existing_area_folder(cleaned)
    if existing:
        return existing
    return root_folder() / f"{next_area_number():02d}_{cleaned}"


def area_markdown_path_for_folder(folder: Path, area_name: str) -> Path:
    return folder / f"{slug(area_name or folder.name)}.md"


def area_name_from_folder(folder: Path) -> str:
    """Convert an existing folder into a friendly area name.

    Examples:
    03_Making_And_Craft -> Making And Craft
    Pottery Projects -> Pottery Projects
    This is intentionally read-only and never renames the user's folder.
    """
    raw = strip_numeric_prefix(folder.name)
    raw = raw.replace("_", " ").replace("-", " ")
    raw = " ".join(part for part in raw.split() if part)
    return raw or strip_numeric_prefix(folder.name) or folder.name


def next_available_google_colour(offset: int = 0) -> str:
    """Choose a Google Calendar colour not already used by active Areas where possible."""
    cycle = ["Sage", "Basil", "Tangerine", "Peacock", "Lavender", "Grape", "Flamingo", "Banana", "Blueberry", "Tomato", "Graphite"]
    used_rows = query("SELECT google_color FROM areas WHERE COALESCE(status,'Active') = 'Active'")
    used = {str(row.get("google_color") or "") for row in used_rows}
    available = [colour for colour in cycle if colour not in used]
    if available:
        return available[offset % len(available)]
    return cycle[offset % len(cycle)]


def sync_areas_from_existing_folders() -> int:
    """Create missing Area records from existing folders under the Pathmark root.

    This lets a user point Pathmark at an existing folder system and immediately
    use those folders as selectable areas without manually recreating them in the app.
    It never deletes, renames, moves, or empties folders.
    """
    created = 0
    for index, (_, folder) in enumerate(existing_area_folders()):
        name = area_name_from_folder(folder)
        markdown_path = area_markdown_path_for_folder(folder, name)
        existing = query("SELECT id, folder_path, markdown_path FROM areas WHERE lower(name)=lower(?)", (name,))
        if existing:
            row = existing[0]
            updates = []
            params: list[Any] = []
            if not row.get("folder_path"):
                updates.append("folder_path=?")
                params.append(str(folder))
            if not row.get("markdown_path"):
                updates.append("markdown_path=?")
                params.append(str(markdown_path))
            if updates:
                params.append(row["id"])
                execute(f"UPDATE areas SET {', '.join(updates)}, updated_at=CURRENT_TIMESTAMP WHERE id=?", tuple(params))
            continue
        execute(
            """INSERT INTO areas (name, description, folder_path, markdown_path, default_calendar, default_task_list, google_color, status, notes)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                name,
                "Imported from an existing folder in the selected Pathmark root.",
                str(folder),
                str(markdown_path),
                name,
                get_setting("default_task_list", "Pathmark") or "Pathmark",
                next_available_google_colour(index),
                "Active",
                "Created automatically from an existing folder. The folder was not renamed or modified.",
            ),
        )
        created += 1
    return created


def archive_invalid_auto_imported_areas() -> int:
    """Hide older auto-imported Areas that were created from unnumbered folders.

    Earlier builds imported every top-level Workspace folder. From v0.5.53 onward,
    only numbered folders such as 01_Body_And_Stability should become Areas. This
    routine archives only records that look auto-created from existing folders and
    whose folder is not a valid numbered Area candidate. It leaves manually edited
    Areas alone and never deletes folders or files.
    """
    root = root_folder().resolve()
    archived = 0
    rows = query("SELECT id, name, folder_path, description, notes, status FROM areas WHERE COALESCE(status,'Active') = 'Active'")
    for row in rows:
        folder_value = (row.get("folder_path") or "").strip()
        if not folder_value:
            continue
        folder = Path(folder_value).expanduser()
        try:
            resolved = folder.resolve()
            is_inside_root = resolved.parent == root
        except Exception:
            is_inside_root = False
        if not is_inside_root:
            continue
        auto_text = f"{row.get('description') or ''} {row.get('notes') or ''}".lower()
        name_text = f"{row.get('name') or ''} {folder.name}".lower().replace("_", " ").replace("-", " ")
        name_text = " ".join(name_text.split())
        looks_auto_imported = (
            "imported from an existing folder" in auto_text
            or "created automatically from an existing folder" in auto_text
        )
        looks_like_app_or_system_folder = any(token in name_text for token in [
            "pathmark app", "local app", "google tasks exports", "google calendar exports",
            "tasklists", "task lists", "00 system", "development system app"
        ])
        if (looks_auto_imported or looks_like_app_or_system_folder) and not is_area_candidate_folder(folder):
            execute(
                "UPDATE areas SET status='Archived', notes=COALESCE(notes,'') || CASE WHEN COALESCE(notes,'')='' THEN '' ELSE char(10) END || ?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                ("Archived automatically because Area folders now require a numeric prefix such as 01_Area_Name. The folder was not deleted or changed.", row["id"]),
            )
            archived += 1
    return archived


def export_ics(rows: list[dict[str, Any]], output_path: Path) -> Path:
    def dt(s: str | None) -> str:
        if not s:
            return datetime.now().strftime("%Y%m%dT%H%M%S")
        try:
            return datetime.fromisoformat(str(s).replace(" ", "T")).strftime("%Y%m%dT%H%M%S")
        except Exception:
            return datetime.now().strftime("%Y%m%dT%H%M%S")
    def esc(v: Any) -> str:
        return ("" if v is None else str(v)).replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Pathmark//Google Calendar Export//EN", "CALSCALE:GREGORIAN"]
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for r in rows:
        lines += [
            "BEGIN:VEVENT",
            f"UID:devsystem-{r.get('id') or slug(r.get('title') or 'event') + '-' + str(abs(hash(str(r))))}@local",
            f"DTSTAMP:{now}",
            f"DTSTART:{dt(r.get('start_datetime'))}",
            f"DTEND:{dt(r.get('end_datetime'))}",
            f"SUMMARY:{esc(r.get('title'))}",
            f"DESCRIPTION:{esc(r.get('description'))}",
        ]
        if r.get("location"):
            lines.append(f"LOCATION:{esc(r.get('location'))}")
        if r.get("recurrence_rule"):
            lines.append(str(r.get("recurrence_rule")))
        if r.get("alarm_minutes") not in (None, ""):
            lines += ["BEGIN:VALARM", f"TRIGGER:-PT{int(r['alarm_minutes'])}M", "ACTION:DISPLAY", f"DESCRIPTION:{esc(r.get('title'))}", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\r\n".join(lines)+"\r\n", encoding="utf-8")
    return output_path


def unique_path(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return path
    stamp = datetime.now().strftime("%H%M%S")
    return path.with_name(f"{path.stem}_{stamp}{path.suffix}")


def open_file(path: Path) -> bool:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except Exception as exc:
        st.error(f"Could not open file: {exc}")
        return False


def open_folder(path: Path) -> bool:
    folder = path if path.is_dir() else path.parent
    return open_file(folder)


def machine_date(value: Any) -> str:
    """Return YYYY-MM-DD for Google Tasks CSV file and other machine-readable exports."""
    if value in (None, "", pd.NaT):
        return ""
    try:
        d = pd.to_datetime(value)
        if pd.isna(d):
            return ""
        return d.strftime("%Y-%m-%d")
    except Exception:
        return str(value)


def export_tasks_csv(rows: list[dict[str, Any]], output_path: Path) -> Path:
    """Export a comma-delimited Google Tasks import CSV.

    The first seven columns remain compatible with the Apps Script importer:
    Task ID, Task List, Title, Notes, Due Date, Reminder Time, Status.
    Extra columns are kept after those columns and can be ignored by the script
    because it looks columns up by header name.
    """
    if output_path.suffix.lower() != ".csv":
        output_path = output_path.with_suffix(".csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    headers = ["Task ID", "Task List", "Title", "Notes", "Due Date", "Reminder Time", "Status", "Repeat Pattern", "Related Google Calendar Item"]
    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        for r in rows:
            source_id = f"DS_TASK_{r.get('id')}"
            writer.writerow({
                "Task ID": source_id,
                "Task List": r.get("task_list") or "Pathmark",
                "Title": r.get("title") or "",
                "Notes": r.get("notes") or "",
                "Due Date": machine_date(r.get("due_date")),
                "Reminder Time": r.get("reminder_time") or "",
                "Status": "completed" if str(r.get("status", "")).lower() == "completed" else "needsAction",
                "Repeat Pattern": r.get("repeat_pattern") or "",
                "Related Google Calendar Item": r.get("linked_calendar_summary") or "",
            })
    return output_path


def export_tasks_tsv(rows: list[dict[str, Any]], output_path: Path) -> Path:
    """Backward-compatible wrapper. Google Tasks exports are CSV again."""
    return export_tasks_csv(rows, output_path.with_suffix(".csv"))


def backup_if_different(path: Path, new_text: str) -> None:
    """Back up an existing text file before replacing it with different content."""
    if not path.exists():
        return
    try:
        existing = path.read_text(encoding="utf-8")
    except Exception:
        existing = ""
    if existing == new_text:
        return
    backup_dir = backup_folder() / "Google Tasks Setup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{path.stem}_{stamp}{path.suffix}"
    shutil.copy2(path, backup_path)


def write_google_tasks_setup_files() -> tuple[Path, Path]:
    """Create the Google Tasks Apps Script setup guide inside the export folder."""
    folder = google_tasks_export_folder()
    folder.mkdir(parents=True, exist_ok=True)
    readme_path = folder / "README - Google Tasks Import Setup.md"
    script_path = folder / "pathmark_google_tasks_import.gs"
    readme_text = google_tasks_setup_readme()
    script_text = GOOGLE_TASKS_APPS_SCRIPT_CODE + "\n"
    backup_if_different(readme_path, readme_text)
    backup_if_different(script_path, script_text)
    readme_path.write_text(readme_text, encoding="utf-8")
    script_path.write_text(script_text, encoding="utf-8")
    return readme_path, script_path


def friendly_date(value: date) -> str:
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    return f"{value.day} {months[value.month - 1]} {value.year}"



def pdf_palette() -> dict[str, str]:
    """A print-safe translation of the selected app theme.

    The PDF should reflect the selected theme without inheriting dark-mode contrast
    problems. Keep the paper white/near-white, use the theme as an accent, and use
    restrained lines rather than boxed dashboard-style blocks.
    """
    t = theme()
    accent = t.get("primary", "#9A704A")
    return {
        "ink": "#22201D",
        "muted": "#5D5751",
        "quiet": "#8A8178",
        "accent": accent,
        "accent_dark": t.get("primary_hover", accent),
        "hairline": "#DDD6CC",
        "rule": "#CDBDA9",
        "paper": "#FFFFFF",
        "soft": "#F7F3EC",
        "subtle": "#F2ECE4",
    }


def register_pdf_fonts() -> tuple[str, str]:
    """Use Segoe UI on Windows when available; otherwise use Helvetica.

    We do not package or share font files. This only uses fonts already installed
    on the user's machine if ReportLab can find them.
    """
    candidates = [
        ("SegoeUI", "SegoeUI-Bold", Path(r"C:\Windows\Fonts\segoeui.ttf"), Path(r"C:\Windows\Fonts\segoeuib.ttf")),
        ("Aptos", "Aptos-Bold", Path(r"C:\Windows\Fonts\aptos.ttf"), Path(r"C:\Windows\Fonts\aptos-bold.ttf")),
        ("Arial", "Arial-Bold", Path(r"C:\Windows\Fonts\arial.ttf"), Path(r"C:\Windows\Fonts\arialbd.ttf")),
    ]
    for regular_name, bold_name, regular_path, bold_path in candidates:
        try:
            if regular_path.exists() and bold_path.exists():
                if regular_name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(regular_name, str(regular_path)))
                if bold_name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
                return regular_name, bold_name
        except Exception:
            pass
    return "Helvetica", "Helvetica-Bold"


class Checkbox(Flowable):
    """A crisp square checkbox drawn directly onto the PDF canvas."""

    def __init__(self, size: float = 4.2 * mm, stroke_colour=None, stroke_width: float = 0.8):
        super().__init__()
        self.size = size
        self.width = size
        self.height = size
        self.stroke_colour = stroke_colour or colors.HexColor(pdf_palette()["accent"])
        self.stroke_width = stroke_width

    def draw(self):
        c = self.canv
        c.saveState()
        c.setStrokeColor(self.stroke_colour)
        c.setLineWidth(self.stroke_width)
        c.rect(0, 0, self.size, self.size, stroke=1, fill=0)
        c.restoreState()


def task_row(text: str, style: ParagraphStyle, *, indent: int = 0, is_subtask: bool = False) -> Table:
    """Google/Windows-style task row with a real square checkbox and clean spacing."""
    pal = pdf_palette()
    accent = colors.HexColor(pal["accent"])
    hairline = colors.HexColor(pal["hairline"])
    box_size = 4.2 * mm if not is_subtask else 3.8 * mm
    indent_width = 0 * mm if indent == 0 else 9 * mm
    table_width = 170 * mm
    checkbox_col = 7 * mm
    text_width = table_width - indent_width - checkbox_col
    tbl = Table(
        [["", Checkbox(size=box_size, stroke_colour=accent, stroke_width=0.75), Paragraph(escape_html(text), style)]],
        colWidths=[indent_width, checkbox_col, text_width],
    )
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2 if not is_subtask else 1.8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6.2 if not is_subtask else 5.0),
        ("LINEBELOW", (1, 0), (2, 0), 0.25, hairline),
    ]))
    return tbl


def section_heading(text: str, style: ParagraphStyle) -> Table:
    """Modern full-width section label with a quiet rule."""
    pal = pdf_palette()
    tbl = Table([[Paragraph(escape_html(text), style)]], colWidths=[170 * mm])
    tbl.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.55, colors.HexColor(pal["rule"])),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 13),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tbl


def focus_panel(text: str, label_style: ParagraphStyle, body_style: ParagraphStyle) -> Table:
    """A restrained focus row rather than a dashboard box."""
    pal = pdf_palette()
    tbl = Table(
        [[Paragraph("Focus", label_style), Paragraph(escape_html(text), body_style)]],
        colWidths=[24 * mm, 146 * mm],
    )
    tbl.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.45, colors.HexColor(pal["hairline"])),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


def weekly_pdf(output_path: Path, action_ids: list[int] | None = None, routine_ids: list[int] | None = None, notes: str = "", title: str = "Weekly Tasklist") -> Path:
    output_path = unique_path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    regular_font, bold_font = register_pdf_fonts()
    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        rightMargin=18 * mm, leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
    )
    styles = getSampleStyleSheet()
    pal = pdf_palette()
    ink = colors.HexColor(pal["ink"])
    muted = colors.HexColor(pal["muted"])
    accent = colors.HexColor(pal["accent"])

    title_style = ParagraphStyle("TasklistTitle", parent=styles["Title"], fontName=bold_font, fontSize=17.5, leading=21, alignment=0, textColor=ink, spaceAfter=0)
    date_style = ParagraphStyle("PreparedDate", parent=styles["BodyText"], fontName=regular_font, fontSize=8.8, leading=10.5, alignment=2, textColor=muted)
    section_style = ParagraphStyle("Section", parent=styles["Heading2"], fontName=bold_font, fontSize=9.8, leading=12, textColor=accent, spaceBefore=8, spaceAfter=2)
    parent_style = ParagraphStyle("Parent", parent=styles["BodyText"], fontName=bold_font, fontSize=8.8, leading=11, textColor=muted, spaceBefore=3, spaceAfter=1)
    body_style = ParagraphStyle("TaskBody", parent=styles["BodyText"], fontName=regular_font, fontSize=10.2, leading=13.0, textColor=ink)
    sub_style = ParagraphStyle("Subtask", parent=styles["BodyText"], fontName=regular_font, fontSize=9.4, leading=12, textColor=ink)
    empty_style = ParagraphStyle("Empty", parent=styles["BodyText"], fontName=regular_font, fontSize=10.0, leading=13, textColor=muted)

    story: list[Any] = []
    header = Table([[Paragraph(escape_html(title or "Tasklist"), title_style), Paragraph(f"Prepared {friendly_date(date.today())}", date_style)]], colWidths=[118 * mm, 52 * mm])
    header.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.8, accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
    ]))
    story += [header, Spacer(1, 8)]

    focus = get_setting("weekly_focus", "No main focus")
    if focus and focus != "No main focus":
        story += [Paragraph("Main focus", section_style), Paragraph(escape_html(focus), body_style), Spacer(1, 4)]

    action_ids = action_ids or []
    actions = pd.DataFrame()
    if action_ids:
        placeholders = ",".join("?" for _ in action_ids)
        actions = actions_df(f"WHERE ac.id IN ({placeholders})", tuple(action_ids))

    def add_grouped(section_title: str, data: pd.DataFrame, parent_col: str) -> None:
        if data.empty:
            return
        story.append(Paragraph(section_title, section_style))
        last_parent = None
        for _, a in data.iterrows():
            parent = str(a.get(parent_col) or "Unlinked").strip()
            if parent != last_parent:
                story.append(Paragraph(escape_html(parent), parent_style))
                last_parent = parent
            story.append(task_row(str(a["title"]), sub_style, indent=1, is_subtask=True))
        story.append(Spacer(1, 2))

    if not actions.empty:
        goal_actions = actions[actions["goal_id"].notna()].copy()
        routine_tasks = actions[actions["routine_id"].notna()].copy()
        other_actions = actions[actions["goal_id"].isna() & actions["routine_id"].isna()].copy()
        add_grouped("Goal actions", goal_actions, "goal_title")
        add_grouped("Routine activitys", routine_tasks, "routine_title")
        add_grouped("Other actions", other_actions, "area_name")

    fixed = [line.strip().lstrip("-•").strip() for line in notes.splitlines() if line.strip()]
    if fixed:
        story += [Paragraph("Notes", section_style)]
        for line in fixed:
            story.append(task_row(line, body_style))

    if not action_ids and not fixed and (not focus or focus == "No main focus"):
        story.append(Paragraph("No tasklist items selected.", empty_style))

    doc.build(story)
    return output_path

# -----------------------------------------------------------------------------
# Pages
# -----------------------------------------------------------------------------


def home_page() -> None:
    page_title("Home", "Choose your focus, review what needs attention, and plan the next step.")

    active_goals = goals_df()
    focus_opts = ["No main focus"]
    if not active_goals.empty:
        focus_opts += active_goals[active_goals["status"].isin(["Active", "Captured"])] ["title"].tolist()
    current = get_setting("weekly_focus", "No main focus")
    if current not in focus_opts:
        focus_opts.append(current)

    # Keep the primary focus controls aligned and out of the metric/card row.
    with st.form("home_focus_form"):
        c1, c2 = st.columns([0.76, 0.24], vertical_alignment="bottom")
        with c1:
            selected_focus = st.selectbox(
                "Main focus",
                focus_opts,
                index=focus_opts.index(current) if current in focus_opts else 0,
                help="This focus appears on the tasklist and brings related actions to the top.",
            )
        with c2:
            submitted_focus = st.form_submit_button("Save focus", use_container_width=True)
    if submitted_focus:
        set_setting("weekly_focus", selected_focus)
        st.success("Focus saved.")
        st.rerun()

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    cols = st.columns(4)
    active_goals_count = scalar("SELECT COUNT(*) FROM goals WHERE status='Active' AND archived_at IS NULL") or 0
    planned_actions = scalar("SELECT COUNT(*) FROM actions WHERE status IN ('Next','Planned','Scheduled') AND archived_at IS NULL") or 0
    review_count = scalar("SELECT COUNT(*) FROM review_issues WHERE status='Open'") or 0
    cal_count = scalar("SELECT COUNT(*) FROM calendar_blocks WHERE export_status='Staged'") or 0
    with cols[0]: metric_card("Active goals", active_goals_count)
    with cols[1]: metric_card("Planned actions", planned_actions)
    with cols[2]: metric_card("Items needing review", review_count)
    with cols[3]: metric_card("Google Calendar exports", cal_count)

    st.markdown("<div style='height: 6px;'></div>", unsafe_allow_html=True)
    if st.button("Run review checks", key="run_review_checks_2338"):
        generate_review_issues()
        st.toast("Review checks updated.")
        st.rerun()

    left, right = st.columns([0.62, 0.38], gap="large")
    with left:
        st.subheader("Planned next actions")
        goal_actions = weekly_actions_df("goals").head(8)
        routine_tasks = weekly_actions_df("routines").head(6)
        unlinked_actions = weekly_actions_df("unlinked").head(4)

        if goal_actions.empty and routine_tasks.empty and unlinked_actions.empty:
            st.markdown("<div class='muted'>No planned actions found.</div>", unsafe_allow_html=True)
        else:
            if not goal_actions.empty:
                st.markdown("<div class='source-heading'>Goal actions</div>", unsafe_allow_html=True)
                grouped: dict[str, list[Any]] = {}
                for _, a in goal_actions.iterrows():
                    source = a.get("goal_title") or a.get("area_name") or "Unassigned goal"
                    grouped.setdefault(str(source), []).append(a)
                for source, rows in grouped.items():
                    st.markdown(f"<div class='small-muted'>{escape_html(source)}</div>", unsafe_allow_html=True)
                    for a in rows:
                        tags = tag_markup(a.get("status", "")) + tag_markup(area_tag(a.get("area_name"), a.get("area_color")))
                        st.markdown(f"<div class='row-card'><strong>{escape_html(a['title'])}</strong><br>{tags}</div>", unsafe_allow_html=True)

            if not routine_tasks.empty:
                st.markdown("<div class='source-heading'>Routine activitys</div>", unsafe_allow_html=True)
                grouped: dict[str, list[Any]] = {}
                for _, a in routine_tasks.iterrows():
                    source = a.get("routine_title") or a.get("area_name") or "Unassigned routine"
                    grouped.setdefault(str(source), []).append(a)
                for source, rows in grouped.items():
                    st.markdown(f"<div class='small-muted'>{escape_html(source)}</div>", unsafe_allow_html=True)
                    for a in rows:
                        tags = tag_markup(a.get("status", "")) + tag_markup(area_tag(a.get("area_name"), a.get("area_color")))
                        st.markdown(f"<div class='row-card'><strong>{escape_html(a['title'])}</strong><br>{tags}</div>", unsafe_allow_html=True)

            if not unlinked_actions.empty:
                st.markdown("<div class='source-heading'>Other actions</div>", unsafe_allow_html=True)
                for _, a in unlinked_actions.iterrows():
                    tags = tag_markup(a.get("status", "")) + tag_markup(area_tag(a.get("area_name"), a.get("area_color")))
                    st.markdown(f"<div class='row-card'><strong>{escape_html(a['title'])}</strong><br>{tags}</div>", unsafe_allow_html=True)
    with right:
        st.subheader("Goals ready to review")
        goals = df("SELECT g.*, a.name AS area_name, a.google_color AS area_color FROM goals g LEFT JOIN areas a ON a.id=g.area_id WHERE g.status IN ('Captured','On hold') AND g.archived_at IS NULL ORDER BY g.updated_at DESC")
        if goals.empty:
            st.markdown("<div class='muted'>No captured or on-hold goals need review.</div>", unsafe_allow_html=True)
        else:
            for _, g in goals.iterrows():
                tags = tag_markup(g["status"]) + tag_markup(area_tag(g.get("area_name"), g.get("area_color")))
                body = escape_html(g.get("desired_outcome") or g.get("purpose") or "")
                st.markdown(f"<div class='row-card'><strong>{escape_html(g['title'])}</strong><br>{tags}<div class='muted'>{body}</div></div>", unsafe_allow_html=True)

def build_focus_options() -> dict[str, dict[str, Any]]:
    options: dict[str, dict[str, Any]] = {}
    for g in query("SELECT * FROM goals WHERE status='Active' AND archived_at IS NULL ORDER BY title"):
        action = query("SELECT * FROM actions WHERE goal_id=? AND status IN ('Next','Scheduled','Planned') AND archived_at IS NULL ORDER BY CASE status WHEN 'Next' THEN 1 WHEN 'Scheduled' THEN 2 ELSE 3 END LIMIT 1", (g["id"],))
        options[f"Goal: {g['title']}"] = {"type": "goal", "id": g["id"], "default_action": action[0]["title"] if action else ""}
    for a in query("SELECT ac.*, g.title AS goal_title FROM actions ac LEFT JOIN goals g ON g.id=ac.goal_id WHERE ac.status IN ('Next','Scheduled','Planned') AND ac.archived_at IS NULL ORDER BY ac.title"):
        options[f"Action: {a['title']}"] = {"type": "action", "id": a["id"], "default_action": a["title"]}
    return options


def this_week_page() -> None:
    page_title("Tasklist", "Name the list, then select goal actions and routine activities to include.")
    active_goals = goals_df()
    focus_opts = ["No main focus"] + active_goals[active_goals["status"].isin(["Active", "Captured"])] ["title"].tolist() if not active_goals.empty else ["No main focus"]
    current = get_setting("weekly_focus", "No main focus")
    if current not in focus_opts:
        focus_opts.append(current)
    focus = st.selectbox("Main focus", focus_opts, index=focus_opts.index(current) if current in focus_opts else 0)
    if focus != current:
        set_setting("weekly_focus", focus)
        st.rerun()

    default_title = get_setting("tasklist_title", "Weekly Tasklist")
    title = st.text_input("Tasklist name", value=default_title, help="This appears at the top of the printable PDF. Choose any name, then select the actions to include.")
    if title != get_setting("tasklist_title", "Weekly Tasklist"):
        set_setting("tasklist_title", title)

    selected_action_ids: list[int] = []
    goal_actions = weekly_actions_df("goals")
    routine_tasks = weekly_actions_df("routines")

    st.subheader("Goal actions")
    if goal_actions.empty:
        st.markdown("<div class='muted'>No planned goal actions found.</div>", unsafe_allow_html=True)
    else:
        for parent, group in goal_actions.groupby(goal_actions["goal_title"].fillna("Unlinked goal"), sort=False):
            st.markdown(f"<div class='source-heading'>{escape_html(str(parent))}</div>", unsafe_allow_html=True)
            for _, a in group.head(10).iterrows():
                checked = st.checkbox(f"{a['title']}", value=False, key=f"week_goal_action_{a['id']}")
                if checked:
                    selected_action_ids.append(int(a["id"]))

    st.subheader("Routine activities")
    if routine_tasks.empty:
        st.markdown("<div class='muted'>No included routine activities found.</div>", unsafe_allow_html=True)
    else:
        for parent, group in routine_tasks.groupby(routine_tasks["routine_title"].fillna("Unlinked routine"), sort=False):
            st.markdown(f"<div class='source-heading'>{escape_html(str(parent))}</div>", unsafe_allow_html=True)
            for _, a in group.head(10).iterrows():
                checked = st.checkbox(f"{a['title']}", value=False, key=f"week_routine_action_{a['id']}")
                if checked:
                    selected_action_ids.append(int(a["id"]))

    st.subheader("Notes")
    fixed_notes = st.text_area("Optional notes for the printed tasklist", help="Add one note per line. These are appended to the end of the tasklist.")

    if st.button("Create tasklist PDF"):
        if not selected_action_ids and not fixed_notes.strip():
            st.warning("Tick at least one action, or add a note.")
        else:
            path = weekly_pdf(tasklist_export_folder() / f"tasklist_{date.today().strftime('%Y%m%d')}.pdf", selected_action_ids, [], fixed_notes, title=title)
            st.session_state["latest_weekly_pdf"] = str(path)
            st.success(f"Created {path.name}")

    latest_path = Path(st.session_state.get("latest_weekly_pdf", "")) if st.session_state.get("latest_weekly_pdf") else None
    if latest_path and latest_path.exists():
        c1, c2 = st.columns([0.25, 0.75])
        if c1.button("Open PDF"):
            open_file(latest_path)
        if c2.button("Open folder"):
            open_folder(latest_path)


def goals_page() -> None:
    page_title("Goals and Projects", "Define goals, keep actions visible, and archive with a short review when the work has reached an endpoint.")
    data = goals_df()
    with st.expander("Add a goal", expanded=False):
        goal_form()
    if data.empty:
        st.info("No goals yet.")
        return
    col_list, col_main = st.columns([0.34, 0.66])
    with col_list:
        st.subheader("Goals")
        labels = {f"{row['title']} ({row['status']})": int(row["id"]) for _, row in data.iterrows()}
        selected_label = st.radio("Select a goal", list(labels.keys()), label_visibility="collapsed")
        selected_id = labels[selected_label]
    with col_main:
        render_goal_detail(selected_id)


def goal_form(goal: dict[str, Any] | None = None) -> None:
    areas = areas_df(active_only=False)
    if areas.empty:
        sync_areas_from_existing_folders()
        areas = areas_df(active_only=False)
    area_names = areas["name"].tolist() if not areas.empty else []
    default_area = 0
    if goal and area_names:
        try: default_area = area_names.index(goal.get("area_name"))
        except Exception: default_area = 0
    with st.form(f"goal_form_{goal['id'] if goal else 'new'}"):
        title = st.text_input("Goal name", value=goal.get("title", "") if goal else "")
        if not area_names:
            st.info("No areas are available yet. Pathmark can import existing folders in your selected Workspace folder, including numbered folders such as 01_Body_And_Stability. Check Settings → Setup and folders if the root folder is not correct.")
        area_name = st.selectbox("Area", area_names, index=default_area if area_names else None, help="The main Workspace folder area, such as Body And Stability or Work And Admin.")
        subarea = st.text_input("Specific area", value=goal.get("subarea", "") if goal else "", help="Optional. Use this for the more specific part of the area, such as Diet, Exercise, Finance, Pottery, or Planning.")
        status = st.selectbox("Status", GOAL_STATUSES, index=GOAL_STATUSES.index(goal.get("status", "Captured")) if goal and goal.get("status") in GOAL_STATUSES else 0)
        purpose = st.text_area("Purpose", value=goal.get("purpose", "") if goal else "", help="Why this goal is worth holding in the system.")
        desired = st.text_area("Desired outcome", value=goal.get("desired_outcome", "") if goal else "", help="What you are trying to make true or complete.")
        closure = st.text_area("Closure criteria", value=goal.get("closure_criteria", "") if goal else "", help="What would make this complete enough to archive as Closed or Abandoned.")
        notes = st.text_area("Notes", value=goal.get("notes", "") if goal else "")
        submitted = st.form_submit_button("Save goal")
    if submitted and title.strip():
        if not area_name:
            st.error("Choose or create an area before saving this goal. If you already have numbered area folders, check that your Pathmark root folder is set correctly in Settings.")
            return
        area_id = area_id_by_name(area_name)
        if goal:
            execute("""UPDATE goals SET title=?, area_id=?, subarea=?, status=?, purpose=?, desired_outcome=?, closure_criteria=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""", (title, area_id, subarea, status, purpose, desired, closure, notes, goal["id"]))
        else:
            execute("""INSERT INTO goals (title, area_id, subarea, status, purpose, desired_outcome, closure_criteria, notes) VALUES (?,?,?,?,?,?,?,?)""", (title, area_id, subarea, status, purpose, desired, closure, notes))
        st.success("Goal saved.")
        st.rerun()


def render_goal_detail(goal_id: int) -> None:
    goal = query("SELECT g.*, a.name AS area_name, a.google_color AS area_color FROM goals g LEFT JOIN areas a ON a.id=g.area_id WHERE g.id=?", (goal_id,))[0]
    st.subheader(goal["title"])
    st.markdown(tag_markup(goal.get("status")) + tag_markup(area_tag(goal.get("area_name"), goal.get("area_color"))), unsafe_allow_html=True)
    tabs = st.tabs(["Details", "Actions", "Archive"])
    with tabs[0]:
        goal_form(goal)
    with tabs[1]:
        st.markdown("<div class='muted'>Actions sit under the goal so it is clear how the work moves forward.</div>", unsafe_allow_html=True)
        render_actions_for_goal(goal_id, goal.get("area_id"))
    with tabs[2]:
        archive_goal_form(goal)


def render_actions_for_goal(goal_id: int, area_id: int | None) -> None:
    actions = actions_df("WHERE ac.goal_id = ? AND ac.archived_at IS NULL", (goal_id,))
    if actions.empty:
        st.info("No actions yet.")
    else:
        for _, a in actions.iterrows():
            with st.expander(f"{a['title']} — {a['status']}", expanded=False):
                st.markdown(tag_markup(a.get("status")) + tag_markup(area_tag(a.get("area_name"), a.get("area_color"))), unsafe_allow_html=True)
                action_form(dict(a), goal_id=goal_id, area_id=area_id)
                c1, c2, c3 = st.columns(3)
                if c1.button("Mark done", key=f"done_{a['id']}"):
                    execute("UPDATE actions SET status='Done', completed_at=CURRENT_TIMESTAMP WHERE id=?", (int(a["id"]),))
                    execute("UPDATE calendar_blocks SET export_status='Removed', removed_at=CURRENT_TIMESTAMP WHERE action_id=? AND export_status='Staged'", (int(a["id"]),))
                    execute("UPDATE reminder_tasks SET export_status='Removed', removed_at=CURRENT_TIMESTAMP WHERE action_id=? AND export_status='Staged'", (int(a["id"]),))
                    st.rerun()
                if c2.button("Prepare exports", key=f"stage_{a['id']}"):
                    stage_exports_from_actions(area_id=None)
                    st.success("Export rows updated.")
                if c3.button("Archive action", key=f"arch_action_{a['id']}"):
                    execute(
                        """INSERT INTO archive_entries (entity_type, entity_id, title, final_status, summary, snapshot_json)
                           VALUES ('action',?,?,?,?,?)""",
                        (int(a["id"]), a["title"], "Archived", a.get("notes") or a.get("description") or "", json.dumps({"action": dict(a)}, default=str)),
                    )
                    execute("UPDATE actions SET archived_at=CURRENT_TIMESTAMP WHERE id=?", (int(a["id"]),))
                    st.rerun()
    with st.expander("Add action", expanded=False):
        action_form(None, goal_id=goal_id, area_id=area_id)


def action_form(action: dict[str, Any] | None, goal_id: int | None = None, area_id: int | None = None, routine_id: int | None = None) -> None:
    key = action["id"] if action else f"new_{goal_id}_{routine_id}"
    is_routine_activity = routine_id is not None and goal_id is None
    with st.form(f"action_form_{key}"):
        if is_routine_activity:
            title = st.text_input("Activity", value=action.get("title", "") if action else "")
            status = st.selectbox("State", ["Included", "Paused"], index=0 if not action or action.get("status") != "Paused" else 1, help="Routine activities repeat. Use Paused to keep the activity but exclude it from tasklists and exports.")
            parent_routine = query("SELECT frequency FROM routines WHERE id=?", (routine_id,))[0] if routine_id else {}
            current_days = normalise_activity_days(action.get("activity_days") if action else "")
            activity_days = st.multiselect(
                "Activity day(s)",
                list(WEEKDAY_INDEX.keys()),
                default=current_days,
                help="Use this when the routine repeats weekly but different activities happen on different days. The activity still inherits the routine's repeat interval.",
            )
            st.markdown("<div class='source-heading'>Activity time</div>", unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            with c1:
                start_time = st.text_input("Start time", value=action.get("calendar_start_time", "09:00") if action else "09:00")
                location = st.text_input("Location", value=action.get("calendar_location", "") if action else "")
            with c2:
                end_time = st.text_input("End time", value=action.get("calendar_end_time", "10:00") if action else "10:00")
                minutes = st.number_input("Estimated minutes", min_value=0, max_value=600, value=int(action.get("estimated_minutes") or 0) if action else 0)
            st.markdown("<div class='source-heading small-section'>Tasklist and exports</div>", unsafe_allow_html=True)
            include_tasklist = st.checkbox("Show on tasklist", value=bool(action.get("include_tasklist", 1)) if action else True)
            cal = st.checkbox("Prepare Google Calendar time", value=bool(action.get("calendar_block")) if action else True, help="Creates a recurring Google Calendar event for this activity using the routine repeat pattern.")
            first_step = st.text_input("Starting prompt for Google Tasks", value=action.get("first_step", "") if action else "", help="This becomes the Google Tasks title for each generated prompt row.")
            rem = st.checkbox("Prepare Google Tasks prompt", value=bool(action.get("reminder")) if action else False, help="Creates Google Tasks prompt rows for the next occurrences of this activity.")
            prompt_time = st.text_input("Reference time for Google Tasks notes", value=action.get("task_reminder_time", start_time) if action else start_time, help="Google Tasks API due dates do not store a time. This time is exported into the task notes only.")
            priority = action.get("priority", "Medium") if action else "Medium"
            due = None
            scheduled = None
        else:
            title = st.text_input("Action", value=action.get("title", "") if action else "")
            status = st.selectbox("Status", ACTION_STATUSES, index=ACTION_STATUSES.index(action.get("status", "Planned")) if action and action.get("status") in ACTION_STATUSES else 0)
            priority = st.selectbox("Priority", ["Low", "Medium", "High"], index=["Low","Medium","High"].index(action.get("priority", "Medium")) if action and action.get("priority") in ["Low","Medium","High"] else 1)
            due = st.date_input("Due date", value=parse_date(action.get("due_date")) if action and action.get("due_date") else None, format="DD/MM/YYYY", help="Used for the Google Tasks prompt. If blank, the scheduled date is used.")
            scheduled = st.date_input("Scheduled date", value=parse_date(action.get("scheduled_date")) if action and action.get("scheduled_date") else None, format="DD/MM/YYYY", help="Used for the Google Calendar time block. If blank, the due date is used.")
            minutes = st.number_input("Estimated minutes", min_value=0, max_value=600, value=int(action.get("estimated_minutes") or 0) if action else 0)
            st.markdown("<div class='source-heading'>Export settings</div>", unsafe_allow_html=True)
            st.markdown("<div class='small-muted'>Use Google Calendar for protected time and Google Tasks for the first cue that makes the work easier to start. Calendar uses the scheduled date; Google Tasks uses the due date. Each falls back to the other if blank.</div>", unsafe_allow_html=True)
            first_step = st.text_input(
                "Starting prompt for Google Tasks",
                value=action.get("first_step", "") if action else "",
                help="This becomes the Google Tasks title. Keep it small and concrete, for example: open the dashboard, put the mat out, or pack trimming tools.",
            )
            st.markdown("<div class='source-heading small-section'>Google Calendar time</div>", unsafe_allow_html=True)
            cal = st.checkbox("Prepare Google Calendar time", value=bool(action.get("calendar_block")) if action else False, help="Adds this item to the Google Calendar export as a scheduled block of time. It uses the scheduled date, or the due date if no scheduled date is set.")
            c1, c2 = st.columns(2)
            with c1:
                start_time = st.text_input("Start time", value=action.get("calendar_start_time", "09:00") if action else "09:00")
                location = st.text_input("Location", value=action.get("calendar_location", "") if action else "")
            with c2:
                end_time = st.text_input("End time", value=action.get("calendar_end_time", "10:00") if action else "10:00")
            st.markdown("<div class='source-heading small-section'>Google Tasks prompt</div>", unsafe_allow_html=True)
            rem = st.checkbox("Prepare Google Tasks prompt", value=bool(action.get("reminder")) if action else False, help="Adds this starting prompt to the Google Tasks CSV. If a Google Calendar time is also prepared, the task notes identify the related calendar item.")
            prompt_time = st.text_input("Reference time for Google Tasks notes", value=action.get("task_reminder_time", "09:00") if action else "09:00", help="Google Tasks API due dates do not store a time. This time is exported into the task notes only.")
            include_tasklist = True
        notes = st.text_area("Notes", value=action.get("notes", "") if action else "")
        submitted = st.form_submit_button("Save activity" if is_routine_activity else "Save action")
    if submitted and title.strip():
        cal_int = int(cal)
        rem_int = int(rem)
        include_int = int(include_tasklist)
        activity_days_text = ",".join(activity_days) if is_routine_activity else (action.get("activity_days", "") if action else "")
        if action:
            execute("""UPDATE actions SET title=?, status=?, priority=?, first_step=?, due_date=?, scheduled_date=?, activity_days=?, estimated_minutes=?, calendar_block=?, reminder=?, include_tasklist=?, task_reminder_time=?, calendar_start_time=?, calendar_end_time=?, calendar_location=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""", (title, status, priority, first_step, str(due) if due else None, str(scheduled) if scheduled else None, activity_days_text, int(minutes) if minutes else None, cal_int, rem_int, include_int, prompt_time, start_time, end_time, location, notes, action["id"]))
        else:
            execute("""INSERT INTO actions (goal_id, routine_id, area_id, title, status, priority, first_step, due_date, scheduled_date, activity_days, estimated_minutes, calendar_block, reminder, include_tasklist, task_reminder_time, calendar_start_time, calendar_end_time, calendar_location, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (goal_id, routine_id, area_id, title, status, priority, first_step, str(due) if due else None, str(scheduled) if scheduled else None, activity_days_text, int(minutes) if minutes else None, cal_int, rem_int, include_int, prompt_time, start_time, end_time, location, notes))
        stage_exports_from_actions()
        st.success(("Routine activity" if is_routine_activity else "Action") + " saved and export rows updated.")
        st.rerun()

def archive_goal_form(goal: dict[str, Any]) -> None:
    st.markdown("<div class='muted'>Archiving asks for a short closure review so the goal can be understood or reconstructed later.</div>", unsafe_allow_html=True)
    with st.form(f"archive_goal_{goal['id']}"):
        final_status = st.selectbox("Final status", ["Closed", "Abandoned"])
        summary = st.text_area("What happened?", help="Briefly summarise the outcome or reason for stopping.")
        went = st.text_area("What went well?")
        not_well = st.text_area("What did not go well?")
        carry = st.text_area("What should be carried forward?")
        submitted = st.form_submit_button("Archive goal")
    if submitted:
        archive_goal_with_review(goal["id"], final_status, summary, went, not_well, carry)
        st.success("Goal archived with closure review.")
        st.rerun()


def routines_page() -> None:
    page_title("Routines", "Maintain recurring activities that repeat on a shared pattern.")
    help_note("A routine holds the repeat pattern. Its activities hold the individual times, locations, tasklist visibility, and Google Tasks starting prompts.")
    data = routines_df(active_only=False)
    with st.expander("Add routine", expanded=False):
        routine_form(None)
    if data.empty:
        st.info("No routines yet.")
        return
    col_list, col_main = st.columns([0.34, 0.66])
    with col_list:
        st.subheader("Routines")
        labels = {f"{row['title']} ({row['status']})": int(row["id"]) for _, row in data.iterrows()}
        selected_label = st.radio("Select a routine", list(labels.keys()), label_visibility="collapsed")
        selected_id = labels[selected_label]
    with col_main:
        render_routine_detail(selected_id)


def render_routine_detail(routine_id: int) -> None:
    rows = query("SELECT r.*, a.name AS area_name, a.google_color AS area_color FROM routines r LEFT JOIN areas a ON a.id=r.area_id WHERE r.id=?", (routine_id,))
    if not rows:
        st.info("Routine not found.")
        return
    r = rows[0]
    st.subheader(r["title"])
    st.markdown(tag_markup(r.get("status")) + tag_markup(area_tag(r.get("area_name"), r.get("area_color"))), unsafe_allow_html=True)
    tabs = st.tabs(["Details", "Activities", "Repeat", "Manage"])
    with tabs[0]:
        routine_form(r)
    with tabs[1]:
        render_actions_for_routine(routine_id, r.get("area_id"))
    with tabs[2]:
        routine_frequency_controls(r)
    with tabs[3]:
        st.markdown("<div class='muted'>Routine activities repeat. Use the Activities tab to include, pause, or archive individual activities. Use these controls only when the routine itself is no longer active.</div>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        if c1.button("Retire routine", key=f"retire_r_{routine_id}"):
            execute("UPDATE routines SET status='Retired', updated_at=CURRENT_TIMESTAMP WHERE id=?", (routine_id,))
            st.rerun()
        if c2.button("Archive routine", key=f"archive_r_{routine_id}"):
            archive_routine(routine_id, "Retired", "Routine archived from Routines page.")
            st.rerun()


def render_actions_for_routine(routine_id: int, area_id: int | None) -> None:
    """Show recurring activities that belong to a routine."""
    actions = actions_df("WHERE ac.routine_id = ? AND ac.archived_at IS NULL", (routine_id,))
    if actions.empty:
        st.info("No activities yet. Add the repeated activities that make up this routine.")
    else:
        for _, a in actions.iterrows():
            state = a.get("status") or "Included"
            time = (a.get("calendar_start_time") or "")
            days = join_days_for_display(normalise_activity_days(a.get("activity_days")))
            day_text = f" · {days}" if days else ""
            label_time = f" · {time}" if time else ""
            with st.expander(f"{a['title']}{day_text}{label_time} — {state}", expanded=False):
                st.markdown(tag_markup(state) + tag_markup(area_tag(a.get("area_name"), a.get("area_color"))), unsafe_allow_html=True)
                action_form(dict(a), routine_id=routine_id, area_id=area_id)
                c1, c2 = st.columns(2)
                if state == "Paused":
                    if c1.button("Include activity", key=f"routine_include_{a['id']}"):
                        execute("UPDATE actions SET status='Included', updated_at=CURRENT_TIMESTAMP WHERE id=?", (int(a["id"]),))
                        stage_exports_from_actions()
                        st.rerun()
                else:
                    if c1.button("Pause activity", key=f"routine_pause_{a['id']}"):
                        execute("UPDATE actions SET status='Paused', updated_at=CURRENT_TIMESTAMP WHERE id=?", (int(a["id"]),))
                        execute("UPDATE calendar_blocks SET export_status='Removed', removed_at=CURRENT_TIMESTAMP WHERE action_id=? AND export_status='Staged'", (int(a["id"]),))
                        execute("UPDATE reminder_tasks SET export_status='Removed', removed_at=CURRENT_TIMESTAMP WHERE action_id=? AND export_status='Staged'", (int(a["id"]),))
                        st.rerun()
                if c2.button("Archive activity", key=f"routine_arch_action_{a['id']}"):
                    execute(
                        """INSERT INTO archive_entries (entity_type, entity_id, title, final_status, summary, snapshot_json)
                           VALUES ('action',?,?,?,?,?)""",
                        (int(a["id"]), a["title"], "Archived", a.get("notes") or a.get("description") or "", json.dumps({"action": dict(a)}, default=str)),
                    )
                    execute("UPDATE actions SET archived_at=CURRENT_TIMESTAMP WHERE id=?", (int(a["id"]),))
                    execute("UPDATE calendar_blocks SET export_status='Removed', removed_at=CURRENT_TIMESTAMP WHERE action_id=? AND export_status='Staged'", (int(a["id"]),))
                    execute("UPDATE reminder_tasks SET export_status='Removed', removed_at=CURRENT_TIMESTAMP WHERE action_id=? AND export_status='Staged'", (int(a["id"]),))
                    st.rerun()
    with st.expander("Add routine activity", expanded=False):
        action_form(None, routine_id=routine_id, area_id=area_id)


def routine_export_controls(routine: dict[str, Any]) -> None:
    with st.form(f"routine_export_{routine['id']}"):
        st.markdown("<div class='small-muted'>This routine creates one Google Calendar time block. The tasks under this routine are included in the calendar notes and can be selected for the printable tasklist.</div>", unsafe_allow_html=True)

        st.markdown("<div class='source-heading small-section'>Google Calendar time</div>", unsafe_allow_html=True)
        st.markdown("<div class='small-muted'>Uses the next due date and repeat pattern to create one recurring Google Calendar block. Routine activities are included in the calendar notes.</div>", unsafe_allow_html=True)
        cal = st.checkbox("Prepare Google Calendar time", value=bool(routine.get("calendar_block")), help="Adds this routine to the Google Calendar export as a recurring scheduled block of time.")
        c1, c2 = st.columns(2)
        with c1:
            start_time = st.text_input("Start time", value=routine.get("calendar_start_time") or "09:00")
            location = st.text_input("Location", value=routine.get("calendar_location") or "")
        with c2:
            end_time = st.text_input("End time", value=routine.get("calendar_end_time") or "10:00")

        st.markdown("<div class='source-heading small-section'>Google Tasks prompt</div>", unsafe_allow_html=True)
        st.markdown("<div class='small-muted'>Google Tasks import creates individual prompts. For repeating routines, the app prepares prompt rows for the next occurrences and links them to the routine calendar block.</div>", unsafe_allow_html=True)
        starting_prompt = st.text_input(
            "Starting prompt for Google Tasks",
            value=routine.get("starting_prompt") or f"Start {routine['title'].lower()}",
            help="This becomes the Google Tasks title. Keep it small and concrete, for example: put the mat out, open the meal plan, or pack trimming tools.",
        )
        rem = st.checkbox("Prepare Google Tasks prompt", value=bool(routine.get("reminder")), help="Adds starting prompts to the Google Tasks CSV. If Google Calendar time is also prepared, each task note identifies the related calendar item.")
        reminder_time = st.text_input("Prompt time", value=routine.get("task_reminder_time") or "09:00")
        submitted = st.form_submit_button("Save export settings")
    if submitted:
        execute("""UPDATE routines SET calendar_block=?, reminder=?, task_reminder_time=?, starting_prompt=?, calendar_start_time=?, calendar_end_time=?, calendar_location=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""", (int(cal), int(rem), reminder_time, starting_prompt, start_time, end_time, location, routine["id"]))
        stage_exports_from_actions()
        st.success("Routine saved and export rows updated.")
        st.rerun()


def infer_repeat_mode(current: str | None) -> str:
    text = (current or "Weekly").lower()
    if text in {"as needed", "does not repeat", "none", ""}:
        return "Does not repeat"
    if "month" in text:
        return "Monthly"
    if "week" in text or any(day in (current or "") for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]):
        return "Weekly"
    if "day" in text or text == "daily":
        return "Daily"
    return "Weekly"


def format_list(items: list[str]) -> str:
    items = [item for item in items if item]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def repeat_preview_from_saved(saved: str | None) -> str:
    saved = saved or "Weekly"
    if saved == "Does not repeat" or saved == "As needed":
        return "Does not repeat"
    return saved


def frequency_builder(current: str | None = None, key_prefix: str = "freq") -> str:
    """Google Calendar-style recurrence builder.

    The stored string is intentionally human-readable but still uses predictable
    wording that frequency_to_rrule can convert to an ICS RRULE.
    """
    current = current or "Weekly"
    st.markdown("<div class='muted'>Set how this routine repeats. These settings are used when preparing Google Calendar export rows.</div>", unsafe_allow_html=True)

    mode_options = ["Does not repeat", "Daily", "Weekly", "Monthly"]
    default_mode = infer_repeat_mode(current)
    mode = st.selectbox("Repeats", mode_options, index=mode_options.index(default_mode), key=f"{key_prefix}_mode")

    if mode == "Does not repeat":
        preview = "Does not repeat"
        st.markdown(f"<div class='card subtle'><strong>Preview</strong><br>{escape_html(preview)}</div>", unsafe_allow_html=True)
        return preview

    if mode == "Daily":
        interval = st.number_input("Repeat every", min_value=1, max_value=30, value=1, step=1, key=f"{key_prefix}_daily_interval")
        st.caption("day" if interval == 1 else "days")
        preview = "Daily" if interval == 1 else f"Every {interval} days"
        st.markdown(f"<div class='card subtle'><strong>Preview</strong><br>{escape_html(preview)}</div>", unsafe_allow_html=True)
        return preview

    if mode == "Weekly":
        interval = st.number_input("Repeat every", min_value=1, max_value=12, value=1, step=1, key=f"{key_prefix}_weekly_interval")
        st.caption("week" if interval == 1 else "weeks")
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        detected = [d for d in weekdays if d in current]
        if not detected:
            detected = ["Monday"]
        selected_days = st.multiselect("Repeat on", weekdays, default=detected, key=f"{key_prefix}_weekly_days")
        day_text = format_list(selected_days) if selected_days else "Monday"
        if interval == 1:
            preview = f"Weekly on {day_text}"
        else:
            preview = f"Every {interval} weeks on {day_text}"
        st.markdown(f"<div class='card subtle'><strong>Preview</strong><br>{escape_html(preview)}</div>", unsafe_allow_html=True)
        return preview

    # Monthly
    interval = st.number_input("Repeat every", min_value=1, max_value=24, value=1, step=1, key=f"{key_prefix}_monthly_interval")
    st.caption("month" if interval == 1 else "months")
    monthly_style = st.radio("Repeat by", ["Day of month", "Weekday of month"], horizontal=True, key=f"{key_prefix}_monthly_style")

    if monthly_style == "Day of month":
        default_day = date.today().day
        import re
        match = re.search(r"day (\d+)", current or "")
        if match:
            default_day = max(1, min(31, int(match.group(1))))
        day = st.number_input("Day of month", min_value=1, max_value=31, value=default_day, step=1, key=f"{key_prefix}_month_day")
        if interval == 1:
            preview = f"Monthly on day {day}"
        else:
            preview = f"Every {interval} months on day {day}"
        st.markdown(f"<div class='card subtle'><strong>Preview</strong><br>{escape_html(preview)}</div>", unsafe_allow_html=True)
        return preview

    ordinals = ["First", "Second", "Third", "Fourth", "Last"]
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    ordinal_default = next((o for o in ordinals if o.lower() in (current or "").lower()), "First")
    weekday_default = next((w for w in weekdays if w in (current or "")), "Monday")
    c1, c2 = st.columns(2)
    with c1:
        ordinal = st.selectbox("Which", ordinals, index=ordinals.index(ordinal_default), key=f"{key_prefix}_ordinal")
    with c2:
        weekday = st.selectbox("Day", weekdays, index=weekdays.index(weekday_default), key=f"{key_prefix}_weekday")
    if interval == 1:
        preview = f"Monthly on the {ordinal.lower()} {weekday}"
    else:
        preview = f"Every {interval} months on the {ordinal.lower()} {weekday}"
    st.markdown(f"<div class='card subtle'><strong>Preview</strong><br>{escape_html(preview)}</div>", unsafe_allow_html=True)
    return preview


def routine_form(routine: dict[str, Any] | None) -> None:
    areas = areas_df(active_only=False)
    area_names = areas["name"].tolist() if not areas.empty else []
    default_area = 0
    if routine and routine.get("area_name") in area_names:
        default_area = area_names.index(routine["area_name"])
    with st.form(f"routine_form_{routine['id'] if routine else 'new'}"):
        title = st.text_input("Routine name", value=routine.get("title", "") if routine else "")
        area_name = st.selectbox("Area", area_names, index=default_area if area_names else None, help="The main Workspace folder area, such as Body And Stability or Work And Admin.")
        subarea = st.text_input("Specific area", value=(routine.get("subarea") or routine.get("core_area") or "") if routine else "", help="Optional. Use this for the more specific part of the area, such as Diet, Exercise, Finance, Pottery, or Planning.")
        purpose = st.text_area("Purpose", value=routine.get("purpose", "") if routine else "", help="Describe what this routine maintains. Example: prepares lunches so food choices are easier when work is busy.")
        freq = routine.get("frequency", "Weekly") if routine else "Weekly"
        status = st.selectbox("Status", ROUTINE_STATUSES, index=ROUTINE_STATUSES.index(routine.get("status", "Active")) if routine and routine.get("status") in ROUTINE_STATUSES else 0)
        notes = st.text_area("Notes", value=routine.get("notes", "") if routine else "")
        submitted = st.form_submit_button("Save routine")
    if submitted and title.strip():
        if not area_name:
            st.error("Choose or create an area before saving this goal. If you already have numbered area folders, check that your Pathmark root folder is set correctly in Settings.")
            return
        area_id = area_id_by_name(area_name)
        if routine:
            execute("""UPDATE routines SET title=?, area_id=?, subarea=?, core_area=?, purpose=?, frequency=?, status=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""", (title, area_id, subarea, subarea, purpose, freq, status, notes, routine["id"]))
        else:
            execute("""INSERT INTO routines (title, area_id, subarea, core_area, purpose, frequency, next_due, status, notes) VALUES (?,?,?,?,?,?,?,?,?)""", (title, area_id, subarea, subarea, purpose, freq, str(date.today()), status, notes))
        st.success("Routine saved.")
        st.rerun()

def routine_frequency_controls(routine: dict[str, Any]) -> None:
    st.markdown(f"<div class='muted'>Current repeat pattern: <strong>{escape_html(routine.get('frequency') or 'Weekly')}</strong></div>", unsafe_allow_html=True)
    starts = st.date_input("Repeat starts", value=parse_date(routine.get("next_due")) if routine and routine.get("next_due") else date.today(), format="DD/MM/YYYY", help="First date used when preparing routine activity calendar events and Google Tasks prompt rows.")
    new_freq = frequency_builder(routine.get("frequency"), key_prefix=f"routine_{routine['id']}")
    if st.button("Save repeat pattern", key=f"save_freq_{routine['id']}"):
        execute("UPDATE routines SET frequency=?, next_due=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (new_freq, str(starts), routine["id"]))
        stage_exports_from_actions()
        st.success("Repeat pattern saved.")
        st.rerun()

def routine_checklist_form(routine: dict[str, Any]) -> None:
    st.markdown("<div class='muted'>Add one checklist item per line. These are printed as indented subtasks below the routine.</div>", unsafe_allow_html=True)
    current_items = [line.strip().lstrip('-•').strip() for line in str(routine.get("checklist") or "").splitlines() if line.strip()]
    if current_items:
        st.markdown("<ul>" + "".join(f"<li>{escape_html(item)}</li>" for item in current_items) + "</ul>", unsafe_allow_html=True)
    with st.form(f"routine_checklist_{routine['id']}"):
        checklist = st.text_area("Checklist items", value="\n".join(current_items), height=180)
        submitted = st.form_submit_button("Save checklist")
    if submitted:
        cleaned = "\n".join([line.strip().lstrip('-•').strip() for line in checklist.splitlines() if line.strip()])
        execute("UPDATE routines SET checklist=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (cleaned, routine["id"]))
        st.success("Checklist saved.")
        st.rerun()


def routine_next_due(freq: str) -> date:
    today = date.today()
    lower = (freq or "Weekly").lower()
    if "as needed" in lower or "does not repeat" in lower:
        return today
    if "daily" in lower or "day" in lower:
        return today + timedelta(days=1)
    if "fortnight" in lower or "every 2 week" in lower:
        return today + timedelta(days=14)
    if "month" in lower:
        return today + timedelta(days=30)
    if "weekday" in lower:
        return today + timedelta(days=1 if today.weekday() < 4 else 3)
    return today + timedelta(days=7)


def areas_page() -> None:
    page_title("Areas", "Match the app to your Workspace folder system and generate Markdown files.")
    help_note(f"Numbered area folders are created under {root_folder()} if missing. Existing files and non-empty folders are not deleted or emptied. Markdown files may be updated, with backups created first. Only numbered top-level folders are detected as Areas, for example 01_Body_And_Stability. New area folders continue the existing numbered sequence, for example 07_New_Area.")
    if st.button("Create missing area folders and Markdown files"):
        regenerate_area_markdown()
        st.success("Workspace folders and Markdown files updated.")
    with st.expander("Add area", expanded=False):
        area_form(None)
    data = areas_df(active_only=True)
    if data.empty:
        st.info("No areas yet.")
        return
    col_list, col_main = st.columns([0.30, 0.70])
    with col_list:
        st.subheader("Areas")
        labels = {f"{row['name']}": int(row["id"]) for _, row in data.iterrows()}
        selected_label = st.radio("Select an area", list(labels.keys()), label_visibility="collapsed")
        selected_id = labels[selected_label]
    with col_main:
        rows = query("SELECT * FROM areas WHERE id=?", (selected_id,))
        if rows:
            area = rows[0]
            st.subheader(area["name"])
            st.markdown(tag_markup(area_tag(area["name"], area.get("google_color"))), unsafe_allow_html=True)
            st.markdown("<div class='muted'>This colour is used for this area throughout the app and should match the Google Calendar sub-calendar where possible.</div>", unsafe_allow_html=True)
            area_form(area)
            if st.button("Update folder and Markdown for this area", key=f"area_md_{area['id']}"):
                ensure_area_folder(area["name"])
                regenerate_area_markdown()
                st.success("Area folder and Markdown updated.")


def area_form(area: dict[str, Any] | None) -> None:
    with st.form(f"area_form_{area['id'] if area else 'new'}"):
        name = st.text_input("Area name", value=area.get("name", "") if area else "")
        if area:
            folder_default = area.get("folder_path") or str(suggested_area_folder(name or "New_Area"))
            md_default = area.get("markdown_path") or str(area_markdown_path_for_folder(Path(folder_default), name or "New_Area"))
        else:
            suggested_folder = suggested_area_folder(name or "New_Area")
            folder_default = str(suggested_folder)
            md_default = str(area_markdown_path_for_folder(suggested_folder, name or "New_Area"))
        desc = st.text_area("Description", value=area.get("description", "") if area else "")
        folder = st.text_input("Folder path", value=folder_default, help="Suggested from the existing numbered area folders. New areas continue the sequence, for example 07_New_Area. Existing files in this folder will not be deleted.")
        md = st.text_input("Markdown path", value=md_default)
        cal = st.text_input("Default Google Calendar", value=area.get("default_calendar", name) if area else name)
        colour_default = area.get("google_color", DEFAULT_AREA_COLOURS.get(name, "Graphite")) if area else DEFAULT_AREA_COLOURS.get(name, "Graphite")
        colour_options = list(GOOGLE_CALENDAR_COLOURS.keys())
        colour = st.selectbox("Google Calendar colour", colour_options, index=colour_options.index(colour_default) if colour_default in colour_options else 0, help="Used to colour this area throughout the app and keep it aligned with your Google Calendar sub-calendar colour.")
        swatch = GOOGLE_CALENDAR_COLOURS.get(colour, GOOGLE_CALENDAR_COLOURS["Graphite"])
        st.markdown(f"<div style='display:inline-block; min-width:170px; padding:8px 12px; border-radius:999px; background:{swatch['bg']}; color:{swatch['text']}; font-weight:600; margin:4px 0 8px 0;'>{escape_html(colour)}</div>", unsafe_allow_html=True)
        task = st.text_input("Default Google Tasks list", value=area.get("default_task_list", name) if area else name)
        notes = st.text_area("Notes", value=area.get("notes", "") if area else "")
        submitted = st.form_submit_button("Save area")
    if submitted and name.strip():
        if area:
            execute("""UPDATE areas SET name=?, description=?, folder_path=?, markdown_path=?, default_calendar=?, default_task_list=?, google_color=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""", (name, desc, folder, md, cal, task, colour, notes, area["id"]))
        else:
            execute("""INSERT INTO areas (name, description, folder_path, markdown_path, default_calendar, default_task_list, google_color, notes) VALUES (?,?,?,?,?,?,?,?)""", (name, desc, folder, md, cal, task, colour, notes))
        ensure_area_folder(name)
        regenerate_area_markdown()
        st.success("Area saved.")
        st.rerun()


def review_page() -> None:
    page_title("Review Queue", "Review items that need a decision, correction, next action, or closure criteria.")
    if st.button("Run review checks", key="run_review_checks_3000"):
        generate_review_issues()
        st.rerun()
    data = review_df(open_only=True)
    if data.empty:
        st.success("No open review items.")
        return
    for _, r in data.iterrows():
        st.markdown(
            f"""
            <div class='card'>
                <div class='tag'>Priority: {escape_html(r['priority'])}</div>
                <div class='tag'>{escape_html(r['type'])}</div>
                <h3>{escape_html(r['source'])}</h3>
                <p><strong>What needs attention</strong><br>{escape_html(r['message'])}</p>
                <p><strong>Suggested next step</strong><br>{escape_html(r['suggested_step'])}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    options = {f"{r['id']}: {r['source']}": int(r["id"]) for _, r in data.iterrows()}
    selected = st.selectbox("Mark item as resolved", list(options.keys()))
    if st.button("Resolve selected item"):
        execute("UPDATE review_issues SET status='Resolved', resolved_at=CURRENT_TIMESTAMP WHERE id=?", (options[selected],))
        st.rerun()



def render_latest_file_controls(state_key: str, file_label: str, folder_label: str) -> None:
    path_value = st.session_state.get(state_key, "")
    if not path_value:
        return
    path = Path(path_value)
    if not path.exists():
        st.warning(f"Last exported file is no longer available: {path}")
        return
    st.markdown(f"<div class='small-muted'>Last export: {escape_html(str(path))}</div>", unsafe_allow_html=True)
    c1, c2 = st.columns([0.32, 0.68])
    if c1.button(file_label, key=f"open_file_{state_key}"):
        open_file(path)
    if c2.button(folder_label, key=f"open_folder_{state_key}"):
        open_folder(path)

def _export_folder_controls(kind: str) -> None:
    """Show stable folder controls that do not depend on currently staged rows."""
    if kind == "calendar":
        folder = calendar_export_folder()
        label = "Open Google Calendar Exports folder"
        key = "open_calendar_export_folder_stable"
    elif kind == "tasks":
        folder = google_tasks_export_folder()
        label = "Open Google Tasks Exports folder"
        key = "open_tasks_export_folder_stable"
    else:
        folder = tasklist_export_folder()
        label = "Open Tasklists folder"
        key = "open_tasklist_export_folder_stable"
    folder.mkdir(parents=True, exist_ok=True)
    st.markdown(f"<div class='small-muted'>Export folder: {escape_html(str(folder))}</div>", unsafe_allow_html=True)
    if st.button(label, key=key):
        open_folder(folder)


def calendar_export_page() -> None:
    page_title("Google Calendar Export", "Prepare and review Google Calendar time blocks, then export the visible rows as an ICS file for Google Calendar.")
    _export_folder_controls("calendar")
    area = st.selectbox("Area", area_options(include_all=True), key="cal_area_filter")
    area_id = area_id_by_name(area)
    if st.button("Prepare export rows", key="prepare_calendar_export_rows"):
        stage_exports_from_actions(area_id=area_id)
        st.success("Google Calendar export rows prepared.")
    where = "WHERE cb.export_status='Staged'"
    params: tuple = ()
    if area_id:
        where += " AND cb.area_id=?"
        params = (area_id,)
    data = calendar_df(where, params)
    if data.empty:
        st.info("No staged Google Calendar rows for this filter.")
        return
    table = data[["id","title","area_name","goal_title","routine_title","start_datetime","end_datetime","calendar_name","recurrence_rule","export_status"]].rename(columns={"id":"ID","title":"Title","area_name":"Area","goal_title":"Goal","routine_title":"Routine","start_datetime":"Start","end_datetime":"End","calendar_name":"Google Calendar","recurrence_rule":"Repeat","export_status":"Status"})
    table = format_dates(table)
    selected_indices = select_rows_table(table, "calendar_export_table")
    visible_ids = [int(x) for x in data["id"].tolist()]
    selected_ids = [int(data.iloc[i]["id"]) for i in selected_indices if i < len(data)]
    st.markdown("<div class='small-muted'>Visible rows will be exported. Select rows in the table only if you want to remove them from the export list. Exports are written to 00_System.</div>", unsafe_allow_html=True)
    c1,c2 = st.columns(2)
    if c1.button("Export visible rows as ICS", key="export_visible_calendar_ics"):
        rows = data.to_dict("records")
        suffix = slug(area if area != "All areas" else "visible")
        path = export_ics(rows, unique_path(calendar_export_folder() / f"google_calendar_{suffix}_{date.today().strftime('%Y%m%d')}.ics"))
        execute(f"UPDATE calendar_blocks SET export_status='Exported', exported_at=CURRENT_TIMESTAMP WHERE id IN ({','.join('?' for _ in visible_ids)})", tuple(visible_ids))
        log_export("Google Calendar ICS", path, len(rows), area)
        st.session_state["latest_calendar_export"] = str(path)
        st.success(f"Created {path.name}. Click the Open Google Calendar Exports folder button above to find it.")
    if c2.button("Remove selected rows from export", key="remove_selected_calendar_rows"):
        if not selected_ids:
            st.warning("Select one or more rows in the table to remove them from the export list.")
        else:
            execute(f"UPDATE calendar_blocks SET export_status='Removed', removed_at=CURRENT_TIMESTAMP WHERE id IN ({','.join('?' for _ in selected_ids)})", tuple(selected_ids))
            st.rerun()


def google_tasks_export_page() -> None:
    page_title("Google Tasks Export", "Prepare and review Google Tasks starting prompts, then export the visible rows as a CSV for the Apps Script importer. Repeating routines export one next prompt by default.")
    _export_folder_controls("tasks")
    guide_col, script_col = st.columns(2)
    with guide_col:
        if st.button("Create Google Tasks setup files", use_container_width=True, key="create_google_tasks_setup_files_on_export_page"):
            readme_path, script_path = write_google_tasks_setup_files()
            st.success("Google Tasks setup guide and Apps Script file updated.")
            st.caption(str(readme_path))
    with script_col:
        if st.button("Open Google Tasks setup guide", use_container_width=True, key="open_google_tasks_setup_guide_on_export_page"):
            readme_path, script_path = write_google_tasks_setup_files()
            open_file(readme_path)
    area = st.selectbox("Area", area_options(include_all=True), key="task_area_filter")
    area_id = area_id_by_name(area)
    routine_prompt_count = st.selectbox(
        "Routine prompt rows",
        [1, 2, 4, 8],
        index=0,
        help="Repeating Google Calendar blocks export as one recurring event. Google Tasks CSV creates one task per row, so one next prompt is the default. Increase this only if you deliberately want future prompt rows prepared.",
        key="routine_prompt_row_count",
    )
    if st.button("Prepare export rows", key="prepare_tasks_export_rows"):
        stage_exports_from_actions(area_id=area_id, routine_task_occurrences=int(routine_prompt_count))
        st.success("Google Tasks export rows prepared.")
    where = "WHERE rt.export_status='Staged'"
    params: tuple = ()
    if area_id:
        where += " AND rt.area_id=?"
        params = (area_id,)
    data = reminders_df(where, params)
    if data.empty:
        st.info("No staged Google Tasks rows for this filter.")
        return
    table = data[["id","title","area_name","goal_title","due_date","reminder_time","task_list","linked_calendar_summary","export_status"]].rename(columns={"id":"Task ID","title":"Starting prompt","area_name":"Area","goal_title":"Goal","due_date":"Due date","reminder_time":"Prompt reference time","task_list":"Google Tasks list","linked_calendar_summary":"Related Google Calendar item","export_status":"Status"})
    table["Related Google Calendar item"] = table["Related Google Calendar item"].fillna("").replace("", "None")
    table = format_dates(table)
    selected_indices = select_rows_table(table, "tasks_export_table")
    visible_ids = [int(x) for x in data["id"].tolist()]
    selected_ids = [int(data.iloc[i]["id"]) for i in selected_indices if i < len(data)]
    st.markdown("<div class='small-muted'>Visible rows will be exported. Select rows in the table only if you want to remove them from the export list. Exports are written to 00_System.</div>", unsafe_allow_html=True)
    c1,c2 = st.columns(2)
    if c1.button("Export visible rows as CSV", key="export_visible_tasks_csv"):
        rows = data.to_dict("records")
        suffix = slug(area if area != "All areas" else "visible")
        path = export_tasks_csv(rows, unique_path(google_tasks_export_folder() / f"google_tasks_{suffix}_{date.today().strftime('%Y%m%d')}.csv"))
        execute(f"UPDATE reminder_tasks SET export_status='Exported', exported_at=CURRENT_TIMESTAMP WHERE id IN ({','.join('?' for _ in visible_ids)})", tuple(visible_ids))
        log_export("Google Tasks CSV export", path, len(rows), area)
        st.session_state["latest_tasks_export"] = str(path)
        st.success(f"Created {path.name}. Click the Open Google Tasks Exports folder button above to find it.")
    if c2.button("Remove selected rows from export", key="remove_selected_tasks_rows"):
        if not selected_ids:
            st.warning("Select one or more rows in the table to remove them from the export list.")
        else:
            execute(f"UPDATE reminder_tasks SET export_status='Removed', removed_at=CURRENT_TIMESTAMP WHERE id IN ({','.join('?' for _ in selected_ids)})", tuple(selected_ids))
            st.rerun()


def archive_promotion_label(entity_type: str) -> str:
    mapping = {
        "goal": "Promote to Goals",
        "routine": "Promote to Routines",
        "action": "Promote to Actions",
    }
    return mapping.get((entity_type or "").lower(), "Promote from Archive")


def archive_page() -> None:
    page_title("Archive", "Review closed or abandoned work, download records, clear with backup, or promote items back into use.")
    data = df("SELECT * FROM archive_entries ORDER BY archived_at DESC")
    if data.empty:
        st.info("Archive is empty.")
        return

    display = data.rename(columns={"entity_type":"Type","title":"Title","final_status":"Final status","summary":"Summary","archived_at":"Archived","promoted_at":"Promoted"})
    cols = [c for c in ["id","Type","Title","Final status","Summary","Archived","Promoted"] if c in display.columns]
    st.dataframe(format_dates(display[cols]), use_container_width=True, hide_index=True)
    csv_bytes = data.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Download archive CSV", csv_bytes, f"archive_{date.today().strftime('%Y%m%d')}.csv", "text/csv")

    selected = st.selectbox("Select archive item", data["id"].tolist(), format_func=lambda x: f"{x}: {data.loc[data['id']==x, 'title'].iloc[0]}")
    item = query("SELECT * FROM archive_entries WHERE id=?", (int(selected),))[0]
    card(
        item["title"],
        f"Type: {escape_html(item['entity_type'])}<br>Final status: {escape_html(item['final_status'])}<br>Summary: {escape_html(item['summary'])}<br>Carried forward: {escape_html(item['carried_forward'])}<br>Promoted: {escape_html(item['promoted_at'] or 'No')}",
    )

    c1, c2, c3 = st.columns([0.34, 0.33, 0.33])
    if c1.button(archive_promotion_label(item["entity_type"])):
        message = promote_archive_entry_to_origin(int(selected))
        st.success(message)
        st.rerun()
    if c2.button("Add to Review Queue"):
        restore_archive_entry(int(selected))
        st.success("Review item created.")
    if c3.button("Back up and clear archive"):
        backup = backup_folder() / "Archive" / f"archive_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        backup.parent.mkdir(parents=True, exist_ok=True)
        data.to_csv(backup, index=False)
        execute("DELETE FROM archive_entries")
        st.success(f"Archive cleared after backup: {backup.name}")
        st.rerun()


def sources_changed_since(timestamp: str | None) -> bool:
    if not timestamp:
        return False
    try:
        latest_values = []
        for table in ["goals", "actions", "routines", "areas"]:
            value = scalar(f"SELECT MAX(updated_at) FROM {table}")
            if value:
                latest_values.append(str(value))
        return any(value > str(timestamp) for value in latest_values)
    except Exception:
        return False


def clear_sample_data() -> Path | None:
    backup = backup_database("before_clear_sample_data")
    for table in ["actions", "goals", "routines", "calendar_blocks", "reminder_tasks", "review_issues", "archive_entries", "sessions"]:
        execute(f"DELETE FROM {table}")
    set_setting("sample_data_cleared", "Yes")
    set_setting("weekly_focus", "No main focus")
    return backup


def create_update_backup() -> Path:
    """Create a portable backup before installing or replacing app files.

    This backs up the local SQLite database and a small settings snapshot. It does
    not delete or modify the user's Workspace folders.
    """
    ensure_core_folders()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_dir = backup_folder() / "Updates"
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / f"pathmark_update_backup_{stamp}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        if DB_PATH.exists():
            z.write(DB_PATH, "pathmark.db")
        settings = {r["key"]: r["value"] for r in query("SELECT key, value FROM app_settings ORDER BY key")}
        z.writestr("settings.json", json.dumps(settings, indent=2))
        z.writestr("README.txt", "Backup created before updating Pathmark. Restore the database from pathmark.db in Settings if needed. Local Markdown and export files were not deleted or changed by this backup.\n")
    log_export("Update backup", zip_path, 1, "before_update")
    return zip_path


def setup_page() -> None:
    apply_css()
    page_title("Set up Pathmark", "Choose the workspace where the app should store folders, Markdown, exports, and starter data.")
    st.write("This setup writes inside your workspace and creates missing folders only. It does not delete, empty, or replace existing files or folders.")
    st.info("Your Workspace folder is where Pathmark keeps for projects, area folders, calendar exports, Google Tasks exports, tasklists, and backups. Keep your project folders inside this architecture so Pathmark can detect them as Areas.")
    with st.form("first_run_setup"):
        system_name = st.text_input("System name", value=get_setting("system_name", "Pathmark") or "Pathmark")
        root = st.text_input("Workspace folder", value=get_setting("root_folder", str(DEFAULT_DEVELOPMENT_ROOT)) or str(DEFAULT_DEVELOPMENT_ROOT), help="This is the folder Pathmark uses for projects, area folders, exports, tasklists, and backups. Existing files are left in place.")
        current_mode = get_setting("theme_mode", launcher_initial_theme_mode()) or launcher_initial_theme_mode()
        theme_options = ["Default", "Seasonal", "Persimmon", "Marigold", "Moss", "Lagoon", "Iris", "Rosewood", "Custom"]
        current_preset = get_setting("theme_preset", launcher_initial_theme_preset()) or launcher_initial_theme_preset()
        mode = st.radio("Mode", ["Light", "Dark"], index=["Light", "Dark"].index(current_mode) if current_mode in ["Light", "Dark"] else 0, horizontal=True)
        preset = st.selectbox("Theme", theme_options, index=theme_options.index(current_preset) if current_preset in theme_options else 0, help="Default matches the homepage and launcher. Seasonal changes with the season. Other themes can be saved locally and included in backups.")
        default_calendar = st.text_input("Default Google Calendar", value=get_setting("default_calendar", "Pathmark"))
        default_task_list = st.text_input("Default Google Tasks list", value=get_setting("default_task_list", "Pathmark"))
        load_examples = st.checkbox("Load editable starter examples", value=False)
        submitted = st.form_submit_button("Create setup")
    if submitted:
        set_setting("system_name", system_name)
        set_setting("root_folder", root)
        set_setting("system_folder", str(Path(root).expanduser() / "00_System"))
        set_setting("calendar_export_folder", str(Path(root).expanduser() / "00_System" / "Google Calendar Exports"))
        set_setting("google_tasks_export_folder", str(Path(root).expanduser() / "00_System" / "Google Tasks Exports"))
        set_setting("tasklist_export_folder", str(Path(root).expanduser() / "00_System" / "Tasklists"))
        set_setting("backup_folder", str(Path(root).expanduser() / "00_System" / "Backups"))
        set_setting("theme_mode", mode)
        set_setting("theme_preset", preset)
        sync_launcher_theme_file(preset, mode)
        set_setting("default_calendar", default_calendar)
        set_setting("default_task_list", default_task_list)
        set_setting("load_sample_data", "Yes" if load_examples else "No")
        set_setting("setup_complete", "Yes")
        ensure_core_folders()
        sync_areas_from_existing_folders()
        if load_examples and table_count("areas") == 0:
            seed_data()
        st.success("Setup complete.")
        st.rerun()


def settings_page() -> None:
    page_title("Settings", "Manage setup, folders, appearance, backups, diagnostics, and compatibility.")

    setup_tab, appearance_tab, maintenance_tab, compatibility_tab = st.tabs([
        "Setup and folders",
        "Appearance",
        "Maintenance",
        "Compatibility and logs",
    ])

    with setup_tab:
        st.subheader("System setup")
        st.caption("The Pathmark.exe launcher should be used to choose the workspace folder on first launch. In the app, use the Root folder field below if you need to point Pathmark at a different workspace later.")
        st.info("The root folder is the workspace Pathmark uses for area folders, exports, tasklists, backups, and the local database. The replaceable Pathmark folder should live somewhere separate, such as Documents\\Pathmark.")

        with st.form("settings_setup_form"):
            system_name = st.text_input("System name", value=get_setting("system_name", "Pathmark"))
            root = st.text_input(
                "Root folder",
                value=str(root_folder()),
                help="Workspace folder. Pathmark creates missing system/export folders here, detects top-level folders as Areas, and does not delete existing files.",
            )
            system_path = st.text_input("System folder", value=str(system_folder()), help="Folder containing DEV_DASHBOARD.md and SYSTEM_GUIDE.md.")
            calendar_path = st.text_input("Google Calendar export folder", value=str(calendar_export_folder()))
            tasks_path = st.text_input("Google Tasks export folder", value=str(google_tasks_export_folder()))
            tasklist_path = st.text_input("Tasklist export folder", value=str(tasklist_export_folder()))
            backup_path = st.text_input("Backup folder", value=str(backup_folder()))
            default_calendar = st.text_input("Default Google Calendar", value=get_setting("default_calendar", "Pathmark"))
            default_task_list = st.text_input("Default Google Tasks list", value=get_setting("default_task_list", "Pathmark"))
            release_hub_url = st.text_input("Update hub URL", value=get_setting("release_hub_url", ""), help="Optional link to the Streamlit release hub for updates.")
            submitted = st.form_submit_button("Save setup settings")
        if submitted:
            set_setting("system_name", system_name)
            set_setting("root_folder", root)
            set_setting("system_folder", system_path)
            set_setting("calendar_export_folder", calendar_path)
            set_setting("google_tasks_export_folder", tasks_path)
            set_setting("tasklist_export_folder", tasklist_path)
            set_setting("backup_folder", backup_path)
            set_setting("default_calendar", default_calendar)
            set_setting("default_task_list", default_task_list)
            set_setting("release_hub_url", release_hub_url)
            ensure_core_folders()
            imported = sync_areas_from_existing_folders()
            msg = "Settings saved. Missing folders were created if needed; existing files were not deleted or emptied."
            if imported:
                msg += f" Imported {imported} area folder(s)."
            st.success(msg)
            st.rerun()

        st.markdown("---")
        st.subheader("Folder actions")
        st.caption(f"Current Pathmark root: `{root_folder()}`")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            if st.button("Open Workspace folder", use_container_width=True, key="open_development_folder_3311"):
                open_folder(root_folder())
        with col_b:
            if st.button("Open 00_System folder", use_container_width=True, key="open_system_folder_from_setup"):
                open_folder(system_folder())
        with col_c:
            if st.button("Create missing folders", use_container_width=True, key="create_missing_folders_3317"):
                ensure_core_folders()
                imported = sync_areas_from_existing_folders()
                msg = "Pathmark and 00_System folders are ready. Existing files were left in place."
                if imported:
                    msg += f" Imported {imported} area folder(s)."
                st.success(msg)
        if st.button("Create area folders and indexes", use_container_width=True, key="create_area_folders_and_indexes_3320"):
            regenerate_area_markdown()
            st.success("Area folders and Markdown indexes updated.")

        st.markdown("---")
        st.subheader("Markdown generation")
        st.caption("Markdown files are backed up before being updated. Existing non-Markdown files are not changed.")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Create goal and routine Markdown", use_container_width=True, key="create_goal_and_routine_markdown_3329"):
                regenerate_goal_and_routine_markdown()
                st.success("Goal and routine Markdown files updated.")
        with col_b:
            if st.button("Create all Markdown", use_container_width=True, key="create_all_markdown_3333"):
                regenerate_area_markdown()
                regenerate_goal_and_routine_markdown()
                st.success("Area, goal, and routine Markdown files updated.")

    with appearance_tab:
        st.subheader("Appearance")
        current_mode = get_setting("theme_mode", "Light")
        current_preset = get_setting("theme_preset", "Default")
        mode = st.radio(
            "Mode",
            ["Light", "Dark"],
            horizontal=True,
            index=["Light", "Dark"].index(current_mode) if current_mode in ["Light", "Dark"] else 0,
            key="theme_mode_select",
        )
        preset_options = ["Default", "Seasonal", "Persimmon", "Marigold", "Moss", "Lagoon", "Iris", "Rosewood", "Custom"]
        preset = st.selectbox(
            "Theme",
            preset_options,
            index=preset_options.index(current_preset) if current_preset in preset_options else 0,
            key="theme_preset_select",
            help="Default matches the public download page and launcher. Seasonal follows the current season. The other themes are higher-contrast colour families. Custom lets you test your own palette.",
        )
        if mode != current_mode or preset != current_preset:
            set_setting("theme_mode", mode)
            set_setting("theme_preset", preset)
            sync_launcher_theme_file(preset, mode)
            st.success("Appearance updated.")
            st.rerun()

        if preset == "Custom":
            st.caption("Custom colours are saved locally in the app database.")
            c1, c2 = st.columns(2)
            custom_fields = [
                ("background", "Page background"),
                ("surface", "Card background"),
                ("surface_alt", "Secondary surface"),
                ("border", "Borders"),
                ("text", "Main text"),
                ("muted_text", "Secondary text"),
                ("primary", "Button/accent"),
                ("input_bg", "Input background"),
                ("input_border", "Input border"),
            ]
            updates = {}
            for i, (key, label) in enumerate(custom_fields):
                parent = c1 if i % 2 == 0 else c2
                with parent:
                    current = get_setting(f"custom_{key}", theme().get(key, "#ffffff"))
                    updates[key] = st.color_picker(label, current, key=f"custom_{key}_picker")
            if st.button("Save custom theme", use_container_width=True):
                for key, value in updates.items():
                    set_setting(f"custom_{key}", value)
                set_setting("theme_preset", "Custom")
                sync_launcher_theme_file("Custom", mode)
                st.success("Custom theme saved.")
                st.rerun()

    with maintenance_tab:
        st.subheader("Standard routines and review")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Create missing standard routines", use_container_width=True, key="create_missing_standard_routines_3394"):
                created = ensure_standard_routines()
                st.success(f"Created {created} missing standard routine(s).")
        with col_b:
            if st.button("Run review checks", use_container_width=True, key="run_review_checks_3398"):
                generate_review_issues()
                st.success("Review checks updated.")

        st.markdown("---")
        st.subheader("Data safety and updates")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Create database backup", use_container_width=True, key="create_database_backup_3406"):
                backup = backup_database("manual")
                st.success(f"Backup created: {backup.name if backup else 'No database found'}")
            if st.button("Clear sample data", use_container_width=True, key="clear_sample_data_3412"):
                backup = clear_sample_data()
                st.success(f"Sample data cleared. Backup: {backup.name if backup else 'No backup created'}")
                st.rerun()
        with col_b:
            st.caption("Use the Pathmark.exe launcher for updates. It creates the update backup and opens the update hub from one Update button.")
            uploaded_db = st.file_uploader(
                "Restore database backup",
                type=["db", "sqlite", "sqlite3"],
                help="Restoring replaces the Pathmark app database after creating a backup.",
            )
            if uploaded_db is not None:
                if st.button("Restore uploaded database", use_container_width=True, key="restore_uploaded_database_3428"):
                    backup_database("before_restore")
                    DB_PATH.write_bytes(uploaded_db.getvalue())
                    st.success("Database restored. The app will reload.")
                    st.rerun()

    with compatibility_tab:
        st.subheader("Export diagnostics")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            if st.button("Create sample ICS", use_container_width=True, key="create_sample_ics_3438"):
                now = datetime.now().replace(second=0, microsecond=0)
                sample = [{"title":"Sample Google Calendar block","start_datetime":now.isoformat(),"end_datetime":(now+timedelta(hours=1)).isoformat(),"description":"Sample file for Google Calendar import testing.","location":"","recurrence_rule":"","alarm_minutes":10}]
                path = export_ics(sample, unique_path(calendar_export_folder() / f"sample_google_calendar_{date.today().strftime('%Y%m%d')}.ics"))
                log_export("Google Calendar ICS diagnostic", path, 1, "Sample")
                st.session_state["diagnostic_file"] = str(path)
                st.success(f"Created {path.name}")
        with col_b:
            if st.button("Create sample Google Tasks CSV", use_container_width=True, key="create_sample_google_tasks_csv_3446"):
                sample = [{"id":"DIAG001","task_list":get_setting("default_task_list", "Pathmark"),"title":"Open the diagnostic task","notes":"Sample file for Google Tasks Apps Script import testing.","due_date":date.today().isoformat(),"reminder_time":"09:00","status":"needsAction"}]
                path = export_tasks_csv(sample, unique_path(google_tasks_export_folder() / f"sample_google_tasks_{date.today().strftime('%Y%m%d')}.csv"))
                log_export("Google Tasks CSV diagnostic", path, 1, "Sample")
                st.session_state["diagnostic_file"] = str(path)
                st.success(f"Created {path.name}")
        with col_c:
            if st.button("Open 00_System folder", use_container_width=True, key="open_system_folder_from_compatibility"):
                open_folder(system_folder())

        diag = st.session_state.get("diagnostic_file")
        if diag and Path(diag).exists():
            if st.button("Open latest diagnostic file", key="open_latest_diagnostic_file_3458"):
                open_file(Path(diag))

        st.markdown("---")
        st.subheader("Export log")
        logs = df("SELECT export_type AS Type, file_path AS File, row_count AS Rows, scope AS Scope, status AS Status, created_at AS Created FROM export_logs ORDER BY created_at DESC LIMIT 20")
        if logs.empty:
            st.caption("No exports have been logged yet.")
        else:
            logs_display = logs.copy()
            logs_display["Source changed after export"] = logs_display["Created"].apply(lambda x: "Yes" if sources_changed_since(str(x)) else "No")
            st.dataframe(format_dates(logs_display), use_container_width=True, hide_index=True)
            selected_log = st.selectbox("Open exported file", logs["File"].tolist(), key="open_export_log")
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Open selected exported file", use_container_width=True, key="open_selected_exported_file_3473"):
                    open_file(Path(selected_log))
            with col_b:
                if st.button("Open selected export folder", use_container_width=True, key="open_selected_export_folder_3476"):
                    open_folder(Path(selected_log))

        st.markdown("---")
        st.subheader("Google Tasks Apps Script setup")
        st.write("Pathmark can create a setup guide and Apps Script file in the Google Tasks Exports folder. Use these to create the Google Sheet importer for Google Tasks.")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Create Google Tasks setup files", use_container_width=True, key="create_google_tasks_setup_files_from_settings"):
                readme_path, script_path = write_google_tasks_setup_files()
                st.success("Google Tasks setup guide and Apps Script file updated.")
                st.caption(str(readme_path))
        with col_b:
            if st.button("Open Google Tasks setup guide", use_container_width=True, key="open_google_tasks_setup_guide_from_settings"):
                readme_path, script_path = write_google_tasks_setup_files()
                open_file(readme_path)

        st.subheader("Export compatibility")
        st.write("Google Tasks CSV columns: Task ID, Task List, Title, Notes, Due Date, Reminder Time, Status. Extra columns may include Repeat Pattern and Related Google Calendar Item; the Apps Script ignores extras. Repeating routine prompts are exported as individual CSV rows, with one next prompt prepared by default.")
        st.write("User-facing dates use NZ formatting. Export dates stay machine-readable where Google import requires it.")
        st.write("Google Calendar exports use ICS format with DTSTART, DTEND, SUMMARY, DESCRIPTION, LOCATION, RRULE where applicable, and VALARM where applicable.")

        st.subheader("Default status model")
        st.write("Goal statuses: Captured, Active, On hold, Closed, Abandoned")
        st.write("Archive is not a status. Archive stores closed or abandoned work with its review notes.")

# -----------------------------------------------------------------------------
# Utility
# -----------------------------------------------------------------------------


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except Exception:
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except Exception:
            return None


MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def display_date_nz(value: Any) -> str:
    if value in (None, "", pd.NaT):
        return ""
    try:
        d = pd.to_datetime(value)
        if pd.isna(d):
            return ""
        return f"{d.day} {MONTH_NAMES[d.month - 1]} {d.year}"
    except Exception:
        return str(value)


def display_time_nz(value: Any) -> str:
    if value in (None, "", pd.NaT):
        return ""
    try:
        d = pd.to_datetime(value)
        if pd.isna(d):
            return ""
        return d.strftime("%H:%M")
    except Exception:
        return str(value)


def display_datetime(value: Any) -> str:
    if value in (None, "", pd.NaT):
        return ""
    raw = str(value)
    try:
        d = pd.to_datetime(value)
        if pd.isna(d):
            return ""
        has_time = (":" in raw) or ("T" in raw and len(raw) > 10)
        if has_time:
            return f"{d.day} {MONTH_NAMES[d.month - 1]} {d.year}, {d.strftime('%H:%M')}"
        return f"{d.day} {MONTH_NAMES[d.month - 1]} {d.year}"
    except Exception:
        return raw


def format_dates(data: pd.DataFrame) -> pd.DataFrame:
    out = data.copy()
    for col in out.columns:
        lower = col.lower()
        if any(token in lower for token in ["date", "found", "started", "ended", "archived", "created", "updated", "start", "end"]):
            out[col] = out[col].apply(display_datetime)
    return out

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon=page_icon(), layout="wide", initial_sidebar_state="expanded")
    migrate_database_out_of_app_folder()
    init_db()
    ensure_schema_updates()
    ensure_default_settings()
    migrate_routine_checklists_to_tasks()
    if not setup_complete():
        setup_page()
        return
    # If the user already has numbered area folders, make them selectable in the app.
    # This is read-only: it does not rename, move, delete, or empty folders.
    archive_invalid_auto_imported_areas()
    sync_areas_from_existing_folders()
    if get_setting("load_sample_data", "Yes") == "Yes" and table_count("areas") == 0:
        seed_data()
    apply_css()
    st.sidebar.title(get_setting("system_name", "Pathmark") or "Pathmark")
    st.sidebar.caption(f"Version {APP_VERSION} — local file system edition")
    pages = {
        "Home": home_page,
        "Tasklist": this_week_page,
        "Goals and Projects": goals_page,
        "Routines": routines_page,
        "Areas": areas_page,
        "Review Queue": review_page,
        "Google Calendar Export": calendar_export_page,
        "Google Tasks Export": google_tasks_export_page,
        "Archive": archive_page,
        "Settings": settings_page,
    }
    page = st.sidebar.radio("Navigate", list(pages.keys()))
    pages[page]()


if __name__ == "__main__":
    main()
