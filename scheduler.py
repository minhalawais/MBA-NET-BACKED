from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import logging
from app import db
from app.models import Customer, Invoice, ServicePlan
from app.crud.invoice_crud import generate_invoice_number, add_invoice
import uuid
from app.utils.backup_utils import PostgreSQLBackupManager  # Updated import
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None

def generate_automatic_invoices(app=None):
    """
    Generate invoices for customers whose recharge date is today.
    This function runs daily and checks all active customers.
    
    Args:
        app: Flask application instance for creating application context
    """
    logger.info(f"Running automatic invoice generation for date: {datetime.now().date()}")
    
    if app:
        with app.app_context():
            _process_invoices()
    else:
        logger.error("No Flask app provided to generate_automatic_invoices")

def _process_invoices():
    """
    Internal function to process invoices within an application context
    """
    today = datetime.now().date()
    
    try:
        # Get all active customers whose recharge date is today
        customers = Customer.query.filter(
            Customer.is_active == True,
            Customer.recharge_date != None,
            db.func.extract('day', Customer.recharge_date) == today.day,
            db.func.extract('month', Customer.recharge_date) == today.month
        ).all()
        
        logger.info(f"Found {len(customers)} customers with recharge date today")
        
        # Check if invoices have already been generated this month for these customers
        current_month_start = datetime(today.year, today.month, 1).date()
        next_month_start = (datetime(today.year, today.month, 1) + timedelta(days=32)).replace(day=1).date()
        
        invoice_count = 0
        
        for customer in customers:
            # Check if an invoice already exists for this customer in the current month
            existing_invoice = Invoice.query.filter(
                Invoice.customer_id == customer.id,
                Invoice.billing_start_date >= current_month_start,
                Invoice.billing_start_date < next_month_start,
                Invoice.invoice_type == 'subscription'
            ).first()
            
            if existing_invoice:
                logger.info(f"Invoice already exists for customer {customer.id} ({customer.first_name} {customer.last_name}) this month")
                continue
            
            try:
                # Get the customer's service plan
                service_plan = ServicePlan.query.get(customer.service_plan_id)
                if not service_plan:
                    logger.error(f"Service plan not found for customer {customer.id}")
                    continue
                
                # Calculate billing period
                billing_start_date = today
                # Calculate the end date (same day next month - 1 day)
                next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
                billing_end_date = (next_month - timedelta(days=1))
                
                # Calculate due date (7 days from today)
                due_date = today + timedelta(days=7)
                
                # Calculate amounts
                subtotal = float(service_plan.price)
                discount_percentage = 0
                if customer.discount_amount:
                    discount_percentage = (float(customer.discount_amount) / subtotal) * 100
                
                total_amount = subtotal - (subtotal * discount_percentage / 100)
                
                # Create invoice data
                invoice_data = {
                    'company_id': str(customer.company_id),
                    'customer_id': str(customer.id),
                    'billing_start_date': billing_start_date.isoformat(),
                    'billing_end_date': billing_end_date.isoformat(),
                    'due_date': due_date.isoformat(),
                    'subtotal': subtotal,
                    'discount_percentage': discount_percentage,
                    'total_amount': total_amount,
                    'invoice_type': 'subscription',
                    'notes': f"Automatically generated invoice for {service_plan.name} plan"
                }
                
                # Use the system user ID for generated_by
                system_user_id = "00000000-0000-0000-0000-000000000000"  # Replace with your actual system user ID
                
                # Add the invoice
                new_invoice = add_invoice(
                    invoice_data, 
                    system_user_id, 
                    'system', 
                    '127.0.0.1',  # IP address
                    'Automatic Invoice Generator'  # User agent
                )
                
                logger.info(f"Successfully generated invoice {new_invoice.invoice_number} for customer {customer.id} ({customer.first_name} {customer.last_name})")
                invoice_count += 1
                
            except Exception as e:
                logger.error(f"Error generating invoice for customer {customer.id}: {str(e)}")
        
        logger.info(f"Automatic invoice generation completed. Generated {invoice_count} invoices.")
    except Exception as e:
        logger.error(f"Error in invoice generation process: {str(e)}")

def create_daily_backup(app=None):
    """
    Create daily database backup using PostgreSQLBackupManager
    """
    logger.info(f"Running daily database backup: {datetime.now()}")
    
    if not app:
        logger.error("No Flask app provided to create_daily_backup")
        return
    
    with app.app_context():
        try:
            # Get the project root directory (parent of api folder)
            project_root = os.path.dirname(os.path.abspath(__file__))      # /api/app/utils
            app_root = os.path.dirname(os.path.dirname(project_root))      # /api
            backup_dir = os.path.join(app_root, 'database_backups')
            
            # Initialize the backup manager
            backup_manager = PostgreSQLBackupManager(app=app, backup_dir=backup_dir)
            
            # Test database connection first
            if not backup_manager.test_connection():
                logger.error("Database connection test failed. Backup aborted.")
                return
            
            # Create backups in both SQL and custom formats
            backup_files = backup_manager.create_backup(formats=['sql', 'custom'])
            
            if backup_files:
                logger.info(f"Daily backup completed successfully. Files created: {backup_files}")
                
                # List current backups
                backups = backup_manager.list_backups()
                logger.info(f"Current backup count: {len(backups)}")
                
                # Cleanup old backups (keep last 30)
                backup_manager.cleanup_old_backups(keep_last=30)
                
            else:
                logger.error("Daily backup failed - no backup files were created")
                
        except Exception as e:
            logger.error(f"Error in daily backup process: {str(e)}")

def create_weekly_backup(app=None):
    """
    Create weekly compressed backup (runs every Sunday)
    """
    logger.info(f"Running weekly database backup: {datetime.now()}")
    
    if not app:
        logger.error("No Flask app provided to create_weekly_backup")
        return
    
    with app.app_context():
        try:
            # Get the project root directory
            project_root = os.path.dirname(os.path.abspath(__file__))
            app_root = os.path.dirname(os.path.dirname(project_root))
            backup_dir = os.path.join(app_root, 'weekly_backups')
            
            # Initialize the backup manager
            backup_manager = PostgreSQLBackupManager(app=app, backup_dir=backup_dir)
            
            # Test database connection first
            if not backup_manager.test_connection():
                logger.error("Database connection test failed. Weekly backup aborted.")
                return
            
            # Create custom format backup (more efficient for weekly)
            backup_files = backup_manager.create_backup(formats=['custom'])
            
            if backup_files:
                logger.info(f"Weekly backup completed successfully. Files created: {backup_files}")
                
                # Cleanup old weekly backups (keep last 8 = ~2 months)
                backup_manager.cleanup_old_backups(keep_last=8)
                
            else:
                logger.error("Weekly backup failed - no backup files were created")
                
        except Exception as e:
            logger.error(f"Error in weekly backup process: {str(e)}")

def cleanup_old_backups_job(app=None):
    """
    Job to specifically clean up old backups (runs monthly)
    """
    logger.info(f"Running backup cleanup job: {datetime.now()}")
    
    if not app:
        logger.error("No Flask app provided to cleanup_old_backups_job")
        return
    
    with app.app_context():
        try:
            # Cleanup daily backups
            project_root = os.path.dirname(os.path.abspath(__file__))
            app_root = os.path.dirname(os.path.dirname(project_root))
            
            daily_backup_dir = os.path.join(app_root, 'database_backups')
            weekly_backup_dir = os.path.join(app_root, 'weekly_backups')
            
            # Cleanup daily backups (keep last 30)
            daily_manager = PostgreSQLBackupManager(app=app, backup_dir=daily_backup_dir)
            daily_manager.cleanup_old_backups(keep_last=30)
            
            # Cleanup weekly backups (keep last 12 = ~3 months)
            weekly_manager = PostgreSQLBackupManager(app=app, backup_dir=weekly_backup_dir)
            weekly_manager.cleanup_old_backups(keep_last=12)
            
            logger.info("Backup cleanup job completed successfully")
            
        except Exception as e:
            logger.error(f"Error in backup cleanup job: {str(e)}")

def init_scheduler(app):
    """
    Initialize the background scheduler with the Flask app context.
    
    Args:
        app: Flask application instance
    """
    if not app:
        logger.error("No Flask app provided to init_scheduler")
        return
    
    global scheduler
    scheduler = BackgroundScheduler()

    
    # Daily Backup Job - Run daily at 1:30 AM (30 minutes after invoice generation)
    scheduler.add_job(
        func=create_daily_backup,
        args=[app],
        trigger=CronTrigger(hour=2, minute=1),
        id='daily_backup_job',
        name='Create daily database backup',
        replace_existing=True
    )
    
    # Weekly Backup Job - Run every Sunday at 2:00 AM
    scheduler.add_job(
        func=create_weekly_backup,
        args=[app],
        trigger=CronTrigger(day_of_week='sun', hour=2, minute=0),
        id='weekly_backup_job',
        name='Create weekly compressed backup',
        replace_existing=True
    )
    
    # Monthly Backup Cleanup Job - Run on 1st of every month at 3:00 AM
    scheduler.add_job(
        func=cleanup_old_backups_job,
        args=[app],
        trigger=CronTrigger(day=1, hour=3, minute=0),
        id='backup_cleanup_job',
        name='Cleanup old backups',
        replace_existing=True
    )
    
    # Start the scheduler
    scheduler.start()
    logger.info("Background scheduler started with jobs:")
    for job in scheduler.get_jobs():
        logger.info(f"  - {job.name} (next run: {job.next_run_time})")
    
    # Shut down the scheduler when the app is shutting down
    @app.teardown_appcontext
    def shutdown_scheduler(exception=None):
        if scheduler and scheduler.running:
            logger.info("Shutting down background scheduler...")
            scheduler.shutdown(wait=False)  # Do not wait for jobs to complete

def manual_backup(app, backup_type='daily'):
    """
    Manual backup function that can be called from routes or other parts of the application
    
    Args:
        app: Flask application instance
        backup_type: 'daily' or 'weekly'
    
    Returns:
        tuple: (success: bool, message: str, backup_files: list)
    """
    if not app:
        return False, "No Flask app provided", []
    
    try:
        with app.app_context():
            project_root = os.path.dirname(os.path.abspath(__file__))
            app_root = os.path.dirname(os.path.dirname(project_root))
            
            if backup_type == 'daily':
                backup_dir = os.path.join(app_root, 'database_backups')
                formats = ['sql', 'custom']
            else:  # weekly
                backup_dir = os.path.join(app_root, 'weekly_backups')
                formats = ['custom']
            
            backup_manager = PostgreSQLBackupManager(app=app, backup_dir=backup_dir)
            
            if not backup_manager.test_connection():
                return False, "Database connection test failed", []
            
            backup_files = backup_manager.create_backup(formats=formats)
            
            if backup_files:
                return True, f"{backup_type.capitalize()} backup created successfully", backup_files
            else:
                return False, f"{backup_type.capitalize()} backup failed", []
                
    except Exception as e:
        logger.error(f"Manual backup error: {str(e)}")
        return False, f"Backup error: {str(e)}", []

def list_backups(app, backup_type='daily'):
    """
    List available backups
    
    Args:
        app: Flask application instance
        backup_type: 'daily' or 'weekly'
    
    Returns:
        list: List of backup information dictionaries
    """
    if not app:
        return []
    
    try:
        with app.app_context():
            project_root = os.path.dirname(os.path.abspath(__file__))
            app_root = os.path.dirname(os.path.dirname(project_root))
            
            if backup_type == 'daily':
                backup_dir = os.path.join(app_root, 'database_backups')
            else:  # weekly
                backup_dir = os.path.join(app_root, 'weekly_backups')
            
            backup_manager = PostgreSQLBackupManager(app=app, backup_dir=backup_dir)
            return backup_manager.list_backups()
            
    except Exception as e:
        logger.error(f"Error listing backups: {str(e)}")
        return []