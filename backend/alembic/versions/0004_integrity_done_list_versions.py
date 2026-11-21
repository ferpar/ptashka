"""integrity done list versions

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-21 11:15:30.011153

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Reordered by hand: autogenerate emitted the composite foreign key before the unique
    # constraint it references, which Postgres rejects.

    # 1. Lists: the done flag, and the (id, board_id) key that cards will reference.
    op.add_column('lists', sa.Column('is_done', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.create_unique_constraint('uq_lists_id_board', 'lists', ['id', 'board_id'])

    # 2. Data migration: boards created before this had a "Done" list without the flag.
    #    Flag one per board (the oldest, should a board have several) before the unique index exists.
    op.execute("""
        UPDATE lists SET is_done = true
        WHERE id IN (SELECT MIN(id) FROM lists WHERE name = 'Done' GROUP BY board_id)
    """)
    #    Cards already sitting in a done list count as completed. updated_at is the best
    #    guess for when that happened.
    op.execute("""
        UPDATE cards SET completed_at = updated_at
        WHERE completed_at IS NULL AND list_id IN (SELECT id FROM lists WHERE is_done)
    """)
    op.create_index('uq_lists_one_done_per_board', 'lists', ['board_id'], unique=True, postgresql_where=sa.text('is_done'), sqlite_where=sa.text('is_done'))

    # 3. Cards: swap the plain list foreign key for the composite one, and add the version counter.
    op.drop_constraint(op.f('cards_list_id_fkey'), 'cards', type_='foreignkey')
    op.create_foreign_key('fk_cards_list_board', 'cards', 'lists', ['list_id', 'board_id'], ['id', 'board_id'], onupdate='CASCADE', ondelete='CASCADE')
    op.add_column('cards', sa.Column('version', sa.Integer(), server_default='1', nullable=False))


def downgrade() -> None:
    # Exactly the reverse of upgrade(): the composite foreign key must go before the unique
    # constraint it depends on. (The data migration isn't undone: completed_at values stay.)
    op.drop_column('cards', 'version')
    op.drop_constraint('fk_cards_list_board', 'cards', type_='foreignkey')
    op.create_foreign_key(op.f('cards_list_id_fkey'), 'cards', 'lists', ['list_id'], ['id'], ondelete='CASCADE')
    op.drop_index('uq_lists_one_done_per_board', table_name='lists', postgresql_where=sa.text('is_done'), sqlite_where=sa.text('is_done'))
    op.drop_constraint('uq_lists_id_board', 'lists', type_='unique')
    op.drop_column('lists', 'is_done')
