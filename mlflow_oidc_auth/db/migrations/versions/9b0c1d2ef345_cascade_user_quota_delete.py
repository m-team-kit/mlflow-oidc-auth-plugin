"""cascade_user_quota_delete

Revision ID: 9b0c1d2ef345
Revises: 8a9b0c1de234
Create Date: 2026-10-02 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "9b0c1d2ef345"
down_revision = "8a9b0c1de234"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove quota rows left behind by users deleted before this migration.
    op.execute("DELETE FROM user_quotas WHERE user_id NOT IN (SELECT id FROM users)")

    with op.batch_alter_table("user_quotas") as batch_op:
        batch_op.drop_constraint("fk_user_quota_user_id", type_="foreignkey")
        batch_op.create_foreign_key("fk_user_quota_user_id", "users", ["user_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    with op.batch_alter_table("user_quotas") as batch_op:
        batch_op.drop_constraint("fk_user_quota_user_id", type_="foreignkey")
        batch_op.create_foreign_key("fk_user_quota_user_id", "users", ["user_id"], ["id"])
