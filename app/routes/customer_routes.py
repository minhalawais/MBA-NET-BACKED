from flask import jsonify, request, send_file,current_app
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from . import main
from ..crud import customer_crud
from werkzeug.utils import secure_filename
import os
import tempfile
import csv
import io
import uuid

UPLOAD_FOLDER = os.path.join(current_app.root_path, 'uploads/cnic_images')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# New route for handling immediate file uploads
@main.route('/customers/upload-file/<string:file_type>', methods=['POST'])
@jwt_required()
def upload_customer_file(file_type):
    claims = get_jwt()
    company_id = claims['company_id']
    
    if file_type not in ['cnic_front_image', 'cnic_back_image', 'agreement_document']:
        return jsonify({'error': 'Invalid file type'}), 400
    
    if file_type not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files[file_type]
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file and allowed_file(file.filename):
        # Generate a unique filename with UUID to prevent collisions
        file_extension = file.filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4()}_{file_type}.{file_extension}"
        
        # Create relative path (this is important)
        relative_path = os.path.join('uploads/cnic_images', unique_filename)
        file_path = os.path.join(PROJECT_ROOT, relative_path)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Save the file
        file.save(file_path)
        
        # Return the relative file path to be stored in the customer record
        return jsonify({
            'success': True,
            'file_path': relative_path,  # Return relative path
            'file_name': unique_filename,
            'file_type': file_extension,
            'message': 'File uploaded successfully'
        }), 200
    
    return jsonify({'error': 'Invalid file format'}), 400

@main.route('/customers/list', methods=['GET'])
@jwt_required()
def get_customers():
    claims = get_jwt()
    company_id = claims['company_id']
    user_role = claims['role']
    employee_id = get_jwt_identity()
    customers = customer_crud.get_all_customers(company_id, user_role, employee_id)
    return jsonify(customers), 200

@main.route('/customers/add', methods=['POST'])
@jwt_required()
def add_new_customer():
    claims = get_jwt()
    company_id = claims['company_id']
    user_role = claims['role']
    current_user_id = get_jwt_identity()
    ip_address = request.remote_addr
    user_agent = request.headers.get('User-Agent')
    
    data = request.form.to_dict()
    data['company_id'] = company_id
    
    # Handle file paths from previous uploads
    for file_field in ['cnic_front_image', 'cnic_back_image', 'agreement_document']:
        if file_field in data and data[file_field]:
            # The file path should already be the relative path from the upload
            pass
    
    try:
        new_customer = customer_crud.add_customer(data, user_role, current_user_id, ip_address, user_agent, company_id)
        return jsonify({'message': 'Customer added successfully', 'id': str(new_customer.id)}), 201
    except Exception as e:
        return jsonify({'error': 'Failed to add customer', 'message': str(e)}), 400

    
@main.route('/customers/update/<string:id>', methods=['PUT'])
@jwt_required()
def update_existing_customer(id):
    claims = get_jwt()
    company_id = claims['company_id']
    user_role = claims['role']
    current_user_id = get_jwt_identity()
    ip_address = request.remote_addr
    user_agent = request.headers.get('User-Agent')
    data = request.json
    updated_customer = customer_crud.update_customer(id, data, company_id, user_role, current_user_id, ip_address, user_agent)
    if updated_customer:
        return jsonify({'message': 'Customer updated successfully'}), 200
    return jsonify({'message': 'Customer not found'}), 404

@main.route('/customers/delete/<string:id>', methods=['DELETE'])
@jwt_required()
def delete_existing_customer(id):
    claims = get_jwt()
    company_id = claims['company_id']
    user_role = claims['role']
    current_user_id = get_jwt_identity()
    ip_address = request.remote_addr
    user_agent = request.headers.get('User-Agent')
    if customer_crud.delete_customer(id, company_id, user_role, current_user_id, ip_address, user_agent):
        return jsonify({'message': 'Customer deleted successfully'}), 200
    return jsonify({'message': 'Customer not found'}), 404

@main.route('/customers/toggle-status/<string:id>', methods=['PATCH'])
@jwt_required()
def toggle_customer_active_status(id):
    claims = get_jwt()
    company_id = claims['company_id']
    user_role = claims['role']
    current_user_id = get_jwt_identity()
    ip_address = request.remote_addr
    user_agent = request.headers.get('User-Agent')
    customer = customer_crud.toggle_customer_status(id, company_id, user_role, current_user_id, ip_address, user_agent)
    if customer:
        return jsonify({'message': f"Customer {'activated' if customer.is_active else 'deactivated'} successfully"}), 200
    return jsonify({'message': 'Customer not found'}), 404

@main.route('/customers/<string:id>', methods=['GET'])
@jwt_required()
def get_customer_details(id):
    claims = get_jwt()
    company_id = claims['company_id']
    customer = customer_crud.get_customer_details(id, company_id)
    if customer:
        return jsonify(customer), 200
    return jsonify({'message': 'Customer not found'}), 404

@main.route('/invoices/customer/<string:id>', methods=['GET'])
@jwt_required()
def get_customer_invoices(id):
    claims = get_jwt()
    company_id = claims['company_id']
    invoices = customer_crud.get_customer_invoices(id, company_id)
    return jsonify(invoices), 200

@main.route('/payments/customer/<string:id>', methods=['GET'])
@jwt_required()
def get_customer_payments(id):
    claims = get_jwt()
    company_id = claims['company_id']
    payments = customer_crud.get_customer_payments(id, company_id)
    return jsonify(payments), 200

@main.route('/complaints/customer/<string:id>', methods=['GET'])
@jwt_required()
def get_customer_complaints(id):
    claims = get_jwt()
    company_id = claims['company_id']
    complaints = customer_crud.get_customer_complaints(id, company_id)
    return jsonify(complaints), 200

@main.route('/customers/cnic-front-image/<string:id>', methods=['GET'])
@jwt_required()
def get_cnic_front_image(id):
    claims = get_jwt()
    company_id = claims['company_id']
    customer = customer_crud.get_customer_cnic(id, company_id)
    if customer and customer.cnic_front_image:
        cnic_image_path = os.path.join(PROJECT_ROOT, customer.cnic_front_image)
        if os.path.exists(cnic_image_path):
            return send_file(cnic_image_path, mimetype='image/jpeg')
        else:
            return jsonify({'error': 'CNIC front image file not found'}), 404
    return jsonify({'error': 'CNIC front image not found'}), 404

@main.route('/customers/cnic-back-image/<string:id>', methods=['GET'])
@jwt_required()
def get_cnic_back_image(id):
    claims = get_jwt()
    company_id = claims['company_id']
    customer = customer_crud.get_customer_cnic(id, company_id)
    if customer and customer.cnic_back_image:
        cnic_image_path = os.path.join(PROJECT_ROOT, customer.cnic_back_image)
        if os.path.exists(cnic_image_path):
            print('Document : ',cnic_image_path)
            return send_file(cnic_image_path, mimetype='image/jpeg')
        else:
            return jsonify({'error': 'CNIC back image file not found'}), 404
    return jsonify({'error': 'CNIC back image not found'}), 404

@main.route('/customers/agreement-document/<string:id>', methods=['GET'])
@jwt_required()
def get_agreement_document(id):
    claims = get_jwt()
    company_id = claims['company_id']
    customer = customer_crud.get_customer_details(id, company_id)
    if customer and customer['agreement_document']:
        agreement_document_path = os.path.join(PROJECT_ROOT, customer['agreement_document'])
        if os.path.exists(agreement_document_path):
            print('Document : ',agreement_document_path)
            return send_file(agreement_document_path, mimetype='image/jpeg')
        else:
            return jsonify({'error': 'Agreement document file not found'}), 404
    return jsonify({'error': 'Agreement document not found'}), 404


@main.route('/customers/template', methods=['GET'])
@jwt_required()
def get_customer_template():
    """Generate and return a CSV template for bulk customer import"""
    claims = get_jwt()
    company_id = claims['company_id']
    
    # Create a buffer for the CSV file
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    
    # Write header row with all required fields
    writer.writerow([
        'internet_id', 'first_name', 'last_name', 'email', 'phone_1', 'phone_2',
        'area_id', 'installation_address', 'service_plan_id', 'isp_id',
        'connection_type', 'internet_connection_type', 'tv_cable_connection_type',
        'installation_date', 'cnic', 'gps_coordinates'
    ])
    
    # Write an example row
    writer.writerow([
        'NET12345', 'John', 'Doe', 'john.doe@example.com', '923001234567', '923007654321',
        'area-uuid-here', '123 Main St, City', 'service-plan-uuid-here', 'isp-uuid-here',
        'internet', 'wire', '', '2023-05-01', '1234512345671', '31.5204,74.3587'
    ])
    
    # Get the CSV content
    buffer.seek(0)
    csv_content = buffer.getvalue()
    buffer.close()
    
    # Create a response with the CSV file
    response = current_app.response_class(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=customer_template.csv'}
    )
    
    return response

@main.route('/customers/bulk-add', methods=['POST'])
@jwt_required()
def bulk_add_customers():
    """Process a CSV/Excel file to add multiple customers"""
    claims = get_jwt()
    company_id = claims['company_id']
    user_role = claims['role']
    current_user_id = get_jwt_identity()
    ip_address = request.remote_addr
    user_agent = request.headers.get('User-Agent')
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Check file extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ['.csv', '.xls', '.xlsx']:
        return jsonify({'error': 'Invalid file format. Please upload a CSV or Excel file'}), 400
    
    # Save the file temporarily
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    file.save(temp_file.name)
    temp_file.close()
    
    try:
        # Read the file based on its extension
        if file_ext == '.csv':
            df = pd.read_csv(temp_file.name)
        else:  # Excel file
            df = pd.read_excel(temp_file.name)
        
        # Process the data
        results = customer_crud.bulk_add_customers(
            df, 
            company_id, 
            user_role, 
            current_user_id, 
            ip_address, 
            user_agent
        )
        
        return jsonify(results), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
