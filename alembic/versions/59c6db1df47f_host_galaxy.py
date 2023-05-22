"""Host galaxy migration

Revision ID: 59c6db1df47f
Revises: fd92295c50ed
Create Date: 2023-05-14 22:02:21.351589

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '59c6db1df47f'
down_revision = 'fd92295c50ed'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('objs', sa.Column('host_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        None, 'objs', 'galaxys', ['host_id'], ['id'], ondelete='CASCADE'
    )
    op.add_column(
        'sourcesconfirmedingcns',
        sa.Column('confirmer_id', sa.Integer(), nullable=False),
    )
    op.add_column(
        'sourcesconfirmedingcns', sa.Column('notes', sa.String(), nullable=True)
    )
    op.alter_column(
        'sourcesconfirmedingcns', 'confirmed', existing_type=sa.BOOLEAN(), nullable=True
    )
    op.create_index(
        op.f('ix_sourcesconfirmedingcns_confirmer_id'),
        'sourcesconfirmedingcns',
        ['confirmer_id'],
        unique=False,
    )
    op.create_foreign_key(
        None,
        'sourcesconfirmedingcns',
        'users',
        ['confirmer_id'],
        ['id'],
        ondelete='CASCADE',
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'sourcesconfirmedingcns', type_='foreignkey')
    op.drop_index(
        op.f('ix_sourcesconfirmedingcns_confirmer_id'),
        table_name='sourcesconfirmedingcns',
    )
    op.alter_column(
        'sourcesconfirmedingcns',
        'confirmed',
        existing_type=sa.BOOLEAN(),
        nullable=False,
    )
    op.drop_column('sourcesconfirmedingcns', 'notes')
    op.drop_column('sourcesconfirmedingcns', 'confirmer_id')
    op.drop_constraint(None, 'objs', type_='foreignkey')
    op.drop_column('objs', 'host_id')
    # ### end Alembic commands ###