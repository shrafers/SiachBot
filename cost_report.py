"""
Monthly cost report — fetches R2 usage from Cloudflare GraphQL and emails
a summary of all service costs to REPORT_EMAIL.

Run manually:  python cost_report.py
Scheduled:     called by the bot's job queue on the 1st of each month.
"""

import os
import smtplib
import logging
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ── R2 pricing (USD, as of 2024) ─────────────────────────────────────────────
R2_STORAGE_FREE_GB = 10
R2_STORAGE_PRICE_PER_GB = 0.015          # per GB/month above free tier

R2_CLASS_A_FREE = 1_000_000              # writes (PUT, POST, DELETE, LIST)
R2_CLASS_A_PRICE_PER_M = 4.50           # per million above free tier

R2_CLASS_B_FREE = 10_000_000             # reads (GET, HEAD)
R2_CLASS_B_PRICE_PER_M = 0.36           # per million above free tier


# ── Cloudflare R2 usage ───────────────────────────────────────────────────────

def _cf_headers() -> dict:
    token = os.environ.get("CF_API_TOKEN", "")
    if not token:
        raise EnvironmentError("CF_API_TOKEN is not set")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def fetch_r2_usage(account_id: str, start: date, end: date) -> dict:
    """
    Query Cloudflare GraphQL for R2 storage bytes and operation counts
    over the given date range.

    Returns:
        {
          "storage_bytes": int,   # snapshot at end of period
          "class_a_ops": int,
          "class_b_ops": int,
        }
    """
    query = """
    query R2Usage($accountId: String!, $startDate: Date!, $endDate: Date!) {
      viewer {
        accounts(filter: {accountTag: $accountId}) {
          storageGroups: r2StorageAdaptiveGroups(
            filter: {date_geq: $startDate, date_leq: $endDate}
            limit: 10000
          ) {
            max {
              payloadSize
              metadataSize
            }
          }
          opsGroups: r2OperationsAdaptiveGroups(
            filter: {date_geq: $startDate, date_leq: $endDate}
            limit: 10000
          ) {
            sum {
              requests
            }
            dimensions {
              actionType
            }
          }
        }
      }
    }
    """
    variables = {
        "accountId": account_id,
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
    }
    resp = requests.post(
        "https://api.cloudflare.com/client/v4/graphql",
        headers=_cf_headers(),
        json={"query": query, "variables": variables},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("errors"):
        raise RuntimeError(f"Cloudflare GraphQL errors: {data['errors']}")

    account_data = data["data"]["viewer"]["accounts"][0]

    # Storage — take the max snapshot across all days
    storage_bytes = 0
    for g in account_data.get("storageGroups", []):
        payload = g.get("max", {}).get("payloadSize") or 0
        meta = g.get("max", {}).get("metadataSize") or 0
        storage_bytes = max(storage_bytes, payload + meta)

    # Operations — split by actionType
    # Class A: WriteObject, DeleteObject, ListBuckets, ListObjects, CreateBucket, DeleteBucket
    # https://developers.cloudflare.com/r2/pricing/
    CLASS_A_ACTIONS = {
        "CreateBucket", "DeleteBucket", "ListBuckets", "ListObjects",
        "PutObject", "CopyObject", "DeleteObject",
        "CreateMultipartUpload", "CompleteMultipartUpload",
        "ListMultipartUploads", "UploadPart", "UploadPartCopy",
        "PutBucketCors", "PutBucketLifecycle",
    }
    class_a_ops = 0
    class_b_ops = 0
    for g in account_data.get("opsGroups", []):
        action = (g.get("dimensions") or {}).get("actionType", "")
        count = (g.get("sum") or {}).get("requests") or 0
        if action in CLASS_A_ACTIONS:
            class_a_ops += count
        else:
            class_b_ops += count

    return {
        "storage_bytes": storage_bytes,
        "class_a_ops": class_a_ops,
        "class_b_ops": class_b_ops,
    }


def calculate_r2_cost(usage: dict) -> dict:
    """Compute R2 cost from usage dict. Returns cost breakdown in USD."""
    storage_gb = usage["storage_bytes"] / (1024 ** 3)
    billable_storage_gb = max(0.0, storage_gb - R2_STORAGE_FREE_GB)
    storage_cost = billable_storage_gb * R2_STORAGE_PRICE_PER_GB

    billable_class_a = max(0, usage["class_a_ops"] - R2_CLASS_A_FREE)
    class_a_cost = (billable_class_a / 1_000_000) * R2_CLASS_A_PRICE_PER_M

    billable_class_b = max(0, usage["class_b_ops"] - R2_CLASS_B_FREE)
    class_b_cost = (billable_class_b / 1_000_000) * R2_CLASS_B_PRICE_PER_M

    return {
        "storage_gb": storage_gb,
        "storage_cost": storage_cost,
        "class_a_ops": usage["class_a_ops"],
        "class_a_cost": class_a_cost,
        "class_b_ops": usage["class_b_ops"],
        "class_b_cost": class_b_cost,
        "total": storage_cost + class_a_cost + class_b_cost,
    }


# ── Email ─────────────────────────────────────────────────────────────────────

def _build_html(month_label: str, railway: float, supabase: float, r2: dict) -> str:
    grand_total = railway + supabase + r2["total"]

    def fmt(n):
        return f"${n:.2f}"

    def fmt_num(n):
        return f"{n:,}"

    rows = [
        ("Railway (Hobby plan)", fmt(railway), "fixed monthly"),
        ("Supabase (Free plan)", fmt(supabase), "fixed monthly"),
        (
            "Cloudflare R2",
            fmt(r2["total"]),
            f"Storage: {r2['storage_gb']:.2f} GB → {fmt(r2['storage_cost'])} | "
            f"Class A ops: {fmt_num(r2['class_a_ops'])} → {fmt(r2['class_a_cost'])} | "
            f"Class B ops: {fmt_num(r2['class_b_ops'])} → {fmt(r2['class_b_cost'])}",
        ),
    ]

    rows_html = "\n".join(
        f"""<tr>
          <td style="padding:8px 12px;border-bottom:1px solid #eee">{name}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right;font-weight:bold">{cost}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#666;font-size:13px">{note}</td>
        </tr>"""
        for name, cost, note in rows
    )

    return f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;color:#222;max-width:600px;margin:auto">
  <h2 style="border-bottom:2px solid #4a90e2;padding-bottom:8px">
    📊 SiachBot — Monthly Cost Report
  </h2>
  <p style="color:#666">{month_label}</p>
  <table style="width:100%;border-collapse:collapse;margin-top:16px">
    <thead>
      <tr style="background:#f5f5f5">
        <th style="padding:8px 12px;text-align:left">Service</th>
        <th style="padding:8px 12px;text-align:right">Cost</th>
        <th style="padding:8px 12px;text-align:left">Details</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
    <tfoot>
      <tr style="background:#e8f4e8">
        <td style="padding:10px 12px;font-weight:bold">Total</td>
        <td style="padding:10px 12px;text-align:right;font-weight:bold;font-size:18px">{fmt(grand_total)}</td>
        <td></td>
      </tr>
    </tfoot>
  </table>
  <p style="font-size:12px;color:#999;margin-top:24px">
    R2 costs are calculated from Cloudflare analytics and may differ slightly from
    the invoice due to adaptive sampling. Railway and Supabase figures are fixed plan costs.
  </p>
</body>
</html>"""


def send_email(subject: str, html_body: str) -> None:
    gmail_user = os.environ.get("GMAIL_SENDER", "")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "")
    recipient = os.environ.get("REPORT_EMAIL", "")

    if not all([gmail_user, gmail_password, recipient]):
        raise EnvironmentError(
            "GMAIL_SENDER, GMAIL_APP_PASSWORD, and REPORT_EMAIL must all be set"
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = recipient
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, recipient, msg.as_string())
    logger.info("Cost report email sent to %s", recipient)


# ── Main entry ────────────────────────────────────────────────────────────────

def run_cost_report() -> None:
    """Fetch usage, calculate costs, send email. Safe to call from scheduler."""
    today = date.today()
    # Report on the previous calendar month
    first_of_this_month = today.replace(day=1)
    last_month_end = first_of_this_month - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    month_label = last_month_start.strftime("%B %Y")

    account_id = os.environ.get("R2_ACCOUNT_ID", "")
    railway_cost = float(os.environ.get("RAILWAY_MONTHLY_COST", "5.00"))
    supabase_cost = float(os.environ.get("SUPABASE_MONTHLY_COST", "0.00"))

    logger.info("Fetching R2 usage for %s…", month_label)
    try:
        usage = fetch_r2_usage(account_id, last_month_start, last_month_end)
        r2 = calculate_r2_cost(usage)
    except Exception as exc:
        logger.error("Failed to fetch R2 usage: %s", exc)
        r2 = {
            "storage_gb": 0, "storage_cost": 0,
            "class_a_ops": 0, "class_a_cost": 0,
            "class_b_ops": 0, "class_b_cost": 0,
            "total": 0,
        }

    html = _build_html(month_label, railway_cost, supabase_cost, r2)
    subject = f"SiachBot costs — {month_label}"
    send_email(subject, html)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_cost_report()
