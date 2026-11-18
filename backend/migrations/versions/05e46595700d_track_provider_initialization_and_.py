"""Track provider initialization and message delivery."""

import sqlalchemy as sa
from alembic import op

revision = "05e46595700d"
down_revision = "df970bcb7889"
branch_labels = None
depends_on = None


def upgrade():
    """Apply this schema revision."""
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("external_id", sa.String(200)))
        batch.create_unique_constraint(
            "uq_notifications_external_id", ["external_id"]
        )
    with op.batch_alter_table("payments") as batch:
        batch.add_column(
            sa.Column(
                "provider_attempts",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column(
                "provider_error",
                sa.String(200),
                nullable=False,
                server_default="",
            )
        )


def downgrade():
    """Reverse this schema revision."""
    with op.batch_alter_table("payments") as batch:
        batch.drop_column("provider_error")
        batch.drop_column("provider_attempts")
    with op.batch_alter_table("notifications") as batch:
        batch.drop_constraint("uq_notifications_external_id", type_="unique")
        batch.drop_column("external_id")
