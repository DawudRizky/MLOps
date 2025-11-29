"""
MinIO/S3 storage client for object storage operations.
"""
from minio import Minio
from minio.error import S3Error
from typing import Optional, List, BinaryIO
from io import BytesIO
import json
from datetime import timedelta
from .config import get_config
from .logging import get_logger
from .metrics import metrics

logger = get_logger(__name__)


class MinIOClient:
    """MinIO client for object storage operations."""
    
    def __init__(self):
        """Initialize MinIO client."""
        config = get_config()
        self.client = Minio(
            config.minio_endpoint,
            access_key=config.minio_access_key,
            secret_key=config.minio_secret_key,
            secure=config.minio_secure
        )
        self.config = config
        logger.info(f"MinIO client initialized: {config.minio_endpoint}")
    
    def ensure_bucket(self, bucket_name: str) -> bool:
        """
        Ensure bucket exists, create if it doesn't.
        
        Args:
            bucket_name: Name of the bucket
        
        Returns:
            True if bucket exists or was created successfully
        """
        try:
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
                logger.info(f"Created bucket: {bucket_name}")
                metrics.record_storage_operation("create_bucket", bucket_name, "success")
            return True
        except S3Error as e:
            logger.error(f"Failed to ensure bucket {bucket_name}: {e}")
            metrics.record_error("s3_error", "ensure_bucket")
            metrics.record_storage_operation("create_bucket", bucket_name, "error")
            return False
    
    def upload_file(self, bucket_name: str, object_name: str, file_path: str,
                    content_type: str = "application/octet-stream") -> bool:
        """
        Upload a file to MinIO.
        
        Args:
            bucket_name: Destination bucket
            object_name: Object name in bucket
            file_path: Local file path
            content_type: MIME type of the file
        
        Returns:
            True if upload successful
        """
        try:
            self.ensure_bucket(bucket_name)
            self.client.fput_object(
                bucket_name,
                object_name,
                file_path,
                content_type=content_type
            )
            logger.info(f"Uploaded {file_path} to {bucket_name}/{object_name}")
            metrics.record_storage_operation("upload", bucket_name, "success")
            return True
        except S3Error as e:
            logger.error(f"Failed to upload {file_path}: {e}")
            metrics.record_error("s3_error", "upload_file")
            metrics.record_storage_operation("upload", bucket_name, "error")
            return False
    
    def upload_data(self, bucket_name: str, object_name: str, data: bytes,
                    content_type: str = "application/octet-stream") -> bool:
        """
        Upload data directly to MinIO.
        
        Args:
            bucket_name: Destination bucket
            object_name: Object name in bucket
            data: Data bytes to upload
            content_type: MIME type
        
        Returns:
            True if upload successful
        """
        try:
            self.ensure_bucket(bucket_name)
            data_stream = BytesIO(data)
            self.client.put_object(
                bucket_name,
                object_name,
                data_stream,
                length=len(data),
                content_type=content_type
            )
            logger.info(f"Uploaded data to {bucket_name}/{object_name}")
            metrics.record_storage_operation("upload", bucket_name, "success")
            return True
        except S3Error as e:
            logger.error(f"Failed to upload data: {e}")
            metrics.record_error("s3_error", "upload_data")
            metrics.record_storage_operation("upload", bucket_name, "error")
            return False
    
    def upload_json(self, bucket_name: str, object_name: str, data: dict) -> bool:
        """
        Upload JSON data to MinIO.
        
        Args:
            bucket_name: Destination bucket
            object_name: Object name in bucket
            data: Dictionary to upload as JSON
        
        Returns:
            True if upload successful
        """
        json_bytes = json.dumps(data, indent=2).encode('utf-8')
        return self.upload_data(bucket_name, object_name, json_bytes, "application/json")
    
    def download_file(self, bucket_name: str, object_name: str, file_path: str) -> bool:
        """
        Download a file from MinIO.
        
        Args:
            bucket_name: Source bucket
            object_name: Object name in bucket
            file_path: Local destination path
        
        Returns:
            True if download successful
        """
        try:
            self.client.fget_object(bucket_name, object_name, file_path)
            logger.info(f"Downloaded {bucket_name}/{object_name} to {file_path}")
            metrics.record_storage_operation("download", bucket_name, "success")
            return True
        except S3Error as e:
            logger.error(f"Failed to download {bucket_name}/{object_name}: {e}")
            metrics.record_error("s3_error", "download_file")
            metrics.record_storage_operation("download", bucket_name, "error")
            return False
    
    def download_data(self, bucket_name: str, object_name: str) -> Optional[bytes]:
        """
        Download data from MinIO.
        
        Args:
            bucket_name: Source bucket
            object_name: Object name in bucket
        
        Returns:
            Data bytes or None if failed
        """
        try:
            response = self.client.get_object(bucket_name, object_name)
            data = response.read()
            response.close()
            response.release_conn()
            logger.info(f"Downloaded data from {bucket_name}/{object_name}")
            metrics.record_storage_operation("download", bucket_name, "success")
            return data
        except S3Error as e:
            logger.error(f"Failed to download data: {e}")
            metrics.record_error("s3_error", "download_data")
            metrics.record_storage_operation("download", bucket_name, "error")
            return None
    
    def download_json(self, bucket_name: str, object_name: str) -> Optional[dict]:
        """
        Download JSON data from MinIO.
        
        Args:
            bucket_name: Source bucket
            object_name: Object name in bucket
        
        Returns:
            Parsed JSON dictionary or None if failed
        """
        data = self.download_data(bucket_name, object_name)
        if data:
            try:
                return json.loads(data.decode('utf-8'))
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON: {e}")
                metrics.record_error("json_error", "download_json")
        return None
    
    def list_objects(self, bucket_name: str, prefix: str = "") -> List[str]:
        """
        List objects in a bucket.
        
        Args:
            bucket_name: Bucket to list
            prefix: Object prefix filter
        
        Returns:
            List of object names
        """
        try:
            objects = self.client.list_objects(bucket_name, prefix=prefix)
            object_names = [obj.object_name for obj in objects]
            logger.info(f"Listed {len(object_names)} objects in {bucket_name}")
            metrics.record_storage_operation("list", bucket_name, "success")
            return object_names
        except S3Error as e:
            logger.error(f"Failed to list objects in {bucket_name}: {e}")
            metrics.record_error("s3_error", "list_objects")
            metrics.record_storage_operation("list", bucket_name, "error")
            return []
    
    def delete_object(self, bucket_name: str, object_name: str) -> bool:
        """
        Delete an object from MinIO.
        
        Args:
            bucket_name: Source bucket
            object_name: Object to delete
        
        Returns:
            True if deletion successful
        """
        try:
            self.client.remove_object(bucket_name, object_name)
            logger.info(f"Deleted {bucket_name}/{object_name}")
            metrics.record_storage_operation("delete", bucket_name, "success")
            return True
        except S3Error as e:
            logger.error(f"Failed to delete {bucket_name}/{object_name}: {e}")
            metrics.record_error("s3_error", "delete_object")
            metrics.record_storage_operation("delete", bucket_name, "error")
            return False
    
    def get_presigned_url(self, bucket_name: str, object_name: str,
                          expires: timedelta = timedelta(hours=1)) -> Optional[str]:
        """
        Generate a presigned URL for temporary access.
        
        Args:
            bucket_name: Bucket containing the object
            object_name: Object name
            expires: URL expiration time
        
        Returns:
            Presigned URL or None if failed
        """
        try:
            url = self.client.presigned_get_object(bucket_name, object_name, expires=expires)
            logger.info(f"Generated presigned URL for {bucket_name}/{object_name}")
            return url
        except S3Error as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            metrics.record_error("s3_error", "get_presigned_url")
            return None
