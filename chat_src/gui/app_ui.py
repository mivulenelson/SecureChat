import json
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QTextEdit, QLineEdit, QMessageBox
)
from PySide6.QtCore import Qt

from chat_src.security.crypto_e2ee import encrypt_to_recipient, decrypt_from_sender
from chat_src.storage.chat_db import ChatDB


class AppWindow(QWidget):
    def __init__(self, node, my_phone: str, my_priv, me: dict):
        super().__init__()
        self.node = node
        self.my_phone = my_phone
        self.my_priv = my_priv
        self.me = me  # {phone, username, pubkey_b64}

        self.db = ChatDB()

        # caches: phone -> user dict
        self.users: dict[str, dict] = {}
        self.following: dict[str, dict] = {}  # optional (safe if server sends it)
        self.friends: dict[str, dict] = {}
        self.requests: dict[str, dict] = {}

        self.active_peer_phone: str | None = None

        # notifications state
        self.unread_messages: dict[str, int] = {}   # peer_phone -> count
        self._last_request_count = 0

        self.setWindowTitle(f"SecureChat - {me['username']} ({my_phone})")
        self.setMinimumSize(1000, 600)

        # Hook node packets (node persists from login screen)
        self.node.packet_received.connect(self.on_packet)

        root = QHBoxLayout(self)

        # ---------------- LEFT: Users + Friends + Requests ----------------
        left = QVBoxLayout()
        left.addWidget(QLabel("All Users"))

        self.user_list = QListWidget()
        left.addWidget(self.user_list)

        self.follow_btn = QPushButton("Send Friend Request")
        self.follow_btn.clicked.connect(self.follow_selected)
        left.addWidget(self.follow_btn)

        left.addWidget(QLabel("Friends (DM allowed after acceptance)"))
        self.friends_list = QListWidget()
        self.friends_list.itemSelectionChanged.connect(self.on_select_friend)
        left.addWidget(self.friends_list)

        left.addWidget(QLabel("Incoming Friend Requests"))
        self.requests_list = QListWidget()
        left.addWidget(self.requests_list)

        req_row = QHBoxLayout()
        self.accept_btn = QPushButton("Accept")
        self.decline_btn = QPushButton("Decline")
        self.accept_btn.clicked.connect(self.accept_request)
        self.decline_btn.clicked.connect(self.decline_request)
        req_row.addWidget(self.accept_btn)
        req_row.addWidget(self.decline_btn)
        left.addLayout(req_row)

        self.refresh_btn = QPushButton("Refresh lists")
        self.refresh_btn.clicked.connect(self.refresh_lists)
        left.addWidget(self.refresh_btn)

        root.addLayout(left, 3)

        # ---------------- MIDDLE: Chat ----------------
        mid = QVBoxLayout()

        self.chat_title = QLabel("Chat: (select a friend)")
        mid.addWidget(self.chat_title)

        self.chat_view = QTextEdit()
        self.chat_view.setReadOnly(True)
        mid.addWidget(self.chat_view)

        bottom = QHBoxLayout()
        self.msg = QLineEdit()
        self.msg.setPlaceholderText("Type message...")
        bottom.addWidget(self.msg)

        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.send_msg)
        self.send_btn.setEnabled(False)
        bottom.addWidget(self.send_btn)

        mid.addLayout(bottom)

        self.history_btn = QPushButton("Load history")
        self.history_btn.clicked.connect(self.load_history)
        mid.addWidget(self.history_btn)

        root.addLayout(mid, 6)

        # ---------------- RIGHT: Notifications ----------------
        notif = QVBoxLayout()
        notif.addWidget(QLabel("Notifications"))

        self.notif_view = QTextEdit()
        self.notif_view.setReadOnly(True)
        self.notif_view.setMinimumWidth(280)
        notif.addWidget(self.notif_view)

        self.clear_notif_btn = QPushButton("Clear")
        self.clear_notif_btn.clicked.connect(self.notif_view.clear)
        notif.addWidget(self.clear_notif_btn)

        root.addLayout(notif, 3)

        self.refresh_lists()

    # ---------------- Notifications helpers ----------------

    def notify(self, text: str):
        dt = datetime.now().strftime("%H:%M:%S")
        self.notif_view.append(f"[{dt}] {text}")

    def _bump_unread(self, peer_phone: str):
        self.unread_messages[peer_phone] = self.unread_messages.get(peer_phone, 0) + 1

    def _clear_unread(self, peer_phone: str):
        self.unread_messages.pop(peer_phone, None)

    # ---------------- Lists / actions ----------------

    def refresh_lists(self):
        self.node.send({"type": "list_users"})
        # optional if server still supports it:
        self.node.send({"type": "list_following"})
        self.node.send({"type": "list_friends"})
        self.node.send({"type": "list_requests"})

    def follow_selected(self):
        item = self.user_list.currentItem()
        if not item:
            return
        phone = item.data(Qt.UserRole)
        self.node.send({"type": "follow", "phone": phone})
        self.notify(f"Sent friend request to {phone}.")

    def on_select_friend(self):
        item = self.friends_list.currentItem()
        if not item:
            return
        peer_phone = item.data(Qt.UserRole)

        self.active_peer_phone = peer_phone
        peer = self.friends.get(peer_phone)

        if not peer:
            self.chat_title.setText("Chat: (select a friend)")
            self.send_btn.setEnabled(False)
            return

        self.chat_title.setText(f"Chat: {peer['username']} ({peer_phone})")
        self.send_btn.setEnabled(True)

        # clear unread badge for this peer
        self._clear_unread(peer_phone)
        self.refresh_lists()

        self.load_history()
        self.notify(f"Opened chat with {peer_phone}.")

    def accept_request(self):
        item = self.requests_list.currentItem()
        if not item:
            return
        from_phone = item.data(Qt.UserRole)
        self.node.send({"type": "accept_request", "from_phone": from_phone})
        self.notify(f"Accepted friend request from {from_phone}.")

    def decline_request(self):
        item = self.requests_list.currentItem()
        if not item:
            return
        from_phone = item.data(Qt.UserRole)
        self.node.send({"type": "decline_request", "from_phone": from_phone})
        self.notify(f"Declined friend request from {from_phone}.")

    # ---------------- History ----------------

    def load_history(self):
        self.chat_view.clear()
        if not self.active_peer_phone:
            self.chat_view.setPlainText("Select a friend to view chat.")
            return

        rows = self.db.fetch(self.my_phone, self.active_peer_phone, limit=500)
        for ts, direction, plaintext in rows:
            dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            prefix = "You" if direction == "out" else self.active_peer_phone
            self.chat_view.append(f"[{dt}] {prefix}: {plaintext if plaintext else '[no plaintext]'}")

    # ---------------- Messaging ----------------

    def send_msg(self):
        if not self.active_peer_phone:
            return

        text = self.msg.text().strip()
        if not text:
            return

        peer = self.friends.get(self.active_peer_phone)
        if not peer:
            QMessageBox.warning(self, "Not a friend", "You can only DM friends.")
            return

        enc = encrypt_to_recipient(peer["pubkey_b64"], text)

        # save local
        self.db.save(
            owner_phone=self.my_phone,
            peer_phone=self.active_peer_phone,
            direction="out",
            payload_json=json.dumps(enc),
            plaintext=text
        )

        self.node.send({
            "type": "dm",
            "to_phone": self.active_peer_phone,
            "enc": enc
        })

        self.msg.clear()
        self.load_history()

    # ---------------- Packet handling ----------------

    def on_packet(self, pkt: dict):
        t = pkt.get("type")

        if t == "error":
            msg = pkt.get("message")
            self.notify(f"Server error: {msg}")
            QMessageBox.critical(self, "Server Error", msg)
            return

        if t == "users":
            self.users = {u["phone"]: u for u in pkt.get("users", [])}
            self.user_list.clear()
            for phone, u in self.users.items():
                it = QListWidgetItem(f"{u['username']}  ({phone})")
                it.setData(Qt.UserRole, phone)
                self.user_list.addItem(it)
            return

        if t == "following":
            self.following = {u["phone"]: u for u in pkt.get("users", [])}
            return

        if t == "friends":
            self.friends = {u["phone"]: u for u in pkt.get("users", [])}
            self.friends_list.clear()

            for phone, u in self.friends.items():
                unread = self.unread_messages.get(phone, 0)
                suffix = f"  •  {unread} new" if unread > 0 else ""
                it = QListWidgetItem(f"{u['username']}  ({phone}){suffix}")
                it.setData(Qt.UserRole, phone)
                self.friends_list.addItem(it)
            return

        if t == "friend_update":
            self.notify("Friend list updated (request accepted / new friend).")
            self.refresh_lists()
            return

        if t == "requests":
            reqs = pkt.get("requests", [])
            self.requests = {r["phone"]: r for r in reqs}

            self.requests_list.clear()
            for phone, r in self.requests.items():
                it = QListWidgetItem(f"{r['username']} ({phone})")
                it.setData(Qt.UserRole, phone)
                self.requests_list.addItem(it)

            new_count = len(self.requests)
            if new_count > self._last_request_count:
                self.notify(f"New friend request(s). Pending: {new_count}")
            self._last_request_count = new_count
            return

        if t == "incoming_requests_update":
            self.notify("Friend requests updated.")
            self.node.send({"type": "list_requests"})
            return

        if t == "request_sent":
            self.notify("Friend request sent.")
            QMessageBox.information(self, "Request sent", "Friend request sent.")
            return

        if t == "accept_ok":
            self.notify(f"Friend request accepted: {pkt.get('from_phone')}.")
            self.refresh_lists()
            return

        if t == "decline_ok":
            self.notify(f"Friend request declined: {pkt.get('from_phone')}.")
            self.refresh_lists()
            return

        if t == "dm":
            from_phone = pkt.get("from_phone")
            enc = pkt.get("enc")
            if not from_phone or not isinstance(enc, dict):
                return

            try:
                plaintext = decrypt_from_sender(self.my_priv, enc)
            except Exception:
                plaintext = "[unable to decrypt]"
                self.notify(f"Message received from {from_phone} (could not decrypt).")

            # save
            self.db.save(
                owner_phone=self.my_phone,
                peer_phone=from_phone,
                direction="in",
                payload_json=json.dumps(enc),
                plaintext=plaintext
            )

            if self.active_peer_phone == from_phone:
                self.load_history()
            else:
                self._bump_unread(from_phone)
                self.notify(f"New message from {from_phone}.")
                self.refresh_lists()
            return

        if t == "dm_sent":
            return