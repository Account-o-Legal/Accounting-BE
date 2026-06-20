from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    status_code = 500

    def __init__(self, message: str):
        self.message = message


class NotFoundError(AppException):
    status_code = 404


class ValidationError(AppException):
    status_code = 422


class UnauthorizedError(AppException):
    status_code = 401


class UnbalancedEntryError(AppException):
    """Raised when a journal entry's debits != credits. Never silently fix."""

    status_code = 422


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def handle_app_exception(_: Request, exc: AppException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})
