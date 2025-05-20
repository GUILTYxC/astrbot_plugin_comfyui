import boto3
from botocore.client import Config
import os
from astrbot.api import logger

def upload_public_file(
    file_path: str,
    bucket_name: str,
    object_name: str,
    endpoint_url: str = "http://123.56.117.196:9000",
    access_key: str = "admin",
    secret_key: str = "admin123456"
):
    # 初始化 S3 客户端
    s3 = boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )

    try:
        s3.upload_file(file_path, bucket_name, object_name)
        # 拼接访问 URL（适用于公开 bucket）
        url = f"{endpoint_url}/{bucket_name}/{object_name}"
        logger.info(f"✅ 上传成功！文件可通过以下链接访问：\n{url}")
        return url
    except Exception as e:
        logger.info(f"❌ 上传失败: {e}")
        return None
