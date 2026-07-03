from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str
    created_at: str


class ChatStore(Protocol):
    def load_messages(self, session_id: str) -> list[ChatMessage]:
        ...

    def append_message(self, session_id: str, role: str, content: str) -> None:
        ...

    def clear_messages(self, session_id: str) -> None:
        ...


class InMemoryChatStore:
    def __init__(self, messages: dict[str, list[ChatMessage]] | None = None) -> None:
        self.messages = messages if messages is not None else {}

    def load_messages(self, session_id: str) -> list[ChatMessage]:
        return list(self.messages.get(session_id, []))

    def append_message(self, session_id: str, role: str, content: str) -> None:
        self.messages.setdefault(session_id, []).append(
            ChatMessage(role=role, content=content, created_at=datetime.now(UTC).isoformat())
        )

    def clear_messages(self, session_id: str) -> None:
        self.messages[session_id] = []


class RdsChatStore:
    """SQL-backed chat store for AWS RDS.

    Set RDS_DATABASE_URL to a SQLAlchemy URL such as:
    postgresql+psycopg://user:password@host:5432/finpilot
    """

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            try:
                from sqlalchemy import create_engine, text
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "RDS_DATABASE_URL is configured, but SQLAlchemy is not installed. "
                    "Install sqlalchemy plus the matching database driver for your AWS RDS engine."
                ) from exc
            self._engine = create_engine(self.database_url, pool_pre_ping=True)
            with self._engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS finpilot_chat_messages (
                            id VARCHAR(36) PRIMARY KEY,
                            session_id VARCHAR(128) NOT NULL,
                            role VARCHAR(32) NOT NULL,
                            content TEXT NOT NULL,
                            created_at TIMESTAMP NOT NULL
                        )
                        """
                    )
                )
        return self._engine

    def load_messages(self, session_id: str) -> list[ChatMessage]:
        from sqlalchemy import text

        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT role, content, created_at
                    FROM finpilot_chat_messages
                    WHERE session_id = :session_id
                    ORDER BY created_at ASC
                    """
                ),
                {"session_id": session_id},
            ).mappings()
            return [
                ChatMessage(
                    role=str(row["role"]),
                    content=str(row["content"]),
                    created_at=row["created_at"].isoformat()
                    if hasattr(row["created_at"], "isoformat")
                    else str(row["created_at"]),
                )
                for row in rows
            ]

    def append_message(self, session_id: str, role: str, content: str) -> None:
        from sqlalchemy import text

        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO finpilot_chat_messages (id, session_id, role, content, created_at)
                    VALUES (:id, :session_id, :role, :content, :created_at)
                    """
                ),
                {
                    "id": str(uuid4()),
                    "session_id": session_id,
                    "role": role,
                    "content": content,
                    "created_at": datetime.now(UTC).replace(tzinfo=None),
                },
            )

    def clear_messages(self, session_id: str) -> None:
        from sqlalchemy import text

        with self.engine.begin() as connection:
            connection.execute(
                text("DELETE FROM finpilot_chat_messages WHERE session_id = :session_id"),
                {"session_id": session_id},
            )


def build_chat_store(database_url: str | None, memory_messages: dict[str, list[ChatMessage]] | None = None) -> ChatStore:
    if database_url:
        return RdsChatStore(database_url)
    return InMemoryChatStore(memory_messages)
