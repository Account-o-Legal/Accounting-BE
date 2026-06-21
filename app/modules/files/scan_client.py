"""Thin wrapper around aioclamd's ClamdAsyncClient.

ponytail: this indirection layer is deliberate, not over-engineering —
it means scan_worker.py and its test don't import aioclamd directly, so
swapping clients later (or mocking in tests) only touches this one file.
For a single external dependency this thin, that's normally not worth
doing, but antivirus-engine vendor lock-in is exactly the kind of thing
worth keeping swappable.

I could not get a fully confirmed current PyPI version number for
aioclamd via search at the time this was written (its PyPI page returned
a JS-rendered page, not parseable version data) — check
https://pypi.org/project/aioclamd/ yourself and pin requirements.txt to
whatever's current before relying on this in CI/production.
"""

from aioclamd import ClamdAsyncClient

from app.core.config import settings


class ScanResult:
    def __init__(self, is_clean: bool, signature: str | None = None, error: str | None = None):
        self.is_clean = is_clean
        self.signature = signature  # e.g. "Win.Test.EICAR_HDB-1" when infected
        self.error = error  # set when the scan itself failed (clamd unreachable, etc.)


async def scan_bytes(data: bytes) -> ScanResult:
    """Streams data to clamd over TCP via INSTREAM and interprets the
    result. Fails closed: if clamd can't be reached or returns something
    unexpected, this returns is_clean=False with an error set — callers
    must treat that the same as "infected" for read-gating purposes (see
    FileUpload.scan_status's "error" state and its docstring).
    """
    client = ClamdAsyncClient(settings.clamav_host, settings.clamav_port)
    try:
        result = await client.instream(data)
    except Exception as exc:  # noqa: BLE001 — deliberately broad: any
        # failure to reach/use clamd must fail closed, not propagate as
        # an unhandled exception that might leave a file un-gated.
        return ScanResult(is_clean=False, error=str(exc))

    # aioclamd's response shape: {'stream': ('OK', None)} or
    # {'stream': ('FOUND', '<signature name>')}
    status, signature = result.get("stream", (None, None))
    if status == "OK":
        return ScanResult(is_clean=True)
    elif status == "FOUND":
        return ScanResult(is_clean=False, signature=signature)
    else:
        return ScanResult(is_clean=False, error=f"Unexpected clamd response: {result}")