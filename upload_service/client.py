"""
Upload Service Client - Integration library for policy_validator

Usage:
    from client import UploadServiceClient
    
    client = UploadServiceClient(base_url="http://localhost:5000")
    result = client.upload_file("policy.txt")
    if result['success']:
        doc_id = result['document_id']
        content = client.get_content(doc_id)
"""

import requests
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class UploadServiceClient:
    """Client for Upload Service API"""
    
    def __init__(self, base_url="http://localhost:5000", api_version="v1"):
        """
        Initialize client
        
        Args:
            base_url: Service URL
            api_version: API version (default: v1)
        """
        self.base_url = base_url.rstrip('/')
        self.api_version = api_version
        self.api_url = f"{self.base_url}/api/{api_version}"
        self.logger = logging.getLogger(__name__)
    
    def health_check(self):
        """
        Check service health
        
        Returns:
            dict: {'status': 'healthy'|'unhealthy', 'database': {...}}
        """
        try:
            response = requests.get(f"{self.api_url}/health", timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('data', {})
            else:
                return {'status': 'unhealthy', 'error': f"HTTP {response.status_code}"}
        except Exception as e:
            self.logger.error(f"Health check failed: {str(e)}")
            return {'status': 'unhealthy', 'error': str(e)}
    
    def upload_file(self, file_path):
        """
        Upload document file
        
        Args:
            file_path (str): Path to file
            
        Returns:
            dict: {
                'success': bool,
                'document_id': str,
                'filename': str,
                'file_size': int,
                'stats': {'lines': int, 'words': int, 'characters': int},
                'version': int,
                'created_at': str,
                'error': str (if failed)
            }
        """
        
        try:
            file_path = Path(file_path)
            
            if not file_path.exists():
                return {
                    'success': False,
                    'document_id': None,
                    'error': f'File not found: {file_path}'
                }
            
            with open(file_path, 'rb') as f:
                files = {'file': f}
                response = requests.post(
                    f"{self.api_url}/upload",
                    files=files,
                    timeout=30
                )
            
            data = response.json()
            
            if response.status_code == 201 and data.get('success'):
                result = data.get('data', {})
                return {
                    'success': True,
                    'document_id': result.get('document_id'),
                    'filename': result.get('filename'),
                    'file_size': result.get('file_size'),
                    'file_type': result.get('file_type'),
                    'stats': result.get('stats', {}),
                    'version': result.get('version'),
                    'created_at': result.get('created_at'),
                    'error': None
                }
            else:
                error = data.get('error', 'Unknown error')
                self.logger.error(f"Upload failed: {error}")
                return {
                    'success': False,
                    'document_id': None,
                    'error': error
                }
        
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'document_id': None,
                'error': 'Upload timeout (30s exceeded)'
            }
        except Exception as e:
            self.logger.error(f"Upload error: {str(e)}")
            return {
                'success': False,
                'document_id': None,
                'error': str(e)
            }
    
    def get_document(self, document_id):
        """
        Get document metadata and preview
        
        Args:
            document_id (str): Document ID
            
        Returns:
            dict: Document data with preview
        """
        
        try:
            response = requests.get(
                f"{self.api_url}/documents/{document_id}",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'data': data.get('data', {}),
                    'error': None
                }
            elif response.status_code == 404:
                return {
                    'success': False,
                    'data': None,
                    'error': 'Document not found'
                }
            else:
                return {
                    'success': False,
                    'data': None,
                    'error': f'HTTP {response.status_code}'
                }
        
        except Exception as e:
            self.logger.error(f"Get document error: {str(e)}")
            return {
                'success': False,
                'data': None,
                'error': str(e)
            }
    
    def get_content(self, document_id):
        """
        Get full document content
        
        Args:
            document_id (str): Document ID
            
        Returns:
            str: Document content or None
        """
        
        try:
            response = requests.get(
                f"{self.api_url}/documents/{document_id}/content",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('data', {}).get('content')
            else:
                self.logger.error(f"Failed to get content: HTTP {response.status_code}")
                return None
        
        except Exception as e:
            self.logger.error(f"Get content error: {str(e)}")
            return None
    
    def list_documents(self, limit=10, skip=0):
        """
        List uploaded documents
        
        Args:
            limit (int): Number of documents
            skip (int): Skip count
            
        Returns:
            dict: {
                'success': bool,
                'documents': list,
                'total': int,
                'limit': int,
                'skip': int,
                'error': str
            }
        """
        
        try:
            response = requests.get(
                f"{self.api_url}/documents",
                params={'limit': limit, 'skip': skip},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                list_data = data.get('data', {})
                return {
                    'success': True,
                    'documents': list_data.get('documents', []),
                    'total': list_data.get('total', 0),
                    'limit': list_data.get('limit', limit),
                    'skip': list_data.get('skip', skip),
                    'error': None
                }
            else:
                return {
                    'success': False,
                    'documents': [],
                    'total': 0,
                    'error': f'HTTP {response.status_code}'
                }
        
        except Exception as e:
            self.logger.error(f"List documents error: {str(e)}")
            return {
                'success': False,
                'documents': [],
                'total': 0,
                'error': str(e)
            }
    
    def upload_and_extract(self, file_path):
        """
        Upload file and get full content (convenience method)
        
        Args:
            file_path (str): Path to file
            
        Returns:
            dict: {
                'success': bool,
                'document_id': str,
                'content': str,
                'stats': dict,
                'error': str
            }
        """
        
        # Upload
        upload_result = self.upload_file(file_path)
        
        if not upload_result['success']:
            return {
                'success': False,
                'document_id': None,
                'content': None,
                'stats': None,
                'error': upload_result['error']
            }
        
        doc_id = upload_result['document_id']
        
        # Get content
        content = self.get_content(doc_id)
        
        if not content:
            return {
                'success': False,
                'document_id': doc_id,
                'content': None,
                'stats': None,
                'error': 'Failed to retrieve content'
            }
        
        return {
            'success': True,
            'document_id': doc_id,
            'content': content,
            'stats': upload_result['stats'],
            'error': None
        }


# Convenience function
def connect_upload_service(base_url="http://localhost:5000"):
    """
    Create client and verify connection
    
    Args:
        base_url: Service URL
        
    Returns:
        UploadServiceClient or None if connection fails
    """
    
    client = UploadServiceClient(base_url)
    health = client.health_check()
    
    if health.get('status') != 'healthy':
        logger.error(f"Cannot connect to Upload Service: {health.get('error')}")
        return None
    
    logger.info(f"Connected to Upload Service at {base_url}")
    return client
