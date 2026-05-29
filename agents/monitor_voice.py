"""Voice Monitor — STT (Whisper) + TTS (Edge/ElevenLabs) + Voice biometrics."""
from .monitor_base import MonitorAgent


class VoiceMonitorAgent(MonitorAgent):
    name = "voice_monitor"
    subsystem_name = "voice"
    icon = "🎙"
    description = "Monitor sistema vocale: STT Whisper, TTS, voice biometrics."
    model_pref = "haiku"
    actions = [
        {"name": "list_voice_profiles", "description": "Lista profili biometrici"},
        {"name": "clear_tts_cache", "description": "Svuota cache TTS audio"},
        {"name": "test_voice", "description": "Test sintesi voce con frase di prova"},
    ]

    def _snapshot(self):
        out = {}
        try:
            import voice_id
            out["voice_profiles"] = voice_id.list_users()
        except Exception:
            out["voice_profiles"] = []
        try:
            import memory
            prefs = memory.get_preferences()
            out["tts"] = {
                "provider": prefs.get("tts_provider", "auto"),
                "voice": prefs.get("voice", "default"),
                "rate": prefs.get("voice_rate", "0%"),
                "eleven_custom": bool(prefs.get("eleven_custom_voice_id")),
            }
            out["stt"] = {"model": "whisper-base"}
            out["voice_interrupt"] = prefs.get("voice_interrupt", False)
            out["always_on"] = prefs.get("always_on", False)
        except Exception as e:
            out["error"] = str(e)[:80]
        # TTS cache size
        try:
            import os
            from pathlib import Path
            tts_dir = Path(__file__).parent.parent / "assets" / "tts_cache"
            if tts_dir.exists():
                files = list(tts_dir.glob("*.mp3"))
                size_mb = sum(f.stat().st_size for f in files) / 1024 / 1024
                out["tts_cache"] = {"files": len(files), "size_mb": round(size_mb, 1)}
        except Exception:
            pass
        return out

    def _diagnose(self):
        snap = self._snapshot()
        snap["analysis"] = []
        if not snap.get("voice_profiles"):
            snap["analysis"].append("Nessun profilo voce: chi parla non viene identificato")
        if snap.get("tts", {}).get("provider") == "edge":
            snap["analysis"].append("TTS Edge: gratis ma latency ~1s. Considera ElevenLabs per qualità")
        return snap

    def _do_action(self, name, args=None):
        if name == "list_voice_profiles":
            try:
                import voice_id
                return {"ok": True, "users": voice_id.list_users()}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        if name == "clear_tts_cache":
            try:
                from pathlib import Path
                tts_dir = Path(__file__).parent.parent / "assets" / "tts_cache"
                count = 0
                if tts_dir.exists():
                    for f in tts_dir.glob("*.mp3"):
                        f.unlink()
                        count += 1
                return {"ok": True, "deleted": count}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        if name == "test_voice":
            return {"ok": True, "msg": "test rimandato: usa engine.text_input('test')"}
        return super()._do_action(name, args)


AGENT = VoiceMonitorAgent()
