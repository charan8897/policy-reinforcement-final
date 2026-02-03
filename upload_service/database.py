"""
MongoDB Database Management
"""

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from datetime import datetime
import logging
import uuid
from config import Config

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manage MongoDB connection and operations"""
    
    def __init__(self, config=None):
        """
        Initialize database manager
        
        Args:
            config: Configuration object (uses Config if None)
        """
        self.config = config or Config
        self.client = None
        self.db = None
        self.collection = None
    
    def connect(self):
        """
        Connect to MongoDB
        
        Returns:
            bool: True if connected, False otherwise
        """
        
        try:
            self.client = MongoClient(
                self.config.MONGODB_URI,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000
            )
            
            # Test connection
            self.client.admin.command('ping')
            
            # Get database and collection
            self.db = self.client[self.config.MONGODB_DB]
            self.collection = self.db[self.config.MONGODB_COLLECTION_DOCUMENTS]
            
            # Create indexes
            self._create_indexes()
            
            logger.info(f"Connected to MongoDB: {self.config.MONGODB_URI}")
            return True
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Database connection error: {str(e)}")
            return False
    
    def disconnect(self):
        """Disconnect from MongoDB"""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB")
    
    def _create_indexes(self):
        """Create necessary database indexes"""
        
        try:
            # Index for timestamps (for sorting/filtering)
            self.collection.create_index('created_at')
            self.collection.create_index('updated_at')
            
            # Compound index for document_id + is_active (for active version lookup)
            self.collection.create_index([('document_id', 1), ('is_active', 1)])
            
            # Index for filename + is_active (for checking existing documents)
            self.collection.create_index([('filename', 1), ('is_active', 1)])
            
            logger.info("Database indexes created successfully")
            
        except Exception as e:
            logger.warning(f"Index creation warning: {str(e)}")
    
    def insert_document(self, document_data):
        """
        Insert new document or create new version if filename exists
        
        Args:
            document_data (dict): Document data with keys:
                - filename: Original filename (used for versioning)
                - file_type: File extension
                - file_size: File size in bytes
                - content: Extracted text content
                - stats: {'lines', 'words', 'characters'}
                - metadata: Additional metadata
        
        Returns:
            dict: {
                'success': bool,
                'document_id': str,
                'version': int,
                'created_at': datetime,
                'error': str (if failed)
            }
        """
        
        try:
            filename = document_data['filename']
            
            # Check if document with same filename exists
            existing = self.collection.find_one({'filename': filename, 'is_active': True})
            
            if existing:
                # Create new version
                next_version = existing.get('version', 1) + 1
                document_id = existing['document_id']  # Keep same ID
                
                # Deactivate old version
                self.collection.update_one(
                    {'_id': existing['_id']},
                    {'$set': {'is_active': False, 'archived_at': datetime.utcnow()}}
                )
                
                logger.info(f"Deactivated previous version: {document_id} v{existing.get('version', 1)}")
            else:
                # New document
                next_version = 1
                document_id = f"doc_{uuid.uuid4().hex[:12]}"
            
            # Create new version document
            doc = {
                'document_id': document_id,
                'filename': filename,
                'file_type': document_data['file_type'],
                'file_size': document_data['file_size'],
                'content': document_data['content'],
                'stats': document_data['stats'],
                'metadata': document_data.get('metadata', {}),
                'version': next_version,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
                'is_active': True
            }
            
            result = self.collection.insert_one(doc)
            
            logger.info(f"Document version created: {document_id} v{next_version}")
            
            return {
                'success': True,
                'document_id': document_id,
                'version': next_version,
                'created_at': doc['created_at'],
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Document insertion failed: {str(e)}")
            return {
                'success': False,
                'document_id': None,
                'version': None,
                'created_at': None,
                'error': str(e)
            }
    
    def get_document(self, document_id):
        """
        Retrieve document by ID
        
        Args:
            document_id (str): Document identifier
            
        Returns:
            dict: Document data or None
        """
        
        try:
            doc = self.collection.find_one(
                {'document_id': document_id, 'is_active': True}
            )
            return doc
        except Exception as e:
            logger.error(f"Document retrieval failed: {str(e)}")
            return None
    
    def list_documents(self, limit=10, skip=0):
        """
        List documents with pagination
        
        Args:
            limit (int): Number of documents to return
            skip (int): Number of documents to skip
            
        Returns:
            list: List of documents
        """
        
        try:
            docs = list(self.collection.find(
                {'is_active': True}
            ).sort('created_at', -1).limit(limit).skip(skip))
            
            return docs
        except Exception as e:
            logger.error(f"Document listing failed: {str(e)}")
            return []
    
    def update_document(self, document_id, update_data):
        """
        Update document
        
        Args:
            document_id (str): Document identifier
            update_data (dict): Fields to update
            
        Returns:
            dict: {'success': bool, 'version': int, 'error': str}
        """
        
        try:
            # Get current document
            current = self.collection.find_one({'document_id': document_id})
            if not current:
                return {'success': False, 'version': None, 'error': 'Document not found'}
            
            # Increment version
            new_version = current.get('version', 1) + 1
            
            # Update document
            update_data['version'] = new_version
            update_data['updated_at'] = datetime.utcnow()
            
            self.collection.update_one(
                {'document_id': document_id},
                {'$set': update_data}
            )
            
            logger.info(f"Document updated: {document_id}, version: {new_version}")
            
            return {
                'success': True,
                'version': new_version,
                'error': None
            }
        
        except Exception as e:
            logger.error(f"Document update failed: {str(e)}")
            return {'success': False, 'version': None, 'error': str(e)}
    
    def save_normalized_policies(self, policies, metadata, approved_by, notes=''):
        """
        Save normalized policies to MongoDB
        
        Args:
            policies (list): List of policy objects
            metadata (dict): Metadata about the policies
            approved_by (str): User who approved
            notes (str): Approval notes
            
        Returns:
            dict: {'success': bool, 'count': int, 'error': str}
        """
        
        try:
            # Get or create normalized_policies collection
            policies_collection = self.db['normalized_policies']
            
            # Create indexes for lookups
            policies_collection.create_index('policyId', unique=False)
            policies_collection.create_index('core_attributes.clauseId')
            policies_collection.create_index('status')
            policies_collection.create_index('approved_at')
            
            # Insert individual policy records with full Stage 8 structure
            inserted_ids = []
            for policy in policies:
                policy_record = {
                    # UI-compatible top-level fields
                    'policyId': policy.get('policyId'),
                    'name': policy.get('name'),
                    'outcome': policy.get('outcome'),
                    'when': policy.get('when'),
                    'what': policy.get('what'),
                    
                    # Full consolidated structure from Stage 8
                    'core_attributes': policy.get('core_attributes'),
                    'classification': policy.get('classification'),
                    'extracted_data': policy.get('extracted_data'),
                    'ambiguity_analysis': policy.get('ambiguity_analysis'),
                    'dsl_rules': policy.get('dsl_rules'),
                    'rationale_metadata': policy.get('rationale_metadata'),
                    
                    # Approval metadata
                    'status': 'approved',
                    'approved_by': approved_by,
                    'approval_notes': notes,
                    'approved_at': datetime.utcnow(),
                    
                    # Document tracking
                    'batch_id': metadata.get('generated', str(datetime.utcnow())),
                    'document_id': metadata.get('document_id', 'unknown')
                }
                result = policies_collection.insert_one(policy_record)
                inserted_ids.append(result.inserted_id)
            
            logger.info(f"Normalized policies saved: {len(inserted_ids)} policies by {approved_by}")
            
            return {
                'success': True,
                'count': len(inserted_ids),
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Save normalized policies failed: {str(e)}")
            return {'success': False, 'count': 0, 'error': str(e)}
    
    def delete_document(self, document_id):
        """
        Soft delete document (mark as inactive)
        
        Args:
            document_id (str): Document identifier
            
        Returns:
            bool: True if successful
        """
        
        try:
            self.collection.update_one(
                {'document_id': document_id},
                {'$set': {'is_active': False, 'deleted_at': datetime.utcnow()}}
            )
            logger.info(f"Document deleted: {document_id}")
            return True
        except Exception as e:
            logger.error(f"Document deletion failed: {str(e)}")
            return False
    
    def health_check(self):
        """
        Check database health
        
        Returns:
            dict: {'status': 'healthy'|'unhealthy', 'details': str}
        """
        
        try:
            if not self.client:
                return {'status': 'unhealthy', 'details': 'Not connected'}
            
            self.client.admin.command('ping')
            doc_count = self.collection.count_documents({})
            
            return {
                'status': 'healthy',
                'details': f'{doc_count} documents in database'
            }
        except Exception as e:
            return {'status': 'unhealthy', 'details': str(e)}


class PipelineStageManager:
    """Manage storage of policy validation pipeline stages in MongoDB"""
    
    def __init__(self, config=None):
        """
        Initialize pipeline stage manager
        
        Args:
            config: Configuration object (uses Config if None)
        """
        self.config = config or Config
        self.client = None
        self.db = None
        self.stages_collection = None
    
    def connect(self):
        """
        Connect to MongoDB for pipeline stages
        
        Returns:
            bool: True if connected, False otherwise
        """
        
        try:
            self.client = MongoClient(
                self.config.MONGODB_URI,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000
            )
            
            # Test connection
            self.client.admin.command('ping')
            
            # Get database and collection
            self.db = self.client[self.config.MONGODB_DB]
            self.stages_collection = self.db[self.config.MONGODB_COLLECTION_STAGES]
            
            # Create indexes
            self._create_indexes()
            
            logger.info(f"Connected to MongoDB (Pipeline Stages): {self.config.MONGODB_URI}")
            return True
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Pipeline stage connection error: {str(e)}")
            return False
    
    def disconnect(self):
        """Disconnect from MongoDB"""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB (Pipeline Stages)")
    
    def _create_indexes(self):
        """Create necessary indexes for pipeline stages"""
        
        try:
            # Index for document_id lookup
            self.stages_collection.create_index('document_id')
            
            # Index for stage number
            self.stages_collection.create_index('stage_number')
            
            # Compound index for document_id + stage_number
            self.stages_collection.create_index([('document_id', 1), ('stage_number', 1)])
            
            # Index for status (for filtering pending approvals)
            self.stages_collection.create_index('status')
            
            # Index for timestamps
            self.stages_collection.create_index('created_at')
            
            logger.info("Pipeline stage indexes created successfully")
            
        except Exception as e:
            logger.warning(f"Stage index creation warning: {str(e)}")
    
    def insert_stage(self, document_id, stage_number, stage_name, stage_output, filename=None):
        """
        Insert a pipeline stage result into MongoDB
        
        Args:
            document_id (str): Reference to document in raw_documents
            stage_number (int): Stage number (1-7)
            stage_name (str): Name of stage (e.g., "extract", "classify-intents")
            stage_output (dict or list): The output JSON/data from this stage
            filename (str): Original filename (optional)
        
        Returns:
            dict: {
                'success': bool,
                'stage_id': str,
                'status': str,
                'created_at': datetime,
                'error': str (if failed)
            }
        """
        
        try:
            stage_id = f"stage_{stage_number}_{uuid.uuid4().hex[:8]}"
            
            # Create stage record
            stage_record = {
                'stage_id': stage_id,
                'document_id': document_id,
                'filename': filename or 'unknown',
                'stage_number': stage_number,
                'stage_name': stage_name,
                'status': 'pending_approval',
                'output': stage_output,
                'metadata': {
                    'created_by': 'policy_validator',
                    'stage_class': stage_name.replace('-', '_').title()
                },
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
                'approved_at': None,
                'approved_by': None,
                'approval_notes': None
            }
            
            result = self.stages_collection.insert_one(stage_record)
            
            logger.info(f"Stage {stage_number} ({stage_name}) stored: {stage_id}")
            
            return {
                'success': True,
                'stage_id': stage_id,
                'status': 'pending_approval',
                'created_at': stage_record['created_at'],
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Stage insertion failed: {str(e)}")
            return {
                'success': False,
                'stage_id': None,
                'status': None,
                'created_at': None,
                'error': str(e)
            }
    
    def get_stage(self, stage_id):
        """
        Retrieve stage by ID
        
        Args:
            stage_id (str): Stage identifier
            
        Returns:
            dict: Stage data or None
        """
        
        try:
            stage = self.stages_collection.find_one({'stage_id': stage_id})
            return stage
        except Exception as e:
            logger.error(f"Stage retrieval failed: {str(e)}")
            return None
    
    def get_document_stages(self, document_id):
        """
        Get all stages for a document
        
        Args:
            document_id (str): Document identifier
            
        Returns:
            list: List of all stages for this document, sorted by stage_number
        """
        
        try:
            stages = list(self.stages_collection.find(
                {'document_id': document_id}
            ).sort('stage_number', 1))
            
            return stages
        except Exception as e:
            logger.error(f"Document stages retrieval failed: {str(e)}")
            return []
    
    def get_pending_stages(self, limit=10):
        """
        Get all stages pending approval
        
        Args:
            limit (int): Maximum number to return
            
        Returns:
            list: List of pending stages
        """
        
        try:
            stages = list(self.stages_collection.find(
                {'status': 'pending_approval'}
            ).sort('created_at', -1).limit(limit))
            
            return stages
        except Exception as e:
            logger.error(f"Pending stages retrieval failed: {str(e)}")
            return []
    
    def approve_stage(self, stage_id, approved_by, approval_notes=None):
        """
        Mark stage as approved
        
        Args:
            stage_id (str): Stage identifier
            approved_by (str): User who approved
            approval_notes (str): Optional approval notes
            
        Returns:
            dict: {'success': bool, 'error': str}
        """
        
        try:
            self.stages_collection.update_one(
                {'stage_id': stage_id},
                {'$set': {
                    'status': 'approved',
                    'approved_at': datetime.utcnow(),
                    'approved_by': approved_by,
                    'approval_notes': approval_notes,
                    'updated_at': datetime.utcnow()
                }}
            )
            
            logger.info(f"Stage approved: {stage_id} by {approved_by}")
            
            return {'success': True, 'error': None}
            
        except Exception as e:
            logger.error(f"Stage approval failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def reject_stage(self, stage_id, rejected_by, rejection_reason):
        """
        Mark stage as rejected
        
        Args:
            stage_id (str): Stage identifier
            rejected_by (str): User who rejected
            rejection_reason (str): Reason for rejection
            
        Returns:
            dict: {'success': bool, 'error': str}
        """
        
        try:
            self.stages_collection.update_one(
                {'stage_id': stage_id},
                {'$set': {
                    'status': 'rejected',
                    'rejected_at': datetime.utcnow(),
                    'rejected_by': rejected_by,
                    'rejection_reason': rejection_reason,
                    'updated_at': datetime.utcnow()
                }}
            )
            
            logger.info(f"Stage rejected: {stage_id} by {rejected_by}")
            
            return {'success': True, 'error': None}
            
        except Exception as e:
            logger.error(f"Stage rejection failed: {str(e)}")
            return {'success': False, 'error': str(e)}
