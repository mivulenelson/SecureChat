SecureChat

A desktop end-to-end encrypted messaging application built with Python + PySide6.

SecureChat provides:

- True end-to-end encrypted direct messages (E2EE)

- Unique phone-based identity

- Unique usernames

- Friend request & acceptance workflow

- Private 1-to-1 chats

- Local encrypted chat history

- Real-time notifications

- Async TCP relay server

Architecture Overview

- SecureChat follows a client-server architecture:

==> Client (PySide6 GUI)  <----> Async Relay Server  <---->  Client

Important Design Principle

- The server never decrypts messages.

- It only:

    > Registers users

    > Maintains friend relationships

    > Relays encrypted messages

    > Tracks online sessions

- All encryption and decryption happen on the client side

Identity Model

- Each user has:

    - Unique Phone Number (Primary Identity)

    - Unique Username

    - Persistent X25519 Identity Keypair

- Phone Number

    - Used as the system’s primary identity

    - Only one active session per phone

    - Stored server-side in SQLite

- Username

    - Must be unique

    - Used for display purposes

    - Cannot be duplicated

Security Model (End-to-End Encryption)

- SecureChat uses:

    - X25519 (Elliptic Curve Diffie-Hellman)

    - HKDF (SHA-256) for key derivation

    - AES-256-GCM for authenticated encryption

How Encryption Works

- When User A sends a message to User B:

    1. A generates a temporary (ephemeral) X25519 keypair

    2. A computes shared secret with B’s public key

    3. HKDF derives a 256-bit AES key

    4. Message encrypted using AES-GCM

    5. Server relays ciphertext only

    6. B derives same AES key using:

        6.1. His private key

        6.2. A’s ephemeral public key

    7. B decrypts locally

Result

- Forward secrecy (new key per message)

- Server cannot decrypt messages

- Only sender and receiver can read content

Friend Request Workflow

- SecureChat enforces mutual consent.

    Step 1 – Send Request

- User A selects a user → clicks “Send Friend Request”

    Step 2 – Incoming Request

- User B sees request in “Incoming Friend Requests”

    Step 3 – Accept or Decline

        3.1. Accept → Both become friends

        3.2. Decline → Request removed

    Step 4 – DM Enabled

    - Only friends can send direct messages.

Notifications System

- The app includes a live notification panel showing:

    1. New messages

    2. Friend requests

    3. Accepted requests

    4. Errors

    5. Status updates

- Unread message counters are shown beside friend names.

Local Data Storage
- Server (server.sqlite)

    - Stores:

        1. Registered users

        2. Friend relationships

        3. Pending friend requests

- Client (securechat.sqlite)

    - Stores:

        1. Encrypted payload

        3. Decrypted plaintext copy (for UI)

        4. Message direction

        5. Timestamp

- Private keys are stored locally in (.securechat/<phone>.identity.json) and these never leave the device.

How to Run
    1. Install Requirements
        - pip install PySide6 cryptography
    
    2. Start Server

        - Open Terminal 1:

            - python3 chat_server.py

        - You should see:

            - SecureChat server listening on ('0.0.0.0', 5050)
    
    3. Start Client

        - Open Terminal 2:

            - python3 run_client.py

        - To simulate another user:

        - Open Terminal 3:

            - python3 run_client.py
How to Use
- Register

- Enter phone number

- Enter unique username

- Click “Send OTP” (mock)

- Enter OTP shown

- Click Register

- Login

- Enter registered phone

- Enter OTP

- Click Login

- Add Friend

- Select user in “All Users”

- Click “Send Friend Request”

- Other user:

- Accept or Decline in Requests panel

- Send Message

- Select friend

- Type message

- Click Send

- Encrypted DM is delivered.

- Network Protocol Summary

- All packets are JSON dicts sent over TCP using length-prefixed framing.

Example DM packet:

{
  "type": "dm",
  "to_phone": "+2567XXXXXXX",
  "enc": {
    "eph_pub": "...",
    "salt": "...",
    "nonce": "...",
    "ct": "..."
  }
}

- The server never decrypts this payload.

Folder Structure
securechat
   > chat_server.py
   > run_client.py
   > chat_src
      -> __init__.py
      -> network
        --> __init__.py
        --> protocol.py
        --> client_node.py
      -> security/
        --> __init__.py
        --> auth.py
        --> crypto_e2ee.py
      -> storage
        --> __init__.py
        --> identity_store.py
        --> chat_db.py
      -> gui
        --> __init__.py
        --> login_ui.py
        --> app_ui.py

Technical Highlights

1. Asyncio TCP server

2. Threaded asyncio client bridge

3. Length-prefixed JSON framing

4. Ephemeral key per message

5. AES-GCM authenticated encryption

6. SQLite local + server DB

6. Modular layered architecture

Security Considerations

- Current implementation provides:

    ✔ End-to-End Encryption
    ✔ Forward secrecy (per message)
    ✔ No server-side decryption
    ✔ Unique identity enforcement
    ✔ Mutual consent for communication

- Not yet implemented:

    - Message authenticity signatures

    - Key verification fingerprints

    - Double Ratchet algorithm

    - Offline message queue

    - Multi-device support

Future Improvements

    - Signal-style Double Ratchet

    - QR code key verification

    - Push notification integration

    - Group chats with shared room keys

    - Dark mode UI

    - Message deletion / edit

    - Typing indicators

    - File attachments (encrypted)


License

- Educational / Experimental Use

Summary

- SecureChat is a secure desktop messaging system that demonstrates:

    - Modern applied cryptography

    - Secure client-server design

    - Identity management

    - Encrypted communication

    - Real-time GUI messaging

- It is a complete secure messaging foundation built in Python.