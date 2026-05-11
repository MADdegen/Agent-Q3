"""
Models & task classifier — Agent-Q3

Classifies incoming prompts → routes to Reasoner (Gemma4-E4B) or Coder (Qwen3.5-4B)
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
import re


# ── Request / Response schemas ────────────────────────────────────────────────

class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    model_role: Optional[Literal["reasoner", "coder", "auto"]] = "auto"
    force_backend: Optional[Literal["local", "huggingface", "runpod"]] = None
    stream: bool = False
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=32768)
    system_prompt: Optional[str] = None


class ChatResponse(BaseModel):
    content: str
    role: str = "assistant"
    model_role: str
    model_used: str
    backend_used: str
    usage: Optional[dict] = None


class HealthResponse(BaseModel):
    status: str
    ollama: bool
    models_loaded: list[str]
    compute_strategy: str
    backends: dict


# ── Task classifier ───────────────────────────────────────────────────────────

# Keywords that strongly indicate CODE / FETCH tasks → Qwen3.5-4B (Coder)
CODER_SIGNALS = re.compile(
    r"\b("
    r"code|function|class|def |import |from .+ import|"
    r"python|typescript|javascript|solidity|rust|golang|"
    r"sql|query|schema|migrate|"
    r"fetch|http|api|endpoint|curl|axios|request|"
    r"bug|fix|error|exception|traceback|debug|"
    r"write .*(script|code|function|class|test)|"
    r"implement|refactor|snippet|boilerplate|"
    r"compile|build|deploy|dockerfile|yaml|json|"
    r"solidity|foundry|forge|cast|abi|erc-?20|erc-?721"
    r")\b",
    re.IGNORECASE
)

# Keywords that strongly indicate REASONING / INSTRUCT tasks → Gemma4-E4B
REASONER_SIGNALS = re.compile(
    r"\b("
    r"research|analyze|analyse|explain|compare|evaluate|"
    r"why|how does|what is|summarize|summarise|describe|"
    r"strategy|plan|roadmap|decision|recommend|advise|"
    r"think through|reason|logic|argument|thesis|"
    r"pros and cons|tradeoff|trade-off|"
    r"market|prediction|probability|sentiment|"
    r"write .*(essay|report|memo|plan|proposal)"
    r")\b",
    re.IGNORECASE
)


def classify_task(messages: list[Message]) -> Literal["reasoner", "coder"]:
    """
    Heuristic classifier: examines last user message to pick the right model.
    Coder wins on ties (faster for mixed tasks).
    """
    text = " ".join(
        m.content for m in messages if m.role in ("user", "system")
    )[-2000:]  # last 2000 chars is enough

    coder_hits    = len(CODER_SIGNALS.findall(text))
    reasoner_hits = len(REASONER_SIGNALS.findall(text))

    if coder_hits > reasoner_hits:
        return "coder"
    elif reasoner_hits > coder_hits:
        return "reasoner"
    else:
        # Tie → default to coder (Qwen3.5-4B is faster on ambiguous tasks)
        return "coder"


# ── System prompts ────────────────────────────────────────────────────────────

REASONER_SYSTEM = """You are the Reasoning Agent in the Agent-Q3 system for MAD Gambit — a prediction conviction platform on Base L2.

Your role: deep analysis, multi-step reasoning, research synthesis, strategic planning, and instructed output.
You have access to the Coder agent for any technical implementation requests.

Be concise. Lead with the answer. Use specific numbers over adjectives.
Never use: leverage, synergy, ecosystem play, unlock value, game-changing, utilize.
"""

CODER_SYSTEM = """You are the Code & Fetch Agent in the Agent-Q3 system for MAD Gambit.

Your role: write precise code, fetch data, check code correctness, debug, and produce structured file output.
Tech stack: React 18 + TypeScript, Hono/HonoX, Supabase, Solidity/Foundry, Arbitrum/Base L2, Alchemy AA-SDK.

Return working code. No filler explanations unless asked.
Prefer TypeScript for frontend/backend. Solidity for contracts. Python for scripts.
"""
