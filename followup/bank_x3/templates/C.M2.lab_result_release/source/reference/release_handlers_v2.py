"""Example bus handler on the v2 portal releases API.

Taken from the portal team's migration notes. Final and amended results both go
through ``PortalClient.release``; the receipt carries the ``release_id`` that
downstream subscribers expect on ``release.completed``.
"""
from labportal.events import RELEASE_COMPLETED, RELEASE_REQUESTED
from labportal.portal_client import ReleaseRequest


def register_release_handlers(bus, portal):
    def on_release_requested(event):
        release = event["release"]
        request = ReleaseRequest(
            patient_id=release.patient_id,
            accession=release.accession,
            kind=release.kind,
            payload={"lines": list(release.summary)},
        )
        receipt = portal.release(request)
        bus.publish(RELEASE_COMPLETED, {"accession": receipt.accession, "release_id": receipt.release_id})

    bus.subscribe(RELEASE_REQUESTED, on_release_requested)
    return on_release_requested
