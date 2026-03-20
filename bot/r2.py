"""Cloudflare R2 helper — download audio bytes for sending via Telegram bot."""

import asyncio
import io
import os

import boto3
from dotenv import load_dotenv

load_dotenv()


def _make_s3_client():
    account_id = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


_s3 = None


def _get_s3():
    global _s3
    if _s3 is None:
        _s3 = _make_s3_client()
    return _s3


def _download_sync(r2_path: str) -> bytes:
    bucket = os.environ["R2_BUCKET_NAME"]
    buf = io.BytesIO()
    _get_s3().download_fileobj(bucket, r2_path, buf)
    return buf.getvalue()


async def get_audio_bytes(r2_path: str) -> bytes:
    """Download audio file from R2 and return bytes. Runs boto3 in a thread."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _download_sync, r2_path)


def upload_audio_sync(data: bytes, r2_path: str) -> None:
    """Upload bytes to R2 at the given path."""
    bucket = os.environ["R2_BUCKET_NAME"]
    _get_s3().put_object(Bucket=bucket, Key=r2_path, Body=data)


async def upload_audio(data: bytes, r2_path: str) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, upload_audio_sync, data, r2_path)
