"""Refuse retired protocol-1 realm checks; use verify_delivery.py --v2-isolated."""

import struct

from verify_delivery import REFUSAL


def command(client, text):
    """Encode a realm SAY command, retained for the realm wire-format test."""
    client.send(0x95, struct.pack("<II", 1, 7) + text.encode("ascii") + b"\0")
    client.stay(1)


if __name__ == "__main__":
    raise SystemExit(REFUSAL)
