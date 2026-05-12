"""Multi-agent orchestration for Agent-Q3.

Kimi (Support model) can spawn sub-agents (Reasoner, Coder) for complex tasks.
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional
import structlog

from ..config import settings
from ..router import ComputeRouter

logger = structlog.get_logger(__name__)


class MultiAgentRouter:
    """Routes requests through multi-agent orchestration."""

    def __init__(self, compute_router: ComputeRouter):
        self.compute = compute_router
        self.models = {
            "reasoner": settings.reasoner_model,
            "coder": settings.coder_model,
            "support": settings.support_model,
        }

    async def should_spawn_agents(self, task: str, context: dict) -> bool:
        """Determine if Kimi should spawn sub-agents."""
        complexity_indicators = [
            "research",
            "analyze",
            "investigate",
            "compare",
            "implement",
            "debug",
            "refactor",
            "optimize",
            "design",
            "architecture",
        ]
        task_lower = task.lower()
        return any(indicator in task_lower for indicator in complexity_indicators)

    async def spawn_reasoner(self, task: str) -> dict:
        """Spawn Reasoner agent for deep analysis."""
        try:
            result = await self.compute.route(
                model_role="reasoner",
                messages=[{"role": "user", "content": task}],
                max_tokens=4096,
            )
            return {
                "agent": "reasoner",
                "success": True,
                "response": result.get("message", {}).get("content", ""),
            }
        except Exception as e:
            logger.error("reasoner spawn failed", error=str(e))
            return {
                "agent": "reasoner",
                "success": False,
                "error": str(e),
            }

    async def spawn_coder(self, task: str) -> dict:
        """Spawn Coder agent for implementation."""
        try:
            result = await self.compute.route(
                model_role="coder",
                messages=[{"role": "user", "content": task}],
                max_tokens=4096,
            )
            return {
                "agent": "coder",
                "success": True,
                "response": result.get("message", {}).get("content", ""),
            }
        except Exception as e:
            logger.error("coder spawn failed", error=str(e))
            return {
                "agent": "coder",
                "success": False,
                "error": str(e),
            }

    async def spawn_agents(self, task: str) -> dict:
        """Spawn Reasoner + Coder in parallel."""
        reasoner_task = self.spawn_reasoner(task)
        coder_task = self.spawn_coder(task)
        reasoner_result, coder_result = await asyncio.gather(
            reasoner_task, coder_task
        )
        return {
            "spawned_agents": ["reasoner", "coder"],
            "results": {
                "reasoner": reasoner_result,
                "coder": coder_result,
            },
        }

    async def route(
        self,
        query: str,
        context: Optional[dict] = None,
        force_single_agent: bool = False,
    ) -> dict:
        """Route request through multi-agent orchestration.

        If Kimi detects a complex task, spawn Reasoner + Coder.
        Otherwise, use Kimi (Support) alone.
        """
        context = context or {}

        should_spawn = (
            not force_single_agent
            and await self.should_spawn_agents(query, context)
        )

        if should_spawn:
            logger.info("spawning sub-agents", query=query[:100])
            agent_results = await self.spawn_agents(query)

            synthesis_prompt = f"""
You are Kimi, a hybrid reasoning model. Two agents have analyzed this task:

TASK: {query}

REASONER ANALYSIS:
{agent_results['results']['reasoner'].get('response', 'No response')}

CODER ANALYSIS:
{agent_results['results']['coder'].get('response', 'No response')}

Synthesize these analyses into a coherent, actionable response.
"""
            try:
                synthesis = await self.compute.route(
                    model_role="support",
                    messages=[{"role": "user", "content": synthesis_prompt}],
                    max_tokens=2048,
                )
                return {
                    "multi_agent": True,
                    "spawned_agents": agent_results["spawned_agents"],
                    "agent_results": agent_results["results"],
                    "synthesis": synthesis.get("message", {}).get("content", ""),
                }
            except Exception as e:
                logger.error("synthesis failed", error=str(e))
                return {
                    "multi_agent": True,
                    "spawned_agents": agent_results["spawned_agents"],
                    "agent_results": agent_results["results"],
                    "error": str(e),
                }
        else:
            logger.info("single agent mode", query=query[:100])
            try:
                result = await self.compute.route(
                    model_role="support",
                    messages=[{"role": "user", "content": query}],
                    max_tokens=2048,
                )
                return {
                    "multi_agent": False,
                    "agent": "support",
                    "response": result.get("message", {}).get("content", ""),
                }
            except Exception as e:
                logger.error("support agent failed", error=str(e))
                return {
                    "multi_agent": False,
                    "agent": "support",
                    "error": str(e),
                }
