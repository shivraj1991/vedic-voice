"""Audio storage on Cloudflare R2 (S3 API). Audio never passes through the API.

- The app uploads with a short-lived signed PUT to a server-chosen key (the
  user never picks the path) and plays reference audio via signed GETs.
- Two credentials (SECURITY.md least privilege): the read key signs GETs; the
  write key signs PUTs and does server-side HEAD/COPY/DELETE.
- Buckets: reference bucket holds `ref/` and `test/`; recordings bucket holds
  `rec/tmp/` (lifecycle: deleted after 24 h) and `rec/consented/`.

`MemoryStorage` is the test/dev fake with the same interface.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Literal, Protocol

Bucket = Literal["reference", "recordings"]

TMP_KEY = re.compile(r"^rec/tmp/(?P<user>[0-9a-f-]{36})/(?P<id>[0-9a-f]{32})\.m4a$")


@dataclass(frozen=True)
class ObjectInfo:
    size: int
    content_type: str | None


@dataclass(frozen=True)
class SignedUrl:
    url: str
    method: str
    headers: dict[str, str]
    expires_in: int


class Storage(Protocol):
    def presign_put(
        self, bucket: Bucket, key: str, content_type: str, expires: int
    ) -> SignedUrl: ...
    def presign_get(self, bucket: Bucket, key: str, expires: int) -> SignedUrl: ...
    def head(self, bucket: Bucket, key: str) -> ObjectInfo | None: ...
    def copy(self, bucket: Bucket, src: str, dst: str) -> None: ...
    def delete(self, bucket: Bucket, key: str) -> None: ...


def new_recording_key(user_id: uuid.UUID) -> str:
    return f"rec/tmp/{user_id}/{uuid.uuid4().hex}.m4a"


def consented_key(user_id: uuid.UUID, attempt_id: uuid.UUID) -> str:
    return f"rec/consented/{user_id}/{attempt_id}.m4a"


def new_asset_key(kind: str, slug: str, ext: str = "m4a") -> str:
    prefix = {"reference": "ref", "test": "test"}[kind]
    return f"{prefix}/{slug}/{uuid.uuid4().hex}.{ext}"


class R2Storage:
    def __init__(self, r2) -> None:
        import boto3
        from botocore.config import Config

        endpoint = f"https://{r2.account_id}.r2.cloudflarestorage.com"
        cfg = Config(signature_version="s3v4", retries={"max_attempts": 2}, connect_timeout=5)
        self._read = boto3.client("s3", endpoint_url=endpoint, region_name="auto", config=cfg,
                                  aws_access_key_id=r2.read_key_id,
                                  aws_secret_access_key=r2.read_secret)  # fmt: skip
        self._write = boto3.client("s3", endpoint_url=endpoint, region_name="auto", config=cfg,
                                   aws_access_key_id=r2.write_key_id,
                                   aws_secret_access_key=r2.write_secret)  # fmt: skip
        self._buckets = {"reference": r2.bucket_reference, "recordings": r2.bucket_recordings}

    def presign_put(self, bucket: Bucket, key: str, content_type: str, expires: int) -> SignedUrl:
        url = self._write.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._buckets[bucket], "Key": key, "ContentType": content_type},
            ExpiresIn=expires,
        )
        return SignedUrl(url, "PUT", {"Content-Type": content_type}, expires)

    def presign_get(self, bucket: Bucket, key: str, expires: int) -> SignedUrl:
        url = self._read.generate_presigned_url(
            "get_object", Params={"Bucket": self._buckets[bucket], "Key": key}, ExpiresIn=expires
        )
        return SignedUrl(url, "GET", {}, expires)

    def head(self, bucket: Bucket, key: str) -> ObjectInfo | None:
        from botocore.exceptions import ClientError

        try:
            r = self._write.head_object(Bucket=self._buckets[bucket], Key=key)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return ObjectInfo(int(r["ContentLength"]), r.get("ContentType"))

    def copy(self, bucket: Bucket, src: str, dst: str) -> None:
        b = self._buckets[bucket]
        self._write.copy_object(Bucket=b, Key=dst, CopySource={"Bucket": b, "Key": src})

    def delete(self, bucket: Bucket, key: str) -> None:
        self._write.delete_object(Bucket=self._buckets[bucket], Key=key)


@dataclass
class MemoryStorage:
    """In-memory fake: tests and local dev without R2."""

    objects: dict[tuple[str, str], ObjectInfo] = field(default_factory=dict)

    def put(self, bucket: Bucket, key: str, size: int, content_type: str = "audio/mp4") -> None:
        self.objects[(bucket, key)] = ObjectInfo(size, content_type)

    def presign_put(self, bucket: Bucket, key: str, content_type: str, expires: int) -> SignedUrl:
        return SignedUrl(f"memory://{bucket}/{key}?put", "PUT", {"Content-Type": content_type},
                         expires)  # fmt: skip

    def presign_get(self, bucket: Bucket, key: str, expires: int) -> SignedUrl:
        return SignedUrl(f"memory://{bucket}/{key}?get", "GET", {}, expires)

    def head(self, bucket: Bucket, key: str) -> ObjectInfo | None:
        return self.objects.get((bucket, key))

    def copy(self, bucket: Bucket, src: str, dst: str) -> None:
        self.objects[(bucket, dst)] = self.objects[(bucket, src)]

    def delete(self, bucket: Bucket, key: str) -> None:
        self.objects.pop((bucket, key), None)
