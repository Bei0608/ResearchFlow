"""V1.1 active baselines, versioned gate policies and evaluations."""

from alembic import op


revision = "0007_v11"
down_revision = "0006_v11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_baselines (
            baseline_id TEXT PRIMARY KEY,
            application_id TEXT NOT NULL REFERENCES
                researchflow_applications(application_id) ON DELETE CASCADE,
            run_id TEXT NOT NULL REFERENCES
                researchflow_evaluation_runs(run_id) ON DELETE RESTRICT,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            activated_by TEXT NOT NULL REFERENCES
                researchflow_users(user_id) ON DELETE RESTRICT,
            activated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deactivated_at TIMESTAMPTZ,
            UNIQUE (application_id, run_id)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_researchflow_active_baseline
        ON researchflow_baselines(application_id) WHERE active
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_gate_policies (
            policy_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL REFERENCES
                researchflow_workspaces(workspace_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            version TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft' CHECK (
                status IN ('draft', 'published')
            ),
            rules_json JSONB NOT NULL,
            created_by TEXT NOT NULL REFERENCES
                researchflow_users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            published_at TIMESTAMPTZ,
            UNIQUE (workspace_id, name, version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_gate_evaluations (
            gate_evaluation_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES
                researchflow_evaluation_runs(run_id) ON DELETE CASCADE,
            baseline_run_id TEXT REFERENCES
                researchflow_evaluation_runs(run_id) ON DELETE RESTRICT,
            policy_id TEXT NOT NULL REFERENCES
                researchflow_gate_policies(policy_id) ON DELETE RESTRICT,
            status TEXT NOT NULL CHECK (
                status IN ('passed', 'failed', 'incomplete')
            ),
            results_json JSONB NOT NULL,
            evaluated_by TEXT NOT NULL REFERENCES
                researchflow_users(user_id) ON DELETE RESTRICT,
            evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_researchflow_gate_evaluations_run
        ON researchflow_gate_evaluations(run_id, evaluated_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS researchflow_gate_evaluations")
    op.execute("DROP TABLE IF EXISTS researchflow_gate_policies")
    op.execute("DROP TABLE IF EXISTS researchflow_baselines")
