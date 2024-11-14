"""Initial migration

Revision ID: d6b34574109e
Revises: 
Create Date: 2024-10-30 17:02:55.206302

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd6b34574109e'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_foreign_key(None, 'annotation', 'task', ['task_id'], ['task_id'])
    op.alter_column('task', 'exported_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               server_default=sa.text('null'),
               existing_nullable=True)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('task', 'exported_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               server_default=None,
               existing_nullable=True)
    op.drop_constraint(None, 'annotation', type_='foreignkey')
    # ### end Alembic commands ###