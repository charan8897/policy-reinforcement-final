"""
Upload Service - Main Flask Application

POST /api/v1/upload - Upload document
GET  /api/v1/documents/<document_id> - Retrieve document
GET  /api/v1/documents - List documents
GET  /api/v1/health - Health check
"""

from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import uuid
from datetime import datetime
import os
import logging
import sys
import json
import subprocess

from config import get_config, Config
from logger import setup_logger
from database import DatabaseManager
from extractor import DocumentExtractor
from pipeline_orchestrator import get_or_create_pipeline, get_pipeline_status
from policy_translator import PolicyTranslator
import asyncio
import threading

# Setup logging
app_logger = setup_logger('upload_service')


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def commit_bundle_to_git(bundle_dir, output_text=''):
    """
    Commit OPA bundle to Git repository
    
    Args:
        bundle_dir (str): Directory containing OPA bundles
        output_text (str): Output from bundle generation
    
    Returns:
        dict: {'success': bool, 'commit_hash': str, 'message': str}
    """
    try:
        import subprocess
        import re
        
        # Extract version from output
        version_match = re.search(r'Bundle Version: ([\d.]+)', output_text)
        version = version_match.group(1) if version_match else 'unknown'
        
        # Git add bundles
        add_result = subprocess.run(
            ['git', 'add', 'opa_bundles/', 'stage9_rego_bundles.json'],
            cwd=bundle_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if add_result.returncode != 0:
            app_logger.warning(f"Git add warning: {add_result.stderr}")
        
        # Check if there are changes to commit
        status_result = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=bundle_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if not status_result.stdout.strip():
            app_logger.info("No changes to commit")
            return {'success': True, 'message': 'No changes to commit', 'commit_hash': None}
        
        # Git commit
        commit_msg = f"chore: update OPA bundle v{version} - auto-generated"
        commit_result = subprocess.run(
            ['git', 'commit', '-m', commit_msg],
            cwd=bundle_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if commit_result.returncode == 0:
            # Extract commit hash
            commit_hash_match = re.search(r'\[phase2 ([a-f0-9]+)\]', commit_result.stdout)
            commit_hash = commit_hash_match.group(1) if commit_hash_match else 'unknown'
            
            app_logger.info(f"Bundle committed to Git: {commit_hash}")
            
            # Try to push (optional, don't fail if it errors)
            push_result = subprocess.run(
                ['git', 'push', 'origin', 'phase2'],
                cwd=bundle_dir,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if push_result.returncode == 0:
                app_logger.info(f"Bundle pushed to origin/phase2")
            else:
                app_logger.warning(f"Git push warning: {push_result.stderr}")
            
            return {
                'success': True,
                'commit_hash': commit_hash,
                'message': 'Bundle committed and pushed to Git'
            }
        else:
            app_logger.warning(f"Git commit message: {commit_result.stdout}")
            return {
                'success': False,
                'message': commit_result.stdout or 'No changes to commit'
            }
    
    except Exception as e:
        app_logger.error(f"Git commit error: {str(e)}")
        return {
            'success': False,
            'message': f'Git error: {str(e)}'
        }


# Flask app setup
app = Flask(__name__, template_folder='templates', static_folder='static')
config = get_config()
app.config.from_object(config)
CORS(app)

# Initialize managers
db_manager = DatabaseManager(config)
extractor = DocumentExtractor()

# Ensure upload folder exists
os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)

# Output directory for normalized policies
OUTPUT_DIR = "/home/hutech/Documents/docupolicy"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================




def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in config.ALLOWED_EXTENSIONS


def format_response(success, data=None, error=None, status_code=200):
    """Format API response"""
    
    response = {
        'success': success,
        'timestamp': datetime.utcnow().isoformat(),
        'data': data
    }
    
    if error:
        response['error'] = error
    
    return jsonify(response), status_code


# ============================================================================
# WEB UI ENDPOINTS
# ============================================================================

@app.route('/', methods=['GET'])
def index():
    """Serve upload UI"""
    return render_template('index.html')


@app.route('/approval', methods=['GET'])
def approval_ui():
    """Serve policy approval UI"""
    return render_template('approval.html')


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/api/v1/upload', methods=['POST'])
def upload_document():
    """
    Upload a document file
    
    Request:
    {
        "file": <binary file data>
    }
    
    Response:
    {
        "success": true,
        "data": {
            "document_id": "doc_abc123",
            "filename": "policy.pdf",
            "file_type": "pdf",
            "file_size": 12345,
            "version": 1,
            "created_at": "2026-01-27T12:00:00",
            "stats": {
                "lines": 429,
                "words": 1397,
                "characters": 8500
            }
        }
    }
    """
    
    try:
        # Check if file is in request
        if 'file' not in request.files:
            return format_response(
                False,
                error='No file provided',
                status_code=400
            )
        
        file = request.files['file']
        
        if file.filename == '':
            return format_response(
                False,
                error='No file selected',
                status_code=400
            )
        
        if not allowed_file(file.filename):
            return format_response(
                False,
                error=f'File type not allowed. Allowed: {", ".join(config.ALLOWED_EXTENSIONS)}',
                status_code=400
            )
        
        # Check file size
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > config.MAX_FILE_SIZE:
            return format_response(
                False,
                error=f'File too large. Max size: {config.MAX_FILE_SIZE} bytes',
                status_code=413
            )
        
        # Save uploaded file temporarily
        filename = secure_filename(file.filename)
        temp_id = uuid.uuid4().hex[:12]
        temp_filename = f"{temp_id}_{filename}"
        temp_path = os.path.join(config.UPLOAD_FOLDER, temp_filename)
        
        file.save(temp_path)
        app_logger.info(f"File saved: {temp_path}")
        
        # Extract content
        extraction_result = extractor.extract(temp_path)
        
        if not extraction_result['success']:
            os.remove(temp_path)
            return format_response(
                False,
                error=f"Extraction failed: {extraction_result['error']}",
                status_code=422
            )
        
        # Prepare document data (database will handle document_id and versioning)
        file_type = filename.rsplit('.', 1)[1].lower()
        document_data = {
            'filename': filename,
            'file_type': file_type,
            'file_size': file_size,
            'content': extraction_result['content'],
            'stats': extraction_result['stats'],
            'metadata': {
                'upload_ip': request.remote_addr,
                'user_agent': request.user_agent.string,
                'temp_path': temp_path
            }
        }
        
        # Store in database
        db_result = db_manager.insert_document(document_data)
        
        if not db_result['success']:
            os.remove(temp_path)
            return format_response(
                False,
                error=f"Database error: {db_result['error']}",
                status_code=500
            )
        
        # Return success response
        doc_id = db_result['document_id']
        response_data = {
            'document_id': doc_id,
            'filename': filename,
            'file_type': file_type,
            'file_size': file_size,
            'version': db_result['version'],
            'created_at': db_result['created_at'].isoformat() if db_result['created_at'] else None,
            'stats': extraction_result['stats'],
            'pipeline_status': 'queued',
            'next_step': f'Process document at /api/v1/process-document/{doc_id}'
        }
        
        app_logger.info(f"Document uploaded: {doc_id} v{db_result['version']}")
        app_logger.info(f"Pipeline ready to trigger: POST /api/v1/process-document/{doc_id}")
        
        # AUTO-TRIGGER: Process document automatically
        try:
            app_logger.info(f"AUTO-TRIGGERING pipeline for document: {doc_id}")
            # Use internal request context to trigger processing
            with app.app_context():
                result = process_document_internal(doc_id)
                if result.get('success'):
                    app_logger.info(f"✅ Pipeline auto-triggered successfully for {doc_id}")
                    response_data['pipeline_status'] = 'processing'
                else:
                    app_logger.warning(f"⚠️ Pipeline auto-trigger failed for {doc_id}: {result.get('error')}")
                    response_data['pipeline_status'] = 'queued'
        except Exception as e:
            app_logger.warning(f"⚠️ Could not auto-trigger pipeline: {str(e)}")
            response_data['pipeline_status'] = 'queued'
        
        return format_response(
            True,
            data=response_data,
            status_code=201
        )
        
    except Exception as e:
        app_logger.error(f"Upload error: {str(e)}")
        return format_response(
            False,
            error=f"Server error: {str(e)}",
            status_code=500
        )


@app.route('/api/v1/documents/<document_id>', methods=['GET'])
def get_document(document_id):
    """
    Retrieve document by ID
    
    Response:
    {
        "success": true,
        "data": {
            "document_id": "doc_abc123",
            "filename": "policy.pdf",
            "file_type": "pdf",
            "file_size": 12345,
            "version": 1,
            "created_at": "2026-01-27T12:00:00",
            "updated_at": "2026-01-27T12:00:00",
            "stats": {...},
            "content_preview": "First 500 characters...",
            "content_length": 8500
        }
    }
    """
    
    try:
        doc = db_manager.get_document(document_id)
        
        if not doc:
            return format_response(
                False,
                error='Document not found',
                status_code=404
            )
        
        # Remove full content from response, provide preview
        response_data = {
            'document_id': doc['document_id'],
            'filename': doc['filename'],
            'file_type': doc['file_type'],
            'file_size': doc['file_size'],
            'version': doc['version'],
            'created_at': doc['created_at'].isoformat(),
            'updated_at': doc['updated_at'].isoformat(),
            'stats': doc['stats'],
            'content_preview': doc['content'][:500] + '...' if len(doc['content']) > 500 else doc['content'],
            'content_length': len(doc['content']),
            'metadata': doc.get('metadata', {})
        }
        
        return format_response(True, data=response_data)
        
    except Exception as e:
        app_logger.error(f"Get document error: {str(e)}")
        return format_response(
            False,
            error=f"Server error: {str(e)}",
            status_code=500
        )


@app.route('/api/v1/documents', methods=['GET'])
def list_documents():
    """
    List documents with pagination
    
    Query params:
    - limit: Number of documents (default: 10)
    - skip: Number to skip (default: 0)
    
    Response:
    {
        "success": true,
        "data": {
            "documents": [...],
            "total": 42,
            "limit": 10,
            "skip": 0
        }
    }
    """
    
    try:
        limit = int(request.args.get('limit', 10))
        skip = int(request.args.get('skip', 0))
        
        # Validate pagination params
        limit = max(1, min(100, limit))  # 1-100
        skip = max(0, skip)
        
        docs = db_manager.list_documents(limit=limit, skip=skip)
        
        # Format documents (no full content)
        formatted_docs = []
        for doc in docs:
            formatted_docs.append({
                'document_id': doc['document_id'],
                'filename': doc['filename'],
                'file_type': doc['file_type'],
                'file_size': doc['file_size'],
                'version': doc['version'],
                'created_at': doc['created_at'].isoformat(),
                'stats': doc['stats']
            })
        
        response_data = {
            'documents': formatted_docs,
            'total': db_manager.collection.count_documents({'is_active': True}),
            'limit': limit,
            'skip': skip
        }
        
        return format_response(True, data=response_data)
        
    except Exception as e:
        app_logger.error(f"List documents error: {str(e)}")
        return format_response(
            False,
            error=f"Server error: {str(e)}",
            status_code=500
        )


@app.route('/api/v1/documents/<document_id>/content', methods=['GET'])
def get_document_content(document_id):
    """
    Retrieve full document content (large response)
    
    Response:
    {
        "success": true,
        "data": {
            "document_id": "doc_abc123",
            "content": "Full document text...",
            "content_length": 8500
        }
    }
    """
    
    try:
        doc = db_manager.get_document(document_id)
        
        if not doc:
            return format_response(
                False,
                error='Document not found',
                status_code=404
            )
        
        response_data = {
            'document_id': doc['document_id'],
            'content': doc['content'],
            'content_length': len(doc['content'])
        }
        
        return format_response(True, data=response_data)
        
    except Exception as e:
        app_logger.error(f"Get content error: {str(e)}")
        return format_response(
            False,
            error=f"Server error: {str(e)}",
            status_code=500
        )


@app.route('/api/v1/health', methods=['GET'])
def health_check():
    """
    Health check endpoint
    
    Response:
    {
        "success": true,
        "data": {
            "status": "healthy",
            "service": "Document Upload Service",
            "version": "1.0.0",
            "database": {...}
        }
    }
    """
    
    db_health = db_manager.health_check()
    
    response_data = {
        'status': 'healthy' if db_health['status'] == 'healthy' else 'degraded',
        'service': config.SERVICE_NAME,
        'version': config.SERVICE_VERSION,
        'uptime': (datetime.utcnow() - config.STARTUP_TIME).total_seconds(),
        'database': db_health
    }
    
    return format_response(True, data=response_data)


@app.route('/api/v1/config', methods=['GET'])
def get_config_info():
    """Get service configuration"""
    
    config_data = {
        'service': config.SERVICE_NAME,
        'version': config.SERVICE_VERSION,
        'api_version': config.API_VERSION,
        'max_file_size': config.MAX_FILE_SIZE,
        'allowed_extensions': list(config.ALLOWED_EXTENSIONS),
        'environment': config.FLASK_ENV
    }
    
    return format_response(True, data=config_data)


@app.route('/api/v1/stages/pending', methods=['GET'])
def get_pending_stages():
    """
    Get all stages pending approval
    
    Query Parameters:
    - limit: Maximum number to return (default: 10, max: 100)
    - document_id: Filter by document (optional)
    
    Response:
    {
        "success": true,
        "data": {
            "pending_stages": [
                {
                    "stage_id": "stage_1_xyz123",
                    "document_id": "doc_abc123",
                    "stage_number": 1,
                    "stage_name": "extract-clauses",
                    "status": "pending_approval",
                    "created_at": "2026-01-27T12:00:00",
                    "filename": "policy.pdf"
                }
            ],
            "total": 5,
            "limit": 10
        }
    }
    """
    try:
        from database import PipelineStageManager
        from config import Config
        
        limit = int(request.args.get('limit', 10))
        limit = max(1, min(100, limit))
        
        stage_mgr = PipelineStageManager()
        if not stage_mgr.connect():
            return format_response(
                False,
                error='Failed to connect to MongoDB',
                status_code=500
            )
        
        pending = stage_mgr.get_pending_stages(limit=limit)
        
        formatted = []
        for stage in pending:
            formatted.append({
                'stage_id': stage.get('stage_id'),
                'document_id': stage.get('document_id'),
                'stage_number': stage.get('stage_number'),
                'stage_name': stage.get('stage_name'),
                'status': stage.get('status'),
                'created_at': stage.get('created_at').isoformat() if stage.get('created_at') else None,
                'filename': stage.get('filename')
            })
        
        stage_mgr.disconnect()
        
        response_data = {
            'pending_stages': formatted,
            'total': len(formatted),
            'limit': limit
        }
        
        return format_response(True, data=response_data)
        
    except Exception as e:
        app_logger.error(f"Get pending stages error: {str(e)}")
        return format_response(
            False,
            error=f"Server error: {str(e)}",
            status_code=500
        )


@app.route('/api/v1/stages/<stage_id>/approve', methods=['POST'])
def approve_stage(stage_id):
    """
    Approve a pending stage
    
    Request Body:
    {
        "approved_by": "user@example.com",
        "notes": "Verification passed"
    }
    
    Response:
    {
        "success": true,
        "data": {
            "stage_id": "stage_1_xyz123",
            "status": "approved",
            "approved_at": "2026-01-27T12:30:00"
        }
    }
    """
    try:
        from database import PipelineStageManager
        
        data = request.get_json() or {}
        approved_by = data.get('approved_by')
        notes = data.get('notes')
        
        if not approved_by:
            return format_response(
                False,
                error='approved_by is required',
                status_code=400
            )
        
        stage_mgr = PipelineStageManager()
        if not stage_mgr.connect():
            return format_response(
                False,
                error='Failed to connect to MongoDB',
                status_code=500
            )
        
        result = stage_mgr.approve_stage(stage_id, approved_by, notes)
        stage_mgr.disconnect()
        
        if result['success']:
            response_data = {
                'stage_id': stage_id,
                'status': 'approved',
                'approved_at': datetime.utcnow().isoformat(),
                'approved_by': approved_by
            }
            return format_response(True, data=response_data)
        else:
            return format_response(
                False,
                error=result.get('error', 'Approval failed'),
                status_code=500
            )
        
    except Exception as e:
        app_logger.error(f"Approve stage error: {str(e)}")
        return format_response(
            False,
            error=f"Server error: {str(e)}",
            status_code=500
        )


@app.route('/api/v1/stages/<stage_id>/reject', methods=['POST'])
def reject_stage(stage_id):
    """
    Reject a pending stage
    
    Request Body:
    {
        "rejected_by": "user@example.com",
        "reason": "Ambiguities not resolved"
    }
    
    Response:
    {
        "success": true,
        "data": {
            "stage_id": "stage_1_xyz123",
            "status": "rejected",
            "rejected_at": "2026-01-27T12:30:00"
        }
    }
    """
    try:
        from database import PipelineStageManager
        
        data = request.get_json() or {}
        rejected_by = data.get('rejected_by')
        reason = data.get('reason')
        
        if not rejected_by or not reason:
            return format_response(
                False,
                error='rejected_by and reason are required',
                status_code=400
            )
        
        stage_mgr = PipelineStageManager()
        if not stage_mgr.connect():
            return format_response(
                False,
                error='Failed to connect to MongoDB',
                status_code=500
            )
        
        result = stage_mgr.reject_stage(stage_id, rejected_by, reason)
        stage_mgr.disconnect()
        
        if result['success']:
            response_data = {
                'stage_id': stage_id,
                'status': 'rejected',
                'rejected_at': datetime.utcnow().isoformat(),
                'rejected_by': rejected_by,
                'reason': reason
            }
            return format_response(True, data=response_data)
        else:
            return format_response(
                False,
                error=result.get('error', 'Rejection failed'),
                status_code=500
            )
        
    except Exception as e:
        app_logger.error(f"Reject stage error: {str(e)}")
        return format_response(
            False,
            error=f"Server error: {str(e)}",
            status_code=500
        )


def process_document_internal(document_id):
    """
    Internal function to trigger pipeline without HTTP context
    Called automatically after document upload
    """
    try:
        # Validate document_id format
        if not document_id or not document_id.startswith('doc_'):
            return {'success': False, 'error': 'Invalid document_id format'}
        
        # Retrieve document from MongoDB
        doc = db_manager.get_document(document_id)
        if not doc:
            return {'success': False, 'error': f'Document not found in MongoDB: {document_id}'}
        
        app_logger.info(f"Starting async pipeline for: {document_id} ({doc['filename']})")
        
        # Create pipeline orchestrator
        pipeline = get_or_create_pipeline(document_id, db_manager)
        
        # Run pipeline in background thread
        def run_async_pipeline():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(pipeline.run())
            
            # After pipeline completes, trigger output formatter
            app_logger.info(f"Pipeline completed for {document_id}, triggering output_formatter.py")
            try:
                result = subprocess.run(
                    'cd /home/hutech/Documents/docupolicy && python3 output_formatter.py',
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                if result.returncode == 0:
                    app_logger.info(f"✅ output_formatter.py executed successfully")
                    app_logger.debug(f"Output: {result.stdout}")
                else:
                    app_logger.error(f"❌ output_formatter.py failed with return code {result.returncode}")
                    app_logger.error(f"Error: {result.stderr}")
            except subprocess.TimeoutExpired:
                app_logger.error(f"❌ output_formatter.py execution timed out")
            except Exception as e:
                app_logger.error(f"❌ Failed to execute output_formatter.py: {str(e)}")
        
        thread = threading.Thread(target=run_async_pipeline, daemon=True)
        thread.start()
        
        app_logger.info(f"Pipeline thread started for {document_id}")
        return {'success': True, 'status': 'processing'}
    
    except Exception as e:
        app_logger.error(f"Error in process_document_internal: {str(e)}")
        return {'success': False, 'error': str(e)}


@app.route('/api/v1/process-document/<document_id>', methods=['POST'])
def generate_pipeline(document_id):
     """
     Trigger the complete 7-stage policy validation pipeline (async)
     
     Starts an async pipeline in background. Returns immediately with status endpoint.
     
     URL: /api/v1/process-document/{document_id}
     
     Response:
     {
         "success": true,
         "data": {
             "document_id": "doc_abc123",
             "status": "processing",
             "status_url": "/api/v1/process-status/{document_id}",
             "message": "Pipeline started asynchronously. Check status_url for progress."
         }
     }
     """
     
     try:
         result = process_document_internal(document_id)
         
         if result['success']:
             return format_response(
                 True,
                 data={
                     'document_id': document_id,
                     'status': 'processing',
                     'status_url': f'/api/v1/process-status/{document_id}',
                     'message': 'Pipeline started asynchronously. Check status_url for progress.'
                 },
                 status_code=202
             )
         else:
             return format_response(
                 False,
                 error=result.get('error', 'Unknown error'),
                 status_code=400
             )
     
     except Exception as e:
         app_logger.error(f"Pipeline initiation error: {str(e)}")
         return format_response(
             False,
             error=f'Failed to start pipeline: {str(e)}',
             status_code=500
         )


@app.route('/api/v1/process-status/<document_id>', methods=['GET'])
def get_process_status(document_id):
    """
    Get pipeline processing status
    
    URL: /api/v1/process-status/{document_id}
    
    Response:
    {
        "success": true,
        "data": {
            "document_id": "doc_abc123",
            "status": "processing",
            "current_stage": 3,
            "total_stages": 7,
            "progress": 42,
            "elapsed_time": 125.5,
            "error": null
        }
    }
    """
    
    try:
        status = get_pipeline_status(document_id)
        
        if not status:
            return format_response(
                False,
                error=f'No pipeline found for document: {document_id}',
                status_code=404
            )
        
        return format_response(
            True,
            data=status,
            status_code=200
        )
    
    except Exception as e:
        app_logger.error(f"Status check error: {str(e)}")
        return format_response(
            False,
            error=f'Status check failed: {str(e)}',
            status_code=500
        )
        
        # Calculate total time
        total_time = time.time() - start_time
        
        # Cleanup temp file
        try:
            os.remove(temp_policy_file)
        except:
            pass
        
        # Return success response
        response_data = {
            'document_id': document_id,
            'status': 'processing_complete',
            'total_stages': len(stages_results),
            'stages': stages_results,
            'total_time_seconds': round(total_time, 2),
            'message': f'All {len(stages_results)} stages completed successfully. Each stage stored in MongoDB with status=pending_approval.',
            'next_steps': 'Review pending stages and approve/reject as needed'
        }
        
        app_logger.info(f"✓ Pipeline complete for {document_id} ({total_time:.2f}s)")
        
        return format_response(
            True,
            data=response_data,
            status_code=200
        )
        
    except Exception as e:
        app_logger.error(f"Pipeline exception: {str(e)}")
        return format_response(
            False,
            error=f'Pipeline failed: {str(e)}',
            status_code=500
        )


@app.route('/api/v1/normalized-policies', methods=['GET'])
def get_normalized_policies():
    """
    Get normalized policies from MongoDB (stage 8)
    WITH human-readable translations and approval status

    Response:
    {
        "success": true,
        "data": {
            "policies": [
                {
                    "policyId": "POLICY_C1",
                    "name": "Policy Rule C1",
                    "approval_status": "pending_approval|approved|rejected",
                    "approved_by": "email@company.com",
                    "approved_at": "2026-02-13T...",
                    "...": "...(original DSL fields)...",
                    "readable": {
                        "enforcement": "WARN",
                        "when_text": "Always applies",
                        "constraint": "Status must be Approved",
                        "explanation": "..."
                    }
                }
            ],
            "metadata": {...}
        }
    }
    """
    try:
        from database import PipelineStageManager
        
        # Try to fetch from MongoDB first
        db = PipelineStageManager()
        db.connect()
        stage8 = db.stages_collection.find_one({'stage_name': 'normalize-policies'})
        
        if stage8 and 'output' in stage8:
            policies_data = stage8['output']
        else:
            # Fallback to JSON file if MongoDB doesn't have it
            normalized_file = f"{OUTPUT_DIR}/stage8_normalized_policies.json"
            if not os.path.exists(normalized_file):
                return format_response(
                    False,
                    error='Normalized policies not found in MongoDB or file',
                    status_code=404
                )
            with open(normalized_file, 'r') as f:
                policies_data = json.load(f)

        # Add human-readable translations to each policy
        if 'policies' in policies_data:
            for policy in policies_data['policies']:
                # Stage8 already has translator-compatible structure
                policy['readable'] = PolicyTranslator.translate_policy(policy)

        return format_response(
            True,
            data=policies_data,
            status_code=200
        )

    except Exception as e:
        app_logger.error(f"Error reading normalized policies: {str(e)}")
        return format_response(
            False,
            error=f'Error reading normalized policies: {str(e)}',
            status_code=500
        )


@app.route('/api/v1/approve-policies', methods=['POST'])
def approve_policies():
    """
    Approve normalized policies and save to MongoDB
    
    Request:
    {
        "policies": [...],
        "metadata": {...},
        "approved_by": "user@example.com",
        "notes": "Approved after review"
    }
    
    Response:
    {
        "success": true,
        "data": {
            "saved_count": 21,
            "collection_name": "normalized_policies"
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return format_response(
                False,
                error='No data provided',
                status_code=400
            )
        
        policies = data.get('policies', [])
        metadata = data.get('metadata', {})
        approved_by = data.get('approved_by', 'unknown')
        notes = data.get('notes', '')
        
        if not policies:
            return format_response(
                False,
                error='No policies to save',
                status_code=400
            )
        
        # Save to MongoDB
        result = db_manager.save_normalized_policies(
            policies=policies,
            metadata=metadata,
            approved_by=approved_by,
            notes=notes
        )
        
        if result['success']:
            app_logger.info(f"Policies approved and saved by {approved_by}: {result['count']} policies")
            return format_response(
                True,
                data={
                    'saved_count': result['count'],
                    'collection_name': 'normalized_policies',
                    'timestamp': datetime.utcnow().isoformat()
                },
                status_code=201
            )
        else:
            app_logger.error(f"Failed to save policies: {result['error']}")
            return format_response(
                False,
                error=f"Failed to save policies: {result['error']}",
                status_code=500
            )
    
    except Exception as e:
        app_logger.error(f"Approval error: {str(e)}")
        return format_response(
            False,
            error=f'Approval failed: {str(e)}',
            status_code=500
        )


@app.route('/api/v1/decline-policies', methods=['POST'])
def decline_policies():
    """
    Decline normalized policies (log the action)
    
    Request:
    {
        "reason": "Needs review",
        "declined_by": "user@example.com"
    }
    
    Response:
    {
        "success": true,
        "data": {
            "status": "declined",
            "message": "Policies declined and logged"
        }
    }
    """
    try:
        data = request.get_json()
        
        declined_by = data.get('declined_by', 'unknown')
        reason = data.get('reason', 'No reason provided')
        
        # Log the declination
        app_logger.info(f"Policies declined by {declined_by}: {reason}")
        
        return format_response(
            True,
            data={
                'status': 'declined',
                'message': 'Policies declined and logged',
                'timestamp': datetime.utcnow().isoformat()
            },
            status_code=200
        )
    
    except Exception as e:
        app_logger.error(f"Decline error: {str(e)}")
        return format_response(
            False,
            error=f'Decline failed: {str(e)}',
            status_code=500
        )


@app.route('/api/v1/approve-clause', methods=['POST'])
def approve_clause():
    """
    Approve a single clause/policy
    
    Request:
    {
        "policy_id": "POLICY_C9",
        "approved_by": "user@example.com",
        "approval_notes": "Looks good"
    }
    
    Response:
    {
        "success": true,
        "data": {
            "policy_id": "POLICY_C9",
            "status": "approved"
        }
    }
    """
    try:
        from database import PipelineStageManager
        
        data = request.get_json()
        policy_id = data.get('policy_id')
        approved_by = data.get('approved_by')
        approval_notes = data.get('approval_notes', '')
        
        if not policy_id or not approved_by:
            return format_response(False, error='Missing policy_id or approved_by', status_code=400)
        
        # Get the current stage 8
        db = PipelineStageManager()
        db.connect()
        stage8 = db.stages_collection.find_one({'stage_name': 'normalize-policies'})
        
        if not stage8:
            return format_response(False, error='No normalized policies found', status_code=404)
        
        # Approve the clause
        result = db.approve_clause(
            stage_id=stage8['stage_id'],
            policy_id=policy_id,
            approved_by=approved_by,
            approval_notes=approval_notes
        )
        
        if result['success']:
            app_logger.info(f"Clause {policy_id} approved by {approved_by}")
            return format_response(
                True,
                data={
                    'policy_id': policy_id,
                    'status': 'approved',
                    'timestamp': datetime.utcnow().isoformat()
                },
                status_code=200
            )
        else:
            return format_response(False, error=result['error'], status_code=400)
    
    except Exception as e:
        app_logger.error(f"Approve clause error: {str(e)}")
        return format_response(False, error=f'Approval failed: {str(e)}', status_code=500)


@app.route('/api/v1/reject-clause', methods=['POST'])
def reject_clause():
    """
    Reject a single clause/policy
    
    Request:
    {
        "policy_id": "POLICY_C9",
        "rejected_by": "user@example.com",
        "rejection_reason": "Needs revision"
    }
    
    Response:
    {
        "success": true,
        "data": {
            "policy_id": "POLICY_C9",
            "status": "rejected"
        }
    }
    """
    try:
        from database import PipelineStageManager
        
        data = request.get_json()
        policy_id = data.get('policy_id')
        rejected_by = data.get('rejected_by')
        rejection_reason = data.get('rejection_reason', '')
        
        if not policy_id or not rejected_by:
            return format_response(False, error='Missing policy_id or rejected_by', status_code=400)
        
        # Get the current stage 8
        db = PipelineStageManager()
        db.connect()
        stage8 = db.stages_collection.find_one({'stage_name': 'normalize-policies'})
        
        if not stage8:
            return format_response(False, error='No normalized policies found', status_code=404)
        
        # Reject the clause
        result = db.reject_clause(
            stage_id=stage8['stage_id'],
            policy_id=policy_id,
            rejected_by=rejected_by,
            rejection_reason=rejection_reason
        )
        
        if result['success']:
            app_logger.info(f"Clause {policy_id} rejected by {rejected_by}: {rejection_reason}")
            return format_response(
                True,
                data={
                    'policy_id': policy_id,
                    'status': 'rejected',
                    'timestamp': datetime.utcnow().isoformat()
                },
                status_code=200
            )
        else:
            return format_response(False, error=result['error'], status_code=400)
    
    except Exception as e:
        app_logger.error(f"Reject clause error: {str(e)}")
        return format_response(False, error=f'Rejection failed: {str(e)}', status_code=500)


@app.route('/api/v1/generate-opa-bundle', methods=['POST'])
def generate_opa_bundle():
    """
    Trigger Stage 10: OPA Bundle Storage
    Generate OPA-compatible bundle from stage 9 Rego rules
    
    Request:
    {
        "stage9_file": "stage9_rego_bundles.json" (optional, defaults to file)
    }
    
    Response:
    {
        "success": true,
        "data": {
            "bundle_version": "1.0.0",
            "bundle_hash": "abc123...",
            "filesystem_path": "/path/to/bundle",
            "stage_id": "stage_10_xyz"
        }
    }
    """
    try:
        import subprocess
        
        data = request.get_json() or {}
        stage9_file = data.get('stage9_file', f'{OUTPUT_DIR}/stage9_rego_bundles.json')
        
        # Verify stage 9 file exists
        if not os.path.exists(stage9_file):
            return format_response(
                False,
                error=f'Stage 9 Rego bundles file not found: {stage9_file}',
                status_code=404
            )
        
        app_logger.info(f"Triggering Stage 10 (OPA Bundle Storage) with {stage9_file}")
        
        # Run stage 10 via policy_validator
        try:
            result = subprocess.run(
                ['python3', 'policy_validator.py', 'opa-bundle-storage', stage9_file],
                cwd=OUTPUT_DIR,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                app_logger.info(f"Stage 10 completed successfully")
                
                # Commit bundle to Git
                git_result = commit_bundle_to_git(OUTPUT_DIR, result.stdout)
                
                return format_response(
                    True,
                    data={
                        'message': 'OPA bundle generated successfully',
                        'output': result.stdout[-500:] if result.stdout else '',  # Last 500 chars
                        'bundle_file': f'{OUTPUT_DIR}/opa_bundles/v1.0.0/',
                        'git_commit': git_result.get('commit_hash') if git_result.get('success') else None,
                        'git_status': 'committed' if git_result.get('success') else 'pending'
                    },
                    status_code=200
                )
            else:
                error_msg = result.stderr if result.stderr else 'Stage 10 failed with unknown error'
                app_logger.error(f"Stage 10 failed: {error_msg}")
                return format_response(
                    False,
                    error=error_msg,
                    status_code=500
                )
        
        except subprocess.TimeoutExpired:
            return format_response(
                False,
                error='Stage 10 execution timed out (60s)',
                status_code=504
            )
    
    except Exception as e:
        app_logger.error(f"OPA bundle generation error: {str(e)}")
        return format_response(False, error=f'Bundle generation failed: {str(e)}', status_code=500)


     # ============================================================================
     # ERROR HANDLERS
     # ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return format_response(
        False,
        error='Endpoint not found',
        status_code=404
    )


@app.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 errors"""
    return format_response(
        False,
        error='Method not allowed',
        status_code=405
    )


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    app_logger.error(f"Internal server error: {str(error)}")
    return format_response(
        False,
        error='Internal server error',
        status_code=500
    )


# ============================================================================
# APP LIFECYCLE
# ============================================================================

@app.before_request
def before_request():
    """Before request hook"""
    app_logger.debug(f"{request.method} {request.path}")


@app.teardown_appcontext
def teardown_db(exception):
    """Cleanup on shutdown"""
    pass


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    # Connect to database
    if not db_manager.connect():
        app_logger.error("Failed to connect to MongoDB. Exiting.")
        exit(1)
    
    app_logger.info(f"Starting {config.SERVICE_NAME} v{config.SERVICE_VERSION}")
    app_logger.info(f"Environment: {config.FLASK_ENV}")
    app_logger.info(f"Listening on {config.SERVER_HOST}:{config.SERVER_PORT}")
    
    try:
        app.run(
            host=config.SERVER_HOST,
            port=config.SERVER_PORT,
            debug=config.FLASK_DEBUG
        )
    except KeyboardInterrupt:
        app_logger.info("Shutting down...")
    finally:
        db_manager.disconnect()
