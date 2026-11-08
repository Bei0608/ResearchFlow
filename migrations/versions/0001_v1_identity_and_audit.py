"""V1 identity, refresh sessions, thread ownership and audit events."""

from alembic import op


revision = "0001_v1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
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
    op.execute(
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
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_researchflow_refresh_tokens_user_id
        ON researchflow_refresh_tokens(user_id)
        """
    )
    op.execute(
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
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_researchflow_threads_user_id
        ON researchflow_threads(user_id)
        """
    )
    op.execute(
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
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_researchflow_audit_user_created
        ON researchflow_audit_events(user_id, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS researchflow_audit_events")
    op.execute("DROP TABLE IF EXISTS researchflow_threads")
    op.execute("DROP TABLE IF EXISTS researchflow_refresh_tokens")
    op.execute("DROP TABLE IF EXISTS researchflow_users")
