from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta, date
import logging
from app import db
from app.models import Customer, Invoice, ServicePlan
from app.crud.invoice_crud import generate_invoice_number, add_invoice
import uuid
from app.utils.backup_utils import PostgreSQLBackupManager  # Updated import
import os

# WhatsApp imports
from app.models import WhatsAppConfig
from app.services.whatsapp_queue_service import WhatsAppQueueService
from app.services.whatsapp_rate_limiter import WhatsAppRateLimiter
from app.services.whatsapp_api_client import WhatsAppAPIClient

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

def process_whatsapp_queue(app=None):
    """
    Process pending WhatsApp messages in queue.
    Sends up to remaining daily quota ordered by priority.
    Runs daily at configured time (default 9:00 AM).
    """
    logger.info(f"Running WhatsApp queue processor: {datetime.now()}")
    
    if not app:
        logger.error("No Flask app provided to process_whatsapp_queue")
        return
    
    with app.app_context():
        try:
            # Get all companies with WhatsApp configured
            configs = WhatsAppConfig.query.filter_by(auto_send_invoices=True).all()
            
            for config in configs:
                company_id = str(config.company_id)
                
                # Check remaining quota
                remaining = WhatsAppRateLimiter.get_remaining_quota(company_id)
                
                if remaining <= 0:
                    logger.info(f"Quota exhausted for company {company_id}")
                    continue
                
                # Get pending messages
                messages = WhatsAppQueueService.get_pending_messages(
                    limit=remaining,
                    company_id=company_id
                )
                
                logger.info(f"Processing {len(messages)} messages for company {company_id}")
                
                # Initialize API client
                client = WhatsAppAPIClient.from_config(company_id)
                
                sent_count = 0
                failed_count = 0
                
                for message in messages:
                    try:
                        # Send message based on media type
                        if message.media_type == 'document':
                            result = client.send_document_message(
                                mobile=message.mobile,
                                document_url=message.media_url,
                                caption=message.message_content,
                                priority=message.priority
                            )
                        elif message.media_type == 'image':
                            result = client.send_image_message(
                                mobile=message.mobile,
                                image_url=message.media_url,
                                caption=message.message_content,
                                priority=message.priority
                            )
                        else:  # text
                            result = client.send_text_message(
                                mobile=message.mobile,
                                message=message.message_content,
                                priority=message.priority
                            )
                        
                        if result['success']:
                            # Update message status to sent
                            WhatsAppQueueService.update_message_status(
                                message_id=str(message.id),
                                status='sent',
                                api_response=result.get('response')
                            )
                            
                            # Increment quota
                            WhatsAppRateLimiter.increment_sent_count(company_id)
                            sent_count += 1
                            
                        else:
                            # Update message status to failed
                            WhatsAppQueueService.update_message_status(
                                message_id=str(message.id),
                                status='failed',
                                error_message=result.get('error')
                            )
                            failed_count += 1
                        
                    except Exception as e:
                        logger.error(f"Error sending message {message.id}: {str(e)}")
                        WhatsAppQueueService.update_message_status(
                            message_id=str(message.id),
                            status='failed',
                            error_message=str(e)
                        )
                        failed_count += 1
                
                logger.info(f"Completed WhatsApp queue processing for company {company_id}: {sent_count} sent, {failed_count} failed")
            
        except Exception as e:
            logger.error(f"Error in WhatsApp queue processing: {str(e)}")

def check_deadline_alerts(app=None):
    """
    Check for invoices with upcoming due dates and enqueue alert messages.
    Runs daily at configured time (default 9:00 AM).
    """
    logger.info(f"Running deadline alerts check: {datetime.now()}")
    
    if not app:
        logger.error("No Flask app provided to check_deadline_alerts")
        return
    
    with app.app_context():
        try:
            # Get all companies with deadline alerts enabled
            configs = WhatsAppConfig.query.filter_by(auto_send_deadline_alerts=True).all()
            
            for config in configs:
                company_id = str(config.company_id)
                days_before = config.deadline_alert_days_before
                
                # Calculate target due date (today + days_before)
                target_date = date.today() + timedelta(days=days_before)
                
                # Find invoices due on target date that are still pending/overdue
                invoices = Invoice.query.filter(
                    Invoice.company_id == company_id,
                    Invoice.due_date == target_date,
                    Invoice.status.in_(['pending', 'partially_paid', 'overdue']),
                    Invoice.is_active == True
                ).all()
                
                logger.info(f"Found {len(invoices)} invoices due in {days_before} days for company {company_id}")
                
                for invoice in invoices:
                    try:
                        # Check if alert already sent for this invoice
                        existing_alert = db.session.query(WhatsAppMessageQueue).filter(
                            WhatsAppMessageQueue.related_invoice_id == invoice.id,
                            WhatsAppMessageQueue.message_type == 'deadline_alert'
                        ).first()
                        
                        if existing_alert:
                            logger.info(f"Alert already sent for invoice {invoice.invoice_number}")
                            continue
                        
                        # Generate alert message
                        customer = invoice.customer
                        message = f"Dear {customer.first_name}, your invoice #{invoice.invoice_number} for Rs.{invoice.total_amount} is due on {invoice.due_date.strftime('%Y-%m-%d')}. Please make payment before the due date."
                        
                        # Enqueue alert message with high priority
                        WhatsAppQueueService.enqueue_message(
                            company_id=company_id,
                            customer_id=str(customer.id),
                            mobile=customer.phone_1,
                            message_content=message,
                            message_type='deadline_alert',
                            priority=config.default_alert_priority,
                            related_invoice_id=str(invoice.id)
                        )
                        
                        logger.info(f"Enqueued deadline alert for invoice {invoice.invoice_number}")
                        
                    except Exception as e:
                        logger.error(f"Error creating deadline alert for invoice {invoice.id}: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error in deadline alerts check: {str(e)}")

def reset_whatsapp_quota(app=None):
    """
    Reset daily WhatsApp quota at midnight.
    """
    logger.info(f"Resetting WhatsApp daily quota: {datetime.now()}")
    
    if not app:
        logger.error("No Flask app provided to reset_whatsapp_quota")
        return
    
    with app.app_context():
        try:
            WhatsAppRateLimiter.reset_daily_quota()
            logger.info("WhatsApp quota reset completed")
            
        except Exception as e:
            logger.error(f"Error resetting WhatsApp quota: {str(e)}")

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
    
    # WhatsApp Queue Processing Job - Run daily at 9:00 AM PKT
    scheduler.add_job(
        func=process_whatsapp_queue,
        args=[app],
        trigger=CronTrigger(hour=20, minute=14),
        id='whatsapp_queue_job',
        name='Process WhatsApp message queue',
        replace_existing=True
    )
    
    # WhatsApp Deadline Alerts Job - Run daily at 9:00 AM PKT (same time as queue processing)
    scheduler.add_job(
        func=check_deadline_alerts,
        args=[app],
        trigger=CronTrigger(hour=9, minute=0),
        id='whatsapp_deadline_alerts_job',
        name='Check and enqueue deadline alerts',
        replace_existing=True
    )
    
    # WhatsApp Quota Reset Job - Run daily at midnight
    scheduler.add_job(
        func=reset_whatsapp_quota,
        args=[app],
        trigger=CronTrigger(hour=0, minute=0),
        id='whatsapp_quota_reset_job',
        name='Reset WhatsApp daily quota',
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