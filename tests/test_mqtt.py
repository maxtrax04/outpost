"""The MQTT client (app/outpost_mqtt.py): packets, and a session with a broker on this machine."""

import contextlib
import io
import socket
import threading
import unittest

import helpers  # noqa: F401 (puts app/ on the path)

import outpost_mqtt as m


def quiet():
    return contextlib.redirect_stderr(io.StringIO())


class PacketTests(unittest.TestCase):
    def test_remaining_length(self):
        for length, encoded in ((0, b"\x00"), (127, b"\x7f"), (128, b"\x80\x01"), (16383, b"\xff\x7f"),
                                (16384, b"\x80\x80\x01"), (2097152, b"\x80\x80\x80\x01")):
            with self.subTest(length=length):
                self.assertEqual(m.remaining_length(length), encoded)
        with self.assertRaises(ValueError):
            m.remaining_length(268_435_456)

    def test_connect(self):
        self.assertEqual(m.connect_packet("id", keepalive=60),
                         b"\x10\x0e\x00\x04MQTT\x04\x02\x00\x3c\x00\x02id")
        with_login = m.connect_packet("id", "user", "pw")
        self.assertEqual(with_login[9], 0x02 | 0x80 | 0x40)
        self.assertTrue(with_login.endswith(b"\x00\x04user\x00\x02pw"))
        # A password needs a username (MQTT 3.1.1), so without one neither is sent
        self.assertEqual(m.connect_packet("id", "", "pw")[9], 0x02)

    def test_subscribe_is_qos_0(self):
        self.assertEqual(m.subscribe_packet(1, ["a/b", "c"]),
                         b"\x82\x0c\x00\x01\x00\x03a/b\x00\x00\x01c\x00")

    def test_publish(self):
        self.assertEqual(m.parse_publish(0x01, b"\x00\x03a/b21.5"), ("a/b", b"21.5", 0, None))
        self.assertEqual(m.parse_publish(0x02, b"\x00\x01a\x00\x07on"), ("a", b"on", 1, 7))
        for body in (b"", b"\x00\x09a", b"\x00\x01\xff", ):
            with self.subTest(body=body), self.assertRaises(m.ProtocolError):
                m.parse_publish(0x00, body)

    def test_reader_takes_packets_in_any_pieces(self):
        stream = m.packet(m.CONNACK, 0, b"\x00\x00") + m.packet(m.PUBLISH, 0, b"\x00\x01a" + b"x" * 300) \
            + m.packet(m.PINGRESP, 0, b"")
        reader = m.Reader()
        packets = []
        for index in range(len(stream)):
            packets += reader.feed(stream[index:index + 1])
        self.assertEqual([kind for kind, _, _ in packets], [m.CONNACK, m.PUBLISH, m.PINGRESP])
        self.assertEqual(packets[1][2], b"\x00\x01a" + b"x" * 300)

    def test_reader_skips_big_packets(self):
        reader = m.Reader(limit=100)
        big = m.packet(m.PUBLISH, 0, b"\x00\x01a" + b"x" * 1000)
        packets = reader.feed(big[:500]) + reader.feed(big[500:] + m.packet(m.PINGRESP, 0, b""))
        self.assertEqual([kind for kind, _, _ in packets], [m.PINGRESP])
        self.assertEqual(reader.skipped, 1)
        self.assertEqual(len(reader.buffer), 0)

    def test_reader_refuses_a_bad_length(self):
        with self.assertRaises(m.ProtocolError):
            m.Reader().feed(b"\x30\xff\xff\xff\xff\x01")


class FakeBroker:
    """A broker on 127.0.0.1 for one connection at a time: answers CONNACK with `code`, SUBACK, then
    sends `messages` (topic, payload), and records what the client sent."""

    def __init__(self, code=0, messages=(), refuse=()):
        self.code = code
        self.messages = list(messages)
        self.refuse = set(refuse)
        self.received = []
        self.connections = 0
        self.connected = threading.Event()
        self.pinged = threading.Event()
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(5)
        self.server.settimeout(10)
        self.port = self.server.getsockname()[1]
        self.close_after_subscribe = False
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            self.connections += 1
            with conn:
                self.talk(conn)

    def talk(self, conn):
        reader = m.Reader()
        conn.settimeout(10)
        while True:
            try:
                data = conn.recv(4096)
            except OSError:
                return
            if not data:
                return
            for kind, flags, body in reader.feed(data):
                self.received.append((kind, flags, body))
                if kind == m.CONNECT:
                    conn.sendall(m.packet(m.CONNACK, 0, bytes([0, self.code])))
                    if self.code:
                        return
                elif kind == m.SUBSCRIBE:
                    topics, rest = [], body[2:]
                    while rest:
                        size = int.from_bytes(rest[:2], "big")
                        topics.append(rest[2:2 + size].decode())
                        rest = rest[3 + size:]
                    codes = bytes(0x80 if topic in self.refuse else 0 for topic in topics)
                    conn.sendall(m.packet(m.SUBACK, 0, body[:2] + codes))
                    for topic, payload in self.messages:
                        conn.sendall(m.packet(m.PUBLISH, 0x01, m.text(topic) + payload))
                    self.connected.set()
                    if self.close_after_subscribe:
                        return
                elif kind == m.PINGREQ:
                    conn.sendall(m.packet(m.PINGRESP, 0, b""))
                    self.pinged.set()

    def close(self):
        self.server.close()


class ClientTests(unittest.TestCase):
    def client(self, broker, topics, **options):
        got = []
        done = threading.Event()
        wait_for = options.pop("wait_for", 1)

        def message(topic, payload):
            got.append((topic, payload))
            if len(got) >= wait_for:
                done.set()

        client = m.Client("127.0.0.1", broker.port, topics, message, **options)
        return client, got, done

    def run_client(self, client, until, timeout=10):
        stop = threading.Event()
        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            thread = threading.Thread(target=client.run, args=(stop,), daemon=True)
            thread.start()
            until.wait(timeout)
            stop.set()
            thread.join(10)
        self.assertFalse(thread.is_alive())
        return log.getvalue()

    def test_subscribes_to_the_listed_topics_and_gets_their_messages(self):
        broker = FakeBroker(messages=[("home/shed", b"21.5"), ("home/other", b"not asked for")])
        self.addCleanup(broker.close)
        client, got, done = self.client(broker, ["home/shed", "home/garage", "home/shed"],
                                        username="outpost", password="secret-password")
        log = self.run_client(client, done)
        self.assertEqual(got, [("home/shed", b"21.5")])
        connect = next(body for kind, _, body in broker.received if kind == m.CONNECT)
        self.assertIn(b"secret-password", connect)
        subscribe = next(body for kind, _, body in broker.received if kind == m.SUBSCRIBE)
        self.assertEqual(subscribe[2:], b"\x00\x09home/shed\x00\x00\x0bhome/garage\x00")
        self.assertIn("MQTT broker connected, 2 topics", log)
        self.assertNotIn("secret-password", log)
        self.assertNotIn("21.5", log)
        # It never publishes
        self.assertNotIn(m.PUBLISH, [kind for kind, _, _ in broker.received])

    def test_a_refused_login_is_logged_without_the_password(self):
        broker = FakeBroker(code=4)
        self.addCleanup(broker.close)
        client, _, _ = self.client(broker, ["a"], username="outpost", password="secret-password")
        with self.assertRaisesRegex(m.ProtocolError, "username or password was refused"):
            client.session(threading.Event())
        self.assertFalse(client.connected)

    def test_a_refused_topic_is_named(self):
        broker = FakeBroker(refuse=["secret/topic"], messages=[("ok", b"1")])
        self.addCleanup(broker.close)
        client, _, done = self.client(broker, ["ok", "secret/topic"])
        log = self.run_client(client, done)
        self.assertIn("refused topic secret/topic", log)

    def test_pings_to_stay_connected(self):
        broker = FakeBroker()
        self.addCleanup(broker.close)
        client, _, _ = self.client(broker, ["a"], keepalive=2)
        alive = []
        client.on_alive = lambda: alive.append(1)
        self.run_client(client, broker.pinged)
        self.assertTrue(broker.pinged.is_set())
        self.assertGreaterEqual(len(alive), 2)

    def test_connects_again_when_the_broker_goes(self):
        broker = FakeBroker(messages=[("a", b"1")])
        broker.close_after_subscribe = True
        self.addCleanup(broker.close)
        states = []
        client, got, done = self.client(broker, ["a"], wait_for=2, on_state=states.append)
        waits = []

        class Stop(threading.Event):
            def wait(self, timeout=None):
                waits.append(timeout)
                return super().wait(0.05)

        stop = Stop()
        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            thread = threading.Thread(target=client.run, args=(stop,), daemon=True)
            thread.start()
            done.wait(10)
            stop.set()
            thread.join(10)
        self.assertEqual(len(got), 2)
        self.assertGreaterEqual(broker.connections, 2)
        self.assertEqual(states[:3], [True, False, True])
        # A growing delay, logged once until it connects again
        self.assertEqual(waits[0], m.FIRST_RETRY_SECONDS)
        text = log.getvalue()
        self.assertEqual(text.count("the broker closed the connection"), 1)
        self.assertIn("connected again", text)

    def test_cant_connect(self):
        with socket.socket() as spare:
            spare.bind(("127.0.0.1", 0))
            port = spare.getsockname()[1]
        client = m.Client("127.0.0.1", port, ["a"], lambda topic, payload: None)
        waited = threading.Event()

        class Stop(threading.Event):
            def wait(self, timeout=None):
                waited.set()
                self.set()
                return True

        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            client.run(Stop())
        self.assertTrue(waited.is_set())
        self.assertIn("can't connect (ConnectionRefusedError); trying again in 5 s", log.getvalue())


if __name__ == "__main__":
    unittest.main()
