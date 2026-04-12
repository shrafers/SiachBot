"""
Stage 3: Tag recordings with Claude API using the Batches API.

One request per recording, matched back via custom_id = message_id.
Results are saved incrementally to data/tagged_recordings.json.
"""

import argparse
import json
import os
import sys
import time

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request
from dotenv import load_dotenv

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────
MODEL = "claude-opus-4-6"
MAX_TOKENS = 512
SAVE_EVERY = 50  # write output file every N results processed

DATA_DIR = "data"
INPUT_FILE = os.path.join(DATA_DIR, "all_recordings.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "tagged_recordings.json")
PROMPT_FILE = "prompts/tag_recordings.txt"

# Batches API pricing (50% off standard rates)
PRICE_CACHE_WRITE_PER_M = 5.00 * 1.25 * 0.5   # $3.125 / 1M tokens
PRICE_CACHE_READ_PER_M  = 5.00 * 0.10 * 0.5   # $0.25  / 1M tokens
PRICE_INPUT_PER_M       = 5.00 * 0.5           # $2.50  / 1M tokens (non-cached)
PRICE_OUTPUT_PER_M      = 25.00 * 0.5          # $12.50 / 1M tokens
AVG_OUTPUT_TOKENS       = 120                  # estimated per recording


# ── Helpers ─────────────────────────────────────────────────────────────────

def load_system_prompt() -> str:
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    # The file starts with "SYSTEM\n\n" — strip that literal header if present
    if content.startswith("SYSTEM\n"):
        content = content[len("SYSTEM\n"):].lstrip("\n")
    return content


def format_user_message(recording: dict) -> str:
    prev_text = None
    if recording.get("prev_message"):
        prev_text = recording["prev_message"].get("text")
    next_text = None
    if recording.get("next_message"):
        next_text = recording["next_message"].get("text")

    payload = {
        "filename":          recording.get("filename", ""),
        "sender":            recording.get("sender", ""),
        "date":              recording.get("date", ""),
        "caption":           recording.get("caption"),
        "prev_message_text": prev_text,
        "next_message_text": next_text,
    }
    return json.dumps(payload, ensure_ascii=False)


def estimate_cost(system_tokens: int, n_recordings: int) -> dict:
    """Return a cost breakdown dict."""
    user_tokens_each = 150  # rough estimate per recording

    # First request: cache write for system prompt
    first_input = system_tokens * PRICE_CACHE_WRITE_PER_M / 1_000_000 \
                + user_tokens_each * PRICE_INPUT_PER_M / 1_000_000

    # Remaining requests: cache read for system prompt
    rest_n = max(0, n_recordings - 1)
    rest_input = rest_n * (
        system_tokens * PRICE_CACHE_READ_PER_M / 1_000_000
        + user_tokens_each * PRICE_INPUT_PER_M / 1_000_000
    )

    total_input_tokens = system_tokens * n_recordings + user_tokens_each * n_recordings
    total_output_tokens = AVG_OUTPUT_TOKENS * n_recordings
    output_cost = total_output_tokens * PRICE_OUTPUT_PER_M / 1_000_000

    total_cost = first_input + rest_input + output_cost

    return {
        "n_recordings":       n_recordings,
        "system_tokens":      system_tokens,
        "user_tokens_each":   user_tokens_each,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens":total_output_tokens,
        "first_input_cost":   first_input,
        "rest_input_cost":    rest_input,
        "output_cost":        output_cost,
        "total_cost":         total_cost,
    }


def print_cost_breakdown(c: dict) -> None:
    print("\n── Cost Estimate (Batches API, 50% off) ──────────────────────")
    print(f"  Recordings to tag:       {c['n_recordings']:,}")
    print(f"  System prompt tokens:    {c['system_tokens']:,}")
    print(f"  User msg tokens each:    ~{c['user_tokens_each']}")
    print(f"  Total input tokens:      ~{c['total_input_tokens']:,}")
    print(f"    Cache-write (1st req): system prompt @ $3.125/M")
    print(f"    Cache-read (rest):     system prompt @ $0.25/M")
    print(f"  Total output tokens:     ~{c['total_output_tokens']:,}  (~{AVG_OUTPUT_TOKENS}/recording)")
    print(f"  Input cost:              ${c['first_input_cost'] + c['rest_input_cost']:.4f}")
    print(f"  Output cost:             ${c['output_cost']:.4f}")
    print(f"  ─────────────────────────────────────────────────────────")
    print(f"  Estimated total:         ${c['total_cost']:.4f}")
    print()


# ── Main ────────────────────────────────────────────────────────────────────

def parse_tag_text(text: str) -> dict:
    """Strip markdown fences and unwrap single-element array if needed."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        stripped = "\n".join(lines[1:end])
    tags = json.loads(stripped)
    if isinstance(tags, list):
        tags = tags[0]
    return tags


def main() -> None:
    parser = argparse.ArgumentParser(description="Tag recordings with Claude Batches API")
    parser.add_argument(
        "--batch-id",
        help="Skip submission and download results from an existing batch ID",
    )
    args = parser.parse_args()

    client = anthropic.Anthropic()

    # Phase A: load data
    print(f"Loading {INPUT_FILE}...")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        all_recordings: list[dict] = json.load(f)

    recordings_by_id = {r["message_id"]: r for r in all_recordings}

    # Load existing tagged results
    tagged: dict[int, dict] = {}
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
        tagged = {r["message_id"]: r for r in existing}
        print(f"Resuming: {len(tagged)} already tagged, skipping.")

    unprocessed = [r for r in all_recordings if r["message_id"] not in tagged]

    # ── If --batch-id given, skip submission and go straight to results ──────
    if args.batch_id:
        batch_id = args.batch_id
        print(f"Using existing batch: {batch_id}")
        print(f"(Will tag all recordings not yet in {OUTPUT_FILE})")
    else:
        if not unprocessed:
            print("All recordings already tagged. Nothing to do.")
            return

        print(f"Recordings to process: {len(unprocessed)}")

        # Load system prompt and count tokens
        system_prompt = load_system_prompt()

        print("Counting system prompt tokens...")
        count_resp = client.messages.count_tokens(
            model=MODEL,
            system=system_prompt,
            messages=[{"role": "user", "content": "{}"}],
        )
        system_tokens = count_resp.input_tokens

        # Phase B: cost estimate & approval
        cost = estimate_cost(system_tokens, len(unprocessed))
        print_cost_breakdown(cost)

        answer = input("Proceed with batch submission? (yes/no): ").strip().lower()
        if answer not in ("yes", "y"):
            print("Aborted.")
            sys.exit(0)

        # Phase C: build & submit batch
        print("\nBuilding batch requests...")
        requests = []
        for recording in unprocessed:
            requests.append(
                Request(
                    custom_id=str(recording["message_id"]),
                    params=MessageCreateParamsNonStreaming(
                        model=MODEL,
                        max_tokens=MAX_TOKENS,
                        system=[{
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }],
                        messages=[{
                            "role": "user",
                            "content": format_user_message(recording),
                        }],
                    ),
                )
            )

        print(f"Submitting batch of {len(requests)} requests...")
        batch = client.messages.batches.create(requests=requests)
        batch_id = batch.id
        print(f"Batch submitted. ID: {batch_id}")
        print("(Pass --batch-id to retrieve results without resubmitting.)\n")

    # Phase D: poll until done
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        counts = batch.request_counts
        print(
            f"[{time.strftime('%H:%M:%S')}] Status: {batch.processing_status} | "
            f"processing={counts.processing} succeeded={counts.succeeded} "
            f"errored={counts.errored}"
        )
        if batch.processing_status == "ended":
            break
        time.sleep(30)

    print(f"\nBatch complete. Downloading results...")

    # Phase E: download & merge results
    n_processed = 0
    n_errors = 0
    n_skipped = 0

    for result in client.messages.batches.results(batch_id):
        message_id = int(result.custom_id)
        original = recordings_by_id.get(message_id)

        if result.result.type == "succeeded":
            msg = result.result.message
            text = next((b.text for b in msg.content if b.type == "text"), None)
            if text is None:
                print(f"  [WARN] No text in result for message_id={message_id}")
                n_errors += 1
                continue
            try:
                tags = parse_tag_text(text)
            except (json.JSONDecodeError, IndexError) as e:
                print(f"  [ERROR] JSON parse failed for message_id={message_id}: {e}")
                print(f"          Raw text: {text[:200]}")
                n_errors += 1
                continue

            tagged[message_id] = {**(original or {}), **tags}
            n_processed += 1

        elif result.result.type == "errored":
            err = result.result.error
            print(f"  [ERROR] message_id={message_id}: {err.type}")
            n_errors += 1

        else:
            print(f"  [SKIP] message_id={message_id} status={result.result.type}")
            n_skipped += 1

        # Incremental save
        if (n_processed + n_errors) % SAVE_EVERY == 0 and n_processed > 0:
            _save(tagged, OUTPUT_FILE)
            print(f"  Saved checkpoint ({n_processed} tagged so far)...")

    # Final save
    _save(tagged, OUTPUT_FILE)

    # Phase F: summary
    all_tagged = list(tagged.values())
    confidence_counts: dict[str, int] = {}
    needs_review = 0
    for r in all_tagged:
        conf = r.get("confidence", "unknown")
        confidence_counts[conf] = confidence_counts.get(conf, 0) + 1
        if r.get("quality_flags", {}).get("needs_human_review"):
            needs_review += 1

    print("\n── Summary ──────────────────────────────────────────────────")
    print(f"  Total tagged (all time): {len(all_tagged):,}")
    print(f"  This run — processed:    {n_processed:,}")
    print(f"  This run — errors:       {n_errors:,}")
    print(f"  This run — skipped:      {n_skipped:,}")
    print(f"  Confidence breakdown:")
    for level in ("high", "medium", "low", "unknown"):
        if level in confidence_counts:
            print(f"    {level:10s}: {confidence_counts[level]:,}")
    print(f"  Needs human review:      {needs_review:,}")
    print(f"\nOutput saved to: {OUTPUT_FILE}")


def _save(tagged: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(list(tagged.values()), f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
