import asyncio
import json
import struct

HEADER = struct.Struct("!I")

async def read_packet(reader: asyncio.StreamReader):
    try:
        header = await reader.readexactly(HEADER.size)
    except (asyncio.IncompleteReadError, ConnectionResetError):
        return None

    (length,) = HEADER.unpack(header)
    if length <= 0 or length > 10_000_000:
        return None

    try:
        payload = await reader.readexactly(length)
    except asyncio.IncompleteReadError:
        return None

    try:
        obj = json.loads(payload.decode("utf-8"))
    except Exception:
        return None

    if not isinstance(obj, dict):
        return None

    return obj

async def send_packet(writer: asyncio.StreamWriter, pkt: dict):
    if not isinstance(pkt, dict):
        raise TypeError(f"send_packet expects dict, got {type(pkt)}")
    raw = json.dumps(pkt, separators=(",", ":")).encode("utf-8")
    writer.write(HEADER.pack(len(raw)) + raw)
    await writer.drain()