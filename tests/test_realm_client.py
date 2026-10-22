"""Offline protocol checks. Run: python -m unittest discover -s tests -p test_realm_client.py"""

import hashlib
import socket
import struct
import threading
import unittest
from unittest.mock import patch

import realm_client as rc


# Fixed server-side fixture from AzerothCore SRP6.cpp equations:
# salt=00..1f, a=0x123456789abcdef, b=0xfedcba987654321, TEST:TEST.
# B=(3*v+g**b)%N; S=(A*v**H(A|B))**b%N, not the client formula.
SERVER_PUBLIC = bytes.fromhex("414742dda6c1ab7158e3393e809deae004f50080fc4bd4e15288d100b4e6bf2b")
PUBLIC = bytes.fromhex("fa0bbbb1d12768d0c5854c7aa773b910e39b7a16825068f04c0c754b102f167a")
KEY = bytes.fromhex("d8d9f8dfd7163ea27b99357e9d2e9409fcad99a5cf5ac45476a27f1f915f9bdf1092bb42d4fc5afe")
M1 = bytes.fromhex("83e1dde3fce87d50bcf673f9dac32384d0654372")
M2 = bytes.fromhex("f67270aace45d7cc984cf83411a238121c2969c2")
REALMS = (bytes.fromhex("000000000100000004") + b"AzerothCore\0localhost:8085\0" +
          bytes.fromhex("0000000000010103030534301000"))
CHARACTERS = b"\x01" + struct.pack("<Q", 42) + b"APProbe\0" + bytes(261)
WHISPER = (bytes.fromhex("07ffffffff2a00000000000000000000002a000000000000000b000000") +
           b"AP\tgranted\0\0")
ITEM = bytes.fromhex(
    "2a00000000000000010000000000000001000000ff17000000"
    "b80d000000000000ffffffff0200000005000000")


class MemorySocket:
    """Fragment every read, so packet parsing cannot depend on TCP boundaries."""

    def __init__(self, data):
        self.data = bytearray(data)
        self.sent = bytearray()
        self.timeouts = []

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def recv(self, size):
        size = min(size, 3)
        result = bytes(self.data[:size])
        del self.data[:size]
        return result

    def sendall(self, data):
        self.sent.extend(data)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def server_packet(opcode, payload):
    return struct.pack(">H", len(payload) + 2) + struct.pack("<H", opcode) + payload


class CryptoTests(unittest.TestCase):
    def test_rc4_published_vectors(self):
        # Original RC4 published examples, plus RFC 6229 key 01 02 03 04 05.
        assert rc.RC4(b"Key").crypt(b"Plaintext").hex() == "bbf316e8d940af0ad3"
        assert rc.RC4(b"Wiki").crypt(b"pedia").hex() == "1021bf0420"
        stream = rc.RC4(bytes.fromhex("0102030405"))
        assert stream.crypt(bytes(16)).hex() == "b2396305f03dc027ccc3524a0a1118a8"
        stream.crypt(bytes(1008))
        assert stream.crypt(bytes(16)).hex() == "30abbcc7c20b01609f23ee2d5f6bb7df"

    def test_header_keys_and_drop1024(self):
        # Independently generated with cryptography ARC4 and AuthCrypt.cpp seeds.
        key = bytes(range(40))
        assert rc.header_cipher(key, incoming=True).crypt(bytes(12)).hex() == "da4770c4efd0bceb7173cb14"
        assert rc.header_cipher(key, incoming=False).crypt(bytes(12)).hex() == "e65788e6a6ce478550d66e87"

    def test_srp_server_fixture(self):
        proof = rc.srp_proof("test", "test", bytes(range(32)), SERVER_PUBLIC, 0x123456789ABCDEF)
        assert proof.public == PUBLIC
        assert proof.session_key == KEY
        assert proof.proof == M1
        assert proof.server_proof == M2
        # Check the fixture's session key with the upstream *server* equation.
        n = int("894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7", 16)
        v = int.from_bytes(bytes.fromhex("a57079472ffeddf921a6477b3b340f3691625bb0f1313427f38742e6f128b614"), "little")
        u = int.from_bytes(hashlib.sha1(PUBLIC + SERVER_PUBLIC).digest(), "little")
        secret = pow(int.from_bytes(proof.public, "little") * pow(v, u, n), 0xFEDCBA987654321, n)
        assert secret.to_bytes(32, "little").hex() == "7c0574f673676f878ace7a7d10db537df12e8941d04446592d7aca2da514c91b"

    def test_interleave_zero_pair_trimming(self):
        # SHA1(empty) = da39a3ee...; the nonzero pair hashes 'a' and NUL.
        assert rc.interleave(bytes(32)).hex() == "dada3939a3a3eeee5e5e6b6b4b4b0d0d32325555bfbfefef9595606018189090afafd8d807070909"
        expected = "865bf7a9e43c379dfab0a5cfa7f9fc3fe1525db51d21dcd7b942ea0eea43eaf637ed76a26778b84f"
        assert rc.interleave(bytes(30) + b"a\0").hex() == expected
        assert rc.interleave(bytes(29) + b"\x01a\0").hex() == expected
        with self.assertRaises(rc.ProtocolError):
            rc.srp_proof("TEST", "TEST", bytes(32), bytes(32), 1)


class ProtocolTests(unittest.TestCase):
    def test_logon_wire_layout(self):
        assert rc.logon_challenge("test").hex() == (
            "00002200576f57000303053430363878006e69570053556e6500000000"
            "7f0000010454455354")

    def test_logout_waits_for_completion_and_rejects_denial(self):
        sock = MemorySocket(server_packet(0x4C, bytes.fromhex("0000000001")) + server_packet(0x4D, b""))
        client = rc.RealmClient(sock)
        client.login = True
        with patch.object(rc.select, "select", return_value=([sock], [], [])):
            client.logout()
        self.assertEqual(bytes(sock.sent), bytes.fromhex("00044b000000"))
        self.assertFalse(client.login)
        denied = MemorySocket(server_packet(0x4C, bytes.fromhex("0100000000")))
        with patch.object(rc.select, "select", return_value=([denied], [], [])):
            with self.assertRaisesRegex(rc.ProtocolError, "Logout rejected"):
                rc.RealmClient(denied).logout()

    def test_fixture_commands_use_say_and_common(self):
        from verify_inventory_edges import command
        sent = []

        class Client:
            def send(self, opcode, payload):
                sent.append((opcode, payload))

            def stay(self, seconds):
                assert seconds == 1

        command(Client(), ".save")
        self.assertEqual(sent, [(0x95, bytes.fromhex("01000000070000002e7361766500"))])

    def test_authenticate_checks_server_proof_and_enumerates_realms(self):
        reply = (b"\0\0\0" + SERVER_PUBLIC + b"\x01\x07\x20" + rc.le32(rc.N) +
                 bytes(range(32)) + bytes(17) + b"\x01\0" + M2 + bytes(10) +
                 b"\x10" + struct.pack("<H", len(REALMS)) + REALMS)
        sock = MemorySocket(reply)
        with patch.object(rc.socket, "create_connection", return_value=sock), patch.object(rc.secrets, "randbelow", return_value=0x123456789ABCDEE):
            auth = rc.authenticate()
        assert auth.session_key == KEY
        assert auth.realms == [rc.Realm("AzerothCore", "localhost:8085", 1, 4, False)]
        assert bytes(sock.sent) == rc.logon_challenge("TEST") + b"\x01" + PUBLIC + M1 + bytes(22) + b"\x10\0\0\0\0"
        corrupted = reply.replace(M2, bytes(20), 1)
        with patch.object(rc.socket, "create_connection", return_value=MemorySocket(corrupted)), patch.object(rc.secrets, "randbelow", return_value=0x123456789ABCDEE):
            with self.assertRaisesRegex(rc.ProtocolError, "server proof mismatch"):
                rc.authenticate()

    def test_ready_wait_polls_same_authenticated_socket_and_key(self):
        offline = bytearray(REALMS)
        offline[8] |= 2
        locked = bytearray(REALMS)
        locked[7] = 1
        invalid = bytearray(REALMS)
        invalid[8] |= 1
        for lists, timeout, error, polls in (
                ([bytes(offline), bytes(locked), bytes(invalid), REALMS], 45, None, 4),
                ([bytes(offline)] * 3, 2, 'timed out', 2),
                ([bytes(offline)], 0, None, 1),
                ([bytes(offline), REALMS[:-1]], 45, 'Truncated packet', 2)):
            with self.subTest(timeout=timeout, error=error):
                prefix = (b'\0\0\0' + SERVER_PUBLIC + b'\x01\x07\x20' + rc.le32(rc.N) +
                          bytes(range(32)) + bytes(17) + b'\x01\0' + M2 + bytes(10))
                sock = MemorySocket(prefix + b''.join(
                    b'\x10' + struct.pack('<H', len(body)) + body for body in lists))
                clock = [0.0]
                def sleep(seconds):
                    self.assertGreaterEqual(seconds, 1)
                    clock[0] += seconds
                with patch.object(rc.socket, 'create_connection', return_value=sock) as connect, \
                        patch.object(rc.secrets, 'randbelow', return_value=0x123456789ABCDEE) as private, \
                        patch.object(rc.time, 'monotonic', side_effect=lambda: clock[0]), \
                        patch.object(rc.time, 'sleep', side_effect=sleep):
                    if error:
                        with self.assertRaisesRegex(rc.ProtocolError, error):
                            rc.authenticate(ready_timeout=timeout)
                    else:
                        auth = rc.authenticate(ready_timeout=timeout)
                        self.assertEqual(auth.session_key, KEY)
                        self.assertEqual(auth.realms[0].flags, 6 if timeout == 0 else 4)
                    connect.assert_called_once()
                    private.assert_called_once()
                self.assertEqual(bytes(sock.sent), rc.logon_challenge('TEST') +
                                 b'\x01' + PUBLIC + M1 + bytes(22) + b'\x10\0\0\0\0' * polls)
                self.assertTrue(all(0 < t <= 10 for t in sock.timeouts))

    def test_ready_response_deadline_covers_fragmented_reads(self):
        sock = MemorySocket(b'abcdef')
        with patch.object(rc.time, 'monotonic', side_effect=[0, 2]):
            with self.assertRaisesRegex(rc.ProtocolError, 'timed out'):
                rc.recv_exact(sock, 6, deadline=1)
        self.assertEqual(sock.timeouts, [1])
        self.assertEqual(sock.data, bytearray(b'def'))

    def test_ready_wait_rejects_invalid_bounds_before_network(self):
        for timeout in (-1, 121, float('nan'), float('inf'), True, '30', None):
            with self.subTest(timeout=timeout), patch.object(rc.socket, 'create_connection') as connect:
                with self.assertRaises(ValueError):
                    rc.authenticate(ready_timeout=timeout)
                connect.assert_not_called()

    def test_ready_wait_never_bypasses_bad_srp_proof(self):
        reply = (b'\0\0\0' + SERVER_PUBLIC + b'\x01\x07\x20' + rc.le32(rc.N) +
                 bytes(range(32)) + bytes(17) + b'\x01\0' + bytes(30))
        sock = MemorySocket(reply)
        with patch.object(rc.socket, 'create_connection', return_value=sock), \
                patch.object(rc.secrets, 'randbelow', return_value=0x123456789ABCDEE):
            with self.assertRaisesRegex(rc.ProtocolError, 'server proof mismatch'):
                rc.authenticate(ready_timeout=45)
        self.assertEqual(bytes(sock.sent), rc.logon_challenge('TEST') + b'\x01' + PUBLIC + M1 + bytes(22))

    def test_repeated_short_stays_share_the_thirty_second_ping_schedule(self):
        clock, sent = [100.0], []

        def wait(readers, writers, errors, timeout):
            clock[0] += timeout
            return [], [], []

        with patch.object(rc.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(rc.select, "select", side_effect=wait):
            client = rc.RealmClient(object())
            client.send = lambda opcode, payload: sent.append((clock[0], opcode, payload))
            for _ in range(6):
                client.stay(0.5)
            client.stay(28)
        self.assertEqual(sent, [(100.0, rc.CMSG_PING, struct.pack("<II", 0, 0)),
                                (130.0, rc.CMSG_PING, struct.pack("<II", 1, 0))])
        self.assertEqual(clock[0], 131.0)

    def test_world_auth_wire_layout(self):
        result = rc.world_auth("test", bytes(range(40)), bytes.fromhex("aabbccdd"), 1, bytes.fromhex("01020304"))
        assert result.hex() == (
            "343000000000000054455354000000000001020304000000000000000001000000"
            "00000000000000000729de1e025d8947588c61cf16f8be19f748df3100000000")

    def test_character_enum_and_create(self):
        assert rc.parse_characters(CHARACTERS) == [rc.Character(42, "APProbe")]
        two = b"\x02" + CHARACTERS[1:] + struct.pack("<Q", 99) + b"Other\0" + bytes(261)
        assert rc.parse_characters(two) == [rc.Character(42, "APProbe"), rc.Character(99, "Other")]
        assert rc.create_character("APProbe") == b"APProbe\0\x01\x01\0\0\0\0\0\0\0"
        assert rc.create_character("Arcanist", race=10, class_id=8) == b"Arcanist\0\x0a\x08\0\0\0\0\0\0\0"
        assert rc.create_character("Shaman", race=11, class_id=7) == b"Shaman\0\x0b\x07\0\0\0\0\0\0\0"
        for profile in ((0, 1), (1, 256), (True, 1), (1, "8")):
            with self.assertRaises(ValueError):
                rc.create_character("Invalid", *profile)
        with self.assertRaises(ValueError):
            rc.create_character("AP\0Probe")
        with self.assertRaises(rc.ProtocolError):
            rc.parse_characters(CHARACTERS[:-1])

    def test_addon_and_item_push(self):
        assert rc.addon_whisper(WHISPER) == dict(sender=42, receiver=42, message="AP\tgranted", tag=0)
        assert rc.addon_whisper(b"\x00\0\0\0\0") is None
        assert rc.item_push(ITEM) == dict(guid=42, received=1, created=0, show_chat=1,
                                        bag=255, slot=23, item=3512, suffix=0,
                                        random_property=-1, count=2, total=5)
        with self.assertRaises(rc.ProtocolError):
            rc.addon_whisper(WHISPER[:-3])

    def test_encrypted_headers_and_large_server_packets(self):
        # Captured fixture generated by independent cryptography ARC4, key=00..27.
        sock = MemorySocket(bytes.fromhex("da4b70c6") + b"0123456789")
        client = rc.RealmClient(sock)
        client.incoming = rc.header_cipher(bytes(range(40)), incoming=True)
        assert client.receive() == (0x200, b"0123456789")
        # A separate plaintext extended header, size=0x8002, opcode=0x1f6.
        client = rc.RealmClient(MemorySocket(bytes.fromhex("808002f601") + b"x" * 0x8000))
        assert client.receive() == (0x1F6, b"x" * 0x8000)
        sock = MemorySocket(b"")
        client = rc.RealmClient(sock)
        client.outgoing = rc.header_cipher(bytes(range(40)), incoming=False)
        client.send(0x37)
        assert bytes(sock.sent).hex() == "e653bfe6a6ce"

    def test_online_notifications_and_time_sync(self):
        sock = MemorySocket(b"")
        lines = []
        client = rc.RealmClient(sock, lines.append)
        client.process(0x236, struct.pack("<Iffff", 0, 1, 2, 3, 4))
        client.process(0x96, WHISPER)
        client.process(0x166, ITEM)
        with patch.object(rc.time, "monotonic", return_value=client.started + 1.25):
            client.process(0x390, bytes.fromhex("07000000"))
        assert bytes(sock.sent).hex() == "000c9103000007000000e2040000"
        assert lines == [
            "LOGIN map=0 x=1.0 y=2.0 z=3.0",
            'ADDON {"sender": 42, "receiver": 42, "message": "AP\\tgranted", "tag": 0}',
            'ITEM_PUSH {"guid": 42, "received": 1, "created": 0, "show_chat": 1, "bag": 255, "slot": 23, "item": 3512, "suffix": 0, "random_property": -1, "count": 2, "total": 5}',
        ]
        with self.assertRaisesRegex(rc.ProtocolError, "Warden"):
            client.process(0x2E6, b"\0")

    def test_full_world_login_creates_only_if_missing(self):
        # Socketpair exercises real framing, encrypted traffic and wait_for.
        for exists in (True, False):
            with self.subTest(exists=exists):
                client_sock, server_sock = socket.socketpair()
                client_sock.settimeout(2)
                server_sock.settimeout(2)
                received = []
                errors = []

                def server():
                    try:
                        with server_sock:
                            server_sock.sendall(server_packet(0x1EC, bytes(40)))
                            size = int.from_bytes(rc.recv_exact(server_sock, 2), "big")
                            auth = rc.recv_exact(server_sock, size)
                            received.append(int.from_bytes(auth[:4], "little"))
                            incoming = rc.header_cipher(bytes(range(40)), incoming=False)
                            outgoing = rc.header_cipher(bytes(range(40)), incoming=True)

                            def send(opcode, data):
                                packet = server_packet(opcode, data)
                                server_sock.sendall(outgoing.crypt(packet[:4]) + packet[4:])

                            def receive():
                                header = incoming.crypt(rc.recv_exact(server_sock, 6))
                                size = int.from_bytes(header[:2], "big")
                                opcode = int.from_bytes(header[2:], "little")
                                data = rc.recv_exact(server_sock, size - 4)
                                received.append(opcode)
                                return data

                            send(0x1EE, b"\x0c" + bytes(10))
                            assert receive() == b""
                            send(0x3B, CHARACTERS if exists else b"\0")
                            if not exists:
                                assert receive() == b"APProbe\0\x01\x01\0\0\0\0\0\0\0"
                                send(0x3A, b"\x2f")
                                assert receive() == b""
                                send(0x3B, CHARACTERS)
                            assert receive() == b"\x2a" + bytes(7)
                            send(0x96, WHISPER)
                            send(0x236, struct.pack("<Iffff", 0, 1, 2, 3, 4))
                    except Exception as exc:
                        errors.append(exc)

                worker = threading.Thread(target=server, daemon=True)
                worker.start()
                lines = []
                try:
                    with client_sock:
                        client = rc.RealmClient(client_sock, lines.append)
                        character = client.connect("TEST", rc.AuthResult(bytes(range(40)), []), rc.Realm("AC", "localhost:8085", 1, 0, False))
                        assert character == rc.Character(42, "APProbe")
                finally:
                    worker.join(3)
                assert errors == [], errors
                assert not worker.is_alive()
                assert received == ([0x1ED, 0x37, 0x3D] if exists else [0x1ED, 0x37, 0x36, 0x37, 0x3D])
                assert "GUID 42 name=APProbe" in lines
                assert lines[-1] == "LOGIN map=0 x=1.0 y=2.0 z=3.0"
                assert any(line.startswith("ADDON ") for line in lines)

    def test_truncation_and_cli_validation(self):
        with self.assertRaisesRegex(rc.ProtocolError, "closed"):
            rc.RealmClient(MemorySocket(b"\0")).receive()
        with self.assertRaises(SystemExit) as exc:
            rc.main(["--seconds", "nan"])
        assert exc.exception.code == 2


if __name__ == "__main__":
    unittest.main()
