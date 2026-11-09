"""Carries out approved exports to destinations outside the organisation."""
import hashlib


class TransferError(Exception):
    """The destination rejected the transfer or the connection failed."""


class ExternalExecutor:
    """Copies a dataset snapshot to an external destination.

    ``uploaders`` maps a URI scheme (``s3``, ``sftp``) to a callable
    ``upload(destination, dataset_id) -> int`` returning the number of bytes sent.
    """

    def __init__(self, uploaders):
        self._uploaders = dict(uploaders)

    def export_dataset(self, request):
        uploader = self._uploaders.get(request.scheme)
        if uploader is None:
            raise TransferError(f"no uploader configured for {request.scheme}")
        sent = uploader(request.destination, request.dataset_id)
        digest = hashlib.sha256(
            f"{request.request_id}:{request.dataset_id}:{sent}".encode()
        ).hexdigest()[:16]
        return f"rcpt-{digest}"
