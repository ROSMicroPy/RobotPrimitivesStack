"""Small, versioned signal envelopes shared by every transport."""
try:
    import ujson as json
except ImportError:
    import json
try:
    import asyncio
except ImportError:
    import uasyncio as asyncio
import os
import time


def now_ms():
    return time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.monotonic() * 1000)


def elapsed(start):
    now = now_ms()
    return time.ticks_diff(now, start) if hasattr(time, "ticks_diff") else now - start


def nonce():
    return "".join("{:02x}".format(byte) for byte in os.urandom(8))


def plain(value):
    if hasattr(value, "as_dict"):
        return plain(value.as_dict())
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and value == value and value not in (float("inf"), -float("inf")):
        return value
    raise ValueError("signal payload must be finite JSON data")


FIELDS = {"v": "version", "e": "entity", "n": "source", "b": "boot",
          "q": "sequence", "s": "name", "p": "payload", "c": "correlation",
          "t": "target", "h": "hops", "l": "ttl_ms"}


def validate(signal):
    if not isinstance(signal, dict) or type(signal.get("version")) is not int or signal.get("version") != 1:
        raise ValueError("expected rp.signal/v1")
    for key, limit in (("entity", 48), ("source", 32), ("boot", 32), ("name", 96), ("target", 32)):
        value = signal.get(key)
        if not isinstance(value, str) or not value or len(value) > limit:
            raise ValueError("invalid signal " + key)
    correlation = signal.get("correlation")
    if correlation is not None and (not isinstance(correlation, str) or not correlation or len(correlation) > 160):
        raise ValueError("invalid correlation")
    for key, minimum, maximum in (("sequence", 1, 2147483647), ("hops", 0, 16), ("ttl_ms", 1, 60000)):
        value = signal.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError("invalid signal " + key)
    plain(signal.get("payload"))
    return signal


def identity(signal):
    return "{}/{}/{}".format(signal["source"], signal["boot"], signal["sequence"])


def encode(signal, limit=2048):
    validate(signal)
    wire = {short: plain(signal.get(long)) for short, long in FIELDS.items()}
    data = json.dumps(wire).encode("utf-8")
    if len(data) > limit:
        raise ValueError("signal exceeds byte limit")
    return data


def decode(data, limit=2048):
    if isinstance(data, str):
        data = data.encode("utf-8")
    if len(data) > limit:
        raise ValueError("signal exceeds byte limit")
    wire = json.loads(bytes(data).decode("utf-8"))
    if not isinstance(wire, dict) or set(wire) != set(FIELDS):
        raise ValueError("invalid signal envelope fields")
    return validate({long: wire[short] for short, long in FIELDS.items()})
