"""SQLite storage: projects, their latest state, subscribers, events and outbox."""
from __future__ import annotations

import json
import sqlite3
from typing import Dict, Iterable, List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    key TEXT PRIMARY KEY,
    authority TEXT NOT NULL,
    project_id TEXT NOT NULL,
    name TEXT,
    builder TEXT,
    location TEXT,
    district TEXT,
    listed TEXT NOT NULL,
    in_list INTEGER NOT NULL DEFAULT 1,
    state TEXT,
    state_at TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY,
    project_key TEXT NOT NULL,
    taken_at TEXT NOT NULL,
    state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS subscribers (
    id INTEGER PRIMARY KEY,
    name TEXT,
    channel TEXT NOT NULL,
    address TEXT NOT NULL,
    lang TEXT NOT NULL DEFAULT 'en',
    active INTEGER NOT NULL DEFAULT 1,
    paid_until TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (channel, address)
);
CREATE TABLE IF NOT EXISTS subscriptions (
    subscriber_id INTEGER NOT NULL,
    project_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (subscriber_id, project_key)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    project_key TEXT NOT NULL,
    kind TEXT NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    data TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    silent INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY,
    subscriber_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    sent_at TEXT,
    error TEXT,
    UNIQUE (subscriber_id, event_id)
);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class Store:
    def __init__(self, path: str = "rera_tracker.db") -> None:
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # -- meta ----------------------------------------------------------------
    def set_meta(self, key: str, value: str) -> None:
        self.db.execute("INSERT INTO meta(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (key, value))
        self.db.commit()

    def get_meta(self, key: str) -> Optional[str]:
        row = self.db.execute("SELECT v FROM meta WHERE k = ?", (key,)).fetchone()
        return row["v"] if row else None

    # -- projects ------------------------------------------------------------
    def upsert_listed(self, authority: str, listed: Iterable[dict], seen_at: str) -> Dict[str, int]:
        """Store one authority's list; returns counts of new, total and dropped projects."""
        new = total = 0
        keys = set()
        for item in listed:
            key = item["key"]
            keys.add(key)
            total += 1
            exists = self.db.execute("SELECT 1 FROM projects WHERE key = ?", (key,)).fetchone()
            if exists:
                self.db.execute(
                    "UPDATE projects SET name=?, builder=?, location=?, district=?, listed=?, in_list=1, last_seen=? WHERE key=?",
                    (item.get("name"), item.get("builder"), item.get("location"), item.get("district"), _dump(item), seen_at, key),
                )
            else:
                new += 1
                self.db.execute(
                    "INSERT INTO projects(key, authority, project_id, name, builder, location, district, listed, in_list, first_seen, last_seen)"
                    " VALUES(?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                    (key, authority, item["project_id"], item.get("name"), item.get("builder"), item.get("location"),
                     item.get("district"), _dump(item), seen_at, seen_at),
                )
        dropped = 0
        for row in self.db.execute("SELECT key FROM projects WHERE authority = ? AND in_list = 1", (authority,)).fetchall():
            if row["key"] not in keys:
                dropped += 1
                self.db.execute("UPDATE projects SET in_list = 0 WHERE key = ?", (row["key"],))
        self.db.commit()
        return {"new": new, "total": total, "dropped": dropped}

    @staticmethod
    def _project(row: Optional[sqlite3.Row]) -> Optional[dict]:
        if row is None:
            return None
        data = dict(row)
        data["listed"] = json.loads(data["listed"])
        data["state"] = json.loads(data["state"]) if data["state"] else None
        data["in_list"] = bool(data["in_list"])
        return data

    def get_project(self, key: str) -> Optional[dict]:
        return self._project(self.db.execute("SELECT * FROM projects WHERE key = ?", (key,)).fetchone())

    def resolve(self, ref: str) -> List[dict]:
        """Projects matching a key ("gurugram:RERA-GRG-1-2024") or a bare project ID."""
        rows = self.db.execute(
            "SELECT * FROM projects WHERE key = ? OR project_id = ? COLLATE NOCASE ORDER BY key", (ref, ref)
        ).fetchall()
        return [self._project(r) for r in rows]

    def find_projects(self, text: str, limit: int = 20) -> List[dict]:
        like = "%" + text.strip() + "%"
        rows = self.db.execute(
            "SELECT * FROM projects WHERE name LIKE ? OR builder LIKE ? OR project_id LIKE ? OR location LIKE ?"
            " ORDER BY name LIMIT ?",
            (like, like, like, like, limit),
        ).fetchall()
        return [self._project(r) for r in rows]

    def all_listed(self, authority: Optional[str] = None) -> List[dict]:
        if authority:
            rows = self.db.execute("SELECT listed FROM projects WHERE authority = ? AND in_list = 1", (authority,)).fetchall()
        else:
            rows = self.db.execute("SELECT listed FROM projects WHERE in_list = 1").fetchall()
        return [json.loads(r["listed"]) for r in rows]

    def save_state(self, key: str, state: dict, taken_at: str) -> bool:
        """Save the latest state; returns True if it differs from the stored one."""
        dumped = _dump(state)
        row = self.db.execute("SELECT state FROM projects WHERE key = ?", (key,)).fetchone()
        changed = row is None or row["state"] != dumped
        self.db.execute("UPDATE projects SET state = ?, state_at = ? WHERE key = ?", (dumped, taken_at, key))
        if changed:
            self.db.execute("INSERT INTO history(project_key, taken_at, state) VALUES(?, ?, ?)", (key, taken_at, dumped))
        self.db.commit()
        return changed

    # -- subscribers ---------------------------------------------------------
    def add_subscriber(self, name: str, channel: str, address: str, lang: str, created_at: str) -> int:
        row = self.db.execute("SELECT id FROM subscribers WHERE channel = ? AND address = ?", (channel, address)).fetchone()
        if row:
            self.db.execute("UPDATE subscribers SET name = ?, lang = ?, active = 1 WHERE id = ?", (name, lang, row["id"]))
            self.db.commit()
            return int(row["id"])
        cursor = self.db.execute(
            "INSERT INTO subscribers(name, channel, address, lang, created_at) VALUES(?, ?, ?, ?, ?)",
            (name, channel, address, lang, created_at),
        )
        self.db.commit()
        return int(cursor.lastrowid)

    def subscribe(self, subscriber_id: int, project_key: str, created_at: str) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO subscriptions(subscriber_id, project_key, created_at) VALUES(?, ?, ?)",
            (subscriber_id, project_key, created_at),
        )
        self.db.commit()

    def unsubscribe(self, subscriber_id: int, project_key: str) -> None:
        self.db.execute("DELETE FROM subscriptions WHERE subscriber_id = ? AND project_key = ?", (subscriber_id, project_key))
        self.db.commit()

    def get_subscriber(self, channel: str, address: str) -> Optional[dict]:
        row = self.db.execute("SELECT * FROM subscribers WHERE channel = ? AND address = ?", (channel, address)).fetchone()
        return dict(row) if row else None

    def tracked_keys(self) -> List[str]:
        rows = self.db.execute(
            "SELECT DISTINCT s.project_key FROM subscriptions s JOIN subscribers u ON u.id = s.subscriber_id"
            " WHERE u.active = 1 ORDER BY s.project_key"
        ).fetchall()
        return [r["project_key"] for r in rows]

    def subscribers_for(self, project_key: str) -> List[dict]:
        rows = self.db.execute(
            "SELECT u.* FROM subscribers u JOIN subscriptions s ON s.subscriber_id = u.id"
            " WHERE s.project_key = ? AND u.active = 1 ORDER BY u.id",
            (project_key,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- events and outbox ---------------------------------------------------
    def record_event(self, project_key: str, kind: str, key: str, data: dict, detected_at: str, silent: bool) -> Optional[int]:
        """Remember an event; returns its id, or None if it was already recorded."""
        try:
            cursor = self.db.execute(
                "INSERT INTO events(project_key, kind, dedupe_key, data, detected_at, silent) VALUES(?, ?, ?, ?, ?, ?)",
                (project_key, kind, "%s|%s" % (project_key, key), _dump(data), detected_at, int(silent)),
            )
        except sqlite3.IntegrityError:
            return None
        self.db.commit()
        return int(cursor.lastrowid)

    def find_event(self, project_key: str, key: str) -> Optional[int]:
        row = self.db.execute("SELECT id FROM events WHERE dedupe_key = ?", ("%s|%s" % (project_key, key),)).fetchone()
        return int(row["id"]) if row else None

    def events_for(self, project_key: str) -> List[dict]:
        rows = self.db.execute("SELECT * FROM events WHERE project_key = ? ORDER BY id", (project_key,)).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["data"] = json.loads(item["data"])
            item["silent"] = bool(item["silent"])
            out.append(item)
        return out

    def queue_message(self, subscriber_id: int, event_id: int, subject: str, body: str, created_at: str) -> bool:
        cursor = self.db.execute(
            "INSERT OR IGNORE INTO outbox(subscriber_id, event_id, subject, body, created_at) VALUES(?, ?, ?, ?, ?)",
            (subscriber_id, event_id, subject, body, created_at),
        )
        self.db.commit()
        return cursor.rowcount > 0

    def pending_messages(self) -> List[dict]:
        rows = self.db.execute(
            "SELECT o.id, o.subject, o.body, o.created_at, u.channel, u.address, u.name, u.lang"
            " FROM outbox o JOIN subscribers u ON u.id = o.subscriber_id"
            " WHERE o.sent_at IS NULL AND u.active = 1 ORDER BY o.id"
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_sent(self, message_id: int, sent_at: Optional[str], error: Optional[str] = None) -> None:
        self.db.execute("UPDATE outbox SET sent_at = ?, error = ? WHERE id = ?", (sent_at, error, message_id))
        self.db.commit()
