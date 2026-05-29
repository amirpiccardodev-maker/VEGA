"""Anthropic Message Batches helper (50% sconto su input/output tokens).

Adatto a workload async non-realtime:
  - Riassunto bulk di N email
  - Classification batch di lead/news
  - Sentiment analysis su corpus
  - Generation di N varianti di brief marketing

Le batch sono asincrone (poll status). Non usare per chat realtime.

API:
    submit(requests: list) -> batch_id
    status(batch_id) -> dict
    results(batch_id) -> list
    pending() -> list of {id, created, status}
"""
import json
import time
from pathlib import Path

import config


ROOT = Path(__file__).parent
STORE_FILE = ROOT / "data" / "batch_jobs.json"
STORE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _get_client():
    import anthropic
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def _load_store() -> dict:
    if not STORE_FILE.exists():
        return {"jobs": []}
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"jobs": []}


def _save_store(d: dict):
    with open(STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def submit(requests: list, label: str = "untitled") -> str:
    """Submit a batch of message requests.

    Each request: {custom_id, model, system, messages, max_tokens}
    Returns batch_id (Anthropic).
    """
    if not requests:
        raise ValueError("empty requests")
    client = _get_client()
    # Build Anthropic batch format
    batch_requests = []
    for i, req in enumerate(requests):
        custom_id = req.get("custom_id") or f"req_{i:04d}"
        params = {
            "model": req.get("model", "claude-haiku-4-5"),
            "max_tokens": req.get("max_tokens", 1024),
            "messages": req.get("messages", []),
        }
        if req.get("system"):
            params["system"] = req["system"]
        batch_requests.append({
            "custom_id": custom_id,
            "params": params,
        })
    batch = client.messages.batches.create(requests=batch_requests)
    bid = batch.id
    # Persist locally for tracking
    store = _load_store()
    store["jobs"].append({
        "id": bid,
        "label": label,
        "created": int(time.time()),
        "request_count": len(requests),
        "status": "in_progress",
    })
    _save_store(store)
    return bid


def status(batch_id: str) -> dict:
    """Get batch status from Anthropic. Updates local store."""
    client = _get_client()
    try:
        b = client.messages.batches.retrieve(batch_id)
    except Exception as e:
        return {"error": str(e)}
    info = {
        "id": batch_id,
        "processing_status": b.processing_status,
        "request_counts": {
            "processing": getattr(b.request_counts, "processing", 0),
            "succeeded": getattr(b.request_counts, "succeeded", 0),
            "errored": getattr(b.request_counts, "errored", 0),
            "canceled": getattr(b.request_counts, "canceled", 0),
            "expired": getattr(b.request_counts, "expired", 0),
        },
        "created_at": str(b.created_at),
        "ended_at": str(b.ended_at) if b.ended_at else None,
    }
    # Update local
    store = _load_store()
    for j in store.get("jobs", []):
        if j["id"] == batch_id:
            j["status"] = b.processing_status
            break
    _save_store(store)
    return info


def results(batch_id: str) -> list:
    """Retrieve batch results (only when ended)."""
    client = _get_client()
    try:
        out = []
        for entry in client.messages.batches.results(batch_id):
            result = entry.result
            item = {
                "custom_id": entry.custom_id,
                "type": result.type,
            }
            if result.type == "succeeded":
                msg = result.message
                item["text"] = "\n".join(
                    b.text for b in msg.content if b.type == "text"
                )
                item["usage"] = {
                    "in": msg.usage.input_tokens,
                    "out": msg.usage.output_tokens,
                }
            elif result.type == "errored":
                item["error"] = str(result.error)
            out.append(item)
        return out
    except Exception as e:
        return [{"error": str(e)}]


def pending() -> list:
    """Local list of batch jobs."""
    store = _load_store()
    return store.get("jobs", [])[-50:]
