import json
from pathlib import Path
from chat_src.security.crypto_e2ee import generate_identity, priv_to_b64, pub_to_b64, b64_to_priv

BASE = Path.home() / ".securechat"
BASE.mkdir(parents=True, exist_ok=True)

def _path(phone: str) -> Path:
    return BASE / f"{phone}.identity.json"

def load_or_create_identity(phone: str):
    p = _path(phone)
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        priv = b64_to_priv(data["priv_b64"])
        pub_b64 = data["pub_b64"]
        return priv, pub_b64

    priv, pub = generate_identity()
    data = {"priv_b64": priv_to_b64(priv), "pub_b64": pub_to_b64(pub)}
    p.write_text(json.dumps(data), encoding="utf-8")
    return priv, data["pub_b64"]