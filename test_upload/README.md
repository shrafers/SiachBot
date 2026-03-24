# Upload Flow Debug Tests

Three isolated tests to pinpoint exactly where the upload breaks.
Run them in order. Each one tests a smaller piece of the system.

---

## Step 1 — Test R2 (no Telegram)

```bash
python test_upload/test_r2.py
```

What it does: uploads a small test object to R2, downloads it back, verifies content, deletes it.

**If ✅**: R2 credentials and bucket are fine.
**If ❌**: Check `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME` in `.env`.

---

## Step 2 — Diagnose Telegram file download

```bash
python test_upload/test_tg_download.py
```

Start this bot, then send it **any audio file** (voice message, mp3, m4a). It will reply with:
- The exact raw `file_path` returned by `get_file()`
- Result of 3 download methods (size in bytes or error)

**Method 1** (`download_as_bytearray`) is the correct approach — it should work in both official API mode and local server mode.
**Method 2** (httpx on `file_path`) is the current broken approach — compare its URL with Method 1 to see what's wrong.
**Method 3** (manually constructed local server URL) only runs if `TELEGRAM_LOCAL_SERVER` is set.

**If Method 1 ✅**: The fix is simply replacing the download code in `upload.py` (see below).
**If Method 1 ❌**: The error message will explain why (e.g., file too large, timeout, auth error).

---

## Step 3 — Full pipeline (no form, no DB)

```bash
python test_upload/test_full_pipeline.py
```

Start this bot, then send it **any audio file**. It immediately:
1. Downloads via `download_as_bytearray()`
2. Uploads to R2 at `audio/test/{timestamp}.{ext}`
3. Downloads back from R2 to verify

If you get "✅ Full pipeline works!" — the chain is solid. The only remaining task is applying the fix to `upload.py`.

---

## The Fix

Once the tests confirm the diagnosis, apply this change to `bot/handlers/upload.py` in `confirm_upload()`:

**Remove** (lines ~459–476):
```python
tg_file = await update.callback_query.get_bot().get_file(file_id)
import re
token = os.environ["TELEGRAM_BOT_TOKEN"]
work_dir = os.environ.get("TELEGRAM_WORK_DIR", "/var/lib/telegram-bot-api")
url = re.sub(r'(?<![:/])//+', '/', tg_file.file_path)
url = url.replace(f"{work_dir}/{token}/", "/")
async with httpx.AsyncClient(timeout=300) as client:
    resp = await client.get(url)
    resp.raise_for_status()
    audio_bytes = resp.content
```

**Replace with:**
```python
tg_file = await update.callback_query.get_bot().get_file(file_id)
audio_bytes = bytes(await tg_file.download_as_bytearray())
```

Also remove the `import httpx` at the top of `upload.py` (no longer needed).

---

## Environment Variables Required

These must be set in `.env`:

| Variable | Used by |
|---|---|
| `TELEGRAM_BOT_TOKEN` | All tests (Steps 2, 3) |
| `R2_ACCOUNT_ID` | Steps 1, 3 |
| `R2_ACCESS_KEY_ID` | Steps 1, 3 |
| `R2_SECRET_ACCESS_KEY` | Steps 1, 3 |
| `R2_BUCKET_NAME` | Steps 1, 3 |
| `TELEGRAM_LOCAL_SERVER` | Optional — only if using local Bot API server |
| `TELEGRAM_WORK_DIR` | Optional — only if using local Bot API server |
