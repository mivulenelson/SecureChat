import sqlite3
import time
from pathlib import Path

class ChatDB:
    def __init__(self, db_path: str = "securechat.sqlite"):
        self.path = Path(db_path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self._init()

    def _init(self):
        cur = self.conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            owner_phone TEXT NOT NULL,
            peer_phone TEXT NOT NULL,
            direction TEXT NOT NULL,     -- in/out
            payload_json TEXT NOT NULL,  -- encrypted payload
            plaintext TEXT               -- decrypted copy for UI
        )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_msg_owner_peer ON messages(owner_phone, peer_phone, ts)")
        self.conn.commit()

    def save(self, owner_phone: str, peer_phone: str, direction: str, payload_json: str, plaintext: str | None):
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO messages (ts, owner_phone, peer_phone, direction, payload_json, plaintext)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (int(time.time()), owner_phone, peer_phone, direction, payload_json, plaintext))
        self.conn.commit()

    def list_threads(self, owner_phone: str):
        cur = self.conn.cursor()
        cur.execute("""
            SELECT peer_phone, MAX(ts) as last_ts, MAX(COALESCE(plaintext, '')) as preview, COUNT(*) as cnt
            FROM messages
            WHERE owner_phone = ?
            GROUP BY peer_phone
            ORDER BY last_ts DESC
        """, (owner_phone,))
        return cur.fetchall()

    def fetch(self, owner_phone: str, peer_phone: str, limit: int = 500):
        cur = self.conn.cursor()
        cur.execute("""
            SELECT ts, direction, plaintext
            FROM messages
            WHERE owner_phone = ? AND peer_phone = ?
            ORDER BY ts ASC
            LIMIT ?
        """, (owner_phone, peer_phone, limit))
        return cur.fetchall()