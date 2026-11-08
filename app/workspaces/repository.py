from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from threading import RLock
from typing import Literal, Protocol
from uuid import uuid4

from app.memory.checkpointer import get_postgres_pool


WorkspaceRole = Literal["owner", "reviewer"]


@dataclass(frozen=True)
class WorkspaceRecord:
    workspace_id: str
    name: str
    owner_id: str
    is_personal: bool
    role: WorkspaceRole
    created_at: datetime


class WorkspaceRepository(Protocol):
    def ensure_personal_workspace(
        self,
        user_id: str,
        username: str,
    ) -> WorkspaceRecord: ...

    def list_workspaces(self, user_id: str) -> list[WorkspaceRecord]: ...

    def get_workspace_for_user(
        self,
        workspace_id: str,
        user_id: str,
    ) -> WorkspaceRecord | None: ...

    def add_reviewer(
        self,
        workspace_id: str,
        owner_id: str,
        reviewer_id: str,
    ) -> WorkspaceRecord | None: ...


class PostgresWorkspaceRepository:
    def __init__(self) -> None:
        self._pool = get_postgres_pool()

    @staticmethod
    def _from_row(row: dict | None) -> WorkspaceRecord | None:
        if row is None:
            return None
        return WorkspaceRecord(
            workspace_id=str(row["workspace_id"]),
            name=str(row["name"]),
            owner_id=str(row["owner_id"]),
            is_personal=bool(row["is_personal"]),
            role=str(row["role"]),  # type: ignore[arg-type]
            created_at=row["created_at"],
        )

    def ensure_personal_workspace(
        self,
        user_id: str,
        username: str,
    ) -> WorkspaceRecord:
        proposed_id = uuid4().hex
        with self._pool.connection() as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO researchflow_workspaces (
                            workspace_id, name, owner_id, is_personal
                        ) VALUES (%s, %s, %s, TRUE)
                        ON CONFLICT (owner_id) WHERE is_personal
                        DO UPDATE SET owner_id = EXCLUDED.owner_id
                        RETURNING workspace_id, name, owner_id,
                                  is_personal, created_at
                        """,
                        (proposed_id, f"{username} 的个人空间", user_id),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise RuntimeError("创建个人Workspace失败")
                    cursor.execute(
                        """
                        INSERT INTO researchflow_workspace_members (
                            workspace_id, user_id, role
                        ) VALUES (%s, %s, 'owner')
                        ON CONFLICT (workspace_id, user_id)
                        DO UPDATE SET role = 'owner'
                        """,
                        (row["workspace_id"], user_id),
                    )
        return WorkspaceRecord(
            workspace_id=str(row["workspace_id"]),
            name=str(row["name"]),
            owner_id=str(row["owner_id"]),
            is_personal=bool(row["is_personal"]),
            role="owner",
            created_at=row["created_at"],
        )

    def list_workspaces(self, user_id: str) -> list[WorkspaceRecord]:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT w.workspace_id, w.name, w.owner_id,
                           w.is_personal, m.role, w.created_at
                    FROM researchflow_workspaces AS w
                    JOIN researchflow_workspace_members AS m
                      ON m.workspace_id = w.workspace_id
                    WHERE m.user_id = %s
                    ORDER BY w.created_at, w.workspace_id
                    """,
                    (user_id,),
                )
                return [
                    self._from_row(row)  # type: ignore[arg-type]
                    for row in cursor.fetchall()
                ]

    def get_workspace_for_user(
        self,
        workspace_id: str,
        user_id: str,
    ) -> WorkspaceRecord | None:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT w.workspace_id, w.name, w.owner_id,
                           w.is_personal, m.role, w.created_at
                    FROM researchflow_workspaces AS w
                    JOIN researchflow_workspace_members AS m
                      ON m.workspace_id = w.workspace_id
                    WHERE w.workspace_id = %s AND m.user_id = %s
                    """,
                    (workspace_id, user_id),
                )
                return self._from_row(cursor.fetchone())

    def add_reviewer(
        self,
        workspace_id: str,
        owner_id: str,
        reviewer_id: str,
    ) -> WorkspaceRecord | None:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO researchflow_workspace_members (
                        workspace_id, user_id, role
                    )
                    SELECT %s, %s, 'reviewer'
                    WHERE EXISTS (
                        SELECT 1 FROM researchflow_workspace_members
                        WHERE workspace_id=%s AND user_id=%s
                          AND role='owner'
                    )
                    ON CONFLICT (workspace_id, user_id)
                    DO UPDATE SET role=CASE
                        WHEN researchflow_workspace_members.role='owner'
                        THEN 'owner' ELSE 'reviewer' END
                    RETURNING workspace_id
                    """,
                    (workspace_id, reviewer_id, workspace_id, owner_id),
                )
                if cursor.fetchone() is None:
                    return None
        return self.get_workspace_for_user(workspace_id, reviewer_id)


class InMemoryWorkspaceRepository:
    def __init__(self) -> None:
        self._workspaces: dict[str, WorkspaceRecord] = {}
        self._personal_by_owner: dict[str, str] = {}
        self._members: dict[tuple[str, str], WorkspaceRole] = {}
        self._lock = RLock()

    def ensure_personal_workspace(
        self,
        user_id: str,
        username: str,
    ) -> WorkspaceRecord:
        with self._lock:
            existing_id = self._personal_by_owner.get(user_id)
            if existing_id is not None:
                return self._workspaces[existing_id]
            workspace = WorkspaceRecord(
                workspace_id=uuid4().hex,
                name=f"{username} 的个人空间",
                owner_id=user_id,
                is_personal=True,
                role="owner",
                created_at=datetime.now(timezone.utc),
            )
            self._workspaces[workspace.workspace_id] = workspace
            self._personal_by_owner[user_id] = workspace.workspace_id
            self._members[(workspace.workspace_id, user_id)] = "owner"
            return workspace

    def list_workspaces(self, user_id: str) -> list[WorkspaceRecord]:
        with self._lock:
            return sorted(
                [
                    WorkspaceRecord(
                        workspace_id=workspace.workspace_id,
                        name=workspace.name,
                        owner_id=workspace.owner_id,
                        is_personal=workspace.is_personal,
                        role=role,
                        created_at=workspace.created_at,
                    )
                    for (workspace_id, member_id), role in self._members.items()
                    if member_id == user_id
                    if (workspace := self._workspaces.get(workspace_id))
                    is not None
                ],
                key=lambda item: (item.created_at, item.workspace_id),
            )

    def get_workspace_for_user(
        self,
        workspace_id: str,
        user_id: str,
    ) -> WorkspaceRecord | None:
        with self._lock:
            workspace = self._workspaces.get(workspace_id)
            role = self._members.get((workspace_id, user_id))
            if workspace is None or role is None:
                return None
            return WorkspaceRecord(
                workspace_id=workspace.workspace_id,
                name=workspace.name,
                owner_id=workspace.owner_id,
                is_personal=workspace.is_personal,
                role=role,
                created_at=workspace.created_at,
            )

    def add_reviewer(
        self,
        workspace_id: str,
        owner_id: str,
        reviewer_id: str,
    ) -> WorkspaceRecord | None:
        with self._lock:
            if self._members.get((workspace_id, owner_id)) != "owner":
                return None
            if workspace_id not in self._workspaces:
                return None
            self._members.setdefault((workspace_id, reviewer_id), "reviewer")
            return self.get_workspace_for_user(workspace_id, reviewer_id)


@lru_cache(maxsize=1)
def get_workspace_repository() -> PostgresWorkspaceRepository:
    return PostgresWorkspaceRepository()
