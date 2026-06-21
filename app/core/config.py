import json
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

JURISDICTIONS_DIR = Path(__file__).resolve().parents[2] / "config" / "jurisdictions"


class Settings(BaseSettings):
    app_name: str = "accounting-software"
    env: str = "local"

    database_url: str
    redis_url: str
    jwt_secret: str
    s3_bucket: str
    s3_endpoint: str | None = None  # MinIO in dev, unset = real AWS
    # MinIO/S3 credentials. Optional because real AWS deployments typically
    # use IAM roles instead of static keys — only required when s3_endpoint
    # points at MinIO in local/dev.
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None

    anthropic_api_key: str | None = None  # ai module, narrow usage only

    clamav_host: str = "clamav"  # service name in docker-compose, override for local non-compose dev
    clamav_port: int = 3310

    default_jurisdiction: str = "pk"

    class Config:
        env_file = ".env"


settings = Settings()


@lru_cache(maxsize=8)
def load_jurisdiction(code: str) -> dict:
    """Load a jurisdiction config pack (tax rules, CoA defaults, currency).

    This is the mechanism behind "new country = config change, not code
    change." MVP ships with pk.json only.
    """
    path = JURISDICTIONS_DIR / f"{code}.json"
    if not path.exists():
        raise FileNotFoundError(f"No jurisdiction pack for '{code}'")
    return json.loads(path.read_text())