"""Persistent reminders the always-on assistant announces out loud, repeatedly,
until you acknowledge them.

Reminders are stored in a SQLite database at
``~/Library/Application Support/Jarvis/reminders.db``.
The engine polls :func:`due_to_announce`; once past due, a reminder is spoken
and re-spoken every ``config.REMINDER_INTERVAL_MIN`` minutes during waking hours
until acknowledged. If ``config.ADD_TO_MAC_REMINDERS`` is on, each new reminder
is also dropped into the macOS Reminders app (so it syncs to your iPhone via
iCloud); that's best-effort and silently no-ops without the Automation grant.

On first run, any existing ``reminders.json`` is migrated automatically.
"""
import datetime
import json
import sqlite3
import subprocess
from contextlib import contextmanager

import config

_DB_PATH = config.app_support_dir() / "reminders.db"
_JSON_PATH = config.app_support_dir() / "reminders.json"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS reminders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    text          TEXT    NOT NULL DEFAULT '',
    due           TEXT,
    created       TEXT    NOT NULL,
    acknowledged  INTEGER NOT NULL DEFAULT 0,
    last_announced TEXT,
    count         INTEGER NOT NULL DEFAULT 0
)
"""


@contextmanager
def _conn():
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(_CREATE_SQL)
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _migrate_json():
    """One-time import of reminders.json into the DB, then rename it out of the way."""
    if not _JSON_PATH.exists():
        return
    try:
        items = json.loads(_JSON_PATH.read_text())
    except Exception:
        return
    if not items:
        _JSON_PATH.rename(_JSON_PATH.with_suffix(".json.migrated"))
        return
    with _conn() as con:
        for r in items:
            con.execute(
                """INSERT OR IGNORE INTO reminders
                   (id, text, due, created, acknowledged, last_announced, count)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    r.get("id"),
                    (r.get("text") or "").strip(),
                    r.get("due"),
                    r.get("created") or _now().isoformat(timespec="seconds"),
                    1 if r.get("acknowledged") else 0,
                    r.get("last_announced"),
                    r.get("count") or 0,
                ),
            )
    _JSON_PATH.rename(_JSON_PATH.with_suffix(".json.migrated"))


def _now():
    return datetime.datetime.now()


def parse_due(iso):
    """Parse a stored/LLM-supplied ISO datetime; return a datetime or None."""
    if not iso:
        return None
    text = str(iso).strip().replace("Z", "")
    try:
        return datetime.datetime.fromisoformat(text)
    except Exception:
        try:
            d = datetime.date.fromisoformat(text[:10])
            return datetime.datetime(d.year, d.month, d.day, 9, 0)
        except Exception:
            return None


def add(text, when_iso):
    """Add a reminder due at ``when_iso``. Returns the stored reminder dict."""
    due = parse_due(when_iso)
    now = _now()
    with _conn() as con:
        cur = con.execute(
            """INSERT INTO reminders (text, due, created, acknowledged, last_announced, count)
               VALUES (?, ?, ?, 0, NULL, 0)""",
            (
                (text or "").strip(),
                due.isoformat(timespec="minutes") if due else None,
                now.isoformat(timespec="seconds"),
            ),
        )
        rid = cur.lastrowid
        row = con.execute("SELECT * FROM reminders WHERE id = ?", (rid,)).fetchone()
    rem = dict(row)
    if config.ADD_TO_MAC_REMINDERS:
        _add_to_mac_reminders(rem["text"], due)
    return rem


def pending():
    """All not-yet-acknowledged reminders, soonest due first."""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM reminders WHERE acknowledged = 0 ORDER BY due ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def due_to_announce(now=None):
    """Reminders that are past due, unacknowledged, inside waking hours, and
    whose nag interval has elapsed since they were last announced."""
    now = now or _now()
    if not (config.REMINDER_WAKE_START <= now.hour < config.REMINDER_WAKE_END):
        return []
    interval = config.REMINDER_INTERVAL_MIN * 60
    with _conn() as con:
        rows = con.execute(
            """SELECT * FROM reminders
               WHERE acknowledged = 0
                 AND due IS NOT NULL
                 AND due <= ?
               ORDER BY due ASC""",
            (now.isoformat(timespec="minutes"),),
        ).fetchall()
    out = []
    for r in rows:
        last = parse_due(r["last_announced"])
        if last is not None and (now - last).total_seconds() < interval:
            continue
        out.append(dict(r))
    return out


def mark_announced(rid, now=None):
    now = now or _now()
    with _conn() as con:
        con.execute(
            "UPDATE reminders SET last_announced = ?, count = count + 1 WHERE id = ?",
            (now.isoformat(timespec="seconds"), rid),
        )


def acknowledge(rid):
    """Mark a single reminder done so it stops nagging."""
    with _conn() as con:
        con.execute(
            "UPDATE reminders SET acknowledged = 1 WHERE id = ?", (rid,)
        )


def cancel(query):
    """Acknowledge (cancel) unacknowledged reminders whose text contains
    ``query``. Returns how many were cancelled."""
    q = (query or "").strip().lower()
    if not q:
        return 0
    with _conn() as con:
        cur = con.execute(
            "UPDATE reminders SET acknowledged = 1 WHERE acknowledged = 0 AND LOWER(text) LIKE ?",
            (f"%{q}%",),
        )
        return cur.rowcount


def cancel_all():
    """Acknowledge every pending reminder. Returns how many were cancelled."""
    with _conn() as con:
        cur = con.execute(
            "UPDATE reminders SET acknowledged = 1 WHERE acknowledged = 0"
        )
        return cur.rowcount


def speak_due(dt):
    """Human phrasing of a due datetime, e.g. 'Saturday, June 7 at 8:00 PM'."""
    return dt.strftime("%A, %B %-d at %-I:%M %p")


# -- macOS Reminders app (best-effort, syncs to iPhone via iCloud) -----------
def _osa_str(s):
    """A safe AppleScript string literal."""
    return '"' + (s or "").replace("\\", "\\\\").replace('"', '\\"') + '"'


def _add_to_mac_reminders(text, due):
    """Add to the macOS Reminders app. Dates are built component-by-component so
    it's locale-independent. Silently no-ops without osascript/permission."""
    name = _osa_str(text)
    if due is not None:
        script = (
            "set d to (current date)\n"
            "set day of d to 1\n"            # avoid month-length overflow first
            f"set year of d to {due.year}\n"
            f"set month of d to {due.month}\n"
            f"set day of d to {due.day}\n"
            f"set hours of d to {due.hour}\n"
            f"set minutes of d to {due.minute}\n"
            "set seconds of d to 0\n"
            'tell application "Reminders" to make new reminder with properties '
            f"{{name:{name}, remind me date:d}}"
        )
    else:
        script = ('tell application "Reminders" to make new reminder with '
                  f"properties {{name:{name}}}")
    try:
        subprocess.run(["osascript", "-e", script], timeout=10,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass  # not macOS, or Automation permission not granted -- local nag still works


# Run migration once at import time
_migrate_json()
