import time
import uuid


def uuid7() -> uuid.UUID:
    """RFC 9562 UUIDv7: 48-bit ms timestamp then 74 random bits (time-ordered)."""
    timestamp_ms = int(time.time() * 1000)
    raw = bytearray(uuid.uuid4().bytes)
    raw[0:6] = timestamp_ms.to_bytes(6, byteorder="big")
    raw[6] = (raw[6] & 0x0F) | 0x70
    raw[8] = (raw[8] & 0x3F) | 0x80
    return uuid.UUID(bytes=bytes(raw))
