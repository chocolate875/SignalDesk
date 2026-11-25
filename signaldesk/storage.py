from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path

from .markets import normalize_symbol


class Store:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            directory.chmod(0o700)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(directory / "signaldesk.sqlite3", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS bars(
                source TEXT, symbol TEXT, timeframe TEXT, timestamp TEXT, payload TEXT NOT NULL,
                PRIMARY KEY(source,symbol,timeframe,timestamp));
            CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, created REAL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox(
                id INTEGER PRIMARY KEY, event_id TEXT, channel TEXT, target TEXT, payload TEXT,
                status TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0, due REAL DEFAULT 0,
                result TEXT DEFAULT '', UNIQUE(event_id,channel,target));
            CREATE TABLE IF NOT EXISTS analyses(
                id TEXT PRIMARY KEY, symbol TEXT, created REAL, status TEXT, payload TEXT NOT NULL);
        """)
        # Interrupted sends have uncertain delivery: never blindly re-send after restart.
        self.db.execute(
            "UPDATE outbox SET status='unknown',result='进程中断，投递结果未知，请核对后重试' WHERE status='sending'"
        )
        self.db.execute("UPDATE analyses SET status='failed' WHERE status IN ('queued','running')")
        self.db.execute("""UPDATE outbox SET status='cancelled',result='短线提醒已停用'
                           WHERE status='pending' AND event_id IN
                           (SELECT id FROM events WHERE json_extract(payload,'$.sleeve')='short')""")
        self.db.commit()
        self._migrate_asian_symbols()

    def _migrate_asian_symbols(self):
        marker = "migration:hk-five-digit-v1"
        if self.get(marker):
            return
        with self.lock, self.db:
            self.db.execute("DELETE FROM bars WHERE substr(symbol, -3) IN ('.HK', '.SH', '.SZ')")
            for mode in ("live", "demo"):
                key = f"portfolio:{mode}"
                if (items := self.get(key)) is not None:
                    for item in items:
                        if item["symbol"].endswith(".HK"):
                            item["symbol"] = normalize_symbol(item["symbol"])
                    self._write_kv(key, items)
            if (groups := self.get("watchlist-groups:live")) is not None:
                for group in groups:
                    group["symbols"] = list(dict.fromkeys(normalize_symbol(s) for s in group["symbols"]))
                self._write_kv("watchlist-groups:live", groups)
            if (valuations := self.get("valuations:live")) is not None:
                self._write_kv("valuations:live", {normalize_symbol(s): v for s, v in valuations.items()})
            for key, value in self.db.execute("SELECT key, value FROM kv WHERE key LIKE 'state:%:%.HK:%'").fetchall():
                parts = key.split(":")
                parts[2] = normalize_symbol(parts[2])
                self.db.execute("INSERT OR IGNORE INTO kv VALUES(?, ?)", (":".join(parts), value))
            self.db.execute(
                """UPDATE events
                   SET payload = json_set(payload, '$.symbol', printf('%05d.HK', json_extract(payload, '$.symbol')))
                   WHERE json_extract(payload, '$.symbol') GLOB '[0-9]*.HK'"""
            )
            self.db.execute(
                """UPDATE analyses
                   SET symbol = printf('%05d.HK', symbol),
                       payload = json_set(payload, '$.symbol', printf('%05d.HK', symbol))
                   WHERE symbol GLOB '[0-9]*.HK'"""
            )
            self._write_kv(marker, True)

    def get(self, key: str, default=None):
        with self.lock:
            row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key: str, value):
        with self.lock, self.db:
            self._write_kv(key, value)

    def _write_kv(self, key: str, value):
        self.db.execute(
            "INSERT INTO kv VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False, allow_nan=False)),
        )

    @staticmethod
    def _bar_source(source: str) -> str:
        """隔离不同历史数据口径版本：v3 起全面采用前复权（ForwardAdjust）以消除拆股/合股跳空。"""
        if source == "live":
            return "live-fwd-v3"
        if source == "macro-live":
            return "macro-live-fwd-v3"
        return source

    def put_bars(self, source: str, symbol: str, timeframe: str, bars: list[dict]):
        source = self._bar_source(source)
        with self.lock, self.db:
            cursor = self.db.executemany(
                """INSERT INTO bars VALUES(?,?,?,?,?) ON CONFLICT(source,symbol,timeframe,timestamp)
                   DO UPDATE SET payload=excluded.payload
                   WHERE excluded.payload != bars.payload AND
                   (json_extract(excluded.payload,'$.confirmed') OR NOT json_extract(bars.payload,'$.confirmed'))""",
                [(source, symbol, timeframe, b["timestamp"], json.dumps(b, allow_nan=False)) for b in bars],
            )
            return cursor.rowcount

    def replace_bars(self, source: str, symbol: str, timeframe: str, bars: list[dict]) -> int:
        """检测到拆股/合股/除权因子变化时，原子清空并重写该标的整段前复权历史 K 线。"""
        source = self._bar_source(source)
        with self.lock, self.db:
            self.db.execute(
                "DELETE FROM bars WHERE source=? AND symbol=? AND timeframe=?",
                (source, symbol, timeframe),
            )
            if not bars:
                return 0
            cursor = self.db.executemany(
                "INSERT OR REPLACE INTO bars VALUES(?,?,?,?,?)",
                [(source, symbol, timeframe, b["timestamp"], json.dumps(b, allow_nan=False)) for b in bars],
            )
            return cursor.rowcount

    def bars(self, source: str, symbol: str, timeframe: str, count: int = 6000) -> list[dict]:
        source = self._bar_source(source)
        with self.lock:
            rows = self.db.execute(
                "SELECT payload FROM bars WHERE source=? AND symbol=? AND timeframe=? ORDER BY timestamp DESC LIMIT ?",
                (source, symbol, timeframe, count),
            ).fetchall()
        return [json.loads(r[0]) for r in reversed(rows)]

    def event(self, event: dict) -> bool:
        with self.lock, self.db:
            cursor = self.db.execute(
                "INSERT OR IGNORE INTO events VALUES(?,?,?)",
                (event["id"], event["created"], json.dumps(event, ensure_ascii=False, allow_nan=False)),
            )
        return cursor.rowcount == 1

    def events(self, source: str | None = None, count: int = 100, sleeve: str | None = None) -> list[dict]:
        with self.lock:
            rows = self.db.execute(
                """SELECT payload FROM events WHERE (? IS NULL OR json_extract(payload,'$.source')=?)
                   AND (? IS NULL OR json_extract(payload,'$.sleeve')=?) ORDER BY created DESC LIMIT ?""",
                (source, source, sleeve, sleeve, count),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def enqueue(self, event_id: str, channel: str, target: str, payload: dict, due: float = 0):
        with self.lock, self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO outbox(event_id,channel,target,payload,due) VALUES(?,?,?,?,?)",
                (event_id, channel, target, json.dumps(payload, ensure_ascii=False, allow_nan=False), due),
            )

    def due(self, now: float, critical_only: bool = False) -> list[dict]:
        with self.lock:
            condition = " AND json_extract(payload,'$.severity')='critical'" if critical_only else ""
            return [
                dict(r)
                for r in self.db.execute(
                    "SELECT * FROM outbox WHERE status='pending' AND due<=?"
                    + condition
                    + " ORDER BY CASE json_extract(payload,'$.severity') WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,id LIMIT 30",
                    (now,),
                ).fetchall()
            ]

    def delivery(self, row_id: int, status: str, result: str, attempts: int, due: float = 0):
        with self.lock, self.db:
            self.db.execute(
                "UPDATE outbox SET status=?,result=?,attempts=?,due=? WHERE id=?",
                (status, result, attempts, due, row_id),
            )

    def deliveries(self) -> list[dict]:
        with self.lock:
            rows = self.db.execute(
                "SELECT id,event_id,channel,status,attempts,result FROM outbox ORDER BY id DESC LIMIT 60"
            ).fetchall()
        return [dict(r) for r in rows]

    def analysis(self, job: dict):
        with self.lock, self.db:
            self.db.execute(
                "INSERT INTO analyses VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,payload=excluded.payload",
                (
                    job["id"],
                    job["symbol"],
                    job["created"],
                    job["status"],
                    json.dumps(job, ensure_ascii=False, allow_nan=False),
                ),
            )

    def analyses(self, count: int = 50, source: str | None = None) -> list[dict]:
        with self.lock:
            rows = self.db.execute(
                """SELECT status,payload FROM analyses WHERE (? IS NULL OR json_extract(payload,'$.source')=?)
                   ORDER BY created DESC LIMIT ?""", (source, source, count)
            ).fetchall()
        return [{**json.loads(r["payload"]), "status": r["status"]} for r in rows]

    def close(self):
        with self.lock:
            self.db.close()
