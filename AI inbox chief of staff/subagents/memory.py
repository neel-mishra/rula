"""
MemoryAgent — memory extraction, scoring, expiry, and retrieval prep.
Memory scope: mailbox_specific | user_global.
Never cross-mailbox retrieval without explicit applies_to_all_mailboxes flag.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import structlog

from core.schemas.contracts import MemoryQueryResult, MemoryQueryTask, MemoryWriteResult, MemoryWriteTask
from subagents.base import BaseAgent

log = structlog.get_logger(__name__)


class MemoryAgent(BaseAgent[MemoryWriteTask, MemoryWriteResult]):
    name = "memory_agent"

    async def _execute(self, task: MemoryWriteTask) -> MemoryWriteResult:
        from sqlalchemy import select
        from core.db import get_db_session
        from core.llm.client import get_llm_client
        from core.models.feedback import FeedbackEvent
        from core.models.memory import Memory, MemoryScope, MemoryType
        from core.security.injection import get_system_prompt_preamble

        async with get_db_session() as session:
            feedback = await session.get(FeedbackEvent, task.feedback_event_id)
            if not feedback:
                raise ValueError(f"FeedbackEvent {task.feedback_event_id} not found")

            # Extract structured memory from feedback using LLM
            llm = get_llm_client()

            system_prompt = (
                get_system_prompt_preamble()
                + "\n\nExtract a persistent user preference or rule from this feedback. "
                + "Return JSON: {\n"
                + '  "memory_type": "profile|policy|style|sender",\n'
                + '  "scope": "mailbox_specific|user_global",\n'
                + '  "applies_to_all_mailboxes": false,\n'
                + '  "content": "concise rule text",\n'
                + '  "structured_data": {"rule": "...", "targets": []},\n'
                + '  "confidence": 0.0-1.0\n'
                + "}\n"
                + "scope=user_global only if the user explicitly says 'all mailboxes' or 'everywhere'."
            )

            response = await llm.complete(
                system=system_prompt,
                user=f"Feedback: {feedback.raw_content}",
                max_tokens=300,
                temperature=0.1,
                response_format="json",
            )

            import json
            parsed = json.loads(response.content)

            scope_str = parsed.get("scope", "mailbox_specific")
            scope = MemoryScope.USER_GLOBAL if scope_str == "user_global" else MemoryScope.MAILBOX_SPECIFIC
            applies_to_all = parsed.get("applies_to_all_mailboxes", False)

            # Safety: if scope is mailbox_specific, mailbox_id must be set
            mailbox_id = task.mailbox_id if scope == MemoryScope.MAILBOX_SPECIFIC else None

            try:
                mem_type = MemoryType(parsed.get("memory_type", "policy"))
            except ValueError:
                mem_type = MemoryType.POLICY

            content_text = parsed.get("content", feedback.raw_content)

            # Generate embedding for semantic retrieval
            embedding_vector = None
            try:
                from core.llm.embeddings import generate_embedding
                embedding_vector = await generate_embedding(content_text)
            except Exception as emb_exc:
                log.warning("memory.embedding_failed", error=str(emb_exc))

            memory = Memory(
                id=uuid.uuid4(),
                user_id=task.user_id,
                mailbox_id=mailbox_id,
                scope=scope,
                applies_to_all_mailboxes=applies_to_all,
                memory_type=mem_type,
                content=content_text,
                structured_data=parsed.get("structured_data", {}),
                source=task.source,
                source_feedback_id=task.feedback_event_id,
                confidence=float(parsed.get("confidence", 0.8)),
                is_active=True,
                last_reinforced_at=datetime.now(tz=timezone.utc),
            )
            if embedding_vector and hasattr(Memory, "embedding") and Memory.embedding is not None:
                memory.embedding = embedding_vector
            session.add(memory)

            # Mark feedback as processed
            feedback.processed = True
            feedback.memory_id = memory.id

            await session.flush()

            log.info(
                "memory.written",
                memory_id=str(memory.id),
                memory_type=mem_type.value,
                scope=scope.value,
                correlation_id=task.correlation_id,
            )

            return MemoryWriteResult(
                memory_id=memory.id,
                memory_type=mem_type.value,
                scope=scope.value,
                confidence=memory.confidence,
            )


class MemoryQueryAgent(BaseAgent[MemoryQueryTask, MemoryQueryResult]):
    name = "memory_query_agent"

    async def _execute(self, task: MemoryQueryTask) -> MemoryQueryResult:
        from sqlalchemy import select
        from core.db import get_db_session
        from core.models.memory import Memory, MemoryScope

        async with get_db_session() as session:
            # Try semantic search if query provided and pgvector available
            if task.query and hasattr(Memory, "embedding") and Memory.embedding is not None:
                try:
                    return await self._semantic_search(task, session)
                except Exception as exc:
                    log.warning("memory.semantic_search_fallback", error=str(exc))

            # Fallback: text-match + confidence ordering
            return await self._text_search(task, session)

    async def _semantic_search(self, task: MemoryQueryTask, session) -> MemoryQueryResult:
        from sqlalchemy import select
        from core.models.memory import Memory, MemoryScope, MemoryType
        from core.llm.embeddings import generate_embedding

        query_embedding = await generate_embedding(task.query)

        scope_filter = (
            (Memory.mailbox_id == task.mailbox_id)
            | (
                (Memory.scope == MemoryScope.USER_GLOBAL)
                & (Memory.applies_to_all_mailboxes == True)  # noqa: E712
            )
        )

        q = (
            select(Memory)
            .where(
                Memory.user_id == task.user_id,
                Memory.is_active == True,  # noqa: E712
                Memory.embedding.isnot(None),
                scope_filter,
            )
            .order_by(Memory.embedding.cosine_distance(query_embedding))
            .limit(task.top_k)
        )

        if task.memory_types:
            q = q.where(Memory.memory_type.in_([MemoryType(t) for t in task.memory_types]))

        result = await session.execute(q)
        memories = result.scalars().all()

        return MemoryQueryResult(
            memories=[
                {
                    "id": str(m.id),
                    "memory_type": m.memory_type.value,
                    "scope": m.scope.value,
                    "content": m.content,
                    "structured_data": m.structured_data,
                    "confidence": m.confidence,
                }
                for m in memories
            ],
            total_retrieved=len(memories),
        )

    async def _text_search(self, task: MemoryQueryTask, session) -> MemoryQueryResult:
        from sqlalchemy import select
        from core.models.memory import Memory, MemoryScope, MemoryType

        q = select(Memory).where(
            Memory.user_id == task.user_id,
            Memory.is_active == True,  # noqa: E712
            (
                (Memory.mailbox_id == task.mailbox_id)
                | (
                    (Memory.scope == MemoryScope.USER_GLOBAL)
                    & (Memory.applies_to_all_mailboxes == True)  # noqa: E712
                )
            ),
        )

        if task.memory_types:
            q = q.where(Memory.memory_type.in_([MemoryType(t) for t in task.memory_types]))

        q = q.order_by(Memory.confidence.desc()).limit(task.top_k)
        result = await session.execute(q)
        memories = result.scalars().all()

        return MemoryQueryResult(
            memories=[
                {
                    "id": str(m.id),
                    "memory_type": m.memory_type.value,
                    "scope": m.scope.value,
                    "content": m.content,
                    "structured_data": m.structured_data,
                    "confidence": m.confidence,
                }
                for m in memories
            ],
            total_retrieved=len(memories),
        )
