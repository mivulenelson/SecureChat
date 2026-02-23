import base64
import os
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def pub_to_b64(pub: x25519.X25519PublicKey) -> str:
    raw = pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode("utf-8")

def b64_to_pub(b64: str) -> x25519.X25519PublicKey:
    raw = base64.b64decode(b64)
    return x25519.X25519PublicKey.from_public_bytes(raw)

def priv_to_b64(priv: x25519.X25519PrivateKey) -> str:
    raw = priv.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption()
    )
    return base64.b64encode(raw).decode("utf-8")

def b64_to_priv(b64: str) -> x25519.X25519PrivateKey:
    raw = base64.b64decode(b64)
    return x25519.X25519PrivateKey.from_private_bytes(raw)

def generate_identity():
    priv = x25519.X25519PrivateKey.generate()
    return priv, priv.public_key()

def _hkdf(shared: bytes, salt: bytes, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(shared)

def encrypt_to_recipient(recipient_pub_b64: str, plaintext: str) -> dict:
    recipient_pub = b64_to_pub(recipient_pub_b64)

    eph_priv = x25519.X25519PrivateKey.generate()
    eph_pub = eph_priv.public_key()

    shared = eph_priv.exchange(recipient_pub)
    salt = os.urandom(16)
    key = _hkdf(shared, salt=salt, info=b"securechat-dm-v1")

    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

    return {
        "eph_pub": pub_to_b64(eph_pub),
        "salt": base64.b64encode(salt).decode("utf-8"),
        "nonce": base64.b64encode(nonce).decode("utf-8"),
        "ct": base64.b64encode(ct).decode("utf-8"),
    }

def decrypt_from_sender(my_priv: x25519.X25519PrivateKey, payload: dict) -> str:
    eph_pub = b64_to_pub(payload["eph_pub"])
    salt = base64.b64decode(payload["salt"])
    nonce = base64.b64decode(payload["nonce"])
    ct = base64.b64decode(payload["ct"])

    shared = my_priv.exchange(eph_pub)
    key = _hkdf(shared, salt=salt, info=b"securechat-dm-v1")

    aesgcm = AESGCM(key)
    pt = aesgcm.decrypt(nonce, ct, None)
    return pt.decode("utf-8")