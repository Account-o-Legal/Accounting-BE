"""Cursor pagination — one helper, used everywhere lists are returned.

ponytail: cursor is just base64(last_id), not an encrypted/signed opaque
token. Upgrade to signed cursors only if you need to stop people from
guessing/forging cursor values for security-sensitive lists (not the case
for in-tenant paginated reads behind auth already).
"""

import base64

from pydantic import BaseModel


class Page(BaseModel):
    items: list
    next_cursor: str | None = None


def encode_cursor(last_id: str) -> str:
    return base64.urlsafe_b64encode(last_id.encode()).decode()


def decode_cursor(cursor: str) -> str:
    return base64.urlsafe_b64decode(cursor.encode()).decode()
