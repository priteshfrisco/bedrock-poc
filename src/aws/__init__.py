"""
AWS Module - Cloud infrastructure integration
"""

from .s3_manager import S3Manager
from .dynamodb_manager import DynamoDBManager

__all__ = ['S3Manager', 'DynamoDBManager']

