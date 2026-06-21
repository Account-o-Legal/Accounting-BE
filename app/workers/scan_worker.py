"""The job behind every file upload: pulls the quarantined object out of
S3, scans it via clamd, and resolves the FileUpload row to clean or
infected. Nothing else in the codebase should ever generate a presigned
URL for an object still sitting in the quarantine prefix — see
files/router.py's download endpoint, which checks scan_status before
returning anything.
"""

import boto3

from app.core.config import settings
from app.db.session import async_session
from app.modules.files.models import FileUpload
from app.modules.files.scan_client import scan_bytes

_s3 = boto3.client(
    "s3",
    endpoint_url=settings.s3_endpoint,
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
)


async def scan_file(ctx, file_upload_id: str) -> dict:
    async with async_session() as db:
        upload = await db.get(FileUpload, file_upload_id)
        if not upload:
            # ponytail: nothing to do if the row vanished — not raising,
            # since a retried/duplicate job for a deleted FileUpload isn't
            # an error condition worth failing the queue over.
            return {"status": "not_found"}

        obj = _s3.get_object(Bucket=settings.s3_bucket, Key=upload.quarantine_key)
        data = obj["Body"].read()

        result = await scan_bytes(data)

        if result.is_clean:
            final_key = upload.quarantine_key.replace("quarantine/", "", 1)
            _s3.copy_object(
                Bucket=settings.s3_bucket,
                CopySource={"Bucket": settings.s3_bucket, "Key": upload.quarantine_key},
                Key=final_key,
            )
            _s3.delete_object(Bucket=settings.s3_bucket, Key=upload.quarantine_key)
            upload.final_key = final_key
            upload.scan_status = "clean"
        elif result.signature:
            # Infected: delete immediately, never leave a known-bad file
            # sitting in S3 even under the quarantine prefix.
            _s3.delete_object(Bucket=settings.s3_bucket, Key=upload.quarantine_key)
            upload.scan_status = "infected"
            upload.scan_message = result.signature
        else:
            # Scan itself failed (clamd unreachable, unexpected response).
            # Fail closed: leave the object in quarantine, mark as error —
            # error is read-gated identically to infected (see
            # files/models.py), so nothing becomes readable just because
            # scanning couldn't complete.
            upload.scan_status = "error"
            upload.scan_message = result.error

        db.add(upload)
        await db.commit()

        return {"status": upload.scan_status, "file_upload_id": upload.id}