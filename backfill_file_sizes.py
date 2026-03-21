"""
One-time script: populate file_size_bytes in DB from R2 metadata.

Uses head_object (no data transfer) to get each file's size, then updates
the recordings table. Safe to re-run — skips rows that already have a size.

Usage:
  python backfill_file_sizes.py
"""

import os

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

R2_ACCOUNT_ID = os.environ["R2_ACCOUNT_ID"]
R2_ACCESS_KEY_ID = os.environ["R2_ACCESS_KEY_ID"]
R2_SECRET_ACCESS_KEY = os.environ["R2_SECRET_ACCESS_KEY"]
R2_BUCKET = os.environ["R2_BUCKET_NAME"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]


def main():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )

    # Fetch all recordings that have an R2 path but no file size yet
    result = (
        sb.table("recordings")
        .select("id, message_id, audio_r2_path, file_size_bytes")
        .not_.is_("audio_r2_path", "null")
        .execute()
    )
    rows = result.data
    to_update = [r for r in rows if not r.get("file_size_bytes")]
    already_have = len(rows) - len(to_update)

    print(f"Total with R2 path: {len(rows)}")
    print(f"Already have size:  {already_have}")
    print(f"Need backfill:      {len(to_update)}\n")

    succeeded = 0
    failed = 0
    not_found = 0

    for i, rec in enumerate(to_update, start=1):
        path = rec["audio_r2_path"]
        rec_id = rec["id"]
        try:
            head = s3.head_object(Bucket=R2_BUCKET, Key=path)
            size = head["ContentLength"]
            sb.table("recordings").update(
                {"file_size_bytes": size}
            ).eq("id", rec_id).execute()
            print(f"[{i}/{len(to_update)}] id={rec_id} → {size / 1_048_576:.1f} MB  ({path})")
            succeeded += 1
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code in ("404", "NoSuchKey"):
                print(f"[{i}/{len(to_update)}] id={rec_id} NOT FOUND in R2: {path}")
                not_found += 1
            else:
                print(f"[{i}/{len(to_update)}] id={rec_id} ERROR: {e}")
                failed += 1
        except Exception as e:
            print(f"[{i}/{len(to_update)}] id={rec_id} ERROR: {e}")
            failed += 1

    print(f"\n=== Done ===")
    print(f"  Updated:   {succeeded}")
    print(f"  Not found: {not_found}")
    print(f"  Errors:    {failed}")


if __name__ == "__main__":
    main()
