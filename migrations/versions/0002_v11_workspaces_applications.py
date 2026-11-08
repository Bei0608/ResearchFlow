"""V1.1 workspaces, applications and immutable agent versions."""

from alembic import op


revision = "0002_v11"
down_revision = "0001_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_workspaces (
            workspace_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            owner_id TEXT NOT NULL REFERENCES
                researchflow_users(user_id) ON DELETE CASCADE,
            is_personal BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            uq_researchflow_personal_workspace_owner
        ON researchflow_workspaces(owner_id)
        WHERE is_personal
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_workspace_members (
            workspace_id TEXT NOT NULL REFERENCES
                researchflow_workspaces(workspace_id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES
                researchflow_users(user_id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('owner', 'reviewer')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (workspace_id, user_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_researchflow_workspace_members_user
        ON researchflow_workspace_members(user_id, workspace_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_applications (
            application_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL REFERENCES
                researchflow_workspaces(workspace_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            target_type TEXT NOT NULL CHECK (
                target_type IN ('internal', 'api', 'mcp')
            ),
            created_by TEXT NOT NULL REFERENCES
                researchflow_users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (workspace_id, name)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_researchflow_applications_workspace
        ON researchflow_applications(workspace_id, created_at)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_agent_versions (
            agent_version_id TEXT PRIMARY KEY,
            application_id TEXT NOT NULL REFERENCES
                researchflow_applications(application_id) ON DELETE CASCADE,
            version TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft' CHECK (
                status IN ('draft', 'published')
            ),
            config_snapshot JSONB NOT NULL,
            git_commit TEXT,
            created_by TEXT NOT NULL REFERENCES
                researchflow_users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            published_at TIMESTAMPTZ,
            UNIQUE (application_id, version)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_researchflow_agent_versions_app
        ON researchflow_agent_versions(application_id, created_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS researchflow_agent_versions")
    op.execute("DROP TABLE IF EXISTS researchflow_applications")
    op.execute("DROP TABLE IF EXISTS researchflow_workspace_members")
    op.execute("DROP TABLE IF EXISTS researchflow_workspaces")
