from collections.abc import Iterator

import boto3
from botocore.client import BaseClient
from botocore.config import Config

from app.config import Settings, get_settings


class Storage:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        self.client = self._client(settings, settings.s3_endpoint)
        public = settings.s3_public_endpoint or settings.s3_endpoint
        self.public_client = self._client(settings, public)

    def upload_file(self, path: str, key: str, content_type: str) -> None:
        self.client.upload_file(path, self.bucket, key, ExtraArgs={"ContentType": content_type})

    def download_file(self, key: str, path: str) -> None:
        self.client.download_file(self.bucket, key, path)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def delete_prefix(self, prefix: str) -> None:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if objects:
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": objects, "Quiet": True})

    def size(self, key: str) -> int:
        response = self.client.head_object(Bucket=self.bucket, Key=key)
        return int(response["ContentLength"])

    def iter_bytes(self, key: str, start: int | None = None, end: int | None = None) -> Iterator[bytes]:
        kwargs: dict[str, str] = {"Bucket": self.bucket, "Key": key}
        if start is not None and end is not None:
            kwargs["Range"] = f"bytes={start}-{end}"
        response = self.client.get_object(**kwargs)
        yield from response["Body"].iter_chunks(64 * 1024)

    def signed_url(self, key: str, expires_seconds: int = 3600) -> str:
        return self.public_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )

    def _client(self, settings: Settings, endpoint: str) -> BaseClient:
        return boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )


def get_storage() -> Storage:
    return Storage(get_settings())
