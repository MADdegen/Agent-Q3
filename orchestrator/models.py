"""Pydantic models and task classifier for Agent-Q3."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    model_role: Literal["reasoner", "coder", "auto"] = "auto"
    force_backend: Optional[Literal["local", "huggingface", "runpod", "openrouter"]] = None
    max_tokens: Optional[int] = None
    temperature: float = 0.7
    stream: bool = False


class TandemRequest(BaseModel):
    research_prompt: str
    code_prompt: str
    max_tokens: Optional[int] = None


CODER_SIGNALS = {
    "function", "class", "import", "install", "pip", "npm", "yarn",
    "error", "bug", "api", "sdk", "library", "package", "python",
    "typescript", "javascript", "solidity", "rust", "go", "code",
    "script", "module", "compile", "deploy", "contract", "test",
    "debug", "fix", "implement", "write", "build", "create a function",
}

REASONER_SIGNALS = {
    "research", "analyze", "analysis", "explain", "why", "how does",
    "compare", "summarize", "market", "prediction", "conviction",
    "sentiment", "study", "report", "paper", "algorithm", "strategy",
    "deep dive", "investigate", "evaluate", "assess", "what is",
}


def classify_task(messages: List[Message]) -> Literal["reasoner", "coder"]:
    """Classify a conversation as requiring the Coder or Reasoner agent."""
    text = " ".join(m.content.lower() for m in messages[-3:])
    coder_score    = sum(1 for s in CODER_SIGNALS    if s in text)
    reasoner_score = sum(1 for s in REASONER_SIGNALS if s in text)
    return "reasoner" if reasoner_score > coder_score else "coder"
