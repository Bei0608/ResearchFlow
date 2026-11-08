"""V1.1 versioned evaluation datasets and rubrics."""

from alembic import op


revision = "0003_v11"
down_revision = "0002_v11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_evaluation_datasets (
            dataset_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL REFERENCES
                researchflow_workspaces(workspace_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL REFERENCES
                researchflow_users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (workspace_id, name)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_evaluation_dataset_versions (
            dataset_version_id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL REFERENCES
                researchflow_evaluation_datasets(dataset_id) ON DELETE CASCADE,
            version TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft' CHECK (
                status IN ('draft', 'published', 'archived')
            ),
            schema_version TEXT NOT NULL,
            environment TEXT NOT NULL CHECK (environment IN ('demo', 'test', 'production')),
            content_hash TEXT,
            created_by TEXT NOT NULL REFERENCES
                researchflow_users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            published_at TIMESTAMPTZ,
            UNIQUE (dataset_id, version)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_researchflow_dataset_content
        ON researchflow_evaluation_dataset_versions(dataset_id, content_hash)
        WHERE content_hash IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_evaluation_cases (
            case_id TEXT PRIMARY KEY,
            dataset_version_id TEXT NOT NULL REFERENCES
                researchflow_evaluation_dataset_versions(dataset_version_id)
                ON DELETE CASCADE,
            external_id TEXT NOT NULL,
            input_json JSONB NOT NULL,
            expected_json JSONB NOT NULL,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (dataset_version_id, external_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_rubrics (
            rubric_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL REFERENCES
                researchflow_workspaces(workspace_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL REFERENCES
                researchflow_users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (workspace_id, name)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_rubric_versions (
            rubric_version_id TEXT PRIMARY KEY,
            rubric_id TEXT NOT NULL REFERENCES
                researchflow_rubrics(rubric_id) ON DELETE CASCADE,
            version TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft' CHECK (
                status IN ('draft', 'published', 'archived')
            ),
            schema_version TEXT NOT NULL,
            environment TEXT NOT NULL CHECK (environment IN ('demo', 'test', 'production')),
            instructions TEXT NOT NULL DEFAULT '',
            content_hash TEXT,
            created_by TEXT NOT NULL REFERENCES
                researchflow_users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            published_at TIMESTAMPTZ,
            UNIQUE (rubric_id, version)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_researchflow_rubric_content
        ON researchflow_rubric_versions(rubric_id, content_hash)
        WHERE content_hash IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_rubric_criteria (
            criterion_id TEXT PRIMARY KEY,
            rubric_version_id TEXT NOT NULL REFERENCES
                researchflow_rubric_versions(rubric_version_id)
                ON DELETE CASCADE,
            criterion_key TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            min_score NUMERIC NOT NULL,
            max_score NUMERIC NOT NULL,
            weight NUMERIC NOT NULL CHECK (weight > 0),
            required BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (max_score > min_score),
            UNIQUE (rubric_version_id, criterion_key)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS researchflow_rubric_criteria")
    op.execute("DROP TABLE IF EXISTS researchflow_rubric_versions")
    op.execute("DROP TABLE IF EXISTS researchflow_rubrics")
    op.execute("DROP TABLE IF EXISTS researchflow_evaluation_cases")
    op.execute("DROP TABLE IF EXISTS researchflow_evaluation_dataset_versions")
    op.execute("DROP TABLE IF EXISTS researchflow_evaluation_datasets")
