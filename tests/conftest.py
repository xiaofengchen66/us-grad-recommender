from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from us_grad_recommender.models import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://xiaofeng@localhost:5432/us_grad_recommender_test"
)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    """A session bound to a connection-level transaction, rolled back after
    each test so tests never see one another's data."""
    connection = engine.connect()
    transaction = connection.begin()
    # create_savepoint: the test's own session.commit()/rollback() calls only
    # affect a SAVEPOINT, leaving the outer connection-level transaction (and
    # this fixture's rollback of it) intact. See SQLAlchemy's "Joining a
    # Session into an External Transaction" recipe.
    session_factory = sessionmaker(
        bind=connection, future=True, join_transaction_mode="create_savepoint"
    )
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
