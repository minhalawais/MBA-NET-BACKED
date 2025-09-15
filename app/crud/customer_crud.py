from app import db
from app.models import Customer, Invoice, Payment, Complaint, Area, ServicePlan, RecoveryTask,ISP,InventoryItem
from app.utils.logging_utils import log_action
import uuid
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
import logging
from datetime import datetime
from flask import jsonify
from sqlalchemy import or_
import re
import uuid


logger = logging.getLogger(__name__)

async def get_all_customers(company_id, user_role, employee_id):
    if user_role == 'super_admin' or user_role == 'employee':
        customers = Customer.query.all()
    elif user_role == 'auditor':
        customers = Customer.query.filter_by(is_active=True, company_id=company_id).all()
    elif user_role == 'company_owner':
        customers = Customer.query.filter_by(company_id=company_id).all()
    elif user_role == 'employee':
        customers = Customer.query.filter_by(company_id=company_id).all()

    result = []
    for customer in customers:
        area = Area.query.get(customer.area_id)
        service_plan = ServicePlan.query.get(customer.service_plan_id)
        isp = ISP.query.get(customer.isp_id)

        result.append({
            # --- Old fields you already had ---
            'id': str(customer.id),
            'internet_id': customer.internet_id,
            'first_name': customer.first_name,
            'last_name': customer.last_name,
            'email': customer.email,
            'phone_1': customer.phone_1,
            'phone_2': customer.phone_2,
            'area': area.name if area else 'Unassigned',
            'installation_address': customer.installation_address,
            'service_plan': service_plan.name if service_plan else 'Unassigned',
            'servicePlanPrice': float(service_plan.price) if service_plan and service_plan.price else 0,
            'isp': isp.name if isp else 'Unassigned',
            'isp_id': str(customer.isp_id) if customer.isp_id else None,
            'connection_type': customer.connection_type,
            'internet_connection_type': customer.internet_connection_type,
            'tv_cable_connection_type': customer.tv_cable_connection_type,
            'installation_date': customer.installation_date.isoformat() if customer.installation_date else None,
            'is_active': customer.is_active,
            'cnic': customer.cnic,
            'cnic_front_image': customer.cnic_front_image,
            'cnic_back_image': customer.cnic_back_image,
            'gps_coordinates': customer.gps_coordinates,
            'agreement_document': customer.agreement_document,

            # --- Extra fields from add_customer ---
            'company_id': str(customer.company_id),
            'area_id': str(customer.area_id) if customer.area_id else None,
            'service_plan_id': str(customer.service_plan_id) if customer.service_plan_id else None,
            'wire_length': customer.wire_length,
            'wire_ownership': customer.wire_ownership,
            'router_ownership': customer.router_ownership,
            'router_id': str(customer.router_id) if customer.router_id else None,
            'router_serial_number': customer.router_serial_number,
            'patch_cord_ownership': customer.patch_cord_ownership,
            'patch_cord_count': customer.patch_cord_count,
            'patch_cord_ethernet_ownership': customer.patch_cord_ethernet_ownership,
            'patch_cord_ethernet_count': customer.patch_cord_ethernet_count,
            'splicing_box_ownership': customer.splicing_box_ownership,
            'splicing_box_serial_number': customer.splicing_box_serial_number,
            'ethernet_cable_ownership': customer.ethernet_cable_ownership,
            'ethernet_cable_length': customer.ethernet_cable_length,
            'dish_ownership': customer.dish_ownership,
            'dish_id': str(customer.dish_id) if customer.dish_id else None,
            'dish_mac_address': customer.dish_mac_address,
            'node_count': customer.node_count,
            'stb_serial_number': customer.stb_serial_number,
            'discount_amount': customer.discount_amount,
            'recharge_date': customer.recharge_date.isoformat() if customer.recharge_date else None,
            'miscellaneous_details': customer.miscellaneous_details,
            'miscellaneous_charges': customer.miscellaneous_charges,
            'created_at': customer.created_at.isoformat() if customer.created_at else None,
            'updated_at': customer.updated_at.isoformat() if customer.updated_at else None,
        })
    return result


def format_phone_number(phone):
    """Format phone number by removing all non-numeric characters."""
    if not phone:
        return None
    # Remove all non-digit characters
    cleaned = ''.join(filter(str.isdigit, str(phone)))
    # Remove '92' from start if it exists
    if cleaned.startswith('92'):
        cleaned = cleaned[2:]
    # Ensure the number starts with '92'
    return f"92{cleaned}"

def check_existing_internet_id(internet_id, company_id):
    existing_customer = Customer.query.filter_by(
        internet_id=internet_id,
        company_id=company_id
    ).first()
    print('Checked existing internet ID:', existing_customer)
    return existing_customer

def check_existing_cnic(cnic, company_id):
    existing_customer = Customer.query.filter_by(
        cnic=cnic,
        company_id=company_id
    ).first()
    return existing_customer

async def add_customer(data, user_role, current_user_id, ip_address, user_agent, company_id):
    try:
        # Check if internet ID already exists
        existing_customer = check_existing_internet_id(data.get('internet_id'), company_id)
        if existing_customer:
            raise ValueError(f"Internet ID '{data.get('internet_id')}' is already taken")
        
        # Check if CNIC already exists
        existing_cnic = check_existing_cnic(data.get('cnic'), company_id)
        if existing_cnic:
            raise ValueError(f"CNIC '{data.get('cnic')}' is already registered")
        
        # Format phone numbers before saving
        phone_1 = format_phone_number(data.get('phone_1')) if data.get('phone_1') else None
        phone_2 = format_phone_number(data.get('phone_2')) if data.get('phone_2') else None

        new_customer = Customer(
            company_id=uuid.UUID(company_id),
            area_id=data.get('area_id'),
            service_plan_id=data.get('service_plan_id'),
            first_name=data.get('first_name'),
            last_name=data.get('last_name'),
            email=data.get('email'),
            internet_id=data.get('internet_id'),
            phone_1=phone_1,
            phone_2=phone_2,
            installation_address=data.get('installation_address'),
            installation_date=data.get('installation_date'),
            isp_id=data.get('isp_id'),
            connection_type=data.get('connection_type'),
            internet_connection_type=data.get('internet_connection_type'),
            wire_length=data.get('wire_length'),
            wire_ownership=data.get('wire_ownership'),
            router_ownership=data.get('router_ownership'),
            router_id=data.get('router_id'),
            router_serial_number=data.get('router_serial_number'),
            patch_cord_ownership=data.get('patch_cord_ownership'),
            patch_cord_count=data.get('patch_cord_count'),
            patch_cord_ethernet_ownership=data.get('patch_cord_ethernet_ownership'),
            patch_cord_ethernet_count=data.get('patch_cord_ethernet_count'),
            splicing_box_ownership=data.get('splicing_box_ownership'),
            splicing_box_serial_number=data.get('splicing_box_serial_number'),
            ethernet_cable_ownership=data.get('ethernet_cable_ownership'),
            ethernet_cable_length=data.get('ethernet_cable_length'),
            dish_ownership=data.get('dish_ownership'),
            dish_id=data.get('dish_id'),
            dish_mac_address=data.get('dish_mac_address'),
            tv_cable_connection_type=data.get('tv_cable_connection_type'),
            node_count=data.get('node_count'),
            stb_serial_number=data.get('stb_serial_number'),
            discount_amount=data.get('discount_amount'),
            recharge_date=data.get('recharge_date'),
            miscellaneous_details=data.get('miscellaneous_details'),
            miscellaneous_charges=data.get('miscellaneous_charges'),
            is_active=True,
            cnic=data.get('cnic'),
            cnic_front_image=data.get('cnic_front_image'),
            cnic_back_image=data.get('cnic_back_image'),
            gps_coordinates=data.get('gps_coordinates'),
            agreement_document=data.get('agreement_document')
        )
        db.session.add(new_customer)
        db.session.commit()

        log_action(
            current_user_id,
            'CREATE',
            'customers',
            new_customer.id,
            None,
            data,
            ip_address,
            user_agent,
            company_id
        )

        return new_customer
    except Exception as e:
        print('Error:', str(e))
        db.session.rollback()
        raise

async def update_customer(id, data, company_id, user_role, current_user_id, ip_address, user_agent):
    if user_role == 'super_admin' or user_role == 'employee':
        customer = Customer.query.get(id)
    elif user_role == 'auditor':
        customer = Customer.query.filter_by(id=id, is_active=True, company_id=company_id).first()
    elif user_role == 'company_owner':
        customer = Customer.query.filter_by(id=id, company_id=company_id).first()
        uuid_fields = ['area_id', 'service_plan_id', 'isp_id', 'router_id', 'dish_id']
    if not customer:
        return None
    old_values = {
        'email': customer.email,
        'first_name': customer.first_name,
        'last_name': customer.last_name,
        'internet_id': customer.internet_id,
        'phone_1': customer.phone_1,
        'phone_2': customer.phone_2,
        'area_id': str(customer.area_id),
        'service_plan_id': str(customer.service_plan_id),
        'isp_id': str(customer.isp_id),
        'installation_address': customer.installation_address,
        'installation_date': customer.installation_date.isoformat() if customer.installation_date else None,
        'connection_type': customer.connection_type,
        'internet_connection_type': customer.internet_connection_type,
        'wire_length': customer.wire_length,
        'wire_ownership': customer.wire_ownership,
        'router_ownership': customer.router_ownership,
        'router_id': str(customer.router_id) if customer.router_id else None,
        'router_serial_number': customer.router_serial_number,
        'patch_cord_ownership': customer.patch_cord_ownership,
        'patch_cord_count': customer.patch_cord_count,
        'patch_cord_ethernet_ownership': customer.patch_cord_ethernet_ownership,
        'patch_cord_ethernet_count': customer.patch_cord_ethernet_count,
        'splicing_box_ownership': customer.splicing_box_ownership,
        'splicing_box_serial_number': customer.splicing_box_serial_number,
        'ethernet_cable_ownership': customer.ethernet_cable_ownership,
        'ethernet_cable_length': customer.ethernet_cable_length,
        'dish_ownership': customer.dish_ownership,
        'dish_id': str(customer.dish_id) if customer.dish_id else None,
        'dish_mac_address': customer.dish_mac_address,
        'tv_cable_connection_type': customer.tv_cable_connection_type,
        'node_count': customer.node_count,
        'stb_serial_number': customer.stb_serial_number,
        'discount_amount': float(customer.discount_amount) if customer.discount_amount else None,
        'recharge_date': customer.recharge_date.isoformat() if customer.recharge_date else None,
        'miscellaneous_details': customer.miscellaneous_details,
        'miscellaneous_charges': float(customer.miscellaneous_charges) if customer.miscellaneous_charges else None,
        'is_active': customer.is_active,
        'cnic': customer.cnic,
        'cnic_front_image': customer.cnic_front_image,
        'cnic_back_image': customer.cnic_back_image,
        'gps_coordinates': customer.gps_coordinates,
        'agreement_document': customer.agreement_document
    }

    for key, value in data.items():
        setattr(customer, key, value)

    db.session.commit()

    log_action(
        current_user_id,
        'UPDATE',
        'customers',
        customer.id,
        old_values,
        data,
        ip_address,
        user_agent,
        company_id
    )

    return customer

async def delete_customer(id, company_id, user_role, current_user_id, ip_address, user_agent):
    if user_role == 'super_admin' or user_role == 'employee':
        customer = Customer.query.get(id)
    elif user_role == 'auditor':
        customer = Customer.query.filter_by(id=id, is_active=True, company_id=company_id).first()
    elif user_role == 'company_owner':
        customer = Customer.query.filter_by(id=id, company_id=company_id).first()
    
    if not customer:
        return False

    old_values = {
        'email': customer.email,
        'first_name': customer.first_name,
        'last_name': customer.last_name,
        'area_id': str(customer.area_id),
        'service_plan_id': str(customer.service_plan_id),
        'installation_address': customer.installation_address,
        'installation_date': customer.installation_date.isoformat() if customer.installation_date else None,
        'is_active': customer.is_active
    }

    db.session.delete(customer)
    db.session.commit()

    log_action(
        current_user_id,
        'DELETE',
        'customers',
        customer.id,
        old_values,
        None,
        ip_address,
        user_agent,
        company_id
    )

    return True
async def validate_customer_data(data, is_update=False, customer_id=None):
    errors = {}
    
    # Required field validation
    required_fields = [
        'first_name', 'last_name', 'cnic', 'phone_1', 'email', 
        'installation_address', 'area_id', 'service_plan_id', 'isp_id',
        'connection_type', 'installation_date'
    ]
    
    if not is_update:
        required_fields.append('internet_id')
    
    for field in required_fields:
        if not data.get(field) or str(data.get(field)).strip() == '':
            field_name = field.replace('_', ' ').title()
            errors[field] = f"{field_name} is required"
    
    # Email format validation
    if data.get('email'):
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, data['email']):
            errors['email'] = 'Please enter a valid email address'
    
    # CNIC format validation (13 digits)
    if data.get('cnic'):
        cnic_clean = re.sub(r'\D', '', data['cnic'])
        if len(cnic_clean) != 13:
            errors['cnic'] = 'CNIC must be exactly 13 digits'
        else:
            data['cnic'] = cnic_clean  # Store clean CNIC
    
    # Phone number validation
    for phone_field in ['phone_1', 'phone_2']:
        if data.get(phone_field):
            phone_clean = re.sub(r'\D', '', data[phone_field])
            if phone_field == 'phone_1' and len(phone_clean) < 10:
                errors[phone_field] = 'Phone number must be at least 10 digits'
            elif phone_field == 'phone_2' and phone_clean and len(phone_clean) < 10:
                errors[phone_field] = 'WhatsApp number must be at least 10 digits'
    
    # Internet ID validation
    if data.get('internet_id'):
        if len(data['internet_id']) < 3:
            errors['internet_id'] = 'Internet ID must be at least 3 characters'
        elif not re.match(r'^[a-zA-Z0-9_-]+$', data['internet_id']):
            errors['internet_id'] = 'Internet ID can only contain letters, numbers, hyphens, and underscores'
    
    return errors
async def toggle_customer_status(id, company_id, user_role, current_user_id, ip_address, user_agent):
    if user_role == 'super_admin' or user_role == 'employee':
        customer = Customer.query.get(id)
    elif user_role == 'auditor':
        customer = Customer.query.filter_by(id=id, is_active=True, company_id=company_id).first()
    elif user_role == 'company_owner':
        customer = Customer.query.filter_by(id=id, company_id=company_id).first()
    
    if not customer:
        return None

    old_status = customer.is_active
    customer.is_active = not customer.is_active
    db.session.commit()

    log_action(
        current_user_id,
        'UPDATE',
        'customers',
        customer.id,
        {'is_active': old_status},
        {'is_active': customer.is_active},
        ip_address,
        user_agent,
        company_id
    )

    return customer

async def get_customer_details(id, company_id):
    try:
        # Check if customer exists
        customer = Customer.query.filter_by(id=id, company_id=company_id).first()
        if not customer:
            return {'error': 'Customer not found'}, 404
        
        # Safely get area and service plan
        area = Area.query.get(customer.area_id)
        service_plan = ServicePlan.query.get(customer.service_plan_id)
        isp = ISP.query.get(customer.isp_id)
        
        # Safely fetch related data
        invoices = Invoice.query.filter_by(customer_id=id).all() or []
        payments = Payment.query.join(Invoice).filter(Invoice.customer_id == id).all() or []
        complaints = Complaint.query.filter_by(customer_id=id).all() or []

        # Financial metrics with safe calculations
        total_amount_paid = sum(payment.amount for payment in payments)
        avg_monthly_payment = total_amount_paid / len(payments) if payments else 0
        payment_reliability_score = (len([p for p in payments if p.status == 'completed']) / len(payments) * 100) if payments else 0
        outstanding_balance = sum(invoice.total_amount for invoice in invoices if invoice.status == 'pending')
        avg_bill_amount = sum(invoice.total_amount for invoice in invoices) / len(invoices) if invoices else 0
        
        # Safe payment method calculation
        payment_methods = [payment.payment_method for payment in payments]
        most_used_payment_method = max(set(payment_methods), key=payment_methods.count) if payment_methods else 'N/A'
        
        # Safe late payment calculation
        late_payment_frequency = 0
        for payment in payments:
            invoice = Invoice.query.get(payment.invoice_id)
            if invoice and payment.payment_date > invoice.due_date:
                late_payment_frequency += 1

        # Service statistics with safe calculations
        service_duration = (datetime.now().date() - customer.installation_date).days if customer.installation_date else 0
        service_plan_history = [sp.name for sp in ServicePlan.query.join(Customer).filter(Customer.id == id).all()]
        upgrade_downgrade_frequency = len(service_plan_history) - 1
        
        # Safe area coverage calculation
        try:
            area_coverage_statistics = {
                area.name: Customer.query.filter_by(area_id=area.id).count() 
                for area in Area.query.all()
            }
        except Exception:
            area_coverage_statistics = {}

        # Support analysis with safe calculations
        total_complaints = len(complaints)
        
        # Safe resolution time calculation
        resolved_complaints = [c for c in complaints if c.resolved_at]
        avg_resolution_time = (
            sum((c.resolved_at - c.created_at).total_seconds() / 3600 for c in resolved_complaints) / len(resolved_complaints)
            if resolved_complaints else 0
        )
        
        # Initialize empty complaint categories distribution
        complaint_categories_distribution = {}
        
        # Safe satisfaction rating calculation
        rated_complaints = [c for c in complaints if c.satisfaction_rating]
        satisfaction_rating_avg = (
            sum(c.satisfaction_rating for c in rated_complaints) / len(rated_complaints)
            if rated_complaints else 0
        )
        
        resolution_attempts_avg = (
            sum(c.resolution_attempts for c in complaints) / total_complaints
            if total_complaints > 0 else 0
        )
        
        # Initialize empty most common complaint types
        most_common_complaint_types = []

        # Billing patterns with safe calculations
        payment_timeline = [
            {'date': payment.payment_date.isoformat(), 'amount': float(payment.amount)}
            for payment in payments if payment.payment_date
        ]
        
        # Safe invoice payment history calculation
        invoice_payment_history = []
        for invoice in invoices:
            payment = next((p for p in payments if p.invoice_id == invoice.id), None)
            if payment and invoice.due_date:
                invoice_payment_history.append({
                    'invoiceId': str(invoice.id),
                    'daysToPay': (payment.payment_date - invoice.due_date).days
                })
        
        discount_usage = sum(1 for invoice in invoices if invoice.discount_percentage > 0)
        
        payment_method_preferences = {
            method: sum(1 for payment in payments if payment.payment_method == method)
            for method in set(p.payment_method for p in payments if p.payment_method)
        }

        # Recovery metrics with safe calculations
        first_invoice = Invoice.query.filter_by(customer_id=id).first()
        recovery_tasks = []
        recovery_tasks_history = []
        recovery_success_rate = 0
        payment_after_recovery_rate = 0
        avg_recovery_time = 0
        
        if first_invoice:
            recovery_tasks = RecoveryTask.query.filter_by(invoice_id=first_invoice.id).all() or []
            recovery_tasks_history = [
                {'date': task.created_at.isoformat(), 'status': task.status}
                for task in recovery_tasks if task.created_at
            ]
            
            if recovery_tasks:
                completed_tasks = [task for task in recovery_tasks if task.status == 'completed']
                recovery_success_rate = (len(completed_tasks) / len(recovery_tasks)) * 100
                
                successful_recoveries = sum(1 for task in completed_tasks 
                    if any(payment.payment_date > task.updated_at for payment in payments))
                payment_after_recovery_rate = (successful_recoveries / len(recovery_tasks)) * 100
                
                if completed_tasks:
                    avg_recovery_time = sum(
                        (task.updated_at - task.created_at).days 
                        for task in completed_tasks 
                        if task.updated_at and task.created_at
                    ) / len(completed_tasks)

        return {
            'id': str(customer.id),
            'first_name': customer.first_name,
            'last_name': customer.last_name,
            'email': customer.email,
            'internet_id': customer.internet_id,
            'phone_1': customer.phone_1,
            'phone_2': customer.phone_2,
            'area': area.name if area else 'Unassigned',
            'service_plan': service_plan.name if service_plan else 'Unassigned',
            'isp': isp.name if isp else 'Unassigned',
            'installation_address': customer.installation_address,
            'installation_date': customer.installation_date.isoformat() if customer.installation_date else None,
            'connection_type': customer.connection_type,
            'internet_connection_type': customer.internet_connection_type,
            'wire_length': customer.wire_length,
            'wire_ownership': customer.wire_ownership,
            'router_ownership': customer.router_ownership,
            'router_id': str(customer.router_id) if customer.router_id else None,
            'router_serial_number': customer.router_serial_number,
            'patch_cord_ownership': customer.patch_cord_ownership,
            'patch_cord_count': customer.patch_cord_count,
            'patch_cord_ethernet_ownership': customer.patch_cord_ethernet_ownership,
            'patch_cord_ethernet_count': customer.patch_cord_ethernet_count,
            'splicing_box_ownership': customer.splicing_box_ownership,
            'splicing_box_serial_number': customer.splicing_box_serial_number,
            'ethernet_cable_ownership': customer.ethernet_cable_ownership,
            'ethernet_cable_length': customer.ethernet_cable_length,
            'dish_ownership': customer.dish_ownership,
            'dish_id': str(customer.dish_id) if customer.dish_id else None,
            'dish_mac_address': customer.dish_mac_address,
            'tv_cable_connection_type': customer.tv_cable_connection_type,
            'node_count': customer.node_count,
            'stb_serial_number': customer.stb_serial_number,
            'discount_amount': float(customer.discount_amount) if customer.discount_amount else None,
            'recharge_date': customer.recharge_date.isoformat() if customer.recharge_date else None,
            'miscellaneous_details': customer.miscellaneous_details,
            'miscellaneous_charges': float(customer.miscellaneous_charges) if customer.miscellaneous_charges else None,
            'is_active': customer.is_active,
            'cnic': customer.cnic,
            'cnic_front_image': customer.cnic_front_image,
            'cnic_back_image': customer.cnic_back_image,
            'gps_coordinates': customer.gps_coordinates,
            'agreement_document': customer.agreement_document,
            'financialMetrics': {
                'totalAmountPaid': float(total_amount_paid) if total_amount_paid is not None else 0,
                'averageMonthlyPayment': float(avg_monthly_payment) if avg_monthly_payment is not None else 0,
                'paymentReliabilityScore': float(payment_reliability_score) if payment_reliability_score is not None else 0,
                'outstandingBalance': float(outstanding_balance) if outstanding_balance is not None else 0,
                'averageBillAmount': float(avg_bill_amount) if avg_bill_amount is not None else 0,
                'mostUsedPaymentMethod': most_used_payment_method or 'N/A',
                'latePaymentFrequency': late_payment_frequency or 0
            },
            'serviceStatistics': {
                'serviceDuration': service_duration,
                'servicePlanHistory': service_plan_history,
                'upgradeDowngradeFrequency': upgrade_downgrade_frequency,
                'areaCoverageStatistics': area_coverage_statistics
            },
            'supportAnalysis': {
                'totalComplaints': total_complaints,
                'averageResolutionTime': float(avg_resolution_time),
                'complaintCategoriesDistribution': complaint_categories_distribution,
                'satisfactionRatingAverage': float(satisfaction_rating_avg),
                'resolutionAttemptsAverage': float(resolution_attempts_avg),
                'supportResponseTime': 0,  # Not available in current model
                'mostCommonComplaintTypes': most_common_complaint_types
            },
            'billingPatterns': {
                'paymentTimeline': payment_timeline,
                'invoicePaymentHistory': invoice_payment_history,
                'discountUsage': discount_usage,
                'lateFeeOccurrences': 0,  # Not available in current model
                'paymentMethodPreferences': payment_method_preferences
            },
            'recoveryMetrics': {
                'recoveryTasksHistory': recovery_tasks_history,
                'recoverySuccessRate': float(recovery_success_rate),
                'paymentAfterRecoveryRate': float(payment_after_recovery_rate),
                'averageRecoveryTime': float(avg_recovery_time)
            }
        }
    except Exception as e:
        # Log the error for debugging
        print(f"Error in get_customer_details: {str(e)}")
        return {'error': 'Internal server error'}, 500

async def get_customer_invoices(id, company_id):
    invoices = Invoice.query.join(Customer).filter(
        Customer.id == id,
        Customer.company_id == company_id
    ).all()
    return [{
        'id': str(invoice.id),
        'invoice_number': invoice.invoice_number,
        'billing_start_date': invoice.billing_start_date.isoformat(),
        'billing_end_date': invoice.billing_end_date.isoformat(),
        'due_date': invoice.due_date.isoformat(),
        'total_amount': float(invoice.total_amount),
        'status': invoice.status
    } for invoice in invoices]

async def get_customer_payments(id, company_id):
    payments = Payment.query.join(Invoice).join(Customer).filter(
        Customer.id == id,
        Customer.company_id == company_id
    ).all()
    return [{
        'id': str(payment.id),
        'invoice_id': str(payment.invoice_id),
        'amount': float(payment.amount),
        'payment_date': payment.payment_date.isoformat(),
        'payment_method': payment.payment_method,
        'status': payment.status
    } for payment in payments]

async def get_customer_complaints(id, company_id):
    complaints = Complaint.query.join(Customer).filter(
        Customer.id == id,
        Customer.company_id == company_id
    ).all()
    return [{
        'id': str(complaint.id),
        'ticket_number': complaint.ticket_number,
        'description': complaint.description,
        'status': complaint.status,
        'created_at': complaint.created_at.isoformat()
    } for complaint in complaints]

async def get_customer_cnic(id, company_id):
    customer = Customer.query.filter_by(id=id, company_id=company_id).first()
    if customer:
        cnic_front_image_path = str(customer.cnic_front_image)
        cnic_back_image_path = str(customer.cnic_back_image)

        if cnic_back_image_path or cnic_front_image_path:
            return customer
        else:
            return None
    return None


async def search_customer(company_id, search_term):
    customer = Customer.query.filter(
        Customer.company_id == company_id,
        or_(
            Customer.phone_1.ilike(f'%{search_term}%'),  # Search by phone_1
            Customer.phone_2.ilike(f'%{search_term}%'),  # Search by phone_2
            Customer.internet_id.ilike(f'%{search_term}%'),  # Search by internet_id
            Customer.first_name.ilike(f'%{search_term}%'),  # Search by first name
            Customer.last_name.ilike(f'%{search_term}%'),  # Search by last name
            Customer.internet_id == search_term  # Search by user ID (UUID)
        )
    ).first()

    if customer:
        return {
            'id': str(customer.id),
            'first_name': customer.first_name,
            'last_name': customer.last_name,
            'internet_id': customer.internet_id,
            'phone_1': customer.phone_1,
            'phone_2': customer.phone_2,
            'installation_address': customer.installation_address,
            'gps_coordinates': customer.gps_coordinates
        }
    return None


async def bulk_add_customers(df, company_id, user_role, current_user_id, ip_address, user_agent):
    """
    Process a dataframe of customer data and add valid customers to the database
    
    Args:
        df: Pandas DataFrame containing customer data
        company_id: UUID of the company
        user_role: Role of the current user
        current_user_id: UUID of the current user
        ip_address: IP address of the request
        user_agent: User agent of the request
        
    Returns:
        Dictionary with results of the bulk add operation
    """
    # Initialize counters and error tracking
    total_records = len(df)
    success_count = 0
    failed_count = 0
    errors = []
    
    # Required fields
    required_fields = [
        'internet_id', 'first_name', 'last_name', 'email', 'phone_1',
        'area_id', 'installation_address', 'service_plan_id', 'isp_id',
        'connection_type', 'cnic', 'installation_date'
    ]
    
    # Validate and process each row
    for index, row in df.iterrows():
        row_errors = []
        
        # Check for missing required fields
        for field in required_fields:
            if field not in row or pd.isna(row[field]) or str(row[field]).strip() == '':
                row_errors.append(f"Missing required field: {field}")
        
        # If there are missing fields, skip this row
        if row_errors:
            errors.append({"row": index, "errors": row_errors})
            failed_count += 1
            continue
        
        # Validate email format
        email = str(row['email']).strip()
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            row_errors.append("Invalid email format")
        
        # Validate phone number format
        phone_1 = str(row['phone_1']).strip()
        # Remove all non-numeric characters
        phone_1 = ''.join(filter(str.isdigit, phone_1))
        if not phone_1.startswith('92'):
            phone_1 = '92' + phone_1
        if len(phone_1) < 10 or len(phone_1) > 13:
            row_errors.append("Invalid phone number format for phone_1")
        
        # Validate phone_2 if provided
        if 'phone_2' in row and not pd.isna(row['phone_2']) and str(row['phone_2']).strip() != '':
            phone_2 = str(row['phone_2']).strip()
            phone_2 = ''.join(filter(str.isdigit, phone_2))
            if not phone_2.startswith('92'):
                phone_2 = '92' + phone_2
            if len(phone_2) < 10 or len(phone_2) > 13:
                row_errors.append("Invalid phone number format for phone_2")
        else:
            phone_2 = None
        
        # Validate CNIC format (13 digits)
        cnic = str(row['cnic']).strip()
        cnic = ''.join(filter(str.isdigit, cnic))
        if len(cnic) != 13:
            row_errors.append("CNIC must be 13 digits")
        
        # Validate connection_type
        connection_type = str(row['connection_type']).strip().lower()
        if connection_type not in ['internet', 'tv_cable', 'both']:
            row_errors.append("connection_type must be one of: internet, tv_cable, both")
        
        # Validate internet_connection_type if connection_type is internet or both
        if connection_type in ['internet', 'both']:
            if 'internet_connection_type' not in row or pd.isna(row['internet_connection_type']) or str(row['internet_connection_type']).strip() == '':
                row_errors.append("internet_connection_type is required when connection_type is internet or both")
            else:
                internet_connection_type = str(row['internet_connection_type']).strip().lower()
                if internet_connection_type not in ['wire', 'wireless']:
                    row_errors.append("internet_connection_type must be one of: wire, wireless")
        
        # Validate tv_cable_connection_type if connection_type is tv_cable or both
        if connection_type in ['tv_cable', 'both']:
            if 'tv_cable_connection_type' not in row or pd.isna(row['tv_cable_connection_type']) or str(row['tv_cable_connection_type']).strip() == '':
                row_errors.append("tv_cable_connection_type is required when connection_type is tv_cable or both")
            else:
                tv_cable_connection_type = str(row['tv_cable_connection_type']).strip().lower()
                if tv_cable_connection_type not in ['analog', 'digital']:
                    row_errors.append("tv_cable_connection_type must be one of: analog, digital")
        
        # Validate installation_date format
        try:
            installation_date = row['installation_date']
            if isinstance(installation_date, str):
                installation_date = datetime.strptime(installation_date, '%Y-%m-%d').date()
            elif isinstance(installation_date, pd.Timestamp):
                installation_date = installation_date.date()
            else:
                row_errors.append("Invalid installation_date format. Use YYYY-MM-DD")
        except (ValueError, TypeError):
            row_errors.append("Invalid installation_date format. Use YYYY-MM-DD")
        
        # Validate UUIDs
        try:
            area_id = uuid.UUID(str(row['area_id']).strip())
            service_plan_id = uuid.UUID(str(row['service_plan_id']).strip())
            isp_id = uuid.UUID(str(row['isp_id']).strip())
            
            # Check if these IDs exist in the database
            area = Area.query.get(area_id)
            if not area:
                row_errors.append(f"Area with ID {area_id} does not exist")
            
            service_plan = ServicePlan.query.get(service_plan_id)
            if not service_plan:
                row_errors.append(f"Service Plan with ID {service_plan_id} does not exist")
            
            isp = ISP.query.get(isp_id)
            if not isp:
                row_errors.append(f"ISP with ID {isp_id} does not exist")
        except ValueError:
            row_errors.append("Invalid UUID format for area_id, service_plan_id, or isp_id")
        
        # Check if internet_id or email already exists
        existing_customer = Customer.query.filter(
            (Customer.internet_id == str(row['internet_id']).strip()) | 
            (Customer.email == email)
        ).first()
        
        if existing_customer:
            if existing_customer.internet_id == str(row['internet_id']).strip():
                row_errors.append(f"Customer with internet_id {row['internet_id']} already exists")
            if existing_customer.email == email:
                row_errors.append(f"Customer with email {email} already exists")
        
        # If there are validation errors, skip this row
        if row_errors:
            errors.append({"row": index, "errors": row_errors})
            failed_count += 1
            continue
        
        # Prepare customer data
        customer_data = {
            'company_id': company_id,
            'area_id': str(area_id),
            'service_plan_id': str(service_plan_id),
            'isp_id': str(isp_id),
            'first_name': str(row['first_name']).strip(),
            'last_name': str(row['last_name']).strip(),
            'email': email,
            'internet_id': str(row['internet_id']).strip(),
            'phone_1': phone_1,
            'phone_2': phone_2,
            'installation_address': str(row['installation_address']).strip(),
            'installation_date': installation_date,
            'connection_type': connection_type,
            'cnic': cnic,
            'is_active': True
        }
        
        # Add optional fields if they exist
        if connection_type in ['internet', 'both'] and 'internet_connection_type' in row and not pd.isna(row['internet_connection_type']):
            customer_data['internet_connection_type'] = str(row['internet_connection_type']).strip().lower()
        
        if connection_type in ['tv_cable', 'both'] and 'tv_cable_connection_type' in row and not pd.isna(row['tv_cable_connection_type']):
            customer_data['tv_cable_connection_type'] = str(row['tv_cable_connection_type']).strip().lower()
        
        if 'gps_coordinates' in row and not pd.isna(row['gps_coordinates']) and str(row['gps_coordinates']).strip() != '':
            customer_data['gps_coordinates'] = str(row['gps_coordinates']).strip()
        
        # Add additional fields if they exist in the CSV
        optional_fields = [
            'wire_length', 'wire_ownership', 'router_ownership', 'router_serial_number',
            'patch_cord_ownership', 'patch_cord_count', 'patch_cord_ethernet_ownership',
            'patch_cord_ethernet_count', 'splicing_box_ownership', 'splicing_box_serial_number',
            'ethernet_cable_ownership', 'ethernet_cable_length', 'dish_ownership',
            'dish_mac_address', 'node_count', 'stb_serial_number', 'discount_amount',
            'recharge_date', 'miscellaneous_details', 'miscellaneous_charges'
        ]
        
        for field in optional_fields:
            if field in row and not pd.isna(row[field]) and str(row[field]).strip() != '':
                customer_data[field] = row[field]
        
        try:
            # Create the customer
            new_customer = add_customer(customer_data, user_role, current_user_id, ip_address, user_agent, company_id)
            success_count += 1
        except Exception as e:
            row_errors.append(f"Error adding customer: {str(e)}")
            errors.append({"row": index, "errors": row_errors})
            failed_count += 1
            continue
    
    # Commit all successful additions
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return {
            'success': False,
            'totalRecords': total_records,
            'successCount': 0,
            'failedCount': total_records,
            'errors': [{"row": 0, "errors": [f"Database error: {str(e)}"]}]
        }
    
    # Return the results
    return {
        'success': failed_count == 0,
        'totalRecords': total_records,
        'successCount': success_count,
        'failedCount': failed_count,
        'errors': errors
    }