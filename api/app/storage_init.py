"""Одноразово создаёт бакет documents (запускается контейнером storage-init)."""
import os
import time

from minio import Minio

c = Minio(os.environ["STORAGE_ENDPOINT"], access_key=os.environ["STORAGE_ACCESS_KEY"],
          secret_key=os.environ["STORAGE_SECRET_KEY"], secure=False)
for _ in range(30):
    try:
        if not c.bucket_exists("documents"):
            c.make_bucket("documents")
        print("storage-init: бакет documents готов")
        break
    except Exception as e:  # хранилище ещё стартует
        print("ожидание хранилища:", type(e).__name__)
        time.sleep(2)
else:
    raise SystemExit(1)
