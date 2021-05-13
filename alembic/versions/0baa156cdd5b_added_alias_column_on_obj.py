"""added alias column on obj

Revision ID: 0baa156cdd5b
Revises: d8a478c3d94c
Create Date: 2021-05-13 21:19:18.256737

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0baa156cdd5b'
down_revision = 'd8a478c3d94c'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('objs', sa.Column('alias', sa.ARRAY(sa.String()), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('objs', 'alias')
    # ### end Alembic commands ###
