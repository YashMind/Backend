"""Create chatbot sharing table

Revision ID: create_chatbot_sharing
Revises: 7ab0bbb0fcc5
Create Date: 2023-07-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'create_chatbot_sharing'
down_revision: Union[str, None] = '7ab0bbb0fcc5'  # Update this to your latest migration
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create chatbot_sharing table
    op.create_table(
        'chatbot_sharing',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('bot_id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('shared_user_id', sa.Integer(), nullable=True),
        sa.Column('shared_email', sa.String(length=255), nullable=True),
        sa.Column('invite_token', sa.String(length=255), nullable=True, unique=True),
        sa.Column('status', sa.Enum('pending', 'active', 'revoked', name='sharing_status_enum'), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(['bot_id'], ['chat_bots.id'], ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['shared_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        mysql_collate='utf8mb4_general_ci',
        mysql_default_charset='utf8mb4',
        mysql_engine='InnoDB'
    )

    # Create index on bot_id and shared_user_id for faster lookups
    op.create_index('ix_chatbot_sharing_bot_id', 'chatbot_sharing', ['bot_id'], unique=False)
    op.create_index('ix_chatbot_sharing_shared_user_id', 'chatbot_sharing', ['shared_user_id'], unique=False)
    op.create_index('ix_chatbot_sharing_shared_email', 'chatbot_sharing', ['shared_email'], unique=False)
    op.create_index('ix_chatbot_sharing_invite_token', 'chatbot_sharing', ['invite_token'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index('ix_chatbot_sharing_invite_token', table_name='chatbot_sharing')
    op.drop_index('ix_chatbot_sharing_shared_email', table_name='chatbot_sharing')
    op.drop_index('ix_chatbot_sharing_shared_user_id', table_name='chatbot_sharing')
    op.drop_index('ix_chatbot_sharing_bot_id', table_name='chatbot_sharing')

    # Drop table
    op.drop_table('chatbot_sharing')
