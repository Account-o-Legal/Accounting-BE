"""S3-compatible file storage. ponytail: virus scanning is a single
ClamAV-via-sidecar call planned, not built — flagging here rather than
silently skipping it, since "receipt upload" is a real attack surface
(arbitrary file upload) and this gap should be visible, not buried."""

import uuid

import boto3
from fastapi import APIRouter, UploadFile

from app.core.config import settings
from app.dependencies import ActiveWorkspace

router = APIRouter()

_s3 = boto3.client("s3", endpoint_url=settings.s3_endpoint)


@router.post("/upload")
async def upload_file(file: UploadFile, workspace: ActiveWorkspace):
    key = f"{workspace}/{uuid.uuid4()}-{file.filename}"
    # ponytail: TODO before production — route through a virus-scan step
    # (ClamAV sidecar or S3 Object Lambda) before this object is readable
    # by any other service. Not implemented yet; do not treat this upload
    # path as safe for untrusted files until it is.
    _s3.upload_fileobj(file.file, settings.s3_bucket, key)
    url = _s3.generate_presigned_url(
        "get_object", Params={"Bucket": settings.s3_bucket, "Key": key}, ExpiresIn=3600
    )
    return {"file_id": key, "url": url}
