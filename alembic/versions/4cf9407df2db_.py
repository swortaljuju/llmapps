"""empty message

Revision ID: 4cf9407df2db
Revises: 15290dcc3b84
Create Date: 2025-04-17 21:29:42.602049

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text  # Add this import
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4cf9407df2db'
down_revision: Union[str, None] = '15290dcc3b84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('news_entries',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('rss_feed_id', sa.Integer(), nullable=True),
    sa.Column('entry_rss_guid', sa.String(), nullable=True),
    sa.Column('entry_url', sa.String(), nullable=True),
    sa.Column('crawl_time', sa.DateTime(), nullable=True),
    sa.Column('title', sa.String(), nullable=True),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('content', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_news_entries_entry_rss_guid'), 'news_entries', ['entry_rss_guid'], unique=True)
    op.create_index(op.f('ix_news_entries_id'), 'news_entries', ['id'], unique=False)
    op.create_table('news_preference_versions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('previous_version_id', sa.Integer(), nullable=True),
    sa.Column('content', sa.String(), nullable=True),
    sa.Column('cause', sa.Enum('survey', 'user_edit', 'news_click', name='newspreferencechangecause'), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_news_preference_versions_id'), 'news_preference_versions', ['id'], unique=False)
    op.create_table('news_summaries',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_news_summaries_id'), 'news_summaries', ['id'], unique=False)
    op.create_table('rss_feeds',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('feed_url', sa.String(), nullable=True),
    sa.Column('last_crawl_time', sa.DateTime(), nullable=True),
    sa.Column('title', sa.String(), nullable=True),
    sa.Column('html_url', sa.String(), nullable=True),
    sa.Column('xml_url', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_rss_feeds_feed_url'), 'rss_feeds', ['feed_url'], unique=True)
    op.create_index(op.f('ix_rss_feeds_id'), 'rss_feeds', ['id'], unique=False)
    op.add_column('users', sa.Column('news_preference', sa.String(), nullable=True))
    op.add_column('users', sa.Column('current_news_preference_version_id', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('subscribed_rss_feeds_id', postgresql.ARRAY(sa.Integer()), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('users', 'subscribed_rss_feeds_id')
    op.drop_column('users', 'current_news_preference_version_id')
    op.drop_column('users', 'news_preference')
    op.drop_index(op.f('ix_rss_feeds_id'), table_name='rss_feeds')
    op.drop_index(op.f('ix_rss_feeds_feed_url'), table_name='rss_feeds')
    op.drop_table('rss_feeds')
    op.drop_index(op.f('ix_news_summaries_id'), table_name='news_summaries')
    op.drop_table('news_summaries')
    op.drop_index(op.f('ix_news_preference_versions_id'), table_name='news_preference_versions')
    op.drop_table('news_preference_versions')
    op.drop_index(op.f('ix_news_entries_id'), table_name='news_entries')
    op.drop_index(op.f('ix_news_entries_entry_rss_guid'), table_name='news_entries')
    op.drop_table('news_entries')
    # ### end Alembic commands ###
