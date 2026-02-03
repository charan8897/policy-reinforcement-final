"""
Configuration module for Upload Service
"""

import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Base configuration"""
    
    # Flask
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'true').lower() == 'true'
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    
    # Server
    SERVER_HOST = os.getenv('SERVER_HOST', '0.0.0.0')
    SERVER_PORT = int(os.getenv('SERVER_PORT', 5000))
    
    # MongoDB
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    MONGODB_DB = os.getenv('MONGODB_DB', 'docupolicy_db')
    MONGODB_COLLECTION_DOCUMENTS = os.getenv('MONGODB_COLLECTION_DOCUMENTS', 'raw_documents')
    MONGODB_COLLECTION_STAGES = os.getenv('MONGODB_COLLECTION_STAGES', 'pipeline_stages')
    
    # Upload
    MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 52428800))  # 50MB
    ALLOWED_EXTENSIONS = set(os.getenv('ALLOWED_EXTENSIONS', 'pdf,doc,docx,txt').split(','))
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'upload_service.log')
    
    # API
    API_VERSION = 'v1'
    API_PREFIX = f'/api/{API_VERSION}'
    
    # Service metadata
    SERVICE_NAME = 'Document Upload Service'
    SERVICE_VERSION = '1.0.0'
    STARTUP_TIME = datetime.utcnow()


class DevelopmentConfig(Config):
    """Development configuration"""
    FLASK_DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration"""
    FLASK_DEBUG = False
    TESTING = False


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    MONGODB_DB = 'docupolicy_test_db'


# Configuration selector
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
}

def get_config(env=None):
    """Get configuration based on environment"""
    if env is None:
        env = os.getenv('FLASK_ENV', 'development')
    return config.get(env, DevelopmentConfig)
