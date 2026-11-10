"""merge upstream and fork quota branches

Revision ID: f1a2b3c4d5e6
Revises: e1f2a3b4c5d6, 9b0c1d2ef345
Create Date: 2026-11-10 12:00:00.000000

Fork-only. The fork's quota migrations (add_quota, cascade_user_quota_delete) branched from
upstream's chain at add_workspace_regex_permissions. This joins the two heads so a fork database
(at cascade_user_quota_delete) picks up upstream's later migrations, and a fresh database gets both.
No schema changes.
"""

# revision identifiers, used by Alembic.
revision = "f1a2b3c4d5e6"
down_revision = ("e1f2a3b4c5d6", "9b0c1d2ef345")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
