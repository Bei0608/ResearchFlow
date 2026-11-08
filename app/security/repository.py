from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from threading import RLock
from typing import Protocol
from uuid import uuid4

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from app.memory.checkpointer import get_postgres_pool


class DuplicateUsernameError(ValueError):
    """用户名已经存在。"""


@dataclass(frozen=True)
class UserRecord:
    """身份仓库中的用户记录。"""

    user_id: str
    username: str
    password_hash: str
    is_active: bool = True


@dataclass(frozen=True)
class AuditEventRecord:
    event_id: str
    user_id: str | None
    event_type: str
    resource: str
    outcome: str
    request_id: str | None
    metadata: dict
    created_at: datetime


class IdentityRepository(Protocol):
    """用户身份与会话归属的存储契约。"""

    def setup(self) -> None: ...

    def create_user(
        self,
        username: str,
        password_hash: str,
    ) -> UserRecord: ...

    def get_user_by_username(
        self,
        username: str,
    ) -> UserRecord | None: ...

    def get_user_by_id(
        self,
        user_id: str,
    ) -> UserRecord | None: ...

    def claim_thread(
        self,
        thread_id: str,
        user_id: str,
    ) -> bool: ...

    def create_refresh_session(
        self,
        token_id: str,
        user_id: str,
        expires_at: datetime,
    ) -> None: ...

    def rotate_refresh_session(
        self,
        old_token_id: str,
        new_token_id: str,
        user_id: str,
        expires_at: datetime,
    ) -> bool: ...

    def revoke_refresh_session(
        self,
        token_id: str,
        user_id: str,
    ) -> bool: ...

    def revoke_all_refresh_sessions(
        self,
        user_id: str,
    ) -> int: ...

    def update_password(
        self,
        user_id: str,
        password_hash: str,
    ) -> bool: ...

    def record_audit_event(
        self,
        *,
        user_id: str | None,
        event_type: str,
        resource: str,
        outcome: str,
        request_id: str | None,
        metadata: dict | None = None,
    ) -> AuditEventRecord: ...

    def list_audit_events(
        self,
        user_id: str,
        limit: int = 100,
    ) -> list[AuditEventRecord]: ...


class PostgresIdentityRepository:
    """使用PostgreSQL保存用户和thread归属。"""

    def __init__(self) -> None:
        self._pool = get_postgres_pool()

    def setup(self) -> None:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS researchflow_users (
                        user_id TEXT PRIMARY KEY,
                        username TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS researchflow_refresh_tokens (
                        token_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL REFERENCES
                            researchflow_users(user_id) ON DELETE CASCADE,
                        expires_at TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        revoked_at TIMESTAMPTZ,
                        replaced_by_token_id TEXT
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_researchflow_refresh_tokens_user_id
                    ON researchflow_refresh_tokens(user_id)
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS researchflow_threads (
                        thread_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL REFERENCES
                            researchflow_users(user_id) ON DELETE CASCADE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        last_accessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_researchflow_threads_user_id
                    ON researchflow_threads(user_id)
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS researchflow_audit_events (
                        event_id TEXT PRIMARY KEY,
                        user_id TEXT REFERENCES
                            researchflow_users(user_id) ON DELETE SET NULL,
                        event_type TEXT NOT NULL,
                        resource TEXT NOT NULL,
                        outcome TEXT NOT NULL,
                        request_id TEXT,
                        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_researchflow_audit_user_created
                    ON researchflow_audit_events(
                        user_id, created_at DESC
                    )
                    """
                )

    @staticmethod
    def _row_to_user(row: dict | None) -> UserRecord | None:
        if row is None:
            return None
        return UserRecord(
            user_id=str(row["user_id"]),
            username=str(row["username"]),
            password_hash=str(row["password_hash"]),
            is_active=bool(row["is_active"]),
        )

    def create_user(
        self,
        username: str,
        password_hash: str,
    ) -> UserRecord:
        user_id = uuid4().hex
        try:
            with self._pool.connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO researchflow_users (
                            user_id,
                            username,
                            password_hash
                        ) VALUES (%s, %s, %s)
                        RETURNING user_id, username,
                                  password_hash, is_active
                        """,
                        (user_id, username, password_hash),
                    )
                    row = cursor.fetchone()
        except UniqueViolation as exception:
            raise DuplicateUsernameError(
                "用户名已存在"
            ) from exception

        user = self._row_to_user(row)
        if user is None:
            raise RuntimeError("创建用户失败")
        return user

    def get_user_by_username(
        self,
        username: str,
    ) -> UserRecord | None:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT user_id, username, password_hash, is_active
                    FROM researchflow_users
                    WHERE username = %s
                    """,
                    (username,),
                )
                return self._row_to_user(cursor.fetchone())

    def get_user_by_id(
        self,
        user_id: str,
    ) -> UserRecord | None:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT user_id, username, password_hash, is_active
                    FROM researchflow_users
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                return self._row_to_user(cursor.fetchone())

    def claim_thread(
        self,
        thread_id: str,
        user_id: str,
    ) -> bool:
        """原子占有新thread；已存在时只允许原所有者。"""
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO researchflow_threads (
                        thread_id,
                        user_id
                    ) VALUES (%s, %s)
                    ON CONFLICT (thread_id) DO NOTHING
                    """,
                    (thread_id, user_id),
                )
                cursor.execute(
                    """
                    UPDATE researchflow_threads
                    SET last_accessed_at = NOW()
                    WHERE thread_id = %s AND user_id = %s
                    RETURNING user_id
                    """,
                    (thread_id, user_id),
                )
                return cursor.fetchone() is not None

    def create_refresh_session(
        self,
        token_id: str,
        user_id: str,
        expires_at: datetime,
    ) -> None:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO researchflow_refresh_tokens (
                        token_id, user_id, expires_at
                    ) VALUES (%s, %s, %s)
                    """,
                    (token_id, user_id, expires_at),
                )

    def rotate_refresh_session(
        self,
        old_token_id: str,
        new_token_id: str,
        user_id: str,
        expires_at: datetime,
    ) -> bool:
        with self._pool.connection() as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE researchflow_refresh_tokens
                        SET revoked_at = NOW(),
                            replaced_by_token_id = %s
                        WHERE token_id = %s
                          AND user_id = %s
                          AND revoked_at IS NULL
                          AND expires_at > NOW()
                        RETURNING token_id
                        """,
                        (new_token_id, old_token_id, user_id),
                    )
                    if cursor.fetchone() is None:
                        return False
                    cursor.execute(
                        """
                        INSERT INTO researchflow_refresh_tokens (
                            token_id, user_id, expires_at
                        ) VALUES (%s, %s, %s)
                        """,
                        (new_token_id, user_id, expires_at),
                    )
                    return True

    def revoke_refresh_session(
        self,
        token_id: str,
        user_id: str,
    ) -> bool:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE researchflow_refresh_tokens
                    SET revoked_at = NOW()
                    WHERE token_id = %s
                      AND user_id = %s
                      AND revoked_at IS NULL
                    RETURNING token_id
                    """,
                    (token_id, user_id),
                )
                return cursor.fetchone() is not None

    def revoke_all_refresh_sessions(
        self,
        user_id: str,
    ) -> int:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE researchflow_refresh_tokens
                    SET revoked_at = NOW()
                    WHERE user_id = %s AND revoked_at IS NULL
                    """,
                    (user_id,),
                )
                return cursor.rowcount

    def update_password(
        self,
        user_id: str,
        password_hash: str,
    ) -> bool:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE researchflow_users
                    SET password_hash = %s
                    WHERE user_id = %s
                    RETURNING user_id
                    """,
                    (password_hash, user_id),
                )
                return cursor.fetchone() is not None

    @staticmethod
    def _row_to_audit(row: dict) -> AuditEventRecord:
        return AuditEventRecord(
            event_id=str(row["event_id"]),
            user_id=(
                str(row["user_id"])
                if row["user_id"] is not None
                else None
            ),
            event_type=str(row["event_type"]),
            resource=str(row["resource"]),
            outcome=str(row["outcome"]),
            request_id=(
                str(row["request_id"])
                if row["request_id"] is not None
                else None
            ),
            metadata=dict(row["metadata"]),
            created_at=row["created_at"],
        )

    def record_audit_event(
        self,
        *,
        user_id: str | None,
        event_type: str,
        resource: str,
        outcome: str,
        request_id: str | None,
        metadata: dict | None = None,
    ) -> AuditEventRecord:
        event_id = uuid4().hex
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO researchflow_audit_events (
                        event_id, user_id, event_type, resource,
                        outcome, request_id, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING event_id, user_id, event_type,
                              resource, outcome, request_id,
                              metadata, created_at
                    """,
                    (
                        event_id,
                        user_id,
                        event_type,
                        resource,
                        outcome,
                        request_id,
                        Jsonb(metadata or {}),
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            raise RuntimeError("写入审计事件失败")
        return self._row_to_audit(row)

    def list_audit_events(
        self,
        user_id: str,
        limit: int = 100,
    ) -> list[AuditEventRecord]:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT event_id, user_id, event_type, resource,
                           outcome, request_id, metadata, created_at
                    FROM researchflow_audit_events
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (user_id, limit),
                )
                return [
                    self._row_to_audit(row)
                    for row in cursor.fetchall()
                ]


class InMemoryIdentityRepository:
    """单元测试使用的线程安全内存身份仓库。"""

    def __init__(self) -> None:
        self._users_by_id: dict[str, UserRecord] = {}
        self._user_ids_by_name: dict[str, str] = {}
        self._thread_owners: dict[str, str] = {}
        self._refresh_sessions: dict[
            str,
            tuple[str, datetime, bool],
        ] = {}
        self._audit_events: list[AuditEventRecord] = []
        self._lock = RLock()

    def setup(self) -> None:
        return None

    def create_user(
        self,
        username: str,
        password_hash: str,
    ) -> UserRecord:
        with self._lock:
            if username in self._user_ids_by_name:
                raise DuplicateUsernameError("用户名已存在")
            user = UserRecord(
                user_id=uuid4().hex,
                username=username,
                password_hash=password_hash,
            )
            self._users_by_id[user.user_id] = user
            self._user_ids_by_name[username] = user.user_id
            return user

    def get_user_by_username(
        self,
        username: str,
    ) -> UserRecord | None:
        with self._lock:
            user_id = self._user_ids_by_name.get(username)
            return (
                self._users_by_id.get(user_id)
                if user_id is not None
                else None
            )

    def get_user_by_id(
        self,
        user_id: str,
    ) -> UserRecord | None:
        with self._lock:
            return self._users_by_id.get(user_id)

    def claim_thread(
        self,
        thread_id: str,
        user_id: str,
    ) -> bool:
        with self._lock:
            owner = self._thread_owners.setdefault(
                thread_id,
                user_id,
            )
            return owner == user_id

    def create_refresh_session(
        self,
        token_id: str,
        user_id: str,
        expires_at: datetime,
    ) -> None:
        with self._lock:
            self._refresh_sessions[token_id] = (
                user_id,
                expires_at,
                False,
            )

    def rotate_refresh_session(
        self,
        old_token_id: str,
        new_token_id: str,
        user_id: str,
        expires_at: datetime,
    ) -> bool:
        with self._lock:
            session = self._refresh_sessions.get(old_token_id)
            if session is None:
                return False
            owner, old_expires_at, revoked = session
            if (
                owner != user_id
                or revoked
                or old_expires_at <= datetime.now(timezone.utc)
            ):
                return False
            self._refresh_sessions[old_token_id] = (
                owner,
                old_expires_at,
                True,
            )
            self._refresh_sessions[new_token_id] = (
                user_id,
                expires_at,
                False,
            )
            return True

    def revoke_refresh_session(
        self,
        token_id: str,
        user_id: str,
    ) -> bool:
        with self._lock:
            session = self._refresh_sessions.get(token_id)
            if session is None:
                return False
            owner, expires_at, revoked = session
            if owner != user_id or revoked:
                return False
            self._refresh_sessions[token_id] = (
                owner,
                expires_at,
                True,
            )
            return True

    def revoke_all_refresh_sessions(
        self,
        user_id: str,
    ) -> int:
        with self._lock:
            revoked_count = 0
            for token_id, session in list(
                self._refresh_sessions.items()
            ):
                owner, expires_at, revoked = session
                if owner == user_id and not revoked:
                    self._refresh_sessions[token_id] = (
                        owner,
                        expires_at,
                        True,
                    )
                    revoked_count += 1
            return revoked_count

    def update_password(
        self,
        user_id: str,
        password_hash: str,
    ) -> bool:
        with self._lock:
            user = self._users_by_id.get(user_id)
            if user is None:
                return False
            self._users_by_id[user_id] = UserRecord(
                user_id=user.user_id,
                username=user.username,
                password_hash=password_hash,
                is_active=user.is_active,
            )
            return True

    def record_audit_event(
        self,
        *,
        user_id: str | None,
        event_type: str,
        resource: str,
        outcome: str,
        request_id: str | None,
        metadata: dict | None = None,
    ) -> AuditEventRecord:
        event = AuditEventRecord(
            event_id=uuid4().hex,
            user_id=user_id,
            event_type=event_type,
            resource=resource,
            outcome=outcome,
            request_id=request_id,
            metadata=metadata or {},
            created_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._audit_events.append(event)
        return event

    def list_audit_events(
        self,
        user_id: str,
        limit: int = 100,
    ) -> list[AuditEventRecord]:
        with self._lock:
            matching = [
                event
                for event in reversed(self._audit_events)
                if event.user_id == user_id
            ]
            return matching[:limit]


@lru_cache(maxsize=1)
def get_identity_repository() -> PostgresIdentityRepository:
    """创建并初始化生产身份仓库。"""
    repository = PostgresIdentityRepository()
    repository.setup()
    return repository
