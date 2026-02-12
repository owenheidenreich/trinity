"""
Trinity Database — SQLite via SQLAlchemy
=========================================
Phase 3.3: Persistent state for rate limits, sessions, usage stats, chat metadata.

Fresh start (no migration from JSON) — all tables created on first run.
Chat *content* stays encrypted on IPFS; only metadata lives here.

Usage:
    from database import get_db, init_db
    init_db()                     # call once at startup
    db = get_db()
    db.upsert_rate_limit(ip, count, window_start)
    db.get_usage_stats(principal, date)
"""

import json
import os
import time
from contextlib import contextmanager
from typing import Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config import CHATS_DIR, logger

# ===== Database path =====
DB_DIR = os.environ.get("TRINITY_DB_DIR", CHATS_DIR)
DB_PATH = os.path.join(DB_DIR, "trinity.db")

Base = declarative_base()


# ===== Models =====

class RateLimit(Base):
    """Per-IP request rate tracking."""
    __tablename__ = "rate_limits"

    ip = Column(String, primary_key=True)
    request_count = Column(Integer, default=0)
    window_start = Column(Integer, default=0)  # epoch seconds


class SessionRecord(Base):
    """Private session management."""
    __tablename__ = "sessions"

    session_id = Column(String, primary_key=True)
    principal = Column(String, nullable=True)
    created_at = Column(Integer, default=lambda: int(time.time()))
    last_activity = Column(Integer, default=lambda: int(time.time()))
    data = Column(Text, default="{}")  # JSON blob for extra info


class UsageStats(Base):
    """Per-principal daily token/request tracking."""
    __tablename__ = "usage_stats"

    principal = Column(String, primary_key=True)
    date = Column(String, primary_key=True)  # YYYY-MM-DD
    tokens_used = Column(Integer, default=0)
    requests = Column(Integer, default=0)

    __table_args__ = (
        Index("idx_usage_date", "date"),
    )


class ChatMetadata(Base):
    """Chat index — content stays on IPFS, metadata here."""
    __tablename__ = "chat_metadata"

    id = Column(String, primary_key=True)  # chatId
    principal = Column(String, nullable=False)
    title = Column(String, default="Untitled")
    pinned = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)
    cid = Column(String, nullable=True)  # IPFS CID
    created_at = Column(Integer, default=lambda: int(time.time() * 1000))
    updated_at = Column(Integer, default=lambda: int(time.time() * 1000))
    message_count = Column(Integer, default=0)

    __table_args__ = (
        Index("idx_chat_principal", "principal"),
    )


# ===== Engine / Session Factory =====

_engine = None
_SessionFactory = None


def init_db(db_path: str = None):
    """
    Initialize the database. Creates tables if they don't exist.
    Safe to call multiple times (idempotent).
    """
    global _engine, _SessionFactory

    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)

    _engine = create_engine(
        f"sqlite:///{path}",
        echo=False,
        connect_args={"check_same_thread": False},  # allow multi-threaded Flask
    )
    Base.metadata.create_all(_engine)
    _SessionFactory = sessionmaker(bind=_engine)
    logger.info(f"📦 SQLite database initialized: {path}")


@contextmanager
def get_session() -> Session:
    """Provide a transactional scope around a series of operations."""
    if _SessionFactory is None:
        init_db()
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ===== DAO helpers =====

class TrinityDB:
    """High-level database access object."""

    # ----- Rate Limits -----

    @staticmethod
    def get_rate_limit(ip: str) -> Optional[Dict]:
        with get_session() as s:
            row = s.query(RateLimit).get(ip)
            if row:
                return {"ip": row.ip, "request_count": row.request_count, "window_start": row.window_start}
            return None

    @staticmethod
    def upsert_rate_limit(ip: str, request_count: int, window_start: int):
        with get_session() as s:
            row = s.query(RateLimit).get(ip)
            if row:
                row.request_count = request_count
                row.window_start = window_start
            else:
                s.add(RateLimit(ip=ip, request_count=request_count, window_start=window_start))

    @staticmethod
    def cleanup_rate_limits(before_epoch: int) -> int:
        """Remove rate limit entries with window_start older than threshold."""
        with get_session() as s:
            count = s.query(RateLimit).filter(RateLimit.window_start < before_epoch).delete()
            return count

    # ----- Sessions -----

    @staticmethod
    def create_session(session_id: str, principal: str = None, data: dict = None):
        with get_session() as s:
            s.add(SessionRecord(
                session_id=session_id,
                principal=principal,
                data=json.dumps(data or {}),
            ))

    @staticmethod
    def get_session_record(session_id: str) -> Optional[Dict]:
        with get_session() as s:
            row = s.query(SessionRecord).get(session_id)
            if row:
                return {
                    "session_id": row.session_id,
                    "principal": row.principal,
                    "created_at": row.created_at,
                    "last_activity": row.last_activity,
                    "data": json.loads(row.data or "{}"),
                }
            return None

    @staticmethod
    def update_session_activity(session_id: str):
        with get_session() as s:
            row = s.query(SessionRecord).get(session_id)
            if row:
                row.last_activity = int(time.time())

    # ----- Usage Stats -----

    @staticmethod
    def record_usage(principal: str, date: str, tokens: int = 0, requests: int = 1):
        with get_session() as s:
            row = s.query(UsageStats).filter_by(principal=principal, date=date).first()
            if row:
                row.tokens_used += tokens
                row.requests += requests
            else:
                s.add(UsageStats(
                    principal=principal, date=date,
                    tokens_used=tokens, requests=requests,
                ))

    @staticmethod
    def get_usage_stats(principal: str, date: str) -> Optional[Dict]:
        with get_session() as s:
            row = s.query(UsageStats).filter_by(principal=principal, date=date).first()
            if row:
                return {"tokens_used": row.tokens_used, "requests": row.requests}
            return None

    @staticmethod
    def get_all_usage_for_date(date: str) -> List[Dict]:
        with get_session() as s:
            rows = s.query(UsageStats).filter_by(date=date).all()
            return [
                {"principal": r.principal, "tokens_used": r.tokens_used, "requests": r.requests}
                for r in rows
            ]

    # ----- Chat Metadata -----

    @staticmethod
    def upsert_chat_metadata(
        chat_id: str,
        principal: str,
        title: str = "Untitled",
        pinned: bool = False,
        is_archived: bool = False,
        cid: str = None,
        message_count: int = 0,
    ):
        with get_session() as s:
            row = s.query(ChatMetadata).get(chat_id)
            if row:
                row.title = title
                row.pinned = pinned
                row.is_archived = is_archived
                if cid:
                    row.cid = cid
                row.message_count = message_count
                row.updated_at = int(time.time() * 1000)
            else:
                s.add(ChatMetadata(
                    id=chat_id, principal=principal, title=title,
                    pinned=pinned, is_archived=is_archived, cid=cid,
                    message_count=message_count,
                ))

    @staticmethod
    def get_chats_for_principal(principal: str) -> List[Dict]:
        with get_session() as s:
            rows = s.query(ChatMetadata).filter_by(principal=principal).order_by(
                ChatMetadata.updated_at.desc()
            ).all()
            return [
                {
                    "chatId": r.id,
                    "title": r.title,
                    "pinned": r.pinned,
                    "isArchived": r.is_archived,
                    "cid": r.cid,
                    "createdAt": r.created_at,
                    "lastUpdated": r.updated_at,
                    "messageCount": r.message_count,
                }
                for r in rows
            ]

    @staticmethod
    def delete_chat_metadata(chat_id: str) -> bool:
        with get_session() as s:
            row = s.query(ChatMetadata).get(chat_id)
            if row:
                s.delete(row)
                return True
            return False


def get_db() -> TrinityDB:
    """Get a TrinityDB instance (stateless, methods are all @staticmethod)."""
    return TrinityDB()
