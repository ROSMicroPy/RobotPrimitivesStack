"""
Example: hook MessagingEndpoint to LighthouseMesh using composition claims and events.
"""

from dnet.messaging import MessagingEndpoint, Schema, build_mount_claim, example_partial_arm
from dnet.signalling.LighthouseMesh import LighthouseMesh


def build_endpoint():
    """Create a ready-to-run mesh + messaging endpoint pair."""
    mesh = LighthouseMesh(use_broadcast=True)
    transport = mesh.create_transport(default_peer="broadcast")
    endpoint = MessagingEndpoint(node_id=mesh.node_id, transport=transport)
    return mesh, endpoint


async def run():
    """Demo loop that broadcasts a mounted-joint claim and a sample event."""
    mesh, endpoint = build_endpoint()
    shoulder = example_partial_arm().subunits[0]
    claim = build_mount_claim(shoulder)

    endpoint.send_announce(
        peer_id="broadcast",
        ttl_ms=3000,
        part_kind=Schema.PART_JOINT,
        firmware="0.1.0",
    )
    endpoint.send_claim(
        peer_id="broadcast",
        ttl_ms=3000,
        claim_id="{}:{}".format(mesh.node_id, claim["loc"]["id"]),
        part=claim["part"],
        location=claim["loc"],
        state=claim["state"],
    )
    endpoint.send_event(
        peer_id="broadcast",
        event_name="vision.person_detected",
        parameters={"confidence": 92, "tracking_id": "p14"},
        priority=Schema.EVENT_PRIORITY_HIGH,
        ttl_ms=1000,
    )

    def on_message(peer_id, message):
        print("message from {} -> {}".format(peer_id, message))

    await mesh.run(endpoint=endpoint, on_message=on_message, poll_ms=25)
