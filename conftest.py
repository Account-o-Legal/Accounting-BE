import os
import pytest

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    os.environ["DATABASE_URL"] = "postgresql://localhost/test_db"
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
    os.environ["JWT_SECRET"] = "mock-secret-for-testing-purposes-only-12345"
    os.environ["S3_BUCKET"] = "test-bucket"