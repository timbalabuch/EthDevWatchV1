"""Add forum discussions columns

Revision ID: add_forum_discussions
Create Date: 2024-12-25
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    # Add magicians_discussions and ethresearch_discussions columns
    op.add_column('article', sa.Column('magicians_discussions', sa.Text(), nullable=True))
    op.add_column('article', sa.Column('ethresearch_discussions', sa.Text(), nullable=True))

def downgrade():
    # Remove the columns
    op.drop_column('article', 'magicians_discussions')
    op.drop_column('article', 'ethresearch_discussions')