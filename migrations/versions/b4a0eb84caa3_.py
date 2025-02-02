"""empty message

Revision ID: b4a0eb84caa3
Revises: 
Create Date: 2024-12-20 02:10:24.849997

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'b4a0eb84caa3'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('customers', schema=None) as batch_op:
        batch_op.alter_column('first_name',
               existing_type=sa.VARCHAR(length=50),
               nullable=False,
               existing_server_default=sa.text("'N/A'::character varying"))
        batch_op.alter_column('last_name',
               existing_type=sa.VARCHAR(length=50),
               nullable=False,
               existing_server_default=sa.text("'N/A'::character varying"))
        batch_op.alter_column('email',
               existing_type=sa.VARCHAR(length=255),
               nullable=False,
               existing_server_default=sa.text('NULL::character varying'))

    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('company_id', sa.UUID(), nullable=True))
        batch_op.add_column(sa.Column('customer_id', sa.UUID(), nullable=True))
        batch_op.add_column(sa.Column('payment_type', postgresql.ENUM('service_plan', 'installation', 'equipment', 'late_fee', 'upgrade', 'reconnection', 'add_on', 'refund', name='payment_type'), nullable=False))
        batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))
        batch_op.drop_constraint('payments_invoice_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(None, 'companies', ['company_id'], ['id'])
        batch_op.create_foreign_key(None, 'customers', ['customer_id'], ['id'])
        batch_op.drop_column('invoice_id')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('employee_id')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('employee_id', sa.UUID(), autoincrement=False, nullable=True))

    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('invoice_id', sa.UUID(), autoincrement=False, nullable=True))
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.create_foreign_key('payments_invoice_id_fkey', 'invoices', ['invoice_id'], ['id'])
        batch_op.drop_column('description')
        batch_op.drop_column('payment_type')
        batch_op.drop_column('customer_id')
        batch_op.drop_column('company_id')

    with op.batch_alter_table('customers', schema=None) as batch_op:
        batch_op.alter_column('email',
               existing_type=sa.VARCHAR(length=255),
               nullable=True,
               existing_server_default=sa.text('NULL::character varying'))
        batch_op.alter_column('last_name',
               existing_type=sa.VARCHAR(length=50),
               nullable=True,
               existing_server_default=sa.text("'N/A'::character varying"))
        batch_op.alter_column('first_name',
               existing_type=sa.VARCHAR(length=50),
               nullable=True,
               existing_server_default=sa.text("'N/A'::character varying"))

    # ### end Alembic commands ###
