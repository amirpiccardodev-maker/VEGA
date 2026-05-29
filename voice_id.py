"""Voice biometrics (speaker identification) leggero.

Implementazione: MFCC (13 coeff) -> mean+std per utente -> cosine similarity.
Non è state-of-the-art come pyannote/resemblyzer ma:
  - zero dipendenze C++ (solo python_speech_features + numpy)
  - latency <50ms per identify
  - per single-user-vs-stranger funziona bene
  - per multi-user (famiglia 3-5 persone) discreto

API:
    enroll(user_id, audio_int16) -> aggiunge una voce sample al profilo
    identify(audio_int16) -> (user_id, similarity) o (None, 0)
    list_users() -> [user_id]
    delete(user_id)
"""
import json
import os
import threading
import time
from pathlib import Path

import numpy as np


ROOT = Path(__file__).parent
PROFILES_DIR = ROOT / "data" / "voice_profiles"
PROFILES_DIR.mkdir(parents=True, exist_ok=True)
PROFILES_FILE = PROFILES_DIR / "profiles.json"

SAMPLE_RATE = 16000
MIN_SECONDS = 2.0
THRESHOLD = 0.85   # cosine sim per accettare match

_lock = threading.Lock()
_profiles = None  # dict: user_id -> {"embedding": [..], "samples": int, "updated": ts}


def _load():
    global _profiles
    if _profiles is not None:
        return _profiles
    if not PROFILES_FILE.exists():
        _profiles = {}
        return _profiles
    try:
        with open(PROFILES_FILE, "r", encoding="utf-8") as f:
            _profiles = json.load(f)
    except Exception:
        _profiles = {}
    return _profiles


def _save():
    with open(PROFILES_FILE, "w", encoding="utf-8") as f:
        json.dump(_profiles, f, ensure_ascii=False, indent=2)


def _extract_embedding(audio_int16: np.ndarray) -> np.ndarray:
    """Compute a 26-dim voice embedding: mean+std of 13 MFCC coefficients."""
    from python_speech_features import mfcc
    if audio_int16.dtype != np.int16:
        audio_int16 = audio_int16.astype(np.int16)
    if audio_int16.size < int(MIN_SECONDS * SAMPLE_RATE):
        # Pad with zeros for short clips (but they'll be unreliable)
        pad = int(MIN_SECONDS * SAMPLE_RATE) - audio_int16.size
        audio_int16 = np.concatenate([audio_int16, np.zeros(pad, dtype=np.int16)])
    # mfcc returns (n_frames, 13)
    feats = mfcc(audio_int16, SAMPLE_RATE, numcep=13)
    # Mean + std across frames -> 26-dim
    mean = feats.mean(axis=0)
    std = feats.std(axis=0)
    emb = np.concatenate([mean, std])
    # L2 normalize
    n = np.linalg.norm(emb)
    if n > 0:
        emb = emb / n
    return emb.astype(np.float32)


def enroll(user_id: str, audio_int16: np.ndarray) -> dict:
    """Add (or merge) a sample for user_id. Returns updated profile info."""
    user_id = user_id.strip().lower()
    if not user_id:
        return {"ok": False, "error": "user_id mancante"}
    try:
        emb = _extract_embedding(audio_int16)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    with _lock:
        profs = _load()
        if user_id in profs:
            # Running average to refine over time
            old = np.array(profs[user_id]["embedding"], dtype=np.float32)
            n_old = profs[user_id].get("samples", 1)
            new_emb = (old * n_old + emb) / (n_old + 1)
            new_emb = new_emb / max(np.linalg.norm(new_emb), 1e-8)
            profs[user_id]["embedding"] = new_emb.tolist()
            profs[user_id]["samples"] = n_old + 1
        else:
            profs[user_id] = {"embedding": emb.tolist(), "samples": 1}
        profs[user_id]["updated"] = int(time.time())
        _save()
    return {"ok": True, "user_id": user_id, "samples": profs[user_id]["samples"]}


def identify(audio_int16: np.ndarray) -> tuple:
    """Return (user_id, similarity) for the best match, or (None, 0)."""
    profs = _load()
    if not profs:
        return None, 0.0
    try:
        emb = _extract_embedding(audio_int16)
    except Exception:
        return None, 0.0
    best_id, best_sim = None, -1.0
    for uid, p in profs.items():
        pe = np.array(p["embedding"], dtype=np.float32)
        sim = float(np.dot(emb, pe))
        if sim > best_sim:
            best_sim = sim
            best_id = uid
    if best_sim >= THRESHOLD:
        return best_id, best_sim
    return None, best_sim  # below threshold = unknown speaker


def list_users() -> list:
    return [{
        "user_id": uid,
        "samples": p.get("samples", 0),
        "updated": p.get("updated", 0),
    } for uid, p in _load().items()]


def delete(user_id: str) -> bool:
    with _lock:
        profs = _load()
        if user_id in profs:
            del profs[user_id]
            _save()
            return True
    return False
