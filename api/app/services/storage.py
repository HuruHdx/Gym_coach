"""统一公共资源存储：默认本地 static/；可选 S3 兼容（Cloudflare R2 / OSS）。"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from app.config import settings

_STATIC_ROOT = Path(__file__).resolve().parents[2] / "static"


def save_public_asset(data: bytes, key: str, content_type: str) -> str:
    """写入公共可读资源，返回可给 H5 / 后台直接用的 URL。

    key 例：plans/three-split-classic/cover_abc.jpg
    """
    key = key.lstrip("/").replace("\\", "/")
    if ".." in key.split("/"):
        raise ValueError("非法 key")

    backend = (settings.storage_backend or "local").strip().lower()
    if backend == "s3":
        return _save_s3(data, key, content_type)
    return _save_local(data, key)


def _save_local(data: bytes, key: str) -> str:
    dest = _STATIC_ROOT / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return f"/static/{key}"


def _save_s3(data: bytes, key: str, content_type: str) -> str:
    try:
        import boto3
    except ImportError as e:
        raise RuntimeError("STORAGE_BACKEND=s3 需要安装 boto3：pip install boto3") from e

    if not settings.s3_bucket_name:
        raise RuntimeError("S3_BUCKET_NAME 未配置")
    if not settings.s3_endpoint_url:
        raise RuntimeError("S3_ENDPOINT_URL 未配置")

    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id or None,
        aws_secret_access_key=settings.s3_secret_access_key or None,
        region_name=settings.s3_region or "auto",
    )
    client.put_object(
        Bucket=settings.s3_bucket_name,
        Key=key,
        Body=data,
        ContentType=content_type or mimetypes.guess_type(key)[0] or "application/octet-stream",
    )
    base = (settings.s3_public_base_url or "").rstrip("/")
    if not base:
        raise RuntimeError("S3_PUBLIC_BASE_URL 未配置")
    return f"{base}/{key}"
