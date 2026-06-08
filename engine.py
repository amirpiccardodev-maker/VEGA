"""Vega engine: wake -> listen -> brain -> speak.

Wake triggers:
  - "Hey Vega" wake word (openwakeword)
  - Italian wake phrases via whisper transcription of recent buffer ("sveglia vega", "vega", "ehi vega", "ciao vega")
  - Two claps in quick succession
  - Manual button (via API)
  - Global hotkey (via API)

Boot ceremony is strictly sequential: music intro -> stop music -> greeting -> idle.
"""
import os
import re
import tempfile
import threading
import time
from datetime import datetime
from collections import deque

import numpy as np

# Heavy audio/ML imports are lazy-loaded inside methods to keep server boot fast.
# sounddevice (~1s), edge_tts (~3.6s), openwakeword (~5s), faster_whisper (~15s)
sd = None
edge_tts = None
playsound = None
WakeModel = None
WhisperModel = None


def _lazy_audio_imports():
    """Load heavy audio/ML modules on first use."""
    global sd, edge_tts, playsound, WakeModel, WhisperModel
    if sd is None:
        import sounddevice as _sd
        sd = _sd
    if edge_tts is None:
        import edge_tts as _et
        edge_tts = _et
    if playsound is None:
        from playsound3 import playsound as _ps
        playsound = _ps
    if WakeModel is None:
        from openwakeword.model import Model as _WM
        WakeModel = _WM
    if WhisperModel is None:
        from faster_whisper import WhisperModel as _WhM
        WhisperModel = _WhM


from brain import Brain, BrainAPIError
import memory
import tools.time_tool as time_tool
from personality import contextual_greeting, detect_easter_egg
import shortcuts

SAMPLE_RATE = 16000
FRAME = 1280  # 80ms @ 16kHz

SILENCE_RMS = 0.012
MIN_SPEECH_SEC = 0.5
SILENCE_TIMEOUT_SEC = 1.4
MAX_RECORD_SEC = 20.0
WAKE_THRESHOLD = 0.5
FOLLOWUP_WINDOW_SEC = 8.0
STOP_WORDS = ("stop vega", "basta vega", "ferma vega", "fermati vega", "silenzio vega", "zitto vega")

MUSIC_STOP_PHRASES = (
    "ferma la musica", "stop musica", "stoppa la musica", "spegni la musica",
    "togli la musica", "basta musica", "smetti la musica", "metti pausa musica",
    "ferma la canzone", "stop la musica", "stop alla musica",
)
MUSIC_PLAY_PHRASES = (
    "metti la musica", "fai partire la musica", "fai partire la canzone",
    "metti i clash", "metti la canzone", "riproduci la musica",
    "play music", "riavvia la musica",
)

# Italian wake phrases checked via secondary transcription
WAKE_PHRASES_IT = ("sveglia vega", "ehi vega", "ei vega", "ehy vega", "hey vega",
                   "ciao vega", "ok vega", "okay vega", "yo vega")
# When a continuous speech segment is detected without openwakeword firing,
# we transcribe it and check for these phrases. Buffer is the last ~3s.

ITALIAN_WAKE_BUFFER_SEC = 3.0
ITALIAN_WAKE_MIN_VOICED_SEC = 0.6

# Whisper accuracy tuning
# Initial prompt: tells Whisper what context to expect (Italian + common Vega vocabulary)
# This significantly reduces transcription errors on domain-specific words.
WHISPER_INITIAL_PROMPT = (
    "Conversazione in italiano con assistente personale Vega. "
    "Amir parla a Vega. Comandi tipici: che ore sono, dimmi le notizie, "
    "che tempo fa, leggi le email, apri Chrome, apri Spotify, blocca il PC, "
    "metti la musica, ferma la musica, alza il volume, abbassa il volume, "
    "fai screenshot, mostra desktop, dimmi le quotazioni, cerca su Wikipedia, "
    "aggiungi un promemoria, ricordami di, salva una nota, ciao, grazie, "
    "buongiorno, buonasera, va bene, perfetto."
)
WHISPER_BEAM_SIZE = 5

# Music boot ceremony
MUSIC_INTRO_SEC = 7.0  # play music for ~7s, then stop and greet

STARTUP_MP3 = os.path.join(os.path.dirname(__file__), "assets", "startup.mp3")


def _strip_for_speech(text: str) -> str:
    """Remove markdown and symbols that TTS would read aloud incorrectly."""
    # Code blocks → skip entirely (no point reading raw code)
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    # Bold / italic → keep text only
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    # Headers → keep text, drop # symbols
    text = re.sub(r"#+\s*", "", text)
    # Lines made of only =, -, _ (table separators / hr) → drop entirely
    text = re.sub(r"(?m)^[\s=\-_|]{2,}$", "", text)
    # Table pipes → space
    text = re.sub(r"\|", " ", text)
    # Blockquotes
    text = re.sub(r"(?m)^>\s*", "", text)
    # Numbered/bulleted list markers → keep text, drop marker
    text = re.sub(r"(?m)^\s*[\-\*\+•]\s+", "", text)
    text = re.sub(r"(?m)^\s*\d+[\.\)]\s+", "", text)
    # Brackets [ ] used in links/references → keep inner text
    # Must run BEFORE URL replacement to avoid breaking [text](url)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # [text](url) → text
    text = re.sub(r"\[([^\]]*)\]", r"\1", text)            # [text] → text
    # URLs → short label (run after markdown link cleanup)
    text = re.sub(r"https?://\S+", "il link", text)
    # Equals signs used as separators (===, ==, etc.) → remove
    text = re.sub(r"=+", " ", text)
    # Misc symbols that TTS reads literally
    text = re.sub(r"[<>{}]", " ", text)
    # Emoji and Unicode symbols: remove entirely (TTS reads them as descriptions)
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)  # supplementary planes (most emoji)
    text = re.sub(r"[☀-➿]", "", text)           # misc symbols, dingbats
    text = re.sub(r"[⬀-⯿]", "", text)           # misc symbols extended
    text = re.sub(r"[︀-️]", "", text)           # variation selectors (️ etc.)
    text = re.sub(r"[​-‏­]", "", text)     # zero-width / soft-hyphen
    # Normalize whitespace and newlines
    text = re.sub(r"\n+", ". ", text)
    text = re.sub(r"\s{2,}", " ", text)
    # Clean up stray dots from empty lines
    text = re.sub(r"(\.\s*){3,}", ". ", text)
    return text.strip(". ")


class Engine:
    def __init__(self, emit):
        self.emit = emit
        self.brain = Brain(emit=self._emit_event)
        self.state = "boot"
        self._thread = None
        self._stop = threading.Event()
        self._interrupt = threading.Event()
        self._wake_request = threading.Event()
        self.wake = None
        self.whisper = None
        self._current_sound = None

        self._speak_lock = threading.Lock()
        self._vega_active = True  # if False, Vega stops listening + speaking
        self._boot_progress = 8  # 0-100 percentage for loading screen (>5 offline cap so bar moves immediately on first server response)
        self._state_message = "AVVIO"  # human-readable status for loading UI

        # Italian wake detection state
        self._audio_buffer = deque(maxlen=int(ITALIAN_WAKE_BUFFER_SEC * SAMPLE_RATE / FRAME))
        self._voiced_frames = 0
        self._unvoiced_frames = 0
        self._last_it_wake_check = 0.0
        self._it_wake_in_progress = False
        self._it_wake_signal = threading.Event()

        time_tool.register_timer_callback(self._on_timer)

    def _emit_event(self, evt, payload):
        self.emit(evt, payload)

    def _set_state(self, s, **extra):
        self.state = s
        self.emit("state", {"state": s, **extra})

    def _emit_level(self, rms):
        self.emit("level", {"rms": float(rms)})

    def _emit_text(self, who, text):
        self.emit("text", {"who": who, "text": text})

    def _on_timer(self, label, secs):
        msg = f"Tempo scaduto: {label}"
        self.emit("notification", {"text": msg})
        # Don't speak if Vega is paused (user is listening to music)
        if not self._vega_active:
            return
        try:
            self._set_state("speaking")
            self._speak(msg)
            self._set_state("idle")
        except Exception:
            pass

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def text_input(self, text: str):
        threading.Thread(target=self._handle_text, args=(text,), daemon=True).start()

    def run_automation_command(self, command: str, mode: str = "voice", source: str = "automation"):
        """Execute a command as if it were a user input, with the specified mode.

        mode: 'voice' = full speak; 'card' = only emit text+cards no speak;
              'silent' = run and emit notification only, no UI text.
        """
        def go():
            self.emit("automation_fire", {"name": source, "mode": mode})
            if mode == "silent":
                # Run brain silently, emit notification with reply
                try:
                    reply = self.brain.ask(command)
                    self.emit("notification", {"text": f"[{source}] {reply[:200]}"})
                except Exception as e:
                    self.emit("error", {"message": f"Automazione '{source}': {e}"})
                return
            if mode == "card":
                # Run brain, emit text but skip TTS
                self._emit_text("vega", f"[Automazione: {source}]")
                self._set_state("thinking")
                try:
                    reply = self.brain.ask(command)
                    self._emit_text("vega", reply)
                except Exception as e:
                    self.emit("error", {"message": str(e)})
                self._set_state("idle")
                return
            # voice mode - full pipeline
            self._handle_text(command)
        threading.Thread(target=go, daemon=True).start()

    def request_wake(self):
        self._wake_request.set()

    def _execute_semantic_action(self, action: dict) -> str:
        """Execute an action returned by semantic_shortcuts.match_intent."""
        if not action:
            return ""
        # Pre-canned templates
        if "template" in action:
            return action["template"]
        # Local commands
        if "local" in action:
            from datetime import datetime
            n = datetime.now()
            giorni = ["lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato", "domenica"]
            mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
                    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
            cmd = action["local"]
            if cmd == "now":
                return f"Sono le {n.hour} e {n.minute:02d} di {giorni[n.weekday()]} {n.day} {mesi[n.month-1]}."
            if cmd == "date":
                return f"Oggi e' {giorni[n.weekday()]} {n.day} {mesi[n.month-1]} {n.year}."
            if cmd == "morning_greeting":
                return f"Buongiorno Amir. Sono le {n.hour} e {n.minute:02d}."
            if cmd == "evening_greeting":
                return f"Buonasera Amir. Sono le {n.hour} e {n.minute:02d}."
            return ""
        # Music control
        if action.get("music_stop"):
            self.emit("music", {"event": "stop"})
            return "Musica fermata."
        # Tool call
        if "tool" in action:
            import tools as tool_registry
            result = tool_registry.execute(action["tool"], action.get("args", {}), emit=self.emit)
            if isinstance(result, list):
                # vision-style return; can't speak it, just confirm
                return "Fatto, vedi la card."
            return str(result)[:1500]
        return ""

    def _route_to_brain(self, text: str) -> bool:
        """Shared routing logic for both text input and voice input.

        Chain: Easter egg → macros → regex shortcuts → semantic shortcuts →
               team mode → debate → long-horizon → multi-step agent →
               local LLM (if enabled) → Claude Sonnet (main path).

        Returns True when a response has been generated.
        """
        # 1. Easter eggs (zero API)
        egg = detect_easter_egg(text)
        if egg:
            self._emit_text("vega", egg)
            self._set_state("speaking")
            self._speak(egg)
            self._set_state("idle")
            return True

        # 2. Macro alias expansion ('apri ufficio' → expanded command)
        try:
            import tools.macros as macros_mod
            macros_mod.capture_command_if_recording(text)
            alias_exp = macros_mod.get_alias_expansion(text)
            if alias_exp:
                text = alias_exp
        except Exception:
            pass

        # 3. Regex shortcuts (parametric, e.g. "timer pasta 5 minuti")
        shortcuts.set_emit(self.emit)
        shortcut_reply = shortcuts.try_match(text)
        if shortcut_reply:
            self._emit_text("vega", shortcut_reply)
            self._set_state("speaking")
            self._speak(shortcut_reply)
            self._set_state("idle")
            return True

        # 4. Semantic shortcuts via embeddings (catches intent variations)
        try:
            import semantic_shortcuts as sem
            match = sem.match_intent(text)
            if match:
                action, sim = match
                reply = self._execute_semantic_action(action)
                if reply:
                    self._emit_text("vega", reply)
                    self._set_state("speaking")
                    self._speak(reply)
                    self._set_state("idle")
                    self.emit("semantic_match", {"similarity": round(sim, 3)})
                    return True
        except Exception:
            pass

        # 5. Team mode: Steward classifies and routes to specialized agents
        try:
            if memory.get_preferences().get("team_mode", False):
                from agents import team_registry
                steward = team_registry.get("steward")
                if steward and steward.is_enabled():
                    decision = steward.classify(text)
                    self.emit("steward_decision", decision)
                    cat = (decision or {}).get("category", "SIMPLE")
                    if cat == "INTEL_REQUEST":
                        self._set_state("thinking", message="INTEL")
                        try:
                            import news_graph
                            results = news_graph.search_recent(text, top_k=5)
                            if results:
                                reply = "Ultime news rilevanti:\n" + "\n".join(
                                    f"- {r.get('content', '')[:200]}" for r in results[:5])
                                self._emit_text("vega", reply)
                                self._set_state("speaking")
                                self._speak(reply[:400])
                                self._set_state("idle")
                                return True
                        except Exception:
                            pass
                    elif cat == "MARKETING":
                        self._set_state("thinking", message="MARKETING")
                        try:
                            result = team_registry.run("marketing", {"op": "weekly_brief"})
                            brief = (result or {}).get("brief", {})
                            if brief:
                                txt = (f"Insight: {brief.get('insight', '')}. "
                                       f"Azione: {brief.get('action', '')}")
                                self._emit_text("vega", txt)
                                self._set_state("speaking")
                                self._speak(txt[:400])
                                self._set_state("idle")
                                return True
                        except Exception:
                            pass
                    # For SIMPLE/SENSITIVE/COMPLEX → fall through to brain
        except Exception as e:
            self.emit("error", {"message": f"team_mode: {e}"})

        # 6. Multi-agent debate trigger
        try:
            import debate as _debate
            d_question = _debate.detect_debate(text)
            if d_question:
                self._set_state("thinking", message="DIBATTITO 3 PROSPETTIVE")
                run_id = f"db_{int(time.time())}"
                def _dev(kind, data):
                    self.emit("debate_progress", {"run_id": run_id, "kind": kind, "data": data})
                result = _debate.run(d_question, on_event=_dev)
                synthesis = result.get("synthesis") or "Nessuna sintesi."
                self._emit_text("vega", synthesis)
                self._set_state("speaking")
                self._speak(synthesis)
                self._set_state("idle")
                return True
        except Exception as e:
            self.emit("error", {"message": f"debate: {e}"})

        # 7. Long-horizon agent trigger
        lh_goal = self._extract_long_horizon_goal(text)
        if lh_goal:
            self._set_state("thinking", message="MISSIONE LUNGA")
            self._emit_text("vega", f"Avvio missione lunga: {lh_goal}")
            threading.Thread(target=self._run_long_horizon, args=(lh_goal,),
                              daemon=True).start()
            return True

        # 8. Multi-step agent trigger ("agente: ..." / "fai per me ..." / "obiettivo: ...")
        agent_goal = self._extract_agent_goal(text)
        if agent_goal:
            self._set_state("thinking", message="PIANIFICO")
            self._emit_text("vega", f"Avvio agent multi-step: {agent_goal}")
            self._run_agent_fabric(agent_goal)
            self._set_state("idle")
            return True

        # 9. Local LLM fallback (Ollama) — only if enabled in settings
        if memory.get_preferences().get("local_llm_enabled", False):
            try:
                import local_brain
                if local_brain.is_available() and local_brain.should_use_local(text):
                    self._set_state("thinking", message="LOCAL LLM")
                    reply = local_brain.chat(text,
                        system="Sei Vega, un assistente AI personale italiano. Rispondi in italiano, breve e diretto.")
                    if reply:
                        self._emit_text("vega", reply)
                        self._set_state("speaking")
                        self._speak(reply)
                        self._set_state("idle")
                        self.emit("model_used", {"model": "ollama:" + local_brain.get_model()})
                        return True
            except Exception:
                pass  # Ollama not available — fall through to Anthropic

        # 10. Main path: Claude Sonnet via streaming
        self._set_state("thinking")
        try:
            self._consume_brain_stream(text)
        except BrainAPIError as e:
            self.emit("error", {"message": str(e)})
            self.emit("api_down", {
                "message": "Modello AI non raggiungibile.",
                "suggestion": "Verifica la chiave del provider selezionato (Anthropic/OpenAI/Gemini) nel file .env, oppure abilita il modello locale (Ollama) dalle Impostazioni."
            })
            err_msg = "Non riesco a contattare il modello AI. Verifica di aver inserito la chiave del provider scelto (Anthropic, OpenAI o Gemini) nel file .env — oppure abilita il modello locale dalle Impostazioni."
            self._emit_text("vega", err_msg)
            self._set_state("speaking")
            self._speak(err_msg)
        except Exception as e:
            self.emit("error", {"message": str(e)})
            err_msg = "Si e' verificato un problema. Riprova."
            self._emit_text("vega", err_msg)
            self._set_state("speaking")
            self._speak(err_msg)
        self._set_state("idle")
        return True

    def _handle_text(self, text: str):
        """Entry point for text input (UI chat box)."""
        self._emit_text("user", text)
        # Signal UI immediately that we're processing — user sees feedback right away
        self._set_state("thinking")
        self._route_to_brain(text)

    def _set_progress(self, pct: int, msg: str = ""):
        self._boot_progress = max(0, min(100, pct))
        if msg:
            self._state_message = msg
            self._set_state("loading", message=msg)

    def _load_models(self):
        """Load Whisper and OpenWakeWord in PARALLEL for faster startup."""
        # Step-by-step progress (solo numerico — niente label testuali rumorosi).
        global sd, edge_tts, playsound, WakeModel, WhisperModel
        self._set_progress(9)
        if sd is None:
            self._set_progress(10)
            import sounddevice as _sd; sd = _sd
        if playsound is None:
            self._set_progress(11)
            from playsound3 import playsound as _ps; playsound = _ps
        if edge_tts is None:
            self._set_progress(12)
            import edge_tts as _et; edge_tts = _et
        if WakeModel is None:
            self._set_progress(13)
            from openwakeword.model import Model as _WM; WakeModel = _WM
        if WhisperModel is None:
            # questo è il più lento: 14-70s al primo import
            self._set_progress(14)
            from faster_whisper import WhisperModel as _WhM; WhisperModel = _WhM
        self._set_progress(15)
        self._set_state("loading")
        # Pre-warm semantic shortcuts in background (~120MB model already cached for RAG)
        try:
            import semantic_shortcuts as _sem
            threading.Thread(target=_sem.warm_up, daemon=True).start()
        except Exception:
            pass

        whisper_result = [None]
        wake_result = [None]
        whisper_err = [None]
        wake_err = [None]

        def load_whisper():
            try:
                # 'base' is ~4x more accurate than 'tiny' for italian
                # (~150MB download first time, then cached)
                whisper_result[0] = WhisperModel("base", device="cpu", compute_type="int8")
            except Exception as e:
                whisper_err[0] = e

        def load_wake():
            try:
                # "hey_jarvis" is openWakeWord's bundled pretrained model name (not VEGA branding).
                # openWakeWord ships no "vega" model, so this stays; spoken VEGA wake phrases are
                # handled via the Whisper fallback in WAKE_PHRASES_IT below.
                wake_result[0] = WakeModel(wakeword_models=["hey_jarvis"], inference_framework="onnx")
            except Exception as e:
                wake_err[0] = e

        t1 = threading.Thread(target=load_whisper, daemon=True)
        t2 = threading.Thread(target=load_wake, daemon=True)
        t1.start(); t2.start()

        # Progress updates while loading: from 15% to 85% over expected ~15s
        import time as _t
        start = _t.time()
        while t1.is_alive() or t2.is_alive():
            elapsed = _t.time() - start
            # Simulate progress: 15 -> 85 linearly over 20s, then asymptote
            pct = min(85, 15 + int(elapsed * 3.5))
            self._boot_progress = pct
            _t.sleep(0.4)
        t1.join(); t2.join()

        if whisper_err[0]:
            raise whisper_err[0]
        if wake_err[0]:
            raise wake_err[0]

        self.whisper = whisper_result[0]
        self.wake = wake_result[0]
        self._set_progress(90, "SISTEMI ONLINE")

    def _maybe_start_italian_wake_check(self):
        """Spawn a background thread that transcribes the current audio buffer
        and sets _it_wake_signal if an Italian wake phrase is found.

        Non-blocking: if a check is already running, do nothing.
        """
        now = time.time()
        if self._it_wake_in_progress:
            return
        if now - self._last_it_wake_check < 1.0:
            return
        if self._voiced_frames < int(ITALIAN_WAKE_MIN_VOICED_SEC * SAMPLE_RATE / FRAME):
            return
        if not self._audio_buffer:
            return
        self._last_it_wake_check = now
        self._it_wake_in_progress = True
        # snapshot buffer
        snapshot = np.concatenate(list(self._audio_buffer)).astype(np.float32) / 32768.0
        threading.Thread(target=self._run_italian_wake_check, args=(snapshot,), daemon=True).start()

    def _run_italian_wake_check(self, audio):
        try:
            segments, _ = self.whisper.transcribe(
                audio,
                language="it",
                beam_size=3,
                initial_prompt="Sveglia Vega, ehi Vega, ciao Vega, hey Vega",
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=200),
                condition_on_previous_text=False,
                temperature=0.0,
            )
            text = " ".join(s.text for s in segments).lower().strip()
            for phrase in WAKE_PHRASES_IT:
                if phrase in text:
                    self._it_wake_signal.set()
                    break
        except Exception:
            pass
        finally:
            self._it_wake_in_progress = False

    def _record_until_silence(self, stream) -> np.ndarray:
        """Record from mic until user stops speaking.
        Emits 'partial_transcript' events at ~1.5s intervals for live UI update."""
        chunks = []
        speech_started = False
        silence_frames = 0
        speech_frames = 0
        max_frames = int(MAX_RECORD_SEC * SAMPLE_RATE / FRAME)
        silence_max = int(SILENCE_TIMEOUT_SEC * SAMPLE_RATE / FRAME)
        min_speech = int(MIN_SPEECH_SEC * SAMPLE_RATE / FRAME)
        no_speech_grace = int(2.5 * SAMPLE_RATE / FRAME)

        partial_interval_frames = int(1.5 * SAMPLE_RATE / FRAME)  # ~1.5s
        last_partial_frame = 0
        partial_in_progress = [False]

        def transcribe_partial(audio_snapshot):
            try:
                # Partial transcripts: faster (low beam) but with initial_prompt
                segments, _ = self.whisper.transcribe(
                    audio_snapshot,
                    language="it",
                    beam_size=1,
                    initial_prompt=WHISPER_INITIAL_PROMPT,
                    vad_filter=False,
                    condition_on_previous_text=False,
                    temperature=0.0,
                )
                text = " ".join(s.text.strip() for s in segments).strip()
                if text:
                    self.emit("partial_transcript", {"text": text})
            except Exception:
                pass
            finally:
                partial_in_progress[0] = False

        for i in range(max_frames):
            if self._stop.is_set():
                break
            audio, _ = stream.read(FRAME)
            audio = audio.flatten()
            rms = float(np.sqrt(np.mean(audio.astype(np.float32) ** 2))) / 32768.0
            self._emit_level(rms)
            chunks.append(audio)

            if rms > SILENCE_RMS:
                speech_started = True
                speech_frames += 1
                silence_frames = 0
                # Fire partial transcription periodically while user speaks
                if (speech_started and not partial_in_progress[0]
                        and i - last_partial_frame >= partial_interval_frames):
                    last_partial_frame = i
                    partial_in_progress[0] = True
                    snapshot = np.concatenate(chunks).astype(np.float32) / 32768.0
                    threading.Thread(target=transcribe_partial,
                                     args=(snapshot,), daemon=True).start()
            else:
                if speech_started:
                    silence_frames += 1
                    if silence_frames >= silence_max and speech_frames >= min_speech:
                        break
                elif i >= no_speech_grace:
                    return np.zeros(0, dtype=np.int16)

        if not chunks or not speech_started:
            return np.zeros(0, dtype=np.int16)
        return np.concatenate(chunks)

    def _followup_listen(self, stream) -> np.ndarray:
        chunks = []
        speech_started = False
        silence_frames = 0
        speech_frames = 0
        # Always-on: la finestra in cui ASPETTIAMO che l'utente inizi a parlare
        # diventa molto piu' larga se la preferenza e' attiva.
        try:
            prefs = memory.get_preferences()
        except Exception:
            prefs = {}
        if prefs.get("always_on", False):
            window_sec = float(prefs.get("always_on_window_sec", 60.0))
        else:
            window_sec = FOLLOWUP_WINDOW_SEC
        max_frames = int(window_sec * SAMPLE_RATE / FRAME)
        silence_max = int(SILENCE_TIMEOUT_SEC * SAMPLE_RATE / FRAME)
        min_speech = int(MIN_SPEECH_SEC * SAMPLE_RATE / FRAME)

        for _ in range(max_frames):
            if self._stop.is_set():
                break
            audio, _ = stream.read(FRAME)
            audio = audio.flatten()
            rms = float(np.sqrt(np.mean(audio.astype(np.float32) ** 2))) / 32768.0
            self._emit_level(rms)

            if rms > SILENCE_RMS:
                speech_started = True
                speech_frames += 1
                silence_frames = 0
                chunks.append(audio)
            else:
                if speech_started:
                    chunks.append(audio)
                    silence_frames += 1
                    if silence_frames >= silence_max and speech_frames >= min_speech:
                        break

        if not chunks or not speech_started:
            return np.zeros(0, dtype=np.int16)
        return np.concatenate(chunks)

    def _transcribe(self, audio_int16: np.ndarray) -> str:
        """Transcribe the user's command. Tuned for ACCURACY over speed."""
        if audio_int16.size == 0:
            return ""
        audio_f = audio_int16.astype(np.float32) / 32768.0
        segments, _ = self.whisper.transcribe(
            audio_f,
            language="it",
            beam_size=WHISPER_BEAM_SIZE,
            initial_prompt=WHISPER_INITIAL_PROMPT,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=300, threshold=0.4),
            condition_on_previous_text=False,
            temperature=0.0,  # deterministic, no hallucinations
        )
        return " ".join(s.text.strip() for s in segments).strip()

    def _tts_to_file(self, text, path):
        """Synthesize using TTS abstraction. Uses pre-cache for common phrases."""
        import tts as tts_module
        # Check pre-cache for short common phrases
        if len(text) < 80:
            cached = self._tts_cache_lookup(text)
            if cached:
                import shutil as _sh
                try:
                    _sh.copyfile(cached, path)
                    return "cache"
                except Exception:
                    pass
        provider = tts_module.synthesize(text, path)
        # Save to cache if it's a short common phrase
        if len(text) < 80:
            self._tts_cache_save(text, path)
        return provider

    def _tts_cache_dir(self):
        import hashlib
        d = os.path.join(os.path.dirname(__file__), "assets", "tts_cache")
        os.makedirs(d, exist_ok=True)
        return d

    def _tts_cache_key(self, text):
        import hashlib
        prefs = memory.get_preferences()
        voice = prefs.get("voice", "default")
        rate = prefs.get("voice_rate", "0%")
        # Cache key depends on voice settings + text
        key = f"{voice}|{rate}|{text.strip().lower()}"
        import hashlib as _h
        return _h.md5(key.encode("utf-8")).hexdigest()[:20]

    def _tts_cache_lookup(self, text):
        key = self._tts_cache_key(text)
        path = os.path.join(self._tts_cache_dir(), f"{key}.mp3")
        return path if os.path.exists(path) else None

    def _tts_cache_save(self, text, src_path):
        try:
            import shutil as _sh
            key = self._tts_cache_key(text)
            dest = os.path.join(self._tts_cache_dir(), f"{key}.mp3")
            if not os.path.exists(dest) and os.path.exists(src_path):
                _sh.copyfile(src_path, dest)
        except Exception:
            pass

    def _start_voice_interrupt_monitor(self):
        """Spawn a daemon thread that watches the mic during TTS and sets
        self._interrupt if the user starts talking. Opt-in via preferences
        ('voice_interrupt': True) because without headphones the speaker
        loop-back would trigger false positives.

        Algorithm: skip first 0.5s (TTS ramp-up). Then require N consecutive
        frames above INTERRUPT_RMS to trigger -> minimizes echo false positives.
        """
        try:
            prefs = memory.get_preferences()
        except Exception:
            prefs = {}
        if not prefs.get("voice_interrupt", False):
            return None

        _lazy_audio_imports()  # ensure sd is loaded

        INTERRUPT_RMS = 0.06         # higher than SILENCE_RMS (0.012) to ignore echo
        REQUIRED_FRAMES = 4          # ~4 frames * 80ms = 320ms of sustained speech
        STARTUP_COOLDOWN_SEC = 0.5

        stop_evt = threading.Event()
        started_at = [None]
        consecutive = [0]

        def _on_audio(indata, frames, time_info, status):
            if stop_evt.is_set():
                raise sd.CallbackStop()
            if started_at[0] is None:
                started_at[0] = time.time()
            if time.time() - started_at[0] < STARTUP_COOLDOWN_SEC:
                return
            try:
                rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
            except Exception:
                rms = 0.0
            if rms > INTERRUPT_RMS:
                consecutive[0] += 1
                if consecutive[0] >= REQUIRED_FRAMES:
                    self._interrupt.set()
                    self.emit("voice_interrupt", {"triggered": True})
                    raise sd.CallbackStop()
            else:
                consecutive[0] = 0

        def _monitor():
            try:
                with sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                                    dtype="float32", blocksize=FRAME,
                                    callback=_on_audio):
                    while not stop_evt.is_set() and not self._interrupt.is_set():
                        time.sleep(0.05)
            except Exception:
                pass

        th = threading.Thread(target=_monitor, daemon=True, name="VoiceInterruptMonitor")
        th.start()
        return stop_evt

    def _speak(self, text, display_text=None, on_audio_ready=None):
        """Synthesize TTS and play.

        Args:
            text: testo da pronunciare (strip per phonemes)
            display_text: se fornito, viene emesso come stream_token SOLO DOPO
                          che la sintesi TTS è pronta — così UI e voce partono
                          simultanee invece di testo-prima-voce-dopo.
            on_audio_ready: callback chiamato appena prima del playback.
        """
        if not text.strip():
            return
        text = _strip_for_speech(text)
        if not self._speak_lock.acquire(blocking=False):
            return
        # Voice interrupt monitor (opt-in via preferences). Listens to mic in
        # parallel with TTS playback; sets self._interrupt when user speaks.
        _interrupt_monitor_stop = None
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.close()
            try:
                self._tts_to_file(text, tmp.name)
                self._interrupt.clear()
                # SYNC: il file mp3 è pronto, emettiamo testo UI E playback nello stesso istante
                if display_text is not None:
                    self.emit("stream_token", {"text": display_text})
                    self.emit("speaking_started", {"text_preview": display_text[:80]})
                if on_audio_ready:
                    try: on_audio_ready()
                    except Exception: pass
                self._current_sound = playsound(tmp.name, block=False)
                _interrupt_monitor_stop = self._start_voice_interrupt_monitor()
                # More realistic vocal pattern: faster updates + smoothed envelope
                # Simulates syllable rhythm without analyzing the audio.
                t0 = time.time()
                while self._current_sound.is_alive():
                    if self._stop.is_set() or self._interrupt.is_set():
                        try: self._current_sound.stop()
                        except Exception: pass
                        break
                    el = time.time() - t0
                    # Syllabic pattern: faster oscillation at ~6Hz (typical speech)
                    syllable = 0.5 + 0.5 * np.sin(el * 12.0)  # 0..1
                    base = 0.20 + 0.30 * syllable
                    noise = 0.10 * np.random.random()
                    self._emit_level(base + noise)
                    time.sleep(0.04)  # ~25 updates/sec for smooth viz
                self._emit_level(0)
            except Exception as e:
                self.emit("error", {"message": f"TTS: {e}"})
            finally:
                self._current_sound = None
                if _interrupt_monitor_stop is not None:
                    _interrupt_monitor_stop.set()
                try: os.unlink(tmp.name)
                except OSError: pass
                # If interrupt was triggered by voice, immediately wake to listen.
                if self._interrupt.is_set():
                    try:
                        threading.Thread(target=self._handle_voice_wake_after_interrupt,
                                         daemon=True).start()
                    except Exception:
                        pass
        finally:
            self._speak_lock.release()

    def _handle_voice_wake_after_interrupt(self):
        """Called when TTS was cut short by user voice. Trigger a wake so the
        main listen loop captures the user's utterance without re-saying 'Vega'."""
        try:
            time.sleep(0.1)  # let TTS audio fully die
            self.request_wake()
        except Exception as e:
            self.emit("error", {"message": f"voice_interrupt wake: {e}"})

    # --- Multi-step agent (agent_fabric) ---
    _AGENT_TRIGGERS = (
        "agente:", "agent:", "obiettivo:", "task complesso:", "task:",
        "fai per me ", "esegui per me ", "pianifica ", "organizza per me ",
    )
    _AGENT_LONG_TRIGGERS = (
        "agente lungo:", "missione:", "lavora per un'ora ", "lavora a lungo su ",
        "obiettivo lungo:",
    )

    def _extract_agent_goal(self, text: str) -> str:
        """Return the goal portion if the user invoked the agent, else empty string."""
        t = (text or "").strip().lower()
        for trig in self._AGENT_TRIGGERS:
            if t.startswith(trig):
                return text.strip()[len(trig):].strip(" :,.;")
        return ""

    def _extract_long_horizon_goal(self, text: str) -> str:
        t = (text or "").strip().lower()
        for trig in self._AGENT_LONG_TRIGGERS:
            if t.startswith(trig):
                return text.strip()[len(trig):].strip(" :,.;")
        return ""

    def _run_long_horizon(self, goal: str, max_minutes: int = 30):
        import agent_fabric
        run_id = f"lh_{int(time.time())}"
        def on_event(kind, data):
            self.emit("agent_progress", {"run_id": run_id, "goal": goal,
                                          "kind": kind, "data": data, "mode": "long"})
        result = agent_fabric.run_long_horizon(goal, max_minutes=max_minutes,
                                                  on_event=on_event)
        self.emit("agent_progress", {"run_id": run_id, "goal": goal,
                                      "kind": "finished", "data": result, "mode": "long"})
        summary = result.get("summary", "Fatto.")
        self._emit_text("vega", summary)
        self._set_state("speaking")
        self._speak(summary[:500])

    def _run_agent_fabric(self, goal: str):
        """Run agent_fabric synchronously here (we're already in a background
        thread from text_input). Streams progress via emit('agent_progress',...)."""
        import agent_fabric
        run_id = f"ag_{int(time.time())}"
        def on_event(kind, data):
            self.emit("agent_progress", {"run_id": run_id, "goal": goal,
                                          "kind": kind, "data": data})
        self.emit("agent_progress", {"run_id": run_id, "goal": goal,
                                      "kind": "started", "data": {}})
        try:
            result = agent_fabric.run(goal, on_event=on_event)
        except Exception as e:
            result = {"ok": False, "summary": f"Errore agent: {e}"}
        self.emit("agent_progress", {"run_id": run_id, "goal": goal,
                                      "kind": "finished", "data": result})
        summary = (result or {}).get("summary") or "Fatto."
        self._emit_text("vega", summary)
        self._set_state("speaking")
        self._speak(summary)

    def interrupt(self):
        self._interrupt.set()

    def pause_vega(self):
        self._vega_active = False
        self._interrupt.set()
        self.emit("vega_active", {"active": False})

    def resume_vega(self):
        self._vega_active = True
        self.emit("vega_active", {"active": True})

    def is_active(self) -> bool:
        return self._vega_active

    def _check_reminders(self):
        # Reminders
        if self.state in ("idle", "boot"):
            pending = memory.get_pending_reminders()
            for r in pending:
                if self.state != "idle":
                    break
                memory.fire_reminder(r)
                self.emit("notification", {"text": f"Promemoria: {r['text']}"})
                if self._vega_active:
                    self._set_state("speaking")
                    self._speak(f"Promemoria: {r['text']}")
                    self._set_state("idle")

        # Multi-timers
        try:
            import tools.timers as tm
            def notify(msg):
                self.emit("notification", {"text": msg})
                if self._vega_active and self.state == "idle":
                    self._set_state("speaking")
                    self._speak(msg)
                    self._set_state("idle")
            tm.check_expired_timers(notify)
        except Exception:
            pass

    def _do_briefing(self):
        if memory.briefing_done_today():
            return
        hour = datetime.now().hour
        if not (7 <= hour <= 11):
            return
        memory.mark_briefing_done()
        self._set_state("thinking")
        try:
            self._consume_brain_stream(
                "Briefing mattutino. Dimmi giorno e ora, riassumi le mie ultime 10 mail "
                "(solo cose importanti), poi 2-3 notizie principali, infine meteo per la mia citta'. "
                "Sii sintetico, max 5 frasi totali. Rispondi RIGOROSAMENTE in italiano."
            )
        except Exception as e:
            self.emit("error", {"message": str(e)})
        self._set_state("idle")

    def _process_utterance(self, text: str) -> bool:
        """Entry point for voice input. Handles voice-only fast paths
        (stop words, music control) then delegates to _route_to_brain."""
        if not text:
            return False
        low = text.lower()
        if any(w in low for w in STOP_WORDS):
            self._set_state("idle")
            return False

        # Voice-only: direct music control via browser HTML5 audio
        if any(p in low for p in MUSIC_STOP_PHRASES):
            self._emit_text("user", text)
            self.emit("music", {"event": "stop"})
            self._emit_text("vega", "Musica fermata.")
            self._set_state("speaking")
            self._speak("Fatto.")
            self._set_state("idle")
            return True
        if any(p in low for p in MUSIC_PLAY_PHRASES):
            self._emit_text("user", text)
            self.emit("music", {"event": "play"})
            self._emit_text("vega", "Musica in riproduzione.")
            return True

        self._emit_text("user", text)
        return self._route_to_brain(text)
        return True

    def _consume_brain_stream(self, user_text: str):
        """Pipe brain.ask_stream sentences to TTS as they arrive.

        Producer thread iterates the Claude stream and queues sentences.
        Consumer (this thread) pulls and speaks each sentence in order.

        Text/voice sync strategy:
          - Each sentence is shown in the UI bubble IMMEDIATELY before TTS speaks it.
          - This makes written text and voice appear in lockstep (sentence by sentence).
          - No token-by-token streaming to UI (tokens arrive too fast, all appear at once).
        """
        import queue as _queue
        q = _queue.Queue()
        error_box = [None]

        def producer():
            parts = []
            try:
                for kind, chunk in self.brain.ask_stream(user_text):
                    if kind == "token":
                        pass  # tokens consumed for sentence splitting; not shown directly
                    else:
                        q.put((kind, chunk))
                        if kind == "sentence":
                            parts.append(chunk)
                        elif kind == "final":
                            full = chunk or " ".join(parts)
                            # Signal consumer to finalize bubble with authoritative text
                            q.put(("finalize", full))
            except Exception as e:
                error_box[0] = e
            q.put(None)

        t = threading.Thread(target=producer, daemon=True)
        t.start()

        # Read user preference for text/voice sync mode (default: ON = sincronizzato)
        try:
            _sync_voice_text = memory.get_preferences().get("sync_voice_text", True)
        except Exception:
            _sync_voice_text = True

        spoke_first = False
        full_text_for_finalize = None
        while True:
            item = q.get()
            if item is None:
                break
            kind, text = item
            if kind == "sentence":
                cleaned = _strip_for_speech(text)
                if not cleaned:
                    continue
                if not spoke_first:
                    self._set_state("speaking")
                    spoke_first = True
                if _sync_voice_text:
                    # SYNC: passa display_text a _speak; UI text e playback partono insieme
                    # dopo che la sintesi TTS è completata.
                    self._speak(cleaned, display_text=text + " ")
                else:
                    # Modalità reattiva: testo subito, voce dopo la sintesi
                    self.emit("stream_token", {"text": text + " "})
                    self._speak(cleaned)
            elif kind == "final":
                pass  # handled by "finalize" event below
            elif kind == "finalize":
                full_text_for_finalize = text

        # Finalize: replace streaming bubble with authoritative full text
        if full_text_for_finalize:
            self._emit_text("vega", full_text_for_finalize)
        elif not spoke_first:
            # Nothing was spoken (empty reply) — emit empty so UI clears bubble
            self._emit_text("vega", "")

        if error_box[0]:
            raise error_box[0]

    def _do_conversation(self, stream, initial_audio):
        self._set_state("thinking")
        # Voice biometrics: identify speaker BEFORE transcription
        if initial_audio is not None and initial_audio.size > 0:
            try:
                import voice_id
                uid, sim = voice_id.identify(initial_audio)
                if uid:
                    self.emit("speaker_identified", {"user_id": uid, "similarity": sim})
                    # Switch episodic memory user
                    try:
                        import episodic_memory as _em
                        _em._user_id = uid
                    except Exception:
                        pass
                else:
                    self.emit("speaker_identified", {"user_id": "unknown", "similarity": sim})
            except Exception:
                pass
        text = self._transcribe(initial_audio) if initial_audio is not None else ""
        if not self._process_utterance(text):
            self._set_state("idle")
            return

        while not self._stop.is_set():
            try:
                _always = memory.get_preferences().get("always_on", False)
            except Exception:
                _always = False
            self._set_state(
                "listening",
                message="ASCOLTO CONTINUO" if _always else "ASCOLTO",
            )
            followup_audio = self._followup_listen(stream)
            if followup_audio.size == 0:
                self._set_state("idle")
                break
            self._set_state("thinking")
            ftext = self._transcribe(followup_audio)
            if not self._process_utterance(ftext):
                break

    def _boot_ceremony(self):
        """Music is now played by the BROWSER (HTML5 audio) to avoid Python
        playback overlaps. We only do the spoken greeting here, AFTER waiting
        for the browser music intro to finish."""
        self._set_progress(100, "PRONTO")
        self._set_state("idle")
        # Wait while browser plays the intro music (it controls itself).
        # We just sleep enough that the music intro finishes before greeting.
        if memory.get_preferences().get("startup_music", True) and os.path.exists(STARTUP_MP3):
            self.emit("music", {"event": "start", "url": "/assets/startup.mp3", "duration_sec": MUSIC_INTRO_SEC})
            time.sleep(MUSIC_INTRO_SEC + 0.3)
            self.emit("music", {"event": "stop"})
        greeting = contextual_greeting()
        self._emit_text("vega", greeting)
        self._set_state("speaking")
        self._speak(greeting)
        self._set_state("idle")
        self._do_briefing()

    def _loop(self):
        try:
            self._load_models()
        except Exception as e:
            self.emit("error", {"message": f"Avvio: {e}"})
            return

        # Strictly sequential boot ceremony, in its own thread so it doesn't
        # block the main listening loop from starting, but the audio stream
        # below only starts after the ceremony finishes (we want greeting
        # before listening — otherwise we'd hear ourselves transcribing the music).
        self._boot_ceremony()

        last_reminder_check = 0

        # Outer loop: reopen mic stream on errors (e.g. device unplugged)
        while not self._stop.is_set():
            try:
                stream_ctx = sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                                            dtype="int16", blocksize=FRAME)
            except Exception as e:
                self.emit("error", {"message": f"Microfono non disponibile: {e}. Riprovo tra 5 secondi."})
                time.sleep(5)
                continue
            try:
                stream = stream_ctx.__enter__()
                self._inner_listen_loop(stream, last_reminder_check)
            except Exception as e:
                self.emit("error", {"message": f"Audio interrotto: {e}. Riprovo..."})
                time.sleep(2)
            finally:
                try:
                    stream_ctx.__exit__(None, None, None)
                except Exception:
                    pass

    def _inner_listen_loop(self, stream, last_reminder_check):
        while not self._stop.is_set():
            now = time.time()
            if now - last_reminder_check > 30:
                last_reminder_check = now
                threading.Thread(target=self._check_reminders, daemon=True).start()

            audio, _ = stream.read(FRAME)
            audio = audio.flatten()

            rms = float(np.sqrt(np.mean(audio.astype(np.float32) ** 2))) / 32768.0
            if self.state == "idle":
                self._emit_level(rms)

            # Rolling buffer for italian wake detection
            self._audio_buffer.append(audio.copy())
            if rms > SILENCE_RMS:
                self._voiced_frames += 1
                self._unvoiced_frames = 0
            else:
                self._unvoiced_frames += 1
                if self._unvoiced_frames > int(0.6 * SAMPLE_RATE / FRAME):
                    self._voiced_frames = 0

            # Manual wake ALWAYS works
            if self._wake_request.is_set():
                self._wake_request.clear()
                if not self._vega_active:
                    self.resume_vega()
                self.emit("wake", {"source": "manual"})
                self._set_state("listening")
                cmd_audio = self._record_until_silence(stream)
                self._do_conversation(stream, cmd_audio)
                self._audio_buffer.clear()
                self._voiced_frames = 0
                continue

            if not self._vega_active:
                continue

            preds = self.wake.predict(audio)
            score = preds.get("hey_jarvis", 0)
            if score > WAKE_THRESHOLD:
                self.wake.reset()
                self.emit("wake", {"source": "voice"})
                self._set_state("listening")
                cmd_audio = self._record_until_silence(stream)
                self._do_conversation(stream, cmd_audio)
                self._audio_buffer.clear()
                self._voiced_frames = 0
                continue

            if self._unvoiced_frames == int(0.6 * SAMPLE_RATE / FRAME):
                self._maybe_start_italian_wake_check()

            if self._it_wake_signal.is_set():
                self._it_wake_signal.clear()
                self.emit("wake", {"source": "voice-it"})
                self._set_state("listening")
                cmd_audio = self._record_until_silence(stream)
                self._do_conversation(stream, cmd_audio)
                self._audio_buffer.clear()
                self._voiced_frames = 0
                continue
