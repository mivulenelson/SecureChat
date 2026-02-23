from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox, QHBoxLayout
)
from chat_src.security.auth import generate_otp, verify_otp, normalize_phone
from chat_src.storage.identity_store import load_or_create_identity
from chat_src.network.client_node import ClientNode
from chat_src.gui.app_ui import AppWindow

class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SecureChat - Register / Login")
        self.setMinimumWidth(420)

        self.node = ClientNode("127.0.0.1", 5050)
        self.node.connected.connect(self._on_connected)
        self.node.packet_received.connect(self._on_packet)
        self.node.error.connect(self._on_error)
        self.node.disconnected.connect(self._on_disconnected)
        self.node.start()

        self.mode = "login"  # or "register"
        self._pending = None  # ("register"/"login", payload)

        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        self.btn_login = QPushButton("Login")
        self.btn_register = QPushButton("Register")
        self.btn_login.clicked.connect(lambda: self.set_mode("login"))
        self.btn_register.clicked.connect(lambda: self.set_mode("register"))
        row.addWidget(self.btn_login)
        row.addWidget(self.btn_register)
        layout.addLayout(row)

        self.status = QLabel("Connecting to server...")
        layout.addWidget(self.status)

        layout.addWidget(QLabel("Phone (unique identity)"))
        self.phone = QLineEdit()
        self.phone.setPlaceholderText("+2567XXXXXXXX")
        layout.addWidget(self.phone)

        layout.addWidget(QLabel("Username (unique, only for Register)"))
        self.username = QLineEdit()
        self.username.setPlaceholderText("e.g. nelson")
        layout.addWidget(self.username)

        self.send_otp_btn = QPushButton("Send OTP (Mock)")
        self.send_otp_btn.clicked.connect(self.on_send_otp)
        layout.addWidget(self.send_otp_btn)

        layout.addWidget(QLabel("OTP"))
        self.otp = QLineEdit()
        self.otp.setPlaceholderText("6 digits")
        layout.addWidget(self.otp)

        self.go_btn = QPushButton("Continue")
        self.go_btn.clicked.connect(self.on_continue)
        layout.addWidget(self.go_btn)

        self.set_mode("login")

    def set_mode(self, mode: str):
        self.mode = mode
        if mode == "login":
            self.username.setEnabled(False)
            self.status.setText("Mode: Login (phone + OTP)")
            self.go_btn.setText("Login")
        else:
            self.username.setEnabled(True)
            self.status.setText("Mode: Register (phone + username + OTP)")
            self.go_btn.setText("Register")

    def _on_connected(self):
        self.status.setText(f"Connected. Mode: {self.mode.title()}")

    def _on_disconnected(self):
        self.status.setText("Disconnected from server.")

    def _on_error(self, msg: str):
        QMessageBox.critical(self, "Network Error", msg)

    def on_send_otp(self):
        phone = normalize_phone(self.phone.text())
        if not phone:
            QMessageBox.warning(self, "Missing", "Enter phone number.")
            return
        otp = generate_otp(phone)
        QMessageBox.information(self, "Mock OTP", f"OTP: {otp}")

    def on_continue(self):
        phone = normalize_phone(self.phone.text())
        otp = self.otp.text().strip()
        username = self.username.text().strip()

        if not phone or not otp:
            QMessageBox.warning(self, "Missing", "Phone + OTP required.")
            return
        if not verify_otp(phone, otp):
            QMessageBox.critical(self, "Failed", "OTP verification failed.")
            return

        # Load or create identity keys per phone (persistent)
        priv, pub_b64 = load_or_create_identity(phone)

        if self.mode == "register":
            if not username:
                QMessageBox.warning(self, "Missing", "Username required for registration.")
                return
            pkt = {"type": "register", "phone": phone, "username": username, "pubkey_b64": pub_b64}
            self._pending = ("register", {"phone": phone, "username": username, "priv": priv, "pub_b64": pub_b64})
            self.node.send(pkt)
        else:
            pkt = {"type": "login", "phone": phone}
            self._pending = ("login", {"phone": phone, "priv": priv, "pub_b64": pub_b64})
            self.node.send(pkt)

    def _on_packet(self, pkt: dict):
        t = pkt.get("type")

        if t == "error":
            QMessageBox.critical(self, "Server Error", pkt.get("message"))
            return

        if t == "register_ok":
            # auto-login after register
            if not self._pending:
                return
            _, data = self._pending
            self.node.send({"type": "login", "phone": data["phone"]})
            return

        if t == "login_ok":
            if not self._pending:
                return
            _, data = self._pending

            me = pkt.get("me")
            # open app window
            self.app = AppWindow(
                node=self.node,
                my_phone=data["phone"],
                my_priv=data["priv"],
                me=me
            )
            self.app.show()
            self.close()
            return