"""Rename the second demo patient while preserving their history."""

from alembic import op
from sqlalchemy import text

revision = "0004_rename_patient"
down_revision = "0003_explained_alerts"


def rename(previous: str, updated: str) -> None:
    op.get_bind().execute(text(
        "UPDATE patients SET display_name = :updated "
        "WHERE id = '20000000-0000-0000-0000-000000000002' "
        "AND display_name = :previous"
    ), {"updated": updated, "previous": previous})


def upgrade() -> None:
    rename("Jon Ellis", "Aryan")


def downgrade() -> None:
    rename("Aryan", "Jon Ellis")
