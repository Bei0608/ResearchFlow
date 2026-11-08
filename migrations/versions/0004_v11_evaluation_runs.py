"""V1.1 persisted program evaluation runs and metrics."""

from alembic import op


revision = "0004_v11"
down_revision = "0003_v11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_evaluation_runs (
            run_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL REFERENCES
                researchflow_workspaces(workspace_id) ON DELETE CASCADE,
            agent_version_id TEXT NOT NULL REFERENCES
                researchflow_agent_versions(agent_version_id) ON DELETE RESTRICT,
            dataset_version_id TEXT NOT NULL REFERENCES
                researchflow_evaluation_dataset_versions(dataset_version_id)
                ON DELETE RESTRICT,
            status TEXT NOT NULL DEFAULT 'created' CHECK (
                status IN ('created', 'running', 'ready_for_review', 'failed')
            ),
            trigger_type TEXT NOT NULL,
            config_snapshot JSONB NOT NULL,
            git_commit TEXT,
            created_by TEXT NOT NULL REFERENCES
                researchflow_users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            error TEXT
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_researchflow_runs_workspace
        ON researchflow_evaluation_runs(workspace_id, created_at)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_case_results (
            case_result_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES
                researchflow_evaluation_runs(run_id) ON DELETE CASCADE,
            case_id TEXT NOT NULL REFERENCES
                researchflow_evaluation_cases(case_id) ON DELETE RESTRICT,
            status TEXT NOT NULL CHECK (
                status IN ('succeeded', 'failed', 'skipped')
            ),
            output_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            evidence_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            trace_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            latency_ms INTEGER CHECK (latency_ms IS NULL OR latency_ms >= 0),
            token_usage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (run_id, case_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_program_metrics (
            program_metric_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES
                researchflow_evaluation_runs(run_id) ON DELETE CASCADE,
            case_result_id TEXT REFERENCES
                researchflow_case_results(case_result_id) ON DELETE CASCADE,
            source TEXT NOT NULL DEFAULT 'program' CHECK (source = 'program'),
            evaluator_key TEXT NOT NULL,
            evaluator_version TEXT NOT NULL,
            metric_key TEXT NOT NULL,
            value DOUBLE PRECISION NOT NULL,
            details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (case_result_id, evaluator_key, evaluator_version, metric_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_researchflow_metrics_run
        ON researchflow_program_metrics(run_id, metric_key)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS researchflow_program_metrics")
    op.execute("DROP TABLE IF EXISTS researchflow_case_results")
    op.execute("DROP TABLE IF EXISTS researchflow_evaluation_runs")
