import asyncio
import sqlite3
import time
from pathlib import Path

from chat_src.network.protocol import read_packet, send_packet

DB_PATH = Path("server.sqlite")


def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        phone TEXT PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        pubkey_b64 TEXT NOT NULL,
        created_ts INTEGER NOT NULL
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS follows (
        follower_phone TEXT NOT NULL,
        followee_phone TEXT NOT NULL,
        created_ts INTEGER NOT NULL,
        PRIMARY KEY (follower_phone, followee_phone)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS friends (
        a_phone TEXT NOT NULL,
        b_phone TEXT NOT NULL,
        created_ts INTEGER NOT NULL,
        PRIMARY KEY (a_phone, b_phone)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS friend_requests (
        from_phone TEXT NOT NULL,
        to_phone TEXT NOT NULL,
        created_ts INTEGER NOT NULL,
        PRIMARY KEY (from_phone, to_phone)
    )
    """)
    conn.commit()


CONN = db()
init_db(CONN)

# phone -> StreamWriter (only one active session per phone)
SESSIONS: dict[str, asyncio.StreamWriter] = {}


def norm_phone(p: str) -> str:
    return (p or "").strip().replace(" ", "")


def now() -> int:
    return int(time.time())


def user_exists(phone: str) -> bool:
    cur = CONN.cursor()
    cur.execute("SELECT 1 FROM users WHERE phone = ?", (phone,))
    return cur.fetchone() is not None


def username_taken(username: str) -> bool:
    cur = CONN.cursor()
    cur.execute("SELECT 1 FROM users WHERE username = ?", (username,))
    return cur.fetchone() is not None


def get_user_by_phone(phone: str):
    cur = CONN.cursor()
    cur.execute("SELECT phone, username, pubkey_b64 FROM users WHERE phone = ?", (phone,))
    row = cur.fetchone()
    if not row:
        return None
    return {"phone": row[0], "username": row[1], "pubkey_b64": row[2]}


def get_user_by_username(username: str):
    cur = CONN.cursor()
    cur.execute("SELECT phone, username, pubkey_b64 FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    if not row:
        return None
    return {"phone": row[0], "username": row[1], "pubkey_b64": row[2]}


def list_users(except_phone: str):
    cur = CONN.cursor()
    cur.execute("SELECT phone, username, pubkey_b64 FROM users WHERE phone != ? ORDER BY username", (except_phone,))
    return [{"phone": r[0], "username": r[1], "pubkey_b64": r[2]} for r in cur.fetchall()]


def list_following(phone: str):
    cur = CONN.cursor()
    cur.execute("""
        SELECT u.phone, u.username, u.pubkey_b64
        FROM follows f JOIN users u ON u.phone = f.followee_phone
        WHERE f.follower_phone = ?
        ORDER BY u.username
    """, (phone,))
    return [{"phone": r[0], "username": r[1], "pubkey_b64": r[2]} for r in cur.fetchall()]


def list_friends(phone: str):
    cur = CONN.cursor()
    cur.execute("""
        SELECT u.phone, u.username, u.pubkey_b64
        FROM friends fr
        JOIN users u ON u.phone = CASE WHEN fr.a_phone = ? THEN fr.b_phone ELSE fr.a_phone END
        WHERE fr.a_phone = ? OR fr.b_phone = ?
        ORDER BY u.username
    """, (phone, phone, phone))
    return [{"phone": r[0], "username": r[1], "pubkey_b64": r[2]} for r in cur.fetchall()]

def list_incoming_requests(to_phone: str):
    cur = CONN.cursor()
    cur.execute("""
        SELECT u.phone, u.username, u.pubkey_b64, r.created_ts
        FROM friend_requests r
        JOIN users u ON u.phone = r.from_phone
        WHERE r.to_phone = ?
        ORDER BY r.created_ts DESC
    """, (to_phone,))
    return [{"phone": r[0], "username": r[1], "pubkey_b64": r[2], "ts": r[3]} for r in cur.fetchall()]

def request_exists(a: str, b: str) -> bool:
    cur = CONN.cursor()
    cur.execute("SELECT 1 FROM friend_requests WHERE from_phone=? AND to_phone=?", (a, b))
    return cur.fetchone() is not None

def add_request(from_phone: str, to_phone: str):
    cur = CONN.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO friend_requests (from_phone, to_phone, created_ts)
        VALUES (?, ?, ?)
    """, (from_phone, to_phone, now()))
    CONN.commit()

def remove_request(from_phone: str, to_phone: str):
    cur = CONN.cursor()
    cur.execute("DELETE FROM friend_requests WHERE from_phone=? AND to_phone=?", (from_phone, to_phone))
    CONN.commit()

def are_friends(a: str, b: str) -> bool:
    a1, b1 = sorted([a, b])
    cur = CONN.cursor()
    cur.execute("SELECT 1 FROM friends WHERE a_phone=? AND b_phone=?", (a1, b1))
    return cur.fetchone() is not None

def make_friend(a: str, b: str):
    # store ordered pair to avoid duplicates
    a, b = sorted([a, b])
    cur = CONN.cursor()
    cur.execute("INSERT OR IGNORE INTO friends (a_phone, b_phone, created_ts) VALUES (?, ?, ?)", (a, b, now()))
    CONN.commit()


def add_follow(follower: str, followee: str):
    cur = CONN.cursor()
    cur.execute("INSERT OR IGNORE INTO follows (follower_phone, followee_phone, created_ts) VALUES (?, ?, ?)",
                (follower, followee, now()))
    CONN.commit()


def remove_follow(follower: str, followee: str):
    cur = CONN.cursor()
    cur.execute("DELETE FROM follows WHERE follower_phone = ? AND followee_phone = ?", (follower, followee))
    CONN.commit()


async def kick_if_connected(phone: str):
    w = SESSIONS.get(phone)
    if not w:
        return
    try:
        await send_packet(w, {"type": "error", "message": "Logged in from another device. Disconnected."})
        w.close()
        await w.wait_closed()
    except Exception:
        pass
    SESSIONS.pop(phone, None)


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    authed_phone = None
    peer = writer.get_extra_info("peername")
    print(f"[+] connection from {peer}")

    try:
        while True:
            pkt = await read_packet(reader)
            if pkt is None:
                break

            t = pkt.get("type")

            # -------- registration / login --------

            if t == "register":
                phone = norm_phone(pkt.get("phone"))
                username = (pkt.get("username") or "").strip()
                pubkey_b64 = pkt.get("pubkey_b64")

                if not phone or not username or not pubkey_b64:
                    await send_packet(writer, {"type": "error", "message": "Missing phone/username/pubkey"})
                    continue

                if user_exists(phone):
                    await send_packet(writer, {"type": "error", "message": "Phone already registered"})
                    continue

                if username_taken(username):
                    await send_packet(writer, {"type": "error", "message": "Username already taken"})
                    continue

                CONN.execute(
                    "INSERT INTO users (phone, username, pubkey_b64, created_ts) VALUES (?, ?, ?, ?)",
                    (phone, username, pubkey_b64, now())
                )
                CONN.commit()

                await send_packet(writer, {"type": "register_ok"})
                continue

            if t == "login":
                phone = norm_phone(pkt.get("phone"))
                if not phone:
                    await send_packet(writer, {"type": "error", "message": "Missing phone"})
                    continue

                user = get_user_by_phone(phone)
                if not user:
                    await send_packet(writer, {"type": "error", "message": "Phone not registered"})
                    continue

                # one active session per phone (kick old)
                await kick_if_connected(phone)
                SESSIONS[phone] = writer
                authed_phone = phone

                await send_packet(writer, {"type": "login_ok", "me": user})
                continue

            # Require auth for the rest
            if not authed_phone:
                await send_packet(writer, {"type": "error", "message": "Not authenticated"})
                continue

            # -------- directory / follow / friends --------

            if t == "list_users":
                await send_packet(writer, {"type": "users", "users": list_users(authed_phone)})
                continue

            if t == "list_following":
                await send_packet(writer, {"type": "following", "users": list_following(authed_phone)})
                continue

            if t == "list_friends":
                await send_packet(writer, {"type": "friends", "users": list_friends(authed_phone)})
                continue

            if t == "follow":
                target = norm_phone(pkt.get("phone"))
                if not target or not user_exists(target):
                    await send_packet(writer, {"type": "error", "message": "User not found"})
                    continue
                if target == authed_phone:
                    await send_packet(writer, {"type": "error", "message": "Cannot request yourself"})
                    continue
                if are_friends(authed_phone, target):
                    await send_packet(writer, {"type": "error", "message": "Already friends"})
                    continue
                if request_exists(authed_phone, target):
                    await send_packet(writer, {"type": "error", "message": "Request already sent"})
                    continue

                add_request(authed_phone, target)
                await send_packet(writer, {"type": "request_sent", "to_phone": target})

                # notify target if online
                w = SESSIONS.get(target)
                if w:
                    await send_packet(w, {"type": "incoming_requests_update"})
                    continue

            if t == "list_requests":
                await send_packet(writer, {"type": "requests", "requests": list_incoming_requests(authed_phone)})
                continue    

            # --------------------
            if t == "accept_request":
                from_phone = norm_phone(pkt.get("from_phone"))
                if not from_phone or not user_exists(from_phone):
                    await send_packet(writer, {"type": "error", "message": "User not found"})
                    continue

                if not request_exists(from_phone, authed_phone):
                    await send_packet(writer, {"type": "error", "message": "No such request"})
                    continue

                remove_request(from_phone, authed_phone)
                make_friend(from_phone, authed_phone)

                await send_packet(writer, {"type": "accept_ok", "from_phone": from_phone})

                # notify both if online to refresh lists
                for p in (authed_phone, from_phone):
                    w = SESSIONS.get(p)
                    if w:
                        await send_packet(w, {"type": "friend_update"})
                        await send_packet(w, {"type": "incoming_requests_update"})
                continue


            if t == "decline_request":
                from_phone = norm_phone(pkt.get("from_phone"))
                if not from_phone:
                    await send_packet(writer, {"type": "error", "message": "Missing from_phone"})
                    continue

                remove_request(from_phone, authed_phone)
                await send_packet(writer, {"type": "decline_ok", "from_phone": from_phone})

                # notify me update
                await send_packet(writer, {"type": "incoming_requests_update"})
                continue

            # --------------------

            if t == "unfollow":
                target = norm_phone(pkt.get("phone"))
                remove_follow(authed_phone, target)
                await send_packet(writer, {"type": "unfollow_ok", "phone": target})
                continue

            if t == "ping":
                await send_packet(writer, {"type": "pong"})
                continue

            # -------- messaging (E2EE relay only) --------

            if t == "dm":
                to_phone = norm_phone(pkt.get("to_phone"))
                enc = pkt.get("enc")
                from_phone = authed_phone

                if not to_phone or not isinstance(enc, dict):
                    await send_packet(writer, {"type": "error", "message": "Bad dm packet"})
                    continue

                # Only allow DM to friends (mutual follow)
                a, b = sorted([from_phone, to_phone])
                cur = CONN.cursor()
                cur.execute("SELECT 1 FROM friends WHERE a_phone=? AND b_phone=?", (a, b))
                if not cur.fetchone():
                    await send_packet(writer, {"type": "error", "message": "You can only DM friends (mutual follow)."})
                    continue

                # relay to recipient if online
                w = SESSIONS.get(to_phone)
                if w:
                    await send_packet(w, {
                        "type": "dm",
                        "from_phone": from_phone,
                        "enc": enc
                    })
                # sender ack (optional)
                await send_packet(writer, {"type": "dm_sent", "to_phone": to_phone})
                continue

            await send_packet(writer, {"type": "error", "message": f"Unknown type: {t}"})

    except Exception as e:
        print(f"[!] client error: {e}")
    finally:
        if authed_phone and SESSIONS.get(authed_phone) is writer:
            SESSIONS.pop(authed_phone, None)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        print("[-] disconnected")


async def main(host="0.0.0.0", port=5050):
    server = await asyncio.start_server(handle_client, host, port)
    addrs = ", ".join(str(s.getsockname()) for s in (server.sockets or []))
    print(f"SecureChat server listening on {addrs}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())