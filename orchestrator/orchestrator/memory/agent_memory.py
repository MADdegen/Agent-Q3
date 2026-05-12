"""Agent memory system — conversation history + reasoning traces.

Stores:
- Conversation history (user/assistant messages)
- Reasoning traces (agent decisions, tool calls, results)
- Agent state (active agents, spawned agents, synthesis results)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
import json
import structlog
from sqlalchemy import (
    Column, String, Text, DateTime, Integer, Boolean, JSON,
    create_engine, ForeignKey
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.pool import NullPool

from ..config import settings

logger = structlog.get_logger(__name__)
Base = declarative_base()


class ConversationMessage(Base):
    """Conversation message (user or assistant)."""
    __tablename__ = "conversation_messages"

    id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    model_used = Column(String, nullable=True)  # "reasoner" | "coder" | "support"
    tokens_used = Column(Integer, nullable=True)

    conversation = relationship("Conversation", back_populates="messages")


class ReasoningTrace(Base):
    """Reasoning trace — agent decision, tool call, result."""
    __tablename__ = "reasoning_traces"

    id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    agent = Column(String, nullable=False)  # "reasoner" | "coder" | "support"
    decision = Column(Text, nullable=False)  # What the agent decided to do
    tool_name = Column(String, nullable=True)  # Tool executed (if any)
    tool_params = Column(JSON, nullable=True)  # Tool parameters
    tool_result = Column(JSON, nullable=True)  # Tool result
    reasoning = Column(Text, nullable=True)  # Agent's reasoning
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    success = Column(Boolean, default=True)

    conversation = relationship("Conversation", back_populates="traces")


class AgentSpawn(Base):
    """Record of spawned sub-agents."""
    __tablename__ = "agent_spawns"

    id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    parent_agent = Column(String, nullable=False)  # "support" (Kimi)
    spawned_agents = Column(JSON, nullable=False)  # ["reasoner", "coder"]
    task = Column(Text, nullable=False)
    synthesis = Column(Text, nullable=True)  # Kimi's synthesis of results
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    conversation = relationship("Conversation", back_populates="spawns")


class Conversation(Base):
    """Conversation session."""
    __tablename__ = "conversations"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    title = Column(String, nullable=True)
    metadata = Column(JSON, nullable=True)

    messages = relationship("ConversationMessage", back_populates="conversation", cascade="all, delete-orphan")
    traces = relationship("ReasoningTrace", back_populates="conversation", cascade="all, delete-orphan")
    spawns = relationship("AgentSpawn", back_populates="conversation", cascade="all, delete-orphan")


class AgentMemoryStore:
    """Memory store for agent conversations and reasoning traces."""

    def __init__(self, db_url: str = None):
        self.db_url = db_url or settings.database_url
        self.engine = create_engine(
            self.db_url,
            poolclass=NullPool,  # Async-safe
            echo=False,
        )
        self.SessionLocal = sessionmaker(bind=self.engine)
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist."""
        try:
            Base.metadata.create_all(self.engine)
            logger.info("agent memory database initialized")
        except Exception as e:
            logger.error("failed to initialize agent memory db", error=str(e))

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        model_used: str = None,
        tokens_used: int = None,
    ) -> ConversationMessage:
        """Add a message to conversation."""
        session = self.SessionLocal()
        try:
            msg = ConversationMessage(
                id=f"{conversation_id}-{datetime.utcnow().timestamp()}",
                conversation_id=conversation_id,
                role=role,
                content=content,
                model_used=model_used,
                tokens_used=tokens_used,
            )
            session.add(msg)
            session.commit()
            logger.info("message added", conversation_id=conversation_id, role=role)
            return msg
        except Exception as e:
            session.rollback()
            logger.error("failed to add message", error=str(e))
            raise
        finally:
            session.close()

    def add_reasoning_trace(
        self,
        conversation_id: str,
        agent: str,
        decision: str,
        tool_name: str = None,
        tool_params: dict = None,
        tool_result: dict = None,
        reasoning: str = None,
        success: bool = True,
    ) -> ReasoningTrace:
        """Add a reasoning trace."""
        session = self.SessionLocal()
        try:
            trace = ReasoningTrace(
                id=f"{conversation_id}-trace-{datetime.utcnow().timestamp()}",
                conversation_id=conversation_id,
                agent=agent,
                decision=decision,
                tool_name=tool_name,
                tool_params=tool_params,
                tool_result=tool_result,
                reasoning=reasoning,
                success=success,
            )
            session.add(trace)
            session.commit()
            logger.info("reasoning trace added", agent=agent, tool=tool_name)
            return trace
        except Exception as e:
            session.rollback()
            logger.error("failed to add reasoning trace", error=str(e))
            raise
        finally:
            session.close()

    def add_agent_spawn(
        self,
        conversation_id: str,
        parent_agent: str,
        spawned_agents: list[str],
        task: str,
        synthesis: str = None,
    ) -> AgentSpawn:
        """Record a multi-agent spawn."""
        session = self.SessionLocal()
        try:
            spawn = AgentSpawn(
                id=f"{conversation_id}-spawn-{datetime.utcnow().timestamp()}",
                conversation_id=conversation_id,
                parent_agent=parent_agent,
                spawned_agents=spawned_agents,
                task=task,
                synthesis=synthesis,
            )
            session.add(spawn)
            session.commit()
            logger.info("agent spawn recorded", parent=parent_agent, spawned=spawned_agents)
            return spawn
        except Exception as e:
            session.rollback()
            logger.error("failed to record agent spawn", error=str(e))
            raise
        finally:
            session.close()

    def get_conversation_history(self, conversation_id: str, limit: int = 50) -> list[dict]:
        """Get conversation message history."""
        session = self.SessionLocal()
        try:
            messages = session.query(ConversationMessage)\
                .filter(ConversationMessage.conversation_id == conversation_id)\
                .order_by(ConversationMessage.timestamp.desc())\
                .limit(limit)\
                .all()
            return [
                {
                    "role": m.role,
                    "content": m.content,
                    "model": m.model_used,
                    "timestamp": m.timestamp.isoformat(),
                }
                for m in reversed(messages)
            ]
        finally:
            session.close()

    def get_reasoning_traces(self, conversation_id: str, limit: int = 50) -> list[dict]:
        """Get reasoning traces for a conversation."""
        session = self.SessionLocal()
        try:
            traces = session.query(ReasoningTrace)\
                .filter(ReasoningTrace.conversation_id == conversation_id)\
                .order_by(ReasoningTrace.timestamp.desc())\
                .limit(limit)\
                .all()
            return [
                {
                    "agent": t.agent,
                    "decision": t.decision,
                    "tool": t.tool_name,
                    "reasoning": t.reasoning,
                    "success": t.success,
                    "timestamp": t.timestamp.isoformat(),
                }
                for t in reversed(traces)
            ]
        finally:
            session.close()

    def get_agent_spawns(self, conversation_id: str) -> list[dict]:
        """Get agent spawn records."""
        session = self.SessionLocal()
        try:
            spawns = session.query(AgentSpawn)\
                .filter(AgentSpawn.conversation_id == conversation_id)\
                .order_by(AgentSpawn.timestamp.desc())\
                .all()
            return [
                {
                    "parent": s.parent_agent,
                    "spawned": s.spawned_agents,
                    "task": s.task,
                    "synthesis": s.synthesis,
                    "timestamp": s.timestamp.isoformat(),
                }
                for s in reversed(spawns)
            ]
        finally:
            session.close()

    def create_conversation(self, user_id: str = None, title: str = None) -> str:
        """Create a new conversation."""
        session = self.SessionLocal()
        try:
            conv_id = f"conv-{datetime.utcnow().timestamp()}"
            conv = Conversation(
                id=conv_id,
                user_id=user_id,
                title=title,
            )
            session.add(conv)
            session.commit()
            logger.info("conversation created", conversation_id=conv_id)
            return conv_id
        except Exception as e:
            session.rollback()
            logger.error("failed to create conversation", error=str(e))
            raise
        finally:
            session.close()


# Singleton
_memory_store: Optional[AgentMemoryStore] = None


def get_memory_store() -> AgentMemoryStore:
    """Get or create memory store."""
    global _memory_store
    if _memory_store is None:
        _memory_store = AgentMemoryStore()
    return _memory_store
