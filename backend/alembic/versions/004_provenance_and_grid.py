"""Add provenance and model identity metadata without changing existing tables."""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("sea_ice_forecasts", sa.Column("provenance", sa.JSON(), nullable=True))
    op.add_column("sea_ice_forecasts", sa.Column("model_id", sa.String(100), nullable=True))
    op.add_column("sea_ice_forecasts", sa.Column("model_hash", sa.String(128), nullable=True))
    op.add_column("iceberg_trajectory_predictions", sa.Column("provenance", sa.JSON(), nullable=True))
    op.add_column("iceberg_trajectory_predictions", sa.Column("model_id", sa.String(100), nullable=True))
    op.add_column("iceberg_trajectory_predictions", sa.Column("model_hash", sa.String(128), nullable=True))
    op.add_column("iceberg_positions", sa.Column("source_kind", sa.String(20), nullable=False, server_default="live"))

def downgrade():
    op.drop_column("iceberg_positions", "source_kind")
    op.drop_column("iceberg_trajectory_predictions", "model_hash")
    op.drop_column("iceberg_trajectory_predictions", "model_id")
    op.drop_column("iceberg_trajectory_predictions", "provenance")
    op.drop_column("sea_ice_forecasts", "model_hash")
    op.drop_column("sea_ice_forecasts", "model_id")
    op.drop_column("sea_ice_forecasts", "provenance")
