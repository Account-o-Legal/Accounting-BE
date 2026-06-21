"""Tracks every uploaded file's scan lifecycle. This is the missing piece
that makes virus scanning actually matter: scanning a file is useless if
nothing checks the result before handing out a readable URL. Any code
path that wants to serve a file back (receipt downloads, future invoice
attachments, etc.) must check scan_status == "clean" here first — not
just upload_file, every reader.

scan_status values:
  pending   - uploaded to the quarantine prefix, scan job queued
  clean     - scanned, no threat found, moved to its real key, readable
  infected  - scanned, threat found, object deleted from S3, never readable
  error     - scan itself failed (clamd unreachable, etc.) — treated the
              same as infected for read-gating purposes: fail closed, not
              open, when scanning couldn't complete.
"""

from sqlmodel import Field, SQLModel

from app.db.mixins import TenantMixin, TimestampMixin, ULIDMixin


class FileUpload(ULIDMixin, TenantMixin, TimestampMixin, SQLModel, table=True):
    __tablename__ = "file_uploads"

    original_filename: str
    quarantine_key: str  # S3 key under the quarantine/ prefix, always set
    final_key: str | None = None  # S3 key once moved out of quarantine; only set once clean
    scan_status: str = Field(default="pending")
    scan_message: str | None = None  # clamav's signature name on infected, or error detail