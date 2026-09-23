try:
    from micropython import const
except Exception:
    def const(value):
        return value

import ubinascii
import network
import aioespnow
try:
    import utime as time
except Exception:
    import time
try:
    import logging
except Exception:
    logging = None
import json

try:
    import uasyncio as asyncio
except Exception:
    import asyncio

from otel.api import get_tracer
from otel.context import SpanContext
from dnet.messaging.protocol import IncomingMessageError


class LighthouseMesh:
    """ESP-NOW mesh adapter with interrupt-driven RX queueing."""
    BROADCAST_TARGET = const(b"\xff\xff\xff\xff\xff\xff")
    ESPNOW_MAX_PAYLOAD_BYTES = const(245)

    # Fragment header: magic(2) + version(1) + msg_id(2) + total(1) + index(1)
    _FRAG_MAGIC = b"\x7fM"
    _FRAG_VERSION = const(1)
    _FRAG_HEADER_BYTES = const(7)
    _FRAG_PAYLOAD_MAX_BYTES = const(ESPNOW_MAX_PAYLOAD_BYTES - _FRAG_HEADER_BYTES)
    _FRAG_REASSEMBLY_TIMEOUT_MS = const(30000)
    _TX_ACK_TIMEOUT_MS = const(1200)
    _TX_QUEUE_MAX_FRAMES = const(96)
    DEFAULT_CHANNEL = const(6)

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, peers=None, debug=False, channel=None):
        if getattr(self, "_initialized", False):
            self._debug = self._debug or bool(debug)
            self._refresh_channel_state(requested_channel=channel)
            self._log_info(
                "mesh already initialized; reusing node_id={} channel={}".format(
                    self.node_id, self._effective_channel
                )
            )
            if peers:
                try:
                    for peer in peers:
                        self.add_peer(peer)
                except Exception as exc:
                    self._log_error("reinit peer add failed err={}".format(exc))
            return

        # Mirror class constants onto the instance for MicroPython variants
        # that don't reliably resolve class attributes via `self`.
        self.BROADCAST_TARGET = b"\xff\xff\xff\xff\xff\xff"
        self.ESPNOW_MAX_PAYLOAD_BYTES = 240
        self._FRAG_MAGIC = b"\x7fM"
        self._FRAG_VERSION = 1
        self._FRAG_HEADER_BYTES = 7
        self._FRAG_REASSEMBLY_TIMEOUT_MS = 30000
        self._TX_ACK_TIMEOUT_MS = 1200
        self._TX_QUEUE_MAX_FRAMES = 96
        self._logger = None
        self._debug = bool(debug)
        self.tracer = get_tracer("dnet.signalling.mesh")
        self._init_logger()
        # Keep a concrete instance field for compatibility with MicroPython.
        self._FRAG_PAYLOAD_MAX_BYTES = int(self.ESPNOW_MAX_PAYLOAD_BYTES) - int(self._FRAG_HEADER_BYTES)
        self._irq_count = 0
        self._irq_packets_drained = 0
        self._irq_draining = False
        self._irq_redrain_requested = False
        self._fragment_expiry_running = False
        self._tx_queue = []
        self._tx_inflight = None
        self._tx_queued_frames = 0
        self._tx_sent_frames = 0
        self._tx_ack_ok = 0
        self._tx_ack_fail = 0
        self._tx_ack_timeout = 0
        self._tx_stat_tx_responses = 0
        self._tx_stat_tx_failures = 0

        if channel is None:
            channel = int(self.DEFAULT_CHANNEL)
        self._channel = int(channel)

        # Bring up STA mode so ESP-NOW can operate.
        self.wlan_sta = network.WLAN(network.STA_IF)
        self.wlan_sta.active(True)
        self._configure_wifi_for_espnow(self._channel)

        # Canonical node id is the local MAC as lowercase hex.
        self.wlan_mac = self.wlan_sta.config("mac")
        self.node_id = self.mac_to_node_id(self.wlan_mac)
        self._effective_channel = self._read_wifi_channel()
        self._peer_channel = self._effective_channel if isinstance(self._effective_channel, int) else 0
        self._ensure_requested_channel(self._channel)
        self._log_info(
            "mesh init node_id={} mac={}".format(self.node_id, self.mac_to_node_id(self.wlan_mac))
        )
        self._log_info("mesh wifi channel={} peer_channel={}".format(self._effective_channel, self._peer_channel))
        self._log_debug("mesh init debug={} peers_arg={}".format(self._debug, peers))

        # ESP-NOW transport endpoint.
        self.espnow = aioespnow.AIOESPNow()
        self.espnow.active(True)
        stats = self.get_stats()
        self._tx_stat_tx_responses = int(stats[1])
        self._tx_stat_tx_failures = int(stats[2])

        # Peer cache and IRQ->async receive buffering.
        self._known_peers = set()
        self._rx_queue = []
        self._max_rx_queue = 32
        self._max_rx_queue_seen = 0
        self._rx_event = None
        self._tx_message_id = 0
        self._fragment_buffers = {}
        self._last_recv_trace_context = None
        self._last_recv_metadata = None
        self.use_broadcast = True
        self.default_peer = self.BROADCAST_TARGET

        self.add_peer(self.BROADCAST_TARGET)
        if peers:
            try:
                for peer in peers:
                    self.add_peer(peer)
            except Exception as exc:
                self._log_error("initial peer add failed err={}".format(exc))
        try:
            if hasattr(self.espnow, "get_peers"):
                self._log_info("mesh peers={}".format(self.espnow.get_peers()))
        except Exception as exc:
            self._log_debug("mesh get_peers unavailable err={}".format(exc))

        # Async event is signaled by ISR drain when new packets arrive.
        self._init_rx_event()
        self.enable_interrupt_rx()
        self._initialized = True

    @staticmethod
    def mac_to_node_id(mac_bytes):
        """Convert raw MAC bytes to 12-char hex node id."""
        return ubinascii.hexlify(mac_bytes).decode()

    @staticmethod
    def node_id_to_mac(node_id):
        """Convert node id text (plain/colon/dash) into raw MAC bytes."""
        if isinstance(node_id, bytes):
            return node_id
        cleaned = node_id.replace(":", "").replace("-", "").lower()
        return ubinascii.unhexlify(cleaned)

    def add_peer(self, peer):
        """Register a peer once with ESP-NOW."""
        mac = self.resolve_peer(peer)
        if mac in self._known_peers:
            return
        try:
            self.espnow.add_peer(mac, channel=self._peer_channel, ifidx=0)
            self._log_debug(
                "peer add params peer={} channel={} ifidx=0".format(
                    self.mac_to_node_id(mac), self._peer_channel
                )
            )
        except Exception as exc:
            self._log_error(
                "add_peer(channel) failed peer={} channel={} err={}".format(
                    peer, self._peer_channel, exc
                )
            )
            if self._is_peer_exists_error(exc):
                self._known_peers.add(mac)
                self._log_debug("peer already present {}".format(self.mac_to_node_id(mac)))
                return
            try:
                self.espnow.add_peer(mac)
            except Exception as inner_exc:
                if self._is_peer_exists_error(inner_exc):
                    self._known_peers.add(mac)
                    self._log_debug("peer already present {}".format(self.mac_to_node_id(mac)))
                    return
                self._log_error("add_peer failed peer={} err={}".format(peer, inner_exc))
                raise
        self._known_peers.add(mac)
        self._log_debug("peer added {}".format(self.mac_to_node_id(mac)))

    def _is_peer_exists_error(self, exc):
        try:
            return exc.args[0] == -12395
        except Exception:
            return "ESP_ERR_ESPNOW_EXIST" in str(exc)

    def _refresh_channel_state(self, requested_channel=None):
        if requested_channel is not None:
            try:
                self._configure_wifi_for_espnow(int(requested_channel))
            except Exception as exc:
                self._log_error("wifi refresh failed channel={} err={}".format(requested_channel, exc))
        self._effective_channel = self._read_wifi_channel()
        self._peer_channel = self._effective_channel if isinstance(self._effective_channel, int) else 0

    def resolve_peer(self, peer):
        """Resolve alias/node-id/bytes peer forms to raw MAC bytes."""
        if peer is None:
            if self.default_peer is None:
                raise ValueError("peer is required when no default peer is configured")
            return self.default_peer
        if isinstance(peer, str) and peer in ("*", "broadcast"):
            return self.BROADCAST_TARGET
        if isinstance(peer, str):
            return self.node_id_to_mac(peer)
        return peer

    def send_raw(self, peer, payload):
        """Send bytes (or utf-8 string) to the resolved peer."""
        target = self.resolve_peer(peer)
        self.add_peer(target)
        with self.tracer.start_span(
            "dnet.signalling.mesh.send_raw",
            attributes={"peer_id": self.mac_to_node_id(target), "transport": "espnow"},
            kind="internal",
        ):
            if isinstance(payload, str):
                payload = payload.encode("utf-8")
            try:
                if len(payload) <= self.ESPNOW_MAX_PAYLOAD_BYTES:
                    self.espnow.send(target, payload, False)
                else:
                    self._send_fragmented(target, payload)
            except Exception as exc:
                self._log_error(
                    "send failed target={} bytes={} err={}".format(
                        self.mac_to_node_id(target), len(payload), exc
                    )
                )
                raise
        self._log_debug(
            "send ok target={} bytes={}".format(self.mac_to_node_id(target), len(payload))
        )

    def recv_raw(self, timeout_ms=0):
        """Read one queued packet; fallback to direct irecv if queue is empty."""
        if self._rx_queue:
            mac, payload, metadata = self._unpack_rx_frame(self._rx_queue.pop(0))
            self._trace_recv(mac, payload, metadata=metadata)
            return mac, payload

        # Fallback in case IRQ has not been set up by platform.
        self._expire_fragment_buffers()
        mac, msg = self.espnow.irecv(timeout_ms=timeout_ms)
        if mac is None or msg is None:
            return None, None
        payload = self._ingest_rx_packet(mac, msg)
        if payload is None:
            return None, None
        self._trace_recv(
            mac,
            payload,
            metadata={
                "ingest_source": "direct",
                "queued_ms": 0,
                "enqueued_ms": self._now_ms(),
            },
        )
        return mac, payload

    def create_transport(self, default_peer=None):
        """Build transport adapter used by dnet.messaging.MessagingEndpoint."""
        from dnet.signalling.LighthouseTransport import LighthouseMeshTransport

        return LighthouseMeshTransport(self, default_peer=default_peer)

    async def run(self, endpoint=None, on_message=None, poll_ms=20):
        # Wait for RX signal, then drain all currently queued packets.
        self._log_debug("run loop started endpoint={}".format(endpoint is not None))
        while True:
            await self._wait_for_rx(poll_ms)
            if endpoint is None:
                while True:
                    peer, payload = self.recv_raw(timeout_ms=0)
                    if payload is None:
                        break
                    if on_message:
                        try:
                            peer_id = self.mac_to_node_id(peer)
                            with self.tracer.start_span(
                                "dnet.signalling.mesh.dispatch_raw",
                                attributes={"peer_id": str(peer_id), "transport": "espnow"},
                                kind="internal",
                            ):
                                on_message(peer_id, payload)
                        except Exception as exc:
                            self._log_error("on_message(raw) failed err={}".format(exc))
            else:
                self._drain_endpoint_messages(endpoint, on_message)

    def get_stats(self):
        return self.espnow.stats()

    def consume_recv_trace_context(self):
        context = self._last_recv_trace_context
        self._last_recv_trace_context = None
        return context

    def consume_recv_metadata(self):
        metadata = self._last_recv_metadata
        self._last_recv_metadata = None
        return metadata

    def _drain_endpoint_messages(self, endpoint, on_message=None):
        while True:
            try:
                peer_id, message = endpoint.poll()
            except IncomingMessageError as exc:
                self._log_invalid_endpoint_frame(exc)
                continue
            except Exception as exc:
                self._log_error("endpoint.poll failed err={}".format(exc))
                break
            if message is None:
                break
            if on_message:
                try:
                    with endpoint.message_context(peer_id, message):
                        with self.tracer.start_span(
                            "dnet.signalling.mesh.dispatch_decoded",
                            attributes={
                                "peer_id": str(peer_id),
                                "transport": "espnow",
                                "message.type": str(message.get("t", "unknown")),
                            },
                            kind="internal",
                        ):
                            on_message(peer_id, message)
                except Exception as exc:
                    self._log_error("on_message(decoded) failed err={}".format(exc))

    def _log_invalid_endpoint_frame(self, exc):
        payload = exc.payload
        if isinstance(payload, bytes):
            preview = payload[:64].decode("utf-8", "replace")
        else:
            preview = str(payload)[:64]
        preview = preview.replace("\n", "\\n").replace("\r", "\\r")
        payload_len = len(payload) if payload is not None else 0
        self._log_error(
            "endpoint.poll dropped invalid frame peer={} bytes={} err={} preview={}".format(
                exc.peer_id,
                payload_len,
                exc.cause,
                preview,
            )
        )

    def _trace_recv(self, mac, payload, metadata=None):
        metadata = metadata or {}
        if metadata.get("queued_ms") is None and metadata.get("enqueued_ms") is not None:
            metadata["queued_ms"] = self._ticks_diff(self._now_ms(), metadata["enqueued_ms"])
        parent_context = self._extract_payload_context(payload)
        attributes = {"peer_id": self.mac_to_node_id(mac), "transport": "espnow"}
        if payload is not None:
            attributes["message.bytes"] = len(payload)
        queued_ms = metadata.get("queued_ms")
        if queued_ms is not None:
            attributes["rx.queue_ms"] = int(queued_ms)
        ingest_source = metadata.get("ingest_source")
        if ingest_source is not None:
            attributes["rx.ingest_source"] = str(ingest_source)
        with self.tracer.start_span(
            "dnet.signalling.mesh.recv_raw",
            parent_context=parent_context,
            attributes=attributes,
            kind="internal",
        ) as span:
            span_context = getattr(span, "context", None)
            self._last_recv_trace_context = span_context
            recv_metadata = dict(metadata)
            if span_context is not None and getattr(span_context, "span_id", None):
                recv_metadata["recv_span_id"] = span_context.span_id
            recv_metadata["message.bytes"] = len(payload) if payload is not None else 0
            self._last_recv_metadata = recv_metadata
            return

    def _unpack_rx_frame(self, frame):
        if isinstance(frame, tuple):
            if len(frame) >= 3:
                return frame[0], frame[1], frame[2]
            if len(frame) == 2:
                return frame[0], frame[1], {}
        raise ValueError("invalid rx frame {!r}".format(frame))

    @staticmethod
    def _extract_payload_context(payload):
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        try:
            message = json.loads(payload)
        except Exception:
            return None
        carrier = message.get("otel")
        if not isinstance(carrier, dict):
            return None
        trace_id = carrier.get("trace_id") or carrier.get("t")
        span_id = carrier.get("span_id") or carrier.get("s")
        if not trace_id or not span_id:
            return None
        return SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            trace_flags=carrier.get("trace_flags") or carrier.get("f") or "01",
            is_remote=True,
        )

    def print_stats(self):
        stats = self.get_stats()
        print("\nESP-NOW Statistics:")
        print("  Packets Sent: {}".format(stats[0]))
        print("  Packets Delivered: {}".format(stats[1]))
        print("  Packets Dropped (TX): {}".format(stats[2]))
        print("  Packets Received: {}".format(stats[3]))
        print("  Packets Dropped (RX): {}".format(stats[4]))

    def enable_interrupt_rx(self):
        """Enable ESP-NOW interrupt callback for incoming packets."""
        self.espnow.irq(self._on_espnow_irq)
        self._log_info("interrupt rx enabled callback={}".format(self._on_espnow_irq))
        self._log_info("initial espnow stats={}".format(self.get_stats()))

    def disable_interrupt_rx(self):
        """Disable ESP-NOW interrupt callback."""
        self.espnow.irq(None)
        self._log_info("interrupt rx disabled")

    def _on_espnow_irq(self, *_):
        # ESPNow.irq() on this port fires on RX events; we also use this wakeup
        # to update TX completion state and drain queued fragments.
        # ISR entry: move pending frames from driver FIFO into local queue.
        self._irq_count += 1
        if self._irq_draining:
            self._irq_redrain_requested = True
            return
        self._irq_draining = True
        try:
            while True:
                self._irq_redrain_requested = False
                self._expire_fragment_buffers()
                self._drain_incoming()
                self._pump_tx_queue(source="irq")
                if not self._irq_redrain_requested:
                    break
        finally:
            self._irq_draining = False

    def _drain_incoming(self):
        """Drain all immediately available packets from ESP-NOW."""
        drained = 0
        while True:
            mac, msg = self.espnow.irecv(timeout_ms=0)
            if mac is None or msg is None:
                break
            payload = self._ingest_rx_packet(mac, msg)
            if payload is None:
                continue
            if len(self._rx_queue) >= self._max_rx_queue:
                # Drop oldest packet to make room for newest packet.
                self._rx_queue.pop(0)
                self._log_error("rx queue overflow, dropping oldest packet")
            enqueued_ms = self._now_ms()
            self._rx_queue.append(
                (
                    mac,
                    payload,
                    {
                        "ingest_source": "irq",
                        "enqueued_ms": enqueued_ms,
                    },
                )
            )
            if len(self._rx_queue) > self._max_rx_queue_seen:
                self._max_rx_queue_seen = len(self._rx_queue)
            drained += 1
        if drained:
            self._irq_packets_drained += drained
        self._signal_rx_event()

    def _next_message_id(self):
        self._tx_message_id = (self._tx_message_id + 1) & 0xFFFF
        return self._tx_message_id

    def _send_fragmented(self, target, payload):
        max_payload = int(self._FRAG_PAYLOAD_MAX_BYTES)
        if max_payload <= 0:
            raise ValueError("invalid fragment payload size: {}".format(max_payload))
        total = (len(payload) + max_payload - 1) // max_payload
        if total > 255:
            raise ValueError("payload too large for fragmentation: {} bytes".format(len(payload)))
        msg_id = self._next_message_id()
        queued = 0
        for index in range(total):
            start = index * max_payload
            end = start + max_payload
            part = payload[start:end]
            if len(part) == 0:
                continue
            header = bytes(
                (
                    self._FRAG_MAGIC[0],
                    self._FRAG_MAGIC[1],
                    self._FRAG_VERSION,
                    (msg_id >> 8) & 0xFF,
                    msg_id & 0xFF,
                    total,
                    index,
                )
            )
            self._enqueue_tx_frame(
                {
                    "target": target,
                    "msg_id": msg_id,
                    "index": index,
                    "total": total,
                    "data": header + part,
                }
            )
            queued += 1
        self._pump_tx_queue(source="fragment-send")
        self._log_debug(
            "fragmented queued target={} bytes={} chunks={}".format(
                self.mac_to_node_id(target), len(payload), queued
            )
        )

    def _ingest_rx_packet(self, mac, msg):
        # Some ESP-NOW ports reuse mutable buffers across irecv() calls.
        # Detach here so queued/reassembled payloads cannot be corrupted by
        # subsequent driver reads.
        if isinstance(msg, bytearray):
            msg = bytes(msg)
        elif isinstance(msg, memoryview):
            msg = bytes(msg)
        frag = self._parse_fragment(msg)
        if frag is None:
            return msg
        if frag is False:
            return None

        msg_id, total, index, part = frag
        key = (mac, msg_id)
        now = self._now_ms()
        entry = self._fragment_buffers.get(key)
        if entry is None or entry["total"] != total:
            entry = {"total": total, "parts": {}, "updated_ms": now}
            self._fragment_buffers[key] = entry
        entry["parts"][index] = part
        entry["updated_ms"] = now

        if len(entry["parts"]) < total:
            return None

        assembled = bytearray()
        for i in range(total):
            if i not in entry["parts"]:
                self._log_error(
                    "rx fragment missing peer={} id={} missing_idx={}".format(
                        self.mac_to_node_id(mac), msg_id, i
                    )
                )
                return None
            assembled.extend(entry["parts"][i])
        del self._fragment_buffers[key]
        return bytes(assembled)

    def _parse_fragment(self, msg):
        if len(msg) < self._FRAG_HEADER_BYTES:
            return None
        if msg[0:2] != self._FRAG_MAGIC:
            return None
        if msg[2] != self._FRAG_VERSION:
            self._log_error("dropping fragment with unsupported version={}".format(msg[2]))
            return False

        msg_id = (msg[3] << 8) | msg[4]
        total = msg[5]
        index = msg[6]
        if total == 0 or index >= total:
            self._log_error("dropping malformed fragment id={} idx={}/{}".format(msg_id, index, total))
            return False
        return msg_id, total, index, msg[self._FRAG_HEADER_BYTES:]

    def _expire_fragment_buffers(self):
        fragment_buffers = getattr(self, "_fragment_buffers", None)
        if not fragment_buffers:
            return
        if getattr(self, "_fragment_expiry_running", False):
            return
        self._fragment_expiry_running = True
        try:
            now = self._now_ms()
            stale = []
            for key, entry in tuple(fragment_buffers.items()):
                if self._ticks_diff(now, entry["updated_ms"]) > self._FRAG_REASSEMBLY_TIMEOUT_MS:
                    stale.append(key)
            for key in stale:
                fragment_buffers.pop(key, None)
            if stale:
                self._log_debug("dropped {} stale fragment buffer(s)".format(len(stale)))
        finally:
            self._fragment_expiry_running = False

    def _now_ms(self):
        if hasattr(time, "ticks_ms"):
            return time.ticks_ms()
        return int(time.time() * 1000)

    def _ticks_diff(self, newer, older):
        if hasattr(time, "ticks_diff"):
            return time.ticks_diff(newer, older)
        return newer - older

    def _init_rx_event(self):
        """Create async event primitive when available on current runtime."""
        try:
            self._rx_event = asyncio.Event()
        except Exception:
            self._rx_event = None

    def _signal_rx_event(self):
        """Wake run loop when IRQ has queued data."""
        if self._rx_event is None:
            return
        try:
            self._rx_event.set()
        except Exception:
            pass

    async def _wait_for_rx(self, poll_ms):
        """Wait for queued data/event, otherwise sleep for poll interval."""
        self._pump_tx_queue(source="wait-loop")
        if self._rx_queue:
            return
        if self._rx_event is not None:
            try:
                # Do not block forever on IRQ event; if IRQ callbacks are not
                # delivered on this port, timed-out waits allow recv polling.
                if hasattr(asyncio, "wait_for_ms"):
                    await asyncio.wait_for_ms(self._rx_event.wait(), poll_ms)
                    self._rx_event.clear()
                    return
                if hasattr(asyncio, "wait_for"):
                    await asyncio.wait_for(self._rx_event.wait(), poll_ms / 1000.0)
                    self._rx_event.clear()
                    return
            except Exception:
                pass
        try:
            await asyncio.sleep_ms(poll_ms)
        except AttributeError:
            await asyncio.sleep(poll_ms / 1000.0)
        self._pump_tx_queue(source="wait-sleep")

    def get_runtime_stats(self):
        return {
            "rx_queue_len": len(self._rx_queue),
            "rx_queue_max_seen": self._max_rx_queue_seen,
            "irq_count": self._irq_count,
            "irq_packets_drained": self._irq_packets_drained,
            "tx_queue_len": len(self._tx_queue),
            "tx_inflight": self._tx_inflight is not None,
            "tx_queued_frames": self._tx_queued_frames,
            "tx_sent_frames": self._tx_sent_frames,
            "tx_ack_ok": self._tx_ack_ok,
            "tx_ack_fail": self._tx_ack_fail,
            "tx_ack_timeout": self._tx_ack_timeout,
        }

    def _enqueue_tx_frame(self, frame):
        if len(self._tx_queue) >= self._TX_QUEUE_MAX_FRAMES:
            dropped = self._tx_queue.pop(0)
            self._log_error(
                "tx queue overflow dropping id={} idx={}/{}".format(
                    dropped.get("msg_id"), dropped.get("index"), dropped.get("total")
                )
            )
        self._tx_queue.append(frame)
        self._tx_queued_frames += 1

    def _pump_tx_queue(self, source):
        # Update completion status for prior async send.
        self._update_tx_completion()

        # Timeout protection in case send callbacks are never delivered.
        if self._tx_inflight is not None:
            elapsed = self._ticks_diff(self._now_ms(), self._tx_inflight["sent_ms"])
            if elapsed > self._TX_ACK_TIMEOUT_MS:
                timed_out = self._tx_inflight
                self._tx_inflight = None
                self._tx_ack_timeout += 1
                self._log_error(
                    "tx timeout id={} idx={}/{} elapsed_ms={}".format(
                        timed_out["msg_id"], timed_out["index"], timed_out["total"], elapsed
                    )
                )
            else:
                return

        if not self._tx_queue:
            return

        frame = self._tx_queue[0]
        try:
            self.espnow.send(frame["target"], frame["data"], False)
        except Exception as exc:
            self._log_error(
                "tx send failed id={} idx={}/{} err={}".format(
                    frame.get("msg_id"), frame.get("index"), frame.get("total"), exc
                )
            )
            # Drop on hard error so queue can continue draining.
            self._tx_queue.pop(0)
            return

        self._tx_queue.pop(0)
        self._tx_sent_frames += 1
        self._tx_inflight = {
            "msg_id": frame["msg_id"],
            "index": frame["index"],
            "total": frame["total"],
            "sent_ms": self._now_ms(),
        }
        self._log_debug(
            "tx queued->sent id={} idx={}/{} qlen={} src={}".format(
                frame["msg_id"], frame["index"], frame["total"], len(self._tx_queue), source
            )
        )

    def _update_tx_completion(self):
        stats = self.get_stats()
        resp = int(stats[1])
        fail = int(stats[2])
        d_resp = resp - self._tx_stat_tx_responses
        d_fail = fail - self._tx_stat_tx_failures
        if d_resp < 0:
            d_resp = 0
        if d_fail < 0:
            d_fail = 0

        if d_resp == 0 and d_fail == 0:
            return

        self._tx_stat_tx_responses = resp
        self._tx_stat_tx_failures = fail
        if self._tx_inflight is not None:
            done = self._tx_inflight
            self._tx_inflight = None
            if d_fail > 0:
                self._tx_ack_fail += 1
                self._log_error(
                    "tx ack fail id={} idx={}/{} resp_delta={} fail_delta={}".format(
                        done["msg_id"], done["index"], done["total"], d_resp, d_fail
                    )
                )
            else:
                self._tx_ack_ok += 1

    def _configure_wifi_for_espnow(self, channel):
        """Set deterministic STA settings used by ESP-NOW."""
        requested_channel = int(channel)
        sta_connected = False
        try:
            sta_connected = bool(self.wlan_sta.isconnected())
        except Exception:
            sta_connected = False

        if sta_connected:
            current_channel = self._read_wifi_channel()
            try:
                current_channel_int = int(current_channel)
            except Exception:
                current_channel_int = None
            if current_channel_int == requested_channel:
                self._log_info(
                    "wifi STA already connected; keeping channel {}".format(
                        current_channel_int
                    )
                )
                return
            self._log_info(
                "wifi STA connected on channel {}; keeping existing channel".format(
                    current_channel_int if current_channel_int is not None else current_channel
                )
            )
            self._log_error(
                "Refusing channel switch while STA is connected to keep network reachable. "
                "Set up STA on requested channel {} before startup or pass an unconnected mesh".format(
                    requested_channel,
                )
            )
            return

        try:
            pm_none = getattr(self.wlan_sta, "PM_NONE", None)
            if pm_none is None:
                pm_none = getattr(network.WLAN, "PM_NONE", None)
            if pm_none is not None:
                self.wlan_sta.config(pm=pm_none)
        except Exception as exc:
            self._log_debug("wifi pm config unavailable err={}".format(exc))
        try:
            self.wlan_sta.config(channel=requested_channel)
            self._log_info("wifi channel configured to {}".format(requested_channel))
        except Exception as exc:
            self._log_error("wifi channel config failed channel={} err={}".format(requested_channel, exc))

    def _ensure_requested_channel(self, requested_channel):
        try:
            requested_channel = int(requested_channel)
        except Exception:
            return
        effective_channel = self._effective_channel
        try:
            effective_channel = int(effective_channel)
        except Exception:
            raise RuntimeError(
                "ESP-NOW channel unavailable requested={} effective={}".format(
                    requested_channel,
                    effective_channel,
                )
            )
        if effective_channel != requested_channel:
            raise RuntimeError(
                "ESP-NOW channel mismatch requested={} effective={}".format(
                    requested_channel,
                    effective_channel,
                )
            )

    def _read_wifi_channel(self):
        try:
            return self.wlan_sta.config("channel")
        except Exception:
            return "unknown"

    def _init_logger(self):
        if logging is None:
            return
        try:
            self._logger = logging.getLogger("dnet.LighthouseMesh")
            if hasattr(self._logger, "setLevel"):
                self._logger.setLevel(logging.DEBUG if self._debug else logging.INFO)
        except Exception:
            self._logger = None

    def _log_debug(self, msg):
        if self._logger is not None and hasattr(self._logger, "debug"):
            self._logger.debug(msg)
            return
        if self._debug:
            print("DEBUG LighthouseMesh: {}".format(msg))

    def _log_info(self, msg):
        if self._logger is not None and hasattr(self._logger, "info"):
            self._logger.info(msg)
            return
        print("INFO LighthouseMesh: {}".format(msg))

    def _log_error(self, msg):
        if self._logger is not None and hasattr(self._logger, "error"):
            self._logger.error(msg)
            return
        print("ERROR LighthouseMesh: {}".format(msg))
