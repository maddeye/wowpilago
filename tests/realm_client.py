"""Test-only, headless build-12340 probe, not a general WoW client.

Run: python tests/realm_client.py --account TEST --password TEST --seconds 30
Import authenticate() for the session key and realm list, or RealmClient to stay
online. Only creates the requested character if absent; never deletes anything.
Packet layouts follow local AzerothCore SRP6.cpp, AuthCrypt.cpp, AuthSession.cpp,
WorldSocket.cpp, Player::BuildEnumData, Chat::BuildChatPacket and PlayerStorage.cpp.
No Warden, movement, gameplay, inventory queries, or addon commands are emulated.
"""

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import hmac
import json
import math
import secrets
import select
import socket
import struct
import sys
import time

BUILD = 12340
N = int("894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7", 16)
G = 7
CMSG_CHAR_CREATE, CMSG_CHAR_ENUM, CMSG_PLAYER_LOGIN = 0x36, 0x37, 0x3D
SMSG_CHAR_CREATE, SMSG_CHAR_ENUM, SMSG_CHARACTER_LOGIN_FAILED = 0x3A, 0x3B, 0x41
SMSG_MESSAGECHAT, SMSG_ITEM_PUSH_RESULT = 0x96, 0x166
CMSG_PING = 0x1DC
SMSG_AUTH_CHALLENGE, CMSG_AUTH_SESSION, SMSG_AUTH_RESPONSE = 0x1EC, 0x1ED, 0x1EE
SMSG_LOGIN_VERIFY_WORLD = 0x236
SMSG_WARDEN_DATA = 0x2E6
SMSG_TIME_SYNC_REQ, CMSG_TIME_SYNC_RESP = 0x390, 0x391


class ProtocolError(Exception):
    pass


def sha1(*parts):
    return hashlib.sha1(b"".join(parts)).digest()


def le32(value):
    return value.to_bytes(32, "little")


def interleave(secret):
    """AzerothCore SHA1Interleave trims leading zero pairs before hashing."""
    if len(secret) != 32:
        raise ValueError("SRP secret must be 32 bytes")
    first = next((i for i, byte in enumerate(secret) if byte), 32)
    start = (first + 1) // 2
    even = sha1(secret[::2][start:])
    odd = sha1(secret[1::2][start:])
    return bytes(byte for pair in zip(even, odd) for byte in pair)


@dataclass(frozen=True)
class SRPProof:
    public: bytes
    proof: bytes
    session_key: bytes
    server_proof: bytes


def srp_proof(account, password, salt, server_public, private=None):
    if len(salt) != 32 or len(server_public) != 32:
        raise ProtocolError("Invalid SRP salt/public key length")
    b = int.from_bytes(server_public, "little")
    if not 0 < b < N:
        raise ProtocolError("Invalid SRP server public key")
    private = private if private is not None else secrets.randbelow(N - 1) + 1
    if private <= 0:
        raise ValueError("SRP private key must be positive")
    account = account.upper().encode("ascii")
    credentials = account + b":" + password.upper().encode("ascii")
    public = le32(pow(G, private, N))
    x = int.from_bytes(sha1(salt, sha1(credentials)), "little")
    u = int.from_bytes(sha1(public, server_public), "little")
    if not u:
        raise ProtocolError("Invalid SRP scrambling parameter")
    secret = pow((b - 3 * pow(G, x, N)) % N, private + u * x, N)
    key = interleave(le32(secret))
    ng = bytes(a ^ b for a, b in zip(sha1(le32(N)), sha1(bytes([G]))))
    proof = sha1(ng, sha1(account), salt, public, server_public, key)
    return SRPProof(public, proof, key, sha1(public, proof, key))


class RC4:
    """Small test-only ARC4, with independent state for each header direction."""

    def __init__(self, key):
        if not key:
            raise ValueError("Empty RC4 key")
        self.state = list(range(256))
        j = 0
        for i in range(256):
            j = (j + self.state[i] + key[i % len(key)]) & 255
            self.state[i], self.state[j] = self.state[j], self.state[i]
        self.i = self.j = 0

    def crypt(self, data):
        result = bytearray()
        s = self.state
        for byte in data:
            self.i = (self.i + 1) & 255
            self.j = (self.j + s[self.i]) & 255
            s[self.i], s[self.j] = s[self.j], s[self.i]
            result.append(byte ^ s[(s[self.i] + s[self.j]) & 255])
        return bytes(result)


def header_cipher(session_key, *, incoming):
    seed = bytes.fromhex("cc98ae04e897eaca12ddc09342915357" if incoming else
                         "c2b3723cc6aed9b5343c53ee2f4367ce")
    cipher = RC4(hmac.digest(seed, session_key, "sha1"))
    cipher.crypt(bytes(1024))
    return cipher


class Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def take(self, size):
        if size < 0 or self.pos + size > len(self.data):
            raise ProtocolError("Truncated packet")
        value = self.data[self.pos:self.pos + size]
        self.pos += size
        return value

    def unpack(self, fmt):
        return struct.unpack("<" + fmt, self.take(struct.calcsize("<" + fmt)))

    def cstring(self):
        end = self.data.find(b"\0", self.pos)
        if end < 0:
            raise ProtocolError("Unterminated string")
        return self.take(end - self.pos + 1)[:-1].decode("utf-8", "replace")

    def finish(self):
        if self.pos != len(self.data):
            raise ProtocolError("Unexpected packet trailing bytes")


def recv_exact(sock, size, *, deadline=None):
    data = bytearray()
    while len(data) < size:
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProtocolError("Ready realm wait timed out")
            sock.settimeout(min(10, remaining))
        part = sock.recv(size - len(data))
        if not part:
            raise ProtocolError("Server closed connection")
        data.extend(part)
    return bytes(data)


@dataclass(frozen=True)
class Realm:
    name: str
    address: str
    realm_id: int
    flags: int
    locked: bool


def parse_realms(data):
    r = Reader(data)
    r.take(4)
    count, = r.unpack("H")
    realms = []
    for _ in range(count):
        _, locked, flags = r.unpack("BBB")
        name, address = r.cstring(), r.cstring()
        _, _, _, realm_id = r.unpack("fBBB")
        if flags & 4:
            r.take(5)  # build major/minor/patch and uint16 build
        realms.append(Realm(name, address, realm_id, flags, bool(locked)))
    if r.take(2) != b"\x10\0":
        raise ProtocolError("Invalid realm-list terminator")
    r.finish()
    return realms


@dataclass(frozen=True)
class AuthResult:
    session_key: bytes
    realms: list


def logon_challenge(account):
    name = account.upper().encode("ascii")
    if not 1 <= len(name) <= 32 or b"\0" in name:
        raise ValueError("Account must contain 1..32 ASCII bytes without NUL")
    body = (b"WoW\0" + struct.pack("<BBBH", 3, 3, 5, BUILD) + b"68x\0niW\0SUne" +
            struct.pack("<II", 0, 0x0100007F) + bytes([len(name)]) + name)
    return b"\0\0" + struct.pack("<H", len(body)) + body


def authenticate(account="TEST", password="TEST", host="127.0.0.1", port=3724, *, ready_timeout=0):
    if type(ready_timeout) not in (int, float) or not math.isfinite(ready_timeout) or not 0 <= ready_timeout <= 120:
        raise ValueError("ready_timeout must be finite and between 0 and 120 seconds")
    with socket.create_connection((host, port), timeout=10) as sock:
        sock.sendall(logon_challenge(account))
        command, _, status = recv_exact(sock, 3)
        if command != 0 or status:
            raise ProtocolError(f"Auth challenge rejected: {status:#x}")
        public = recv_exact(sock, 32)
        generator = recv_exact(sock, recv_exact(sock, 1)[0])
        modulus = recv_exact(sock, recv_exact(sock, 1)[0])
        salt = recv_exact(sock, 32)
        recv_exact(sock, 16)  # version challenge, not used without client-file checks
        flags = recv_exact(sock, 1)[0]
        if generator != b"\x07" or modulus != le32(N) or flags:
            raise ProtocolError("Unsupported SRP group or PIN/matrix/token requirement")
        proof = srp_proof(account, password, salt, public)
        sock.sendall(b"\x01" + proof.public + proof.proof + bytes(20) + b"\0\0")
        command, status = recv_exact(sock, 2)
        if command != 1 or status:
            raise ProtocolError(f"Auth proof rejected: {status:#x}; client-file validation unsupported")
        reply = recv_exact(sock, 30)
        if not hmac.compare_digest(reply[:20], proof.server_proof):
            raise ProtocolError("SRP server proof mismatch")
        deadline = time.monotonic() + ready_timeout if ready_timeout else None
        while True:
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProtocolError("Ready realm wait timed out: no ready unlocked realm")
                sock.settimeout(min(10, remaining))
            sock.sendall(b"\x10\0\0\0\0")
            try:
                if recv_exact(sock, 1, deadline=deadline) != b"\x10":
                    raise ProtocolError("Expected realm list")
                size, = struct.unpack("<H", recv_exact(sock, 2, deadline=deadline))
                realms = parse_realms(recv_exact(sock, size, deadline=deadline))
            except socket.timeout as exc:
                raise ProtocolError("Ready realm-list response timed out") from exc
            if not ready_timeout or any(not r.locked and not r.flags & 3 for r in realms):
                return AuthResult(proof.session_key, realms)
            if deadline - time.monotonic() < 1:
                raise ProtocolError("Ready realm wait timed out: no ready unlocked realm")
            time.sleep(1)


def world_auth(account, session_key, server_seed, realm_id, client_seed=None):
    client_seed = secrets.token_bytes(4) if client_seed is None else client_seed
    if len(client_seed) != 4 or len(server_seed) != 4 or len(session_key) != 40:
        raise ValueError("Invalid world-auth seed/key length")
    name = account.upper().encode("ascii")
    digest = sha1(name, bytes(4), client_seed, server_seed, session_key)
    return (struct.pack("<II", BUILD, 0) + name + b"\0" + struct.pack("<I", 0) +
            client_seed + struct.pack("<IIIQ", 0, 0, realm_id, 0) + digest + bytes(4))


@dataclass(frozen=True)
class Character:
    guid: int
    name: str


def parse_characters(data):
    r = Reader(data)
    characters = []
    for _ in range(r.take(1)[0]):
        guid, = r.unpack("Q")
        name = r.cstring()
        # race/class/gender, five appearance bytes, level, zone/map/xyz,
        # guild/flags/customize, first-login, pet fields, 23 equipment slots.
        r.take(9 + 20 + 12 + 1 + 12 + 23 * 9)
        characters.append(Character(guid, name))
    r.finish()
    return characters


def create_character(name, race=1, class_id=1):
    if not isinstance(name, str) or not name.isascii() or not name.isalpha() or not 2 <= len(name) <= 12:
        raise ValueError("Character name must be 2..12 ASCII letters")
    if any(type(value) is not int or not 1 <= value <= 255 for value in (race, class_id)):
        raise ValueError("Race and class must be positive byte IDs; the realm validates legal combinations")
    return name.encode("ascii") + b"\0" + bytes([race, class_id, 0, 0, 0, 0, 0, 0, 0])


def addon_whisper(data):
    r = Reader(data)
    kind, language = r.unpack("BI")
    if kind != 7 or language != 0xFFFFFFFF:
        return None
    sender, _, receiver, size = r.unpack("QIQI")
    message = r.take(size)
    if not message.endswith(b"\0"):
        raise ProtocolError("Addon whisper missing terminator")
    tag, = r.unpack("B")
    r.finish()
    return dict(sender=sender, receiver=receiver,
                message=message[:-1].decode("utf-8", "replace"), tag=tag)


def item_push(data):
    r = Reader(data)
    values = r.unpack("QIIIBIIIiII")
    r.finish()
    return dict(zip(("guid", "received", "created", "show_chat", "bag", "slot",
                     "item", "suffix", "random_property", "count", "total"), values))


class RealmClient:
    def __init__(self, sock, emit=print):
        self.sock = sock
        self.emit = emit
        self.incoming = self.outgoing = None
        self.ignored = Counter()
        self.started = time.monotonic()
        self.next_ping = self.started
        self.ping_sequence = 0
        self.login = False

    def send(self, opcode, payload=b""):
        header = struct.pack(">H", len(payload) + 4) + struct.pack("<I", opcode)
        if self.outgoing:
            header = self.outgoing.crypt(header)
        self.sock.sendall(header + payload)

    def receive(self):
        def header_bytes(size):
            data = recv_exact(self.sock, size)
            return self.incoming.crypt(data) if self.incoming else data
        first = header_bytes(1)[0]
        size = int.from_bytes(bytes([first & 0x7F]) + header_bytes(2 if first & 0x80 else 1), "big")
        opcode, = struct.unpack("<H", header_bytes(2))
        if not 2 <= size <= 0x7FFFFF:
            raise ProtocolError(f"Invalid world packet size {size}")
        return opcode, recv_exact(self.sock, size - 2)

    def process(self, opcode, payload):
        if opcode == SMSG_TIME_SYNC_REQ:
            counter, = struct.unpack("<I", payload)
            ticks = int((time.monotonic() - self.started) * 1000) & 0xFFFFFFFF
            self.send(CMSG_TIME_SYNC_RESP, struct.pack("<II", counter, ticks))
        elif opcode == SMSG_LOGIN_VERIFY_WORLD:
            world = struct.unpack("<Iffff", payload)
            self.login = True
            self.emit(f"LOGIN map={world[0]} x={world[1]} y={world[2]} z={world[3]}")
        elif opcode == SMSG_CHARACTER_LOGIN_FAILED:
            raise ProtocolError(f"Character login failed: {payload.hex()}")
        elif opcode == SMSG_MESSAGECHAT:
            message = addon_whisper(payload)
            if message is not None:
                self.emit("ADDON " + json.dumps(message, ensure_ascii=True))
        elif opcode == SMSG_ITEM_PUSH_RESULT:
            self.emit("ITEM_PUSH " + json.dumps(item_push(payload)))
        elif opcode == SMSG_WARDEN_DATA:
            raise ProtocolError("SMSG_WARDEN_DATA received; Warden is not implemented")
        else:
            self.ignored[opcode] += 1

    def wait_for(self, expected, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not select.select([self.sock], [], [], max(0, deadline - time.monotonic()))[0]:
                break
            opcode, payload = self.receive()
            if opcode == expected:
                return payload
            self.process(opcode, payload)
        raise ProtocolError(f"Timed out waiting for opcode {expected:#x}")

    def connect(self, account, auth, realm, character="APProbe", *, race=1, class_id=1):
        creation = create_character(character, race, class_id)  # Validate before sending anything.
        challenge = self.wait_for(SMSG_AUTH_CHALLENGE)
        if len(challenge) != 40:
            raise ProtocolError("Invalid world auth challenge")
        self.send(CMSG_AUTH_SESSION, world_auth(account, auth.session_key, challenge[4:8], realm.realm_id))
        self.incoming = header_cipher(auth.session_key, incoming=True)
        self.outgoing = header_cipher(auth.session_key, incoming=False)
        response = self.wait_for(SMSG_AUTH_RESPONSE)
        if not response or response[0] != 0x0C:
            raise ProtocolError(f"World auth rejected or queued: {response.hex()}")
        self.send(CMSG_CHAR_ENUM)
        characters = parse_characters(self.wait_for(SMSG_CHAR_ENUM))
        chosen = next((c for c in characters if c.name.casefold() == character.casefold()), None)
        if chosen is None:
            self.send(CMSG_CHAR_CREATE, creation)
            result = self.wait_for(SMSG_CHAR_CREATE)
            if result != b"\x2f":
                raise ProtocolError(f"Character creation rejected: {result.hex()}; no characters deleted")
            self.emit(f"CREATED {character}")
            self.send(CMSG_CHAR_ENUM)
            characters = parse_characters(self.wait_for(SMSG_CHAR_ENUM))
            chosen = next((c for c in characters if c.name.casefold() == character.casefold()), None)
            if chosen is None:
                raise ProtocolError("Created character absent from enumeration")
        self.emit(f"GUID {chosen.guid} name={chosen.name}")
        self.send(CMSG_PLAYER_LOGIN, struct.pack("<Q", chosen.guid))
        self.process(SMSG_LOGIN_VERIFY_WORLD, self.wait_for(SMSG_LOGIN_VERIFY_WORLD, 30))
        return chosen

    def logout(self):
        self.send(0x4B)
        response = self.wait_for(0x4C)
        if len(response) != 5 or struct.unpack("<IB", response)[0] != 0:
            raise ProtocolError(f"Logout rejected: {response.hex()}")
        self.wait_for(0x4D, timeout=30)
        self.login = False

    def stay(self, seconds=30):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= self.next_ping:
                self.send(CMSG_PING, struct.pack("<II", self.ping_sequence, 0))
                self.ping_sequence += 1
                self.next_ping = now + 30
            if select.select([self.sock], [], [], max(0, min(deadline, self.next_ping) - now))[0]:
                self.process(*self.receive())
        self.emit("IGNORED " + json.dumps({f"0x{k:03x}": v for k, v in sorted(self.ignored.items())}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", default="TEST")
    parser.add_argument("--password", default="TEST", help="test-only credential, visible in process arguments")
    parser.add_argument("--character", default="APProbe")
    parser.add_argument("--seconds", type=float, default=30)
    args = parser.parse_args(argv)
    if not math.isfinite(args.seconds) or args.seconds < 0:
        parser.error("--seconds must be finite and nonnegative")
    try:
        create_character(args.character)
        auth = authenticate(args.account, args.password)
        for realm in auth.realms:
            print(f"REALM id={realm.realm_id} name={realm.name} address={realm.address} flags={realm.flags:#x}", flush=True)
        realm = next((r for r in auth.realms if not r.locked and not r.flags & 3), None)
        if realm is None:
            raise ProtocolError("No unlocked online realm")
        # Deliberately use loopback, never follow a realm-list address off-machine.
        with socket.create_connection(("127.0.0.1", 8085), timeout=10) as sock:
            client = RealmClient(sock, emit=lambda line: print(line, flush=True))
            client.connect(args.account, auth, realm, args.character)
            client.stay(args.seconds)
    except (OSError, ProtocolError, ValueError, struct.error) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
