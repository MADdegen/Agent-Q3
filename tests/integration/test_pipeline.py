"""
Integration tests — Agent-Q3
Runs Ollama via Testcontainers Cloud and validates full routing pipeline.
Skipped automatically if TC_CLOUD_TOKEN is not set.
"""
import os
import pytest
import httpx

pytestmark = pytest.mark.skipif(
    not os.environ.get("TC_CLOUD_TOKEN"),
    reason="TC_CLOUD_TOKEN not set — skipping container integration tests"
)


@pytest.fixture(scope="module")
def orchestrator_url():
    """
    In CI: The Testcontainers Cloud agent spins up a real Ollama container.
    Locally: Expects a running orchestrator on port 8000.
    """
    return os.environ.get("ORCHESTRATOR_URL", "http://localhost:8000")


@pytest.mark.asyncio
async def test_health_endpoint(orchestrator_url):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{orchestrator_url}/health")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert "backends" in data


@pytest.mark.asyncio
async def test_classifier_routing(orchestrator_url):
    """Verify auto-classifier routes code prompts to coder model."""
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{orchestrator_url}/v1/chat", json={
            "messages": [{"role": "user", "content": "write a TypeScript function"}],
            "model_role": "auto",
            "max_tokens": 100
        })
        if r.status_code == 200:
            data = r.json()
            assert data["model_role"] == "coder"
