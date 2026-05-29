"""Text-to-speech abstraction.

Primary: ElevenLabs (high quality, paid).
Fallback: Edge-TTS (free, decent quality).

Switches automatically when ElevenLabs quota runs out or errors.
"""
import asyncio
import os
import tempfile
from typing import Optional

import edge_tts

import memory

ELEVEN_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

# Default ElevenLabs voice IDs (multilingual v2 voices that handle Italian well)
# Adam: deep natural male, perfect for assistant-like Vega
# These are pre-built ElevenLabs voice IDs available on free tier:
DEFAULT_ELEVEN_VOICES = {
    "adam": "pNInz6obpgDQGcFmaJgB",        # male, deep, natural
    "antoni": "ErXwobaYiN019PkySvjV",      # male, well-rounded
    "josh": "TxGEqnHWrfWFTfGW9XjX",        # male, mature
    "sam": "yoZ06aMxZJJ28mfd3POQ",         # male, raspy
    "rachel": "21m00Tcm4TlvDq8ikWAM",      # female, calm
    "domi": "AZnzlk1XvdvUeBnXmlld",        # female, strong
    "bella": "EXAVITQu4vr4xnSDxMAh",       # female, soft
}

_eleven_client = None


def _get_eleven_client():
    global _eleven_client
    if not ELEVEN_API_KEY:
        return None
    if _eleven_client is None:
        try:
            from elevenlabs.client import ElevenLabs
            _eleven_client = ElevenLabs(api_key=ELEVEN_API_KEY)
        except Exception as e:
            print(f"[ElevenLabs init error: {e}]")
            _eleven_client = False  # mark as broken
    return _eleven_client if _eleven_client else None


def _eleven_generate(text: str, voice_id: str, output_path: str) -> bool:
    """Generate TTS via ElevenLabs. Returns True on success, False on failure."""
    client = _get_eleven_client()
    if not client:
        return False
    try:
        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_64",
        )
        with open(output_path, "wb") as f:
            for chunk in audio:
                if chunk:
                    f.write(chunk)
        # track usage
        memory.record_tts_chars(provider="elevenlabs", chars=len(text))
        return True
    except Exception as e:
        print(f"[ElevenLabs TTS error: {e}]")
        # If it's a quota error, mark as exhausted in memory
        msg = str(e).lower()
        if "quota" in msg or "limit" in msg or "401" in msg:
            memory.set_preference("elevenlabs_exhausted", True)
        return False


async def _edge_generate(text: str, voice: str, output_path: str,
                         rate: str = "-3%", pitch: str = "+0Hz"):
    try:
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    except TypeError:
        comm = edge_tts.Communicate(text, voice)
    await comm.save(output_path)
    memory.record_tts_chars(provider="edge", chars=len(text))


def synthesize(text: str, output_path: str) -> str:
    """Synthesize text to mp3 at output_path. Returns provider used."""
    prefs = memory.get_preferences()
    use_eleven = (
        ELEVEN_API_KEY
        and prefs.get("tts_provider", "auto") in ("auto", "elevenlabs")
        and not prefs.get("elevenlabs_exhausted", False)
    )

    if use_eleven:
        # Voice clone custom: prefs.eleven_custom_voice_id ha priorità
        custom_id = prefs.get("eleven_custom_voice_id", "").strip()
        if custom_id:
            voice_id = custom_id
        else:
            voice_key = prefs.get("eleven_voice", "adam").lower()
            voice_id = DEFAULT_ELEVEN_VOICES.get(voice_key, DEFAULT_ELEVEN_VOICES["adam"])
        if _eleven_generate(text, voice_id, output_path):
            return "elevenlabs"
        # fallback to edge if eleven failed

    edge_voice = prefs.get("voice", "it-IT-GiuseppeNeural")
    rate = prefs.get("voice_rate", "-3%")
    pitch = prefs.get("voice_pitch", "+0Hz")
    asyncio.run(_edge_generate(text, edge_voice, output_path, rate, pitch))
    return "edge"
