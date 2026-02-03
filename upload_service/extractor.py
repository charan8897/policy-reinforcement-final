"""
Document Content Extractor - Refactored from policy_validator.py

Supports: PDF, DOC, DOCX, TXT files
"""

import subprocess
import os
import tempfile
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class DocumentExtractor:
    """Extract text content from documents"""
    
    SUPPORTED_FORMATS = {
        'pdf': '_extract_pdf',
        'doc': '_extract_doc',
        'docx': '_extract_docx',
        'txt': '_extract_txt'
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def extract(self, file_path):
        """
        Extract text content from document
        
        Args:
            file_path (str): Path to document file
            
        Returns:
            dict: {
                'success': bool,
                'content': str,
                'stats': {'lines': int, 'words': int, 'chars': int},
                'error': str (if failed)
            }
        """
        
        try:
            # Get file extension
            ext = Path(file_path).suffix.lstrip('.').lower()
            
            if ext not in self.SUPPORTED_FORMATS:
                return {
                    'success': False,
                    'content': None,
                    'error': f'Unsupported file format: {ext}'
                }
            
            # Call appropriate extractor
            extractor_method = getattr(self, self.SUPPORTED_FORMATS[ext])
            content = extractor_method(file_path)
            
            if content is None:
                return {
                    'success': False,
                    'content': None,
                    'error': f'Failed to extract content from {ext} file'
                }
            
            # Calculate statistics
            stats = self._calculate_stats(content)
            
            return {
                'success': True,
                'content': content,
                'stats': stats,
                'error': None
            }
            
        except Exception as e:
            self.logger.error(f"Extraction error: {str(e)}")
            return {
                'success': False,
                'content': None,
                'error': str(e)
            }
    
    def _extract_pdf(self, file_path):
        """Extract text from PDF using pdftotext"""
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
                tmp_path = tmp.name
            
            # Use pdftotext command
            result = subprocess.run(
                ['pdftotext', file_path, tmp_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                self.logger.error(f"pdftotext error: {result.stderr}")
                os.unlink(tmp_path)
                return None
            
            # Read extracted text
            with open(tmp_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            os.unlink(tmp_path)
            return content
            
        except FileNotFoundError:
            self.logger.error("pdftotext not installed. Install: sudo apt-get install poppler-utils")
            return None
        except subprocess.TimeoutExpired:
            self.logger.error("PDF extraction timeout")
            return None
        except Exception as e:
            self.logger.error(f"PDF extraction failed: {str(e)}")
            return None
    
    def _extract_docx(self, file_path):
        """Extract text from DOCX"""
        
        try:
            from docx import Document
            
            doc = Document(file_path)
            content = '\n'.join([para.text for para in doc.paragraphs])
            return content
            
        except ImportError:
            self.logger.error("python-docx not installed. Install: pip install python-docx")
            return None
        except Exception as e:
            self.logger.error(f"DOCX extraction failed: {str(e)}")
            return None
    
    def _extract_doc(self, file_path):
        """Extract text from DOC (using libreoffice)"""
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
                tmp_path = tmp.name
            
            # Convert DOC to TXT using LibreOffice
            result = subprocess.run(
                ['libreoffice', '--headless', '--convert-to', 'txt', 
                 '--outdir', os.path.dirname(tmp_path), file_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                self.logger.warning("LibreOffice extraction failed, trying fallback")
                return self._extract_docx(file_path)  # Try as DOCX
            
            # Read converted file
            converted_path = file_path.replace('.doc', '.txt')
            with open(converted_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            os.unlink(converted_path)
            return content
            
        except FileNotFoundError:
            self.logger.error("LibreOffice not installed")
            return None
        except Exception as e:
            self.logger.error(f"DOC extraction failed: {str(e)}")
            return None
    
    def _extract_txt(self, file_path):
        """Extract text from TXT (direct read)"""
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            return content
        except Exception as e:
            self.logger.error(f"TXT extraction failed: {str(e)}")
            return None
    
    def _calculate_stats(self, content):
        """Calculate document statistics"""
        
        lines = len(content.split('\n'))
        words = len(content.split())
        chars = len(content)
        
        return {
            'lines': lines,
            'words': words,
            'characters': chars
        }
