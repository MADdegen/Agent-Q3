"""LangGraph decision workflow for multi-agent orchestration.

Kimi uses this graph to decide:
1. Should I spawn sub-agents?
2. Which agents to spawn?
3. How to synthesize their results?
"""
from __future__ import annotations

from typing import Optional, TypedDict
import structlog
from langgraph.graph import StateGraph, END
from langgraph.types import Send

from ..config import settings
from ..router import ComputeRouter
from ..memory.agent_memory import get_memory_store

logger = structlog.get_logger(__name__)


class AgentState(TypedDict):
    """State for multi-agent workflow."""
    conversation_id: str
    query: str
    context: dict
    should_spawn: bool
    spawned_agents: list[str]
    reasoner_result: Optional[str]
    coder_result: Optional[str]
    synthesis: Optional[str]
    final_response: str


class DecisionGraph:
    """LangGraph workflow for Kimi's decision-making."""

    def __init__(self, compute_router: ComputeRouter):
        self.compute = compute_router
        self.memory = get_memory_store()
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the decision workflow."""
        graph = StateGraph(AgentState)

        # Nodes
        graph.add_node("analyze_query", self._analyze_query)
        graph.add_node("spawn_reasoner", self._spawn_reasoner)
        graph.add_node("spawn_coder", self._spawn_coder)
        graph.add_node("synthesize", self._synthesize)
        graph.add_node("single_agent", self._single_agent)

        # Edges
        graph.add_edge("analyze_query", "spawn_reasoner")
        graph.add_edge("analyze_query", "spawn_coder")
        graph.add_edge("spawn_reasoner", "synthesize")
        graph.add_edge("spawn_coder", "synthesize")
        graph.add_edge("synthesize", END)
        graph.add_edge("single_agent", END)

        # Conditional: analyze_query → spawn or single_agent
        graph.add_conditional_edges(
            "analyze_query",
            self._should_spawn,
            {
                True: "spawn_reasoner",
                False: "single_agent",
            }
        )

        graph.set_entry_point("analyze_query")
        return graph.compile()

    async def _analyze_query(self, state: AgentState) -> AgentState:
        """Analyze query complexity."""
        query = state["query"]
        complexity_indicators = [
            "research", "analyze", "investigate", "compare",
            "implement", "debug", "refactor", "optimize",
            "design", "architecture", "complex", "difficult"
        ]
        should_spawn = any(ind in query.lower() for ind in complexity_indicators)

        state["should_spawn"] = should_spawn
        logger.info("query analyzed", should_spawn=should_spawn, query=query[:100])

        # Log reasoning trace
        self.memory.add_reasoning_trace(
            conversation_id=state["conversation_id"],
            agent="support",
            decision=f"Spawn agents: {should_spawn}",
            reasoning=f"Query complexity: {query[:100]}",
        )

        return state

    def _should_spawn(self, state: AgentState) -> bool:
        """Conditional: should spawn agents?"""
        return state["should_spawn"]

    async def _spawn_reasoner(self, state: AgentState) -> AgentState:
        """Spawn Reasoner agent."""
        try:
            result = await self.compute.route(
                model_role="reasoner",
                messages=[{"role": "user", "content": state["query"]}],
                max_tokens=4096,
            )
            response = result.get("message", {}).get("content", "")
            state["reasoner_result"] = response

            # Log trace
            self.memory.add_reasoning_trace(
                conversation_id=state["conversation_id"],
                agent="reasoner",
                decision="Analyzed query",
                reasoning=response[:500],
                success=True,
            )

            logger.info("reasoner spawned", query=state["query"][:100])
            return state
        except Exception as e:
            logger.error("reasoner spawn failed", error=str(e))
            state["reasoner_result"] = f"Error: {str(e)}"
            return state

    async def _spawn_coder(self, state: AgentState) -> AgentState:
        """Spawn Coder agent."""
        try:
            result = await self.compute.route(
                model_role="coder",
                messages=[{"role": "user", "content": state["query"]}],
                max_tokens=4096,
            )
            response = result.get("message", {}).get("content", "")
            state["coder_result"] = response

            # Log trace
            self.memory.add_reasoning_trace(
                conversation_id=state["conversation_id"],
                agent="coder",
                decision="Implemented solution",
                reasoning=response[:500],
                success=True,
            )

            logger.info("coder spawned", query=state["query"][:100])
            return state
        except Exception as e:
            logger.error("coder spawn failed", error=str(e))
            state["coder_result"] = f"Error: {str(e)}"
            return state

    async def _synthesize(self, state: AgentState) -> AgentState:
        """Kimi synthesizes Reasoner + Coder results."""
        synthesis_prompt = f"""
You are Kimi, a hybrid reasoning model. Two agents have analyzed this task:

TASK: {state['query']}

REASONER ANALYSIS:
{state.get('reasoner_result', 'No response')}

CODER ANALYSIS:
{state.get('coder_result', 'No response')}

Synthesize these analyses into a coherent, actionable response.
"""
        try:
            result = await self.compute.route(
                model_role="support",
                messages=[{"role": "user", "content": synthesis_prompt}],
                max_tokens=2048,
            )
            synthesis = result.get("message", {}).get("content", "")
            state["synthesis"] = synthesis
            state["final_response"] = synthesis

            # Log spawn record
            self.memory.add_agent_spawn(
                conversation_id=state["conversation_id"],
                parent_agent="support",
                spawned_agents=["reasoner", "coder"],
                task=state["query"],
                synthesis=synthesis[:500],
            )

            logger.info("synthesis complete")
            return state
        except Exception as e:
            logger.error("synthesis failed", error=str(e))
            state["final_response"] = f"Error: {str(e)}"
            return state

    async def _single_agent(self, state: AgentState) -> AgentState:
        """Kimi handles query alone."""
        try:
            result = await self.compute.route(
                model_role="support",
                messages=[{"role": "user", "content": state["query"]}],
                max_tokens=2048,
            )
            response = result.get("message", {}).get("content", "")
            state["final_response"] = response

            # Log trace
            self.memory.add_reasoning_trace(
                conversation_id=state["conversation_id"],
                agent="support",
                decision="Handled query alone",
                reasoning=response[:500],
                success=True,
            )

            logger.info("single agent mode")
            return state
        except Exception as e:
            logger.error("single agent failed", error=str(e))
            state["final_response"] = f"Error: {str(e)}"
            return state

    async def invoke(self, state: AgentState) -> AgentState:
        """Run the decision graph."""
        return await self.graph.ainvoke(state)


# Singleton
_decision_graph: Optional[DecisionGraph] = None


def get_decision_graph(compute_router: ComputeRouter) -> DecisionGraph:
    """Get or create decision graph."""
    global _decision_graph
    if _decision_graph is None:
        _decision_graph = DecisionGraph(compute_router)
    return _decision_graph

