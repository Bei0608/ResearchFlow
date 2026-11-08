"""V1.1 aggregate metrics and generated reports."""

from alembic import op


revision = "0006_v11"
down_revision = "0005_v11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_aggregate_metrics (
            aggregate_metric_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES
                researchflow_evaluation_runs(run_id) ON DELETE CASCADE,
            source TEXT NOT NULL CHECK (source IN ('program', 'human')),
            namespace_key TEXT NOT NULL,
            metric_key TEXT NOT NULL,
            value DOUBLE PRECISION,
            sample_count INTEGER NOT NULL CHECK (sample_count >= 0),
            missing_count INTEGER NOT NULL CHECK (missing_count >= 0),
            pass_count INTEGER CHECK (pass_count IS NULL OR pass_count >= 0),
            pass_rate DOUBLE PRECISION CHECK (
                pass_rate IS NULL OR (pass_rate >= 0 AND pass_rate <= 1)
            ),
            details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (run_id, source, namespace_key, metric_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_researchflow_aggregates_run
        ON researchflow_aggregate_metrics(run_id, source)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_reports (
            report_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES
                researchflow_evaluation_runs(run_id) ON DELETE CASCADE,
            format TEXT NOT NULL CHECK (format IN ('json', 'html')),
            status TEXT NOT NULL DEFAULT 'generating' CHECK (
                status IN ('generating', 'completed', 'failed')
            ),
            storage_path TEXT,
            content_hash TEXT,
            generated_at TIMESTAMPTZ,
            error TEXT,
            created_by TEXT NOT NULL REFERENCES
                researchflow_users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (
                (status = 'completed' AND storage_path IS NOT NULL
                    AND content_hash IS NOT NULL AND generated_at IS NOT NULL
                    AND error IS NULL)
                OR status <> 'completed'
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_researchflow_reports_run
        ON researchflow_reports(run_id, created_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS researchflow_reports")
    op.execute("DROP TABLE IF EXISTS researchflow_aggregate_metrics")
