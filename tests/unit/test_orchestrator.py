"""Unit tests for Agent-Q3 orchestrator — classifier, router, schema."""
from __future__ import annotations

from orchestrator.config import Settings
from orchestrator.models import ChatRequest, Message, classify_task


def msg(content: str, role: str = "user") -> Message:
    return Message(role=role, content=content)


class TestClassifier:
    def test_code_prompt_routes_to_coder(self):
        msgs = [msg("write a python function to fetch data from an API")]
        assert classify_task(msgs) == "coder"

    def test_reasoning_prompt_routes_to_reasoner(self):
        msgs = [msg("analyze the market sentiment for prediction markets")]
        assert classify_task(msgs) == "reasoner"

    def test_solidity_routes_to_coder(self):
        msgs = [msg("write a Solidity ERC-20 contract with 1.88% fee logic")]
        assert classify_task(msgs) == "coder"

    def test_research_routes_to_reasoner(self):
        msgs = [msg("research the best approach for a prediction market oracle resolution strategy")]
        assert classify_task(msgs) == "reasoner"

    def test_default_is_coder(self):
        msgs = [msg("hello")]
        assert classify_task(msgs) == "coder"


class TestSettings:
    def test_defaults(self):
        s = Settings()
        assert s.reasoner_model == "gemma4:e4b-instruct-q4_K_M"
        assert s.coder_model == "qwen3.5:4b-instruct-q4_K_M"
        assert s.local_weight == 60
        assert s.hf_weight == 25
        assert s.runpod_weight == 15
        assert s.compute_strategy == "round_robin"

    def test_weights_sum_to_100(self):
        s = Settings()
        assert s.local_weight + s.hf_weight + s.runpod_weight == 100


class TestChatRequest:
    def test_default_role_is_auto(self):
        req = ChatRequest(messages=[msg("test")])
        assert req.model_role == "auto"

    def test_force_backend_optional(self):
        req = ChatRequest(messages=[msg("test")], force_backend=None)
        assert req.force_backend is None
