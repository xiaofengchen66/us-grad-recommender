from __future__ import annotations

from typing import Iterator

from sqlalchemy.orm import Session

from us_grad_recommender.db import get_session_factory


def get_db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
