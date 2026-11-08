from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from threading import RLock
from typing import Literal, Protocol
from uuid import uuid4

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from app.memory.checkpointer import get_postgres_pool
from app.workspaces import WorkspaceRepository


ApplicationTarget = Literal["internal", "api", "mcp"]
AgentVersionStatus = Literal["draft", "published"]


class DuplicateApplicationError(ValueError):
    pass


class DuplicateAgentVersionError(ValueError):
    pass


class ImmutableAgentVersionError(ValueError):
    pass


@dataclass(frozen=True)
class ApplicationRecord:
    application_id: str
    workspace_id: str
    name: str
    description: str
    target_type: ApplicationTarget
    created_by: str
    created_at: datetime


@dataclass(frozen=True)
class AgentVersionRecord:
    agent_version_id: str
    application_id: str
    version: str
    status: AgentVersionStatus
    config_snapshot: dict
    git_commit: str | None
    created_by: str
    created_at: datetime
    published_at: datetime | None


class ApplicationRepository(Protocol):
    def create_application(
        self,
        *,
        workspace_id: str,
        user_id: str,
        name: str,
        description: str,
        target_type: ApplicationTarget,
    ) -> ApplicationRecord | None: ...

    def list_applications(
        self,
        workspace_id: str,
        user_id: str,
    ) -> list[ApplicationRecord]: ...

    def get_application(
        self,
        application_id: str,
        user_id: str,
    ) -> ApplicationRecord | None: ...

    def create_version(
        self,
        *,
        application_id: str,
        user_id: str,
        version: str,
        config_snapshot: dict,
        git_commit: str | None,
    ) -> AgentVersionRecord | None: ...

    def list_versions(
        self,
        application_id: str,
        user_id: str,
    ) -> list[AgentVersionRecord]: ...

    def get_version(
        self,
        application_id: str,
        agent_version_id: str,
        user_id: str,
    ) -> AgentVersionRecord | None: ...

    def update_version(
        self,
        *,
        application_id: str,
        agent_version_id: str,
        user_id: str,
        config_snapshot: dict,
        git_commit: str | None,
    ) -> AgentVersionRecord | None: ...

    def publish_version(
        self,
        application_id: str,
        agent_version_id: str,
        user_id: str,
    ) -> AgentVersionRecord | None: ...


class PostgresApplicationRepository:
    def __init__(self) -> None:
        self._pool = get_postgres_pool()

    @staticmethod
    def _application_from_row(row: dict | None) -> ApplicationRecord | None:
        if row is None:
            return None
        return ApplicationRecord(
            application_id=str(row["application_id"]),
            workspace_id=str(row["workspace_id"]),
            name=str(row["name"]),
            description=str(row["description"]),
            target_type=str(row["target_type"]),  # type: ignore[arg-type]
            created_by=str(row["created_by"]),
            created_at=row["created_at"],
        )

    @staticmethod
    def _version_from_row(row: dict | None) -> AgentVersionRecord | None:
        if row is None:
            return None
        return AgentVersionRecord(
            agent_version_id=str(row["agent_version_id"]),
            application_id=str(row["application_id"]),
            version=str(row["version"]),
            status=str(row["status"]),  # type: ignore[arg-type]
            config_snapshot=dict(row["config_snapshot"]),
            git_commit=(
                str(row["git_commit"])
                if row["git_commit"] is not None
                else None
            ),
            created_by=str(row["created_by"]),
            created_at=row["created_at"],
            published_at=row["published_at"],
        )

    def create_application(
        self,
        *,
        workspace_id: str,
        user_id: str,
        name: str,
        description: str,
        target_type: ApplicationTarget,
    ) -> ApplicationRecord | None:
        application_id = uuid4().hex
        try:
            with self._pool.connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO researchflow_applications (
                            application_id, workspace_id, name,
                            description, target_type, created_by
                        )
                        SELECT %s, %s, %s, %s, %s, %s
                        WHERE EXISTS (
                            SELECT 1
                            FROM researchflow_workspace_members
                            WHERE workspace_id = %s
                              AND user_id = %s
                              AND role = 'owner'
                        )
                        RETURNING application_id, workspace_id, name,
                                  description, target_type, created_by,
                                  created_at
                        """,
                        (
                            application_id,
                            workspace_id,
                            name,
                            description,
                            target_type,
                            user_id,
                            workspace_id,
                            user_id,
                        ),
                    )
                    return self._application_from_row(cursor.fetchone())
        except UniqueViolation as exc:
            raise DuplicateApplicationError(
                "Workspace中已存在同名应用"
            ) from exc

    def list_applications(
        self,
        workspace_id: str,
        user_id: str,
    ) -> list[ApplicationRecord]:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT a.application_id, a.workspace_id, a.name,
                           a.description, a.target_type, a.created_by,
                           a.created_at
                    FROM researchflow_applications AS a
                    JOIN researchflow_workspace_members AS m
                      ON m.workspace_id = a.workspace_id
                    WHERE a.workspace_id = %s AND m.user_id = %s
                    ORDER BY a.created_at, a.application_id
                    """,
                    (workspace_id, user_id),
                )
                return [
                    self._application_from_row(row)  # type: ignore[arg-type]
                    for row in cursor.fetchall()
                ]

    def get_application(
        self,
        application_id: str,
        user_id: str,
    ) -> ApplicationRecord | None:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT a.application_id, a.workspace_id, a.name,
                           a.description, a.target_type, a.created_by,
                           a.created_at
                    FROM researchflow_applications AS a
                    JOIN researchflow_workspace_members AS m
                      ON m.workspace_id = a.workspace_id
                    WHERE a.application_id = %s AND m.user_id = %s
                    """,
                    (application_id, user_id),
                )
                return self._application_from_row(cursor.fetchone())

    def create_version(
        self,
        *,
        application_id: str,
        user_id: str,
        version: str,
        config_snapshot: dict,
        git_commit: str | None,
    ) -> AgentVersionRecord | None:
        agent_version_id = uuid4().hex
        try:
            with self._pool.connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO researchflow_agent_versions (
                            agent_version_id, application_id, version,
                            config_snapshot, git_commit, created_by
                        )
                        SELECT %s, a.application_id, %s, %s, %s, %s
                        FROM researchflow_applications AS a
                        JOIN researchflow_workspace_members AS m
                          ON m.workspace_id = a.workspace_id
                        WHERE a.application_id = %s
                          AND m.user_id = %s
                          AND m.role = 'owner'
                        RETURNING agent_version_id, application_id,
                                  version, status, config_snapshot,
                                  git_commit, created_by, created_at,
                                  published_at
                        """,
                        (
                            agent_version_id,
                            version,
                            Jsonb(config_snapshot),
                            git_commit,
                            user_id,
                            application_id,
                            user_id,
                        ),
                    )
                    return self._version_from_row(cursor.fetchone())
        except UniqueViolation as exc:
            raise DuplicateAgentVersionError(
                "应用中已存在相同版本号"
            ) from exc

    def list_versions(
        self,
        application_id: str,
        user_id: str,
    ) -> list[AgentVersionRecord]:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT v.agent_version_id, v.application_id,
                           v.version, v.status, v.config_snapshot,
                           v.git_commit, v.created_by, v.created_at,
                           v.published_at
                    FROM researchflow_agent_versions AS v
                    JOIN researchflow_applications AS a
                      ON a.application_id = v.application_id
                    JOIN researchflow_workspace_members AS m
                      ON m.workspace_id = a.workspace_id
                    WHERE v.application_id = %s AND m.user_id = %s
                    ORDER BY v.created_at, v.agent_version_id
                    """,
                    (application_id, user_id),
                )
                return [
                    self._version_from_row(row)  # type: ignore[arg-type]
                    for row in cursor.fetchall()
                ]

    def get_version(
        self,
        application_id: str,
        agent_version_id: str,
        user_id: str,
    ) -> AgentVersionRecord | None:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT v.agent_version_id, v.application_id,
                           v.version, v.status, v.config_snapshot,
                           v.git_commit, v.created_by, v.created_at,
                           v.published_at
                    FROM researchflow_agent_versions AS v
                    JOIN researchflow_applications AS a
                      ON a.application_id = v.application_id
                    JOIN researchflow_workspace_members AS m
                      ON m.workspace_id = a.workspace_id
                    WHERE v.application_id = %s
                      AND v.agent_version_id = %s
                      AND m.user_id = %s
                    """,
                    (application_id, agent_version_id, user_id),
                )
                return self._version_from_row(cursor.fetchone())

    def _get_version_for_owner(
        self,
        application_id: str,
        agent_version_id: str,
        user_id: str,
    ) -> AgentVersionRecord | None:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT v.agent_version_id, v.application_id,
                           v.version, v.status, v.config_snapshot,
                           v.git_commit, v.created_by, v.created_at,
                           v.published_at
                    FROM researchflow_agent_versions AS v
                    JOIN researchflow_applications AS a
                      ON a.application_id = v.application_id
                    JOIN researchflow_workspace_members AS m
                      ON m.workspace_id = a.workspace_id
                    WHERE v.application_id = %s
                      AND v.agent_version_id = %s
                      AND m.user_id = %s
                      AND m.role = 'owner'
                    """,
                    (application_id, agent_version_id, user_id),
                )
                return self._version_from_row(cursor.fetchone())

    def update_version(
        self,
        *,
        application_id: str,
        agent_version_id: str,
        user_id: str,
        config_snapshot: dict,
        git_commit: str | None,
    ) -> AgentVersionRecord | None:
        current = self._get_version_for_owner(
            application_id,
            agent_version_id,
            user_id,
        )
        if current is not None and current.status == "published":
            raise ImmutableAgentVersionError("已发布版本不可修改")
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE researchflow_agent_versions AS v
                    SET config_snapshot = %s, git_commit = %s
                    FROM researchflow_applications AS a,
                         researchflow_workspace_members AS m
                    WHERE v.agent_version_id = %s
                      AND v.application_id = %s
                      AND v.status = 'draft'
                      AND a.application_id = v.application_id
                      AND m.workspace_id = a.workspace_id
                      AND m.user_id = %s
                      AND m.role = 'owner'
                    RETURNING v.agent_version_id, v.application_id,
                              v.version, v.status, v.config_snapshot,
                              v.git_commit, v.created_by, v.created_at,
                              v.published_at
                    """,
                    (
                        Jsonb(config_snapshot),
                        git_commit,
                        agent_version_id,
                        application_id,
                        user_id,
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            latest = self._get_version_for_owner(
                application_id,
                agent_version_id,
                user_id,
            )
            if latest is not None and latest.status == "published":
                raise ImmutableAgentVersionError("已发布版本不可修改")
        return self._version_from_row(row)

    def publish_version(
        self,
        application_id: str,
        agent_version_id: str,
        user_id: str,
    ) -> AgentVersionRecord | None:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE researchflow_agent_versions AS v
                    SET status = 'published', published_at = NOW()
                    FROM researchflow_applications AS a,
                         researchflow_workspace_members AS m
                    WHERE v.agent_version_id = %s
                      AND v.application_id = %s
                      AND v.status = 'draft'
                      AND a.application_id = v.application_id
                      AND m.workspace_id = a.workspace_id
                      AND m.user_id = %s
                      AND m.role = 'owner'
                    RETURNING v.agent_version_id, v.application_id,
                              v.version, v.status, v.config_snapshot,
                              v.git_commit, v.created_by, v.created_at,
                              v.published_at
                    """,
                    (agent_version_id, application_id, user_id),
                )
                row = cursor.fetchone()
        if row is not None:
            return self._version_from_row(row)
        return self._get_version_for_owner(
            application_id,
            agent_version_id,
            user_id,
        )


class InMemoryApplicationRepository:
    def __init__(self, workspaces: WorkspaceRepository) -> None:
        self._workspaces = workspaces
        self._applications: dict[str, ApplicationRecord] = {}
        self._versions: dict[str, AgentVersionRecord] = {}
        self._lock = RLock()

    def _can_read(self, workspace_id: str, user_id: str) -> bool:
        return (
            self._workspaces.get_workspace_for_user(workspace_id, user_id)
            is not None
        )

    def _can_write(self, workspace_id: str, user_id: str) -> bool:
        workspace = self._workspaces.get_workspace_for_user(
            workspace_id,
            user_id,
        )
        return workspace is not None and workspace.role == "owner"

    def create_application(
        self,
        *,
        workspace_id: str,
        user_id: str,
        name: str,
        description: str,
        target_type: ApplicationTarget,
    ) -> ApplicationRecord | None:
        with self._lock:
            if not self._can_write(workspace_id, user_id):
                return None
            if any(
                item.workspace_id == workspace_id and item.name == name
                for item in self._applications.values()
            ):
                raise DuplicateApplicationError(
                    "Workspace中已存在同名应用"
                )
            application = ApplicationRecord(
                application_id=uuid4().hex,
                workspace_id=workspace_id,
                name=name,
                description=description,
                target_type=target_type,
                created_by=user_id,
                created_at=datetime.now(timezone.utc),
            )
            self._applications[application.application_id] = application
            return application

    def list_applications(
        self,
        workspace_id: str,
        user_id: str,
    ) -> list[ApplicationRecord]:
        with self._lock:
            if not self._can_read(workspace_id, user_id):
                return []
            return sorted(
                [
                    item
                    for item in self._applications.values()
                    if item.workspace_id == workspace_id
                ],
                key=lambda item: (item.created_at, item.application_id),
            )

    def get_application(
        self,
        application_id: str,
        user_id: str,
    ) -> ApplicationRecord | None:
        with self._lock:
            item = self._applications.get(application_id)
            if item is None or not self._can_read(item.workspace_id, user_id):
                return None
            return item

    def create_version(
        self,
        *,
        application_id: str,
        user_id: str,
        version: str,
        config_snapshot: dict,
        git_commit: str | None,
    ) -> AgentVersionRecord | None:
        with self._lock:
            application = self._applications.get(application_id)
            if application is None or not self._can_write(
                application.workspace_id,
                user_id,
            ):
                return None
            if any(
                item.application_id == application_id
                and item.version == version
                for item in self._versions.values()
            ):
                raise DuplicateAgentVersionError(
                    "应用中已存在相同版本号"
                )
            record = AgentVersionRecord(
                agent_version_id=uuid4().hex,
                application_id=application_id,
                version=version,
                status="draft",
                config_snapshot=dict(config_snapshot),
                git_commit=git_commit,
                created_by=user_id,
                created_at=datetime.now(timezone.utc),
                published_at=None,
            )
            self._versions[record.agent_version_id] = record
            return record

    def list_versions(
        self,
        application_id: str,
        user_id: str,
    ) -> list[AgentVersionRecord]:
        with self._lock:
            application = self.get_application(application_id, user_id)
            if application is None:
                return []
            return sorted(
                [
                    item
                    for item in self._versions.values()
                    if item.application_id == application_id
                ],
                key=lambda item: (item.created_at, item.agent_version_id),
            )

    def get_version(
        self,
        application_id: str,
        agent_version_id: str,
        user_id: str,
    ) -> AgentVersionRecord | None:
        with self._lock:
            application = self.get_application(application_id, user_id)
            item = self._versions.get(agent_version_id)
            if (
                application is None
                or item is None
                or item.application_id != application_id
            ):
                return None
            return item

    def update_version(
        self,
        *,
        application_id: str,
        agent_version_id: str,
        user_id: str,
        config_snapshot: dict,
        git_commit: str | None,
    ) -> AgentVersionRecord | None:
        with self._lock:
            application = self._applications.get(application_id)
            current = self._versions.get(agent_version_id)
            if (
                application is None
                or current is None
                or current.application_id != application_id
                or not self._can_write(application.workspace_id, user_id)
            ):
                return None
            if current.status == "published":
                raise ImmutableAgentVersionError("已发布版本不可修改")
            updated = AgentVersionRecord(
                agent_version_id=current.agent_version_id,
                application_id=current.application_id,
                version=current.version,
                status=current.status,
                config_snapshot=dict(config_snapshot),
                git_commit=git_commit,
                created_by=current.created_by,
                created_at=current.created_at,
                published_at=current.published_at,
            )
            self._versions[agent_version_id] = updated
            return updated

    def publish_version(
        self,
        application_id: str,
        agent_version_id: str,
        user_id: str,
    ) -> AgentVersionRecord | None:
        with self._lock:
            application = self._applications.get(application_id)
            current = self._versions.get(agent_version_id)
            if (
                application is None
                or current is None
                or current.application_id != application_id
                or not self._can_write(application.workspace_id, user_id)
            ):
                return None
            if current.status == "published":
                return current
            published = AgentVersionRecord(
                agent_version_id=current.agent_version_id,
                application_id=current.application_id,
                version=current.version,
                status="published",
                config_snapshot=dict(current.config_snapshot),
                git_commit=current.git_commit,
                created_by=current.created_by,
                created_at=current.created_at,
                published_at=datetime.now(timezone.utc),
            )
            self._versions[agent_version_id] = published
            return published


@lru_cache(maxsize=1)
def get_application_repository() -> PostgresApplicationRepository:
    return PostgresApplicationRepository()
