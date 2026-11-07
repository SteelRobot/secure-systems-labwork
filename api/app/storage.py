"""Объектное хранилище (S3 API, MinIO) под отдельной учётной записью приложения."""
from minio import Minio

from . import config

client = Minio(config.STORAGE_ENDPOINT, access_key=config.STORAGE_ACCESS_KEY,
               secret_key=config.STORAGE_SECRET_KEY, secure=False)
