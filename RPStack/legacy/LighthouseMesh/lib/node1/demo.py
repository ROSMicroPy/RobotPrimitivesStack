import json

try:
    import uasyncio as asyncio
except Exception:
    import asyncio

try:
    import logging
except Exception:
    logging = None

try:
    import urandom as random
except Exception:
    import random

from dnet.messaging import MessagingEndpoint
from dnet.messaging import Schema
from dnet.signalling.LighthouseMesh import LighthouseMesh

from capability_selftest import run_selftest


PROFILE_PATH = "/lib/node1/profile.json"
ANNOUNCE_INTERVAL_S = 5
CLAIM_INTERVAL_S = 15
SENSOR_EVENT_INTERVAL_S = 1
CLAIM_TTL_MS = 20000
EVENT_TTL_MS = 2500
MESH_CHANNEL = 6


def _init_logger():
    if logging is None:
        return None
    log = logging.getLogger("node1.demo")
    if hasattr(log, "setLevel"):
        log.setLevel(logging.INFO)
    return log


LOGGER = _init_logger()


def _log_info(message):
    if LOGGER is not None and hasattr(LOGGER, "info"):
        LOGGER.info(message)
        return
    print("INFO node1.demo: {}".format(message))


def load_profile(path=PROFILE_PATH):
    with open(path, "r") as f:
        return json.load(f)


def send_announce(endpoint, profile):
    payload = endpoint.send_announce(
        peer_id="broadcast",
        ttl_ms=int(profile.get("announce_ttl_ms", CLAIM_TTL_MS)),
        part_kind=profile["part_kind"],
        firmware=profile.get("firmware"),
    )
    _log_info("broadcasted announce ({} bytes)".format(len(payload)))


def send_claim(endpoint, profile):
    payload = endpoint.send_claim(
        peer_id="broadcast",
        ttl_ms=int(profile.get("claim_ttl_ms", CLAIM_TTL_MS)),
        claim_id=profile["claim_id"],
        part=profile["part"],
        location=profile["location"],
        state=profile["state"],
    )
    _log_info("broadcasted claim {} ({} bytes)".format(profile["claim_id"], len(payload)))


def _distance_parameters(profile, sequence_no):
    sensor = profile.get("sensor", {})
    minimum_mm = int(sensor.get("min_mm", 20))
    maximum_mm = int(sensor.get("max_mm", 4000))
    quality_min = int(sensor.get("quality_min", 70))
    quality_max = int(sensor.get("quality_max", 100))
    spread = maximum_mm - minimum_mm
    if spread < 0:
        spread = 0
    distance_mm = minimum_mm + ((sequence_no * 173) % (spread + 1 if spread else 1))
    quality = quality_min + ((sequence_no * 11) % (max(quality_max - quality_min, 0) + 1))
    return {
        "sensor_id": sensor.get("id", "front_distance"),
        "distance_mm": distance_mm,
        "quality": quality,
        "unit": Schema.UNIT_MM,
        "mount": profile["location"][Schema.F_LOCATION_ID],
    }


def send_distance_event(endpoint, profile, sequence_no):
    event_name = profile.get("sensor_event_name", "sensor.distance.measured")
    payload = endpoint.send_event(
        peer_id="broadcast",
        event_name=event_name,
        parameters=_distance_parameters(profile, sequence_no),
        priority=Schema.EVENT_PRIORITY_NORMAL,
        ttl_ms=int(profile.get("event_ttl_ms", EVENT_TTL_MS)),
    )
    _log_info("broadcasted event {} ({} bytes)".format(event_name, len(payload)))


async def announce_loop(endpoint, profile):
    while True:
        send_announce(endpoint, profile)
        await asyncio.sleep(ANNOUNCE_INTERVAL_S)


async def claim_loop(endpoint, profile):
    while True:
        send_claim(endpoint, profile)
        await asyncio.sleep(CLAIM_INTERVAL_S)


async def distance_event_loop(endpoint, profile):
    sequence_no = random.randint(0, 1024)
    while True:
        send_distance_event(endpoint, profile, sequence_no)
        sequence_no += 1
        await asyncio.sleep(SENSOR_EVENT_INTERVAL_S)


def on_message(peer_id, message):
    _log_info("message from {}: {}".format(peer_id, message))


def log_capability_selftest():
    result = run_selftest()
    match_result = result.get("match_result", {})
    _log_info(
        "capability selftest profile={} matched_roles={} missing_roles={}".format(
            match_result.get("selected_profile"),
            match_result.get("matched_roles"),
            match_result.get("missing_roles"),
        )
    )


async def run():
    profile = load_profile()
    log_capability_selftest()
    _log_info(
        "demo config channel={} announce_s={} claim_s={} sensor_s={}".format(
            MESH_CHANNEL,
            ANNOUNCE_INTERVAL_S,
            CLAIM_INTERVAL_S,
            SENSOR_EVENT_INTERVAL_S,
        )
    )
    mesh = LighthouseMesh(channel=MESH_CHANNEL)
    transport = mesh.create_transport(default_peer="broadcast")
    endpoint = MessagingEndpoint(node_id=mesh.node_id, transport=transport)

    asyncio.create_task(announce_loop(endpoint, profile))
    asyncio.create_task(claim_loop(endpoint, profile))
    asyncio.create_task(distance_event_loop(endpoint, profile))
    await mesh.run(endpoint=endpoint, on_message=on_message, poll_ms=25)


if __name__ == "__main__":
    asyncio.run(run())
