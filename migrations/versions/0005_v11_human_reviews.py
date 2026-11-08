"""V1.1 human review tasks, revisions and scores."""

from alembic import op


revision = "0005_v11"
down_revision = "0004_v11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_review_tasks (
            task_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES
                researchflow_evaluation_runs(run_id) ON DELETE CASCADE,
            rubric_version_id TEXT NOT NULL REFERENCES
                researchflow_rubric_versions(rubric_version_id) ON DELETE RESTRICT,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open' CHECK (
                status IN ('open', 'completed')
            ),
            created_by TEXT NOT NULL REFERENCES
                researchflow_users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            UNIQUE (run_id, name)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_review_assignments (
            assignment_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES
                researchflow_review_tasks(task_id) ON DELETE CASCADE,
            reviewer_id TEXT NOT NULL REFERENCES
                researchflow_users(user_id) ON DELETE RESTRICT,
            status TEXT NOT NULL DEFAULT 'assigned' CHECK (
                status IN ('assigned', 'in_progress', 'completed')
            ),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            UNIQUE (task_id, reviewer_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_researchflow_assignments_reviewer
        ON researchflow_review_assignments(reviewer_id, status, created_at)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_reviews (
            review_id TEXT PRIMARY KEY,
            assignment_id TEXT NOT NULL REFERENCES
                researchflow_review_assignments(assignment_id) ON DELETE CASCADE,
            case_result_id TEXT NOT NULL REFERENCES
                researchflow_case_results(case_result_id) ON DELETE RESTRICT,
            latest_revision INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending' CHECK (
                status IN ('pending', 'draft', 'submitted')
            ),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (assignment_id, case_result_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_review_revisions (
            revision_id TEXT PRIMARY KEY,
            review_id TEXT NOT NULL REFERENCES
                researchflow_reviews(review_id) ON DELETE CASCADE,
            revision INTEGER NOT NULL,
            status TEXT NOT NULL CHECK (
                status IN ('draft', 'submitted', 'superseded')
            ),
            overall_comment TEXT NOT NULL DEFAULT '',
            reason TEXT,
            idempotency_key TEXT,
            created_by TEXT NOT NULL REFERENCES
                researchflow_users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            submitted_at TIMESTAMPTZ,
            UNIQUE (review_id, revision),
            UNIQUE (review_id, idempotency_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS researchflow_human_scores (
            score_id TEXT PRIMARY KEY,
            revision_id TEXT NOT NULL REFERENCES
                researchflow_review_revisions(revision_id) ON DELETE CASCADE,
            criterion_id TEXT NOT NULL REFERENCES
                researchflow_rubric_criteria(criterion_id) ON DELETE RESTRICT,
            score DOUBLE PRECISION NOT NULL,
            comment TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (revision_id, criterion_id)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS researchflow_human_scores")
    op.execute("DROP TABLE IF EXISTS researchflow_review_revisions")
    op.execute("DROP TABLE IF EXISTS researchflow_reviews")
    op.execute("DROP TABLE IF EXISTS researchflow_review_assignments")
    op.execute("DROP TABLE IF EXISTS researchflow_review_tasks")
