"""OpenTelemetry tracing for agent decisions and tool execution.

Traces:
- Agent decisions
- Tool calls and results
- Multi-agent spawning
- Reasoning steps
"""
from __future__ import annotations

from typing import Optional
import structlog
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

from ..config import settings

logger = structlog.get_logger(__name__)


class AgentTracer:
    """OpenTelemetry tracer for agent orchestration."""

    def __init__(self, service_name: str = "agent-q3-orchestrator"):
        self.service_name = service_name
        self.tracer = self._init_tracer()

    def _init_tracer(self) -> trace.Tracer:
        """Initialize OpenTelemetry tracer."""
        try:
            # Jaeger exporter
            jaeger_exporter = JaegerExporter(
                agent_host_name="localhost",
                agent_port=6831,
            )

            # Tracer provider
            trace_provider = TracerProvider(
                resource=Resource.create({SERVICE_NAME: self.service_name})
            )
            trace_provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
            trace.set_tracer_provider(trace_provider)

            # Instrument libraries
            FastAPIInstrumentor().instrument()
            HTTPXClientInstrumentor().instrument()
            SQLAlchemyInstrumentor().instrument()

            logger.info("opentelemetry tracer initialized")
            return trace.get_tracer(__name__)
        except Exception as e:
            logger.warning("failed to initialize jaeger, using no-op tracer", error=str(e))
            return trace.get_tracer(__name__)

    def trace_agent_decision(
        self,
        agent: str,
        query: str,
        decision: str,
        attributes: dict = None,
    ):
        """Trace an agent decision."""
        with self.tracer.start_as_current_span(f"agent_decision_{agent}") as span:
            span.set_attribute("agent", agent)
            span.set_attribute("query", query[:200])
            span.set_attribute("decision", decision)
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, str(value))
            logger.info("agent decision traced", agent=agent, decision=decision)

    def trace_tool_execution(
        self,
        tool_name: str,
        params: dict,
        result: dict,
        success: bool = True,
    ):
        """Trace a tool execution."""
        with self.tracer.start_as_current_span(f"tool_execution_{tool_name}") as span:
            span.set_attribute("tool", tool_name)
            span.set_attribute("params", str(params)[:200])
            span.set_attribute("success", success)
            if result:
                span.set_attribute("result", str(result)[:200])
            logger.info("tool execution traced", tool=tool_name, success=success)

    def trace_multi_agent_spawn(
        self,
        parent_agent: str,
        spawned_agents: list[str],
        task: str,
    ):
        """Trace a multi-agent spawn."""
        with self.tracer.start_as_current_span("multi_agent_spawn") as span:
            span.set_attribute("parent_agent", parent_agent)
            span.set_attribute("spawned_agents", ",".join(spawned_agents))
            span.set_attribute("task", task[:200])
            logger.info("multi-agent spawn traced", parent=parent_agent, spawned=spawned_agents)

    def trace_reasoning_step(
        self,
        agent: str,
        step: str,
        reasoning: str,
    ):
        """Trace a reasoning step."""
        with self.tracer.start_as_current_span(f"reasoning_step_{agent}") as span:
            span.set_attribute("agent", agent)
            span.set_attribute("step", step)
            span.set_attribute("reasoning", reasoning[:200])
            logger.info("reasoning step traced", agent=agent, step=step)


# Singleton
_agent_tracer: Optional[AgentTracer] = None


def get_agent_tracer() -> AgentTracer:
    """Get or create agent tracer."""
    global _agent_tracer
    if _agent_tracer is None:
        _agent_tracer = AgentTracer()
    return _agent_tracer


def init_tracing():
    """Initialize tracing on app startup."""
    tracer = get_agent_tracer()
    logger.info("agent tracing initialized")
    return tracer
