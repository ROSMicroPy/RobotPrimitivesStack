# Meshnet

`rpstack.meshnet:EspNowTransport` is RPStack's asynchronous ESP-NOW signal
adapter. It uses the LighthouseMesh prototype's 240-byte frames and seven-byte
fragment header (`7f 4d`, version 1, two-byte ID, count, index). The signal
payload is the new RPStack envelope; legacy dnet events are not wire-compatible.

Reception polls `irecv(0)` and copies reusable buffers. Transmission queues
frames with `send(peer, frame, False)` and yields between them; broadcast
transmission has no end-to-end acknowledgement. No Python worker thread,
singleton, IRQ callback or telemetry package is required.

Reassembly is keyed by peer/message ID, rejects conflicting fragments, accepts
out-of-order fragments, and defaults to eight pending messages of at most 2048
bytes each. Three-second expiry is measured from the first fragment; duplicates
do not extend it. Bounds include per-frame checks and total assembled bytes.
Configuration: `channel`, `poll_ms` (10), `max_bytes` (2048), `max_pending` (8),
`timeout_ms` (3000). Keep the transport and signal bus byte limits consistent.

The adapter activates STA Wi-Fi but does not shut down the shared Wi-Fi interface.
An explicit channel must match an already-connected access point. If omitted,
the current Wi-Fi channel is preserved. Mesh peers must share a radio channel.
Use `relay: true` in the manifest for bounded broadcast relaying; direct
broadcast alone reaches only radio neighbors. See the
[signal runtime](../signals/README.md) for routing and delivery guarantees.

Host tests cover framing and the radio interface; real radio range, congestion,
channel coexistence and board memory usage still require device testing.
