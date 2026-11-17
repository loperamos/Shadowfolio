"""The system's jobs (the daily sync, filling due orders) run inside the app when it is deployed; their endpoints, for
a scheduler outside it, need the job secret (Authorization: Bearer <SHADOWFOLIO_JOB_TOKEN>), and are closed without
one configured, so the public cannot trigger them."""

import pytest
from fastapi.testclient import TestClient

from shadowfolio.wiring.test import build_test_app

JOBS = ["/api/sync", "/api/orders/fill"]


@pytest.mark.parametrize("path", JOBS)
def test_without_a_job_secret_configured_the_jobs_cannot_be_called(path: str) -> None:
    client = TestClient(build_test_app(job_token=None))

    response = client.post(path, headers={"Authorization": "Bearer anything"})

    assert response.status_code == 403
    assert "SHADOWFOLIO_JOB_TOKEN" in response.json()["detail"]


@pytest.mark.parametrize("path", JOBS)
@pytest.mark.parametrize(("authorization", "status"), [(None, 401), ("Bearer wrong", 401), ("Bearer the-job-secret", 200)])
def test_only_the_job_secret_calls_them(path: str, authorization: str | None, status: int) -> None:
    client = TestClient(build_test_app(job_token="the-job-secret"))

    response = client.post(path, headers={"Authorization": authorization} if authorization else {})

    assert response.status_code == status
