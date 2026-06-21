"""S3-compatible file storage with mandatory virus scanning.

Upload is async: the file lands in a quarantine/ prefix immediately, a
FileUpload row is created with scan_status="pending", and a scan job is
enqueued. The response returns the file's id, not a usable URL — nothing
is downloadable until the scan completes and comes back clean. See
workers/scan_worker.py for the scan itself, and the download endpoint
below for the read-side gate that makes the scan actually matter.
"""

import uuid

import boto3
from fastapi import APIRouter, UploadFile
from sqlmodel import select

from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.dependencies import ActiveWorkspace, DbSession
from app.modules.files.models import FileUpload

router = APIRouter()

_s3 = boto3.client(
    "s3",
    endpoint_url=settings.s3_endpoint,
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
)

@router.post("/upload")
async def upload_file(file: UploadFile, workspace: ActiveWorkspace, db: DbSession):
    quarantine_key = f"quarantine/{workspace}/{uuid.uuid4()}-{file.filename}"
    _s3.upload_fileobj(file.file, settings.s3_bucket, quarantine_key)

    upload = FileUpload(
        tenant_id=workspace,
        original_filename=file.filename,
        quarantine_key=quarantine_key,
        scan_status="pending",
    )
    db.add(upload)
    await db.commit()
    await db.refresh(upload)

    from app.workers.main import import_queue  # ponytail: lazy import, see banking/router.py for the same pattern
    await import_queue.enqueue_job("scan_file", upload.id)

    return {"file_id": upload.id, "status": "pending"}


@router.get("/{file_id}")
async def get_file_download_url(file_id: str, workspace: ActiveWorkspace, db: DbSession):
    """Returns a presigned download URL — but only once the file has been
    scanned and come back clean. This is the gate that makes scanning
    actually mean something: scan_worker.py running is not protection by
    itself if nothing here checks its result before handing out a URL.
    """
    upload = (
        await db.exec(
            select(FileUpload).where(FileUpload.id == file_id, FileUpload.tenant_id == workspace)
        )
    ).first()
    if not upload:
        raise NotFoundError("File not found")

    if upload.scan_status == "pending":
        return {"file_id": file_id, "status": "pending", "message": "Scan in progress"}
    if upload.scan_status in ("infected", "error"):
        # ponytail: same response shape for infected and error — a caller
        # checking scan results doesn't need (and arguably shouldn't be
        # told) the difference between "we found a virus" and "we
        # couldn't finish scanning"; either way the file isn't available,
        # and that's the only fact that matters to a non-admin caller.
        raise ValidationError(
            "This file is not available for download (failed virus scan)"
        )

    url = _s3.generate_presigned_url(
        "get_object", Params={"Bucket": settings.s3_bucket, "Key": upload.final_key}, ExpiresIn=3600
    )
    return {"file_id": file_id, "status": "clean", "url": url}