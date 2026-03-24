"""
test_r2.py — Standalone R2 connectivity test. No Telegram involved.

Run: python test_upload/test_r2.py

Tests:
  1. Can connect to R2 with current credentials
  2. Can upload a small object
  3. Can download it back and verify content
  4. Can delete the test object (cleanup)
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

REQUIRED = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME"]


def check():
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        print(f"❌ Missing env vars: {missing}")
        sys.exit(1)

    import boto3

    account_id = os.environ["R2_ACCOUNT_ID"]
    bucket = os.environ["R2_BUCKET_NAME"]
    test_key = "audio/test/canary.txt"
    test_content = b"SiachBot R2 canary test - ok"

    print(f"Bucket:   {bucket}")
    print(f"Endpoint: https://{account_id}.r2.cloudflarestorage.com")
    print()

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )

    # 1. Upload
    print("Step 1: uploading test object...")
    try:
        s3.put_object(Bucket=bucket, Key=test_key, Body=test_content)
        print("  ✅ upload succeeded")
    except Exception as e:
        print(f"  ❌ upload FAILED: {e}")
        sys.exit(1)

    # 2. Download and verify
    print("Step 2: downloading back and verifying...")
    try:
        import io
        buf = io.BytesIO()
        s3.download_fileobj(bucket, test_key, buf)
        downloaded = buf.getvalue()
        if downloaded == test_content:
            print(f"  ✅ content matches ({len(downloaded)} bytes)")
        else:
            print(f"  ❌ content mismatch! got: {downloaded!r}")
            sys.exit(1)
    except Exception as e:
        print(f"  ❌ download FAILED: {e}")
        sys.exit(1)

    # 3. Cleanup
    print("Step 3: deleting test object...")
    try:
        s3.delete_object(Bucket=bucket, Key=test_key)
        print("  ✅ deleted")
    except Exception as e:
        print(f"  ⚠️  delete failed (not critical): {e}")

    print()
    print("✅ R2 is working correctly.")


if __name__ == "__main__":
    check()
