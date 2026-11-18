import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.infrastructure.db.models import Base
from src.api.routes.analytics import (
    get_analytics_overview,
    get_analytics_tokens,
    get_analytics_qa_reports,
    get_analytics_security,
    get_analytics_approvals,
)


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_analytics_endpoints_empty_db(in_memory_db):
    ov = get_analytics_overview(None, in_memory_db)
    assert ov["total_projects"] == 0
    assert ov["tokens"]["total"] == 0
    assert ov["qa"]["total_runs"] == 0
    assert ov["security"]["total_scans"] == 0
    assert ov["approvals"]["total"] == 0

    tok = get_analytics_tokens(None, 100, in_memory_db)
    assert tok["totals"]["total_tokens"] == 0
    assert len(tok["invocations"]) == 0

    qa = get_analytics_qa_reports(None, 20, in_memory_db)
    assert len(qa["test_runs"]) == 0

    sec = get_analytics_security(None, 20, in_memory_db)
    assert len(sec["scans"]) == 0

    app = get_analytics_approvals(None, 20, in_memory_db)
    assert len(app["approvals"]) == 0
