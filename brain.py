"""Brain: Claude with tool use, safe history truncation, graceful error recovery."""
import time
import threading
from anthropic import Anthropic, APIError, APIStatusError, RateLimitError
from config import ANTHROPIC_API_KEY, MODEL, MAX_TOKENS
import tools as tool_registry
import memory
from personality import build_static_system_prompt, build_dynamic_system_part

client = Anthropic(api_key=ANTHROPIC_API_KEY)

MAX_HISTORY_MSGS = 16  # short window to limit prompt size
MAX_TOOL_ITERATIONS = 5  # lowered from 8: prevents runaway tool chains
RATE_LIMIT_RETRIES = 3
RATE_LIMIT_BACKOFF_BASE = 8.0  # seconds

# Summarization trigger: when history grows past this, summarize the oldest
# turns via Haiku into a single context message. Saves Sonnet tokens.
SUMMARIZE_THRESHOLD = 12  # messages (fallback when token count unavailable)
SUMMARIZE_KEEP_RECENT = 6  # keep last N messages verbatim
# Token-based summarization: trigger when input is going to exceed this
# (Anthropic charges by token, not by message count, so this is more accurate).
SUMMARIZE_TOKEN_THRESHOLD = 12000


def _estimate_history_tokens(history) -> int:
    """Rough estimate: 1 token ≈ 4 chars (English/Italian average)."""
    total = 0
    for m in history:
        content = m.get("content", "")
        if isinstance(content, str):
            total += len(content) // 4
        elif isinstance(content, list):
            for b in content:
                if isinstance(b, dict):
                    t = b.get("text", "") or str(b.get("input", "")) or ""
                    total += len(t) // 4
    return total


def _is_tool_result_message(msg) -> bool:
    """A user message whose content is a list of tool_result blocks."""
    if msg.get("role") != "user":
        return False
    content = msg.get("content")
    if not isinstance(content, list):
        return False
    return any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


def _safe_trim(history):
    """Truncate history to last MAX_HISTORY_MSGS, but never break tool_use/tool_result pairing."""
    if len(history) <= MAX_HISTORY_MSGS:
        return history

    # find a safe starting index: a user message that is NOT a tool_result message
    safe_start = None
    for i in range(max(0, len(history) - MAX_HISTORY_MSGS), len(history)):
        msg = history[i]
        if msg.get("role") == "user" and not _is_tool_result_message(msg):
            safe_start = i
            break
    if safe_start is None:
        return []
    return history[safe_start:]


def _summarize_if_long(history):
    """If history is too long, summarize the oldest portion with Haiku
    and replace it with a single context message. Saves significant tokens
    on Sonnet calls while preserving context.

    Trigger: token estimate > SUMMARIZE_TOKEN_THRESHOLD OR message count >=
    SUMMARIZE_THRESHOLD (whichever happens first).
    """
    tokens = _estimate_history_tokens(history)
    if len(history) < SUMMARIZE_THRESHOLD and tokens < SUMMARIZE_TOKEN_THRESHOLD:
        return history

    # Find a safe split point: a user msg with non-tool_result content
    # before the last SUMMARIZE_KEEP_RECENT messages
    split = max(0, len(history) - SUMMARIZE_KEEP_RECENT)
    while split > 0:
        m = history[split]
        if m.get("role") == "user" and not _is_tool_result_message(m):
            break
        split -= 1
    if split <= 1:
        return history  # nothing to summarize

    to_summarize = history[:split]
    keep = history[split:]
    # Only summarize if substantial
    if len(to_summarize) < 4:
        return history

    try:
        import fast_brain
        summary = fast_brain.summarize_old_history(to_summarize, target_summary_length=120)
        if not summary or len(summary) < 20:
            return history
        # Create a context message and prepend
        context_msg = {"role": "user", "content":
            f"[Riassunto conversazioni precedenti]\n{summary}"}
        ack = {"role": "assistant", "content": "Contesto ricevuto."}
        return [context_msg, ack] + keep
    except Exception:
        return history


import re as _re

# Max chars per spoken chunk — keeps TTS clips short and text/voice in sync
_MAX_CHUNK   = 260

# Primary: sentence-ending punctuation WITHIN _MAX_CHUNK chars.
# Capped at _MAX_CHUNK so it never swallows a full paragraph.
_SENTENCE_RE = _re.compile(rf'^(.{{6,{_MAX_CHUNK}}}?[.?!])(\s+|$)', _re.DOTALL)
# Secondary: " - " list separator used heavily in Italian news summaries
_DASH_RE     = _re.compile(r'^(.{40,}?) - (?=\S)', _re.DOTALL)
# Tertiary: semicolons in compound sentences
_SEMI_RE     = _re.compile(r'^(.{20,}?;)(\s+)', _re.DOTALL)


def _split_sentence(buffer: str):
    """Split buffer into (chunk, remainder) at the shortest natural boundary.

    Collects all pattern matches, picks the SHORTEST chunk — this gives the
    most granular split so text and TTS stay in sync even for bullet-style
    content (Italian news uses ' - ' as separator, not periods).

    Fallback: hard cap at _MAX_CHUNK chars when no pattern matches.
    """
    candidates = []

    m = _SENTENCE_RE.match(buffer)
    if m:
        candidates.append((len(m.group(1)), m.group(1).strip(), buffer[m.end():]))

    m = _DASH_RE.match(buffer)
    if m:
        chunk = m.group(1).strip()
        candidates.append((len(chunk), chunk, buffer[m.end():].lstrip()))

    m = _SEMI_RE.match(buffer)
    if m:
        candidates.append((len(m.group(1)), m.group(1).strip(), buffer[m.end():]))

    if candidates:
        # Pick the shortest candidate → most granular split → best sync
        candidates.sort(key=lambda x: x[0])
        _, chunk, rest = candidates[0]
        return chunk, rest

    # Hard cap: prevent huge blobs when Claude generates no punctuation
    if len(buffer) >= _MAX_CHUNK:
        cut = buffer.rfind(' ', 0, _MAX_CHUNK)
        if cut > 0:
            return buffer[:cut].strip(), buffer[cut + 1:]
        return buffer[:_MAX_CHUNK].strip(), buffer[_MAX_CHUNK:]

    return None, buffer


def _safe_exec(tool_name, tool_input, emit):
    """Execute a tool with ACL + DPO preflight (GDPR) + sanitize via prompt_shield.

    Pipeline:
      1. tool_acl (CISO-level safety: PIN session for HIGH_RISK)
      2. DPO preflight (GDPR Art. 5/6/25 — for SENSITIVE tools only)
      3. tool execute
      4. prompt_shield sanitize tool_result
    """
    # 1) ACL check
    try:
        import tool_acl
        ok, reason = tool_acl.can_execute(tool_name, tool_input)
        if not ok:
            return (f"[ACL_BLOCKED tool={tool_name} reason={reason}] "
                    f"Questo tool richiede autorizzazione (PIN session o consent). "
                    f"\n\nCOSA DEVI DIRE ALL'UTENTE: spiega che l'azione è sensibile e "
                    f"chiedi conferma esplicita. PROPONI alternative: "
                    f"a) 'fammi inserire il PIN', b) 'procedi solo una volta con conferma', "
                    f"c) 'fai un'azione meno invasiva che ottiene risultato simile'.")
    except Exception:
        pass

    # 2) DPO preflight (GDPR) — skip per tool read-only (no esfiltrazione dati,
    # solo lettura). Resta attivo per tool che potrebbero esfiltrare/agire.
    READ_ONLY_TOOLS = {
        "get_weather", "get_news", "sports_news", "wikipedia",
        "ask_recent_news", "list_emails", "summarize_inbox",
        "web_search", "web_images", "system_info", "pc_stats", "stocks",
        "youtube_transcript", "read_article",
    }
    conditions = []
    try:
        from agents import dpo as _dpo
        if _dpo.AGENT.is_enabled() and tool_name not in READ_ONLY_TOOLS:
            verdict = _dpo.AGENT.preflight(tool_name, tool_input or {})
            v = verdict.get("verdict", "allow")
            if v == "deny":
                # Emit a UI card so the user sees the rejection
                try:
                    import bus
                    bus.publish("card", {
                        "type": "dpo_veto",
                        "data": {
                            "title": "🔐 DPO Veto",
                            "tool": tool_name,
                            "basis": verdict.get("basis_juridique", "?"),
                            "rationale": verdict.get("rationale", "")[:300],
                        },
                    })
                except Exception:
                    pass
                try:
                    import audit_log
                    audit_log.log("dpo.veto", {
                        "tool": tool_name,
                        "basis": verdict.get("basis_juridique"),
                        "rationale": verdict.get("rationale", "")[:200],
                    })
                except Exception:
                    pass
                return (f"[DPO_VETO tool={tool_name}] Il DPO (privacy officer) ha "
                        f"bloccato l'esecuzione di '{tool_name}'. "
                        f"Base giuridica problematica: {verdict.get('basis_juridique', '?')}. "
                        f"Motivo: {verdict.get('rationale', 'non specificato')}. "
                        f"\n\nCOSA DEVI DIRE ALL'UTENTE: "
                        f"spiega in 1-2 frasi il problema GDPR (senza essere tecnico), poi "
                        f"PROPONI UN'ALTERNATIVA: es. 'preparo solo una bozza che rivedi tu', "
                        f"'chiedo prima il consenso al destinatario', 'verifichiamo la base giuridica'. "
                        f"Mai dire solo 'non posso'.")
            elif v == "escalate":
                # Emit card, user must approve via PIN consent
                try:
                    import bus
                    bus.publish("card", {
                        "type": "dpo_escalate",
                        "data": {
                            "title": "🔐 DPO richiede decisione utente",
                            "tool": tool_name,
                            "rationale": verdict.get("rationale", "")[:300],
                        },
                    })
                except Exception:
                    pass
                return (f"[DPO_ESCALATE tool={tool_name}] Decisione utente richiesta. "
                        f"Motivo DPO: {verdict.get('rationale', '?')}. "
                        f"\n\nCOSA DEVI DIRE: chiedi all'utente in modo chiaro se vuole "
                        f"procedere COMUNQUE, illustrando brevemente il trade-off. "
                        f"Non rifiutare l'operazione, lascia la scelta all'utente.")
            elif v == "allow_with_conditions":
                conditions = verdict.get("conditions", [])
    except Exception:
        pass

    # 3) Execute (with cache lookup for read-only tools)
    try:
        import tool_cache
        cached = tool_cache.get(tool_name, tool_input)
        if cached is not None:
            result = cached
            if emit:
                emit("tool_cache_hit", {"tool": tool_name})
        else:
            result = tool_registry.execute(tool_name, tool_input, emit=emit)
            try:
                tool_cache.put(tool_name, tool_input, result)
            except Exception:
                pass
    except Exception as e:
        # Informative error: tells Claude WHAT failed + WHAT to do
        err_str = str(e)
        hint = ""
        low = err_str.lower()
        if "network" in low or "connection" in low or "timeout" in low:
            hint = " Riprova tra qualche secondo, o usa un tool alternativo (es. memory_search se è una info storica)."
        elif "permission" in low or "denied" in low or "acl" in low:
            hint = " L'azione è bloccata da policy. Suggerisci all'utente come autorizzare o proporre un'alternativa."
        elif "not found" in low or "no such" in low or "404" in low:
            hint = " La risorsa non esiste. Verifica il parametro o suggerisci un tool simile."
        elif "rate" in low or "429" in low:
            hint = " Rate limit raggiunto. Aspetta o usa Ollama locale se disponibile."
        elif "api key" in low or "auth" in low:
            hint = " Credenziali mancanti/scadute. Avvisa l'utente di configurare la chiave."
        else:
            hint = " Spiega all'utente il problema in modo semplice e proponi un'azione alternativa concreta."
        return (f"[TOOL_ERROR tool={tool_name}] {err_str[:200]}.{hint} "
                f"NON dire solo 'non riesco'. Trova un altro modo.")

    # Prepend DPO conditions to result so Claude sees them
    if conditions:
        cond_note = "\n[DPO conditions: " + "; ".join(conditions[:3]) + "]"
        if isinstance(result, str):
            result = result + cond_note
        elif isinstance(result, list):
            result = result + [{"type": "text", "text": cond_note}]

    # 4) Tool chain hints (B4.5)
    try:
        import tool_chain
        result = tool_chain.annotate(tool_name, result)
    except Exception:
        pass

    # 5) Sanitize (prompt shield)
    try:
        import prompt_shield
        return prompt_shield.safe_tool_result(result, tool_name=tool_name)
    except Exception:
        return result


def _run_tools_parallel(tool_use_blocks, emit):
    """Execute a list of tool_use blocks in parallel. Preserves order in results."""
    if not tool_use_blocks:
        return []
    if len(tool_use_blocks) == 1:
        b = tool_use_blocks[0]
        res = _safe_exec(b.name, b.input, emit)
        return [{"type": "tool_result", "tool_use_id": b.id, "content": res}]
    # Multiple tools: parallel execution
    import concurrent.futures as _cf
    def _exec(blk):
        return blk.id, _safe_exec(blk.name, blk.input, emit)
    results_by_id = {}
    with _cf.ThreadPoolExecutor(max_workers=min(6, len(tool_use_blocks))) as ex:
        for fut in _cf.as_completed([ex.submit(_exec, b) for b in tool_use_blocks]):
            try:
                bid, res = fut.result()
                results_by_id[bid] = res
            except Exception:
                pass
    out = []
    for b in tool_use_blocks:
        out.append({
            "type": "tool_result",
            "tool_use_id": b.id,
            "content": results_by_id.get(b.id, "errore esecuzione"),
        })
    return out


class Brain:
    def __init__(self, emit=None):
        self.history = []
        self.emit = emit or (lambda *a, **k: None)
        self._lock = threading.Lock()

    def reset(self):
        with self._lock:
            self.history = []

    # --- Reasoning toggle ---
    _THINK_TRIGGERS = (
        "pensaci bene", "ragiona profondamente", "ragiona attentamente",
        "rifletti", "pensa con cura", "modalita ragionamento",
        "modalità ragionamento", "deep thinking", "thinking mode",
    )

    def _wants_extended_thinking(self, user_message: str) -> bool:
        t = (user_message or "").lower()
        if any(p in t for p in self._THINK_TRIGGERS):
            return True
        try:
            return bool(memory.get_preferences().get("extended_thinking", False))
        except Exception:
            return False

    def _thinking_budget_for(self, user_message: str) -> int:
        """Adaptive thinking budget based on query complexity.

        Heuristics:
          - Short query (<50 char): 2K (quick reasoning)
          - Medium (50-200): 5K (default thoughtful)
          - Long/complex (>200, multi-clause): 10K
          - Forced via "pensaci profondamente": 15K (deep)
        """
        t = (user_message or "").strip()
        low = t.lower()
        # Deep override
        if "profondamente" in low or "molto attentamente" in low or "deep" in low:
            return 15000
        n = len(t)
        # Complexity signals: question marks, "e", "oppure", lists, multi-step
        complexity_score = 0
        complexity_score += t.count("?")
        complexity_score += min(3, t.count(" e ") + t.count(", "))
        complexity_score += 2 if any(w in low for w in
            ("confronta", "analizza", "valuta", "scegli", "decidi",
             "pro e contro", "trade-off", "strategia", "pianifica")) else 0
        if n < 50 and complexity_score <= 1:
            return 2000
        if n < 200 and complexity_score <= 3:
            return 5000
        return 10000

    # --- Episodic memory hooks (Mem0) ---
    _BANAL_PATTERNS = (
        "che ore", "che giorno", "che data", "che tempo",
        "ciao", "grazie", "ok", "si", "no",
        "stop", "basta", "ferma",
    )

    def _episodic_recall(self, user_message: str) -> str:
        """Returns a system-prompt fragment with relevant past memories, or ''.
        Skipped for banal queries (saves ~200ms).
        Best-effort: failures are silent."""
        if not user_message:
            return ""
        msg_low = user_message.strip().lower()
        # Skip per query molto brevi o pattern banali
        if len(msg_low) < 12:
            return ""
        if any(msg_low.startswith(p) for p in self._BANAL_PATTERNS):
            return ""
        try:
            import episodic_memory as _em
            return _em.recall_context(user_message, max_chars=600)
        except Exception:
            return ""

    def _rag_docs_recall(self, user_message: str) -> str:
        """Cerca tra i documenti RAG caricati e ritorna fragment system prompt
        se trova match rilevanti (similarity >= 0.55)."""
        if not user_message or len(user_message.strip()) < 12:
            return ""
        msg_low = user_message.strip().lower()
        if any(msg_low.startswith(p) for p in self._BANAL_PATTERNS):
            return ""
        try:
            from tools import rag as _rag
            results, err = _rag._search(user_message, top_k=3)
            if err or not results:
                return ""
            # Filter by min_similarity
            results = [r for r in results if r.get("score", 0) >= 0.55]
            if not results:
                return ""
            chunks = []
            for r in results[:3]:
                src = r.get("file", "?")
                text = (r.get("text", "") or "")[:400]
                chunks.append(f"[doc:{src}] {text}")
            return ("DOCUMENTI RILEVANTI (RAG sui tuoi file):\n"
                    + "\n---\n".join(chunks)
                    + "\nUsa queste info se rispondono alla domanda; altrimenti ignorale.")
        except Exception:
            return ""

    def _episodic_save(self, user_message: str, assistant_reply: str):
        """Save exchange to Mem0 in background. Skipped in privacy_mode."""
        try:
            import security as _sec
            if getattr(_sec, "PRIVACY_MODE", False):
                return
        except Exception:
            pass
        # Skip trivial exchanges to avoid bloating memory
        if not user_message or len(user_message.strip()) < 5:
            return
        if not assistant_reply or len(assistant_reply.strip()) < 5:
            return
        def _bg():
            try:
                import episodic_memory as _em
                _em.add([
                    {"role": "user", "content": user_message[:2000]},
                    {"role": "assistant", "content": assistant_reply[:2000]},
                ])
            except Exception:
                pass
        threading.Thread(target=_bg, daemon=True).start()

    # ------------------------------------------------------------------
    # Helpers condivisi tra ask e ask_stream (eliminano duplicazione)
    # ------------------------------------------------------------------

    def _build_system_blocks(self, user_message: str) -> list:
        """Costruisce i blocchi system con prompt caching a due livelli."""
        static_sys = build_static_system_prompt()
        dynamic_sys = build_dynamic_system_part()
        episodic = self._episodic_recall(user_message)
        rag_docs = self._rag_docs_recall(user_message)
        blocks = [{"type": "text", "text": static_sys,
                   "cache_control": {"type": "ephemeral"}}]
        if dynamic_sys:
            blocks.append({"type": "text", "text": dynamic_sys})
        if episodic:
            blocks.append({"type": "text", "text": episodic})
        if rag_docs:
            blocks.append({"type": "text", "text": rag_docs})
        return blocks

    def _get_routed_schemas(self, user_message: str) -> list:
        """Ritorna gli schemi tool filtrati via smart router (o tutti in fallback)."""
        try:
            import smart_router
            raw_schemas, cats = smart_router.get_tools_for(user_message, tool_registry.all_schemas())
            self.emit("routing", {"categories": cats, "tool_count": len(raw_schemas)})
        except Exception:
            raw_schemas = tool_registry.all_schemas()
        schemas = [dict(s) for s in raw_schemas]
        if schemas:
            schemas[-1] = {**schemas[-1], "cache_control": {"type": "ephemeral"}}
        return schemas

    # ------------------------------------------------------------------

    def ask(self, user_message: str) -> str:
        with self._lock:
            return self._ask_locked(user_message)

    def ask_stream(self, user_message: str):
        """Generator yielding ('sentence', text) as Claude generates,
        and ('final', full_text) at the end. Drives the response in real time."""
        with self._lock:
            yield from self._ask_stream_locked(user_message)

    def _ask_locked(self, user_message: str) -> str:
        # Build safe history before sending
        self.history = _safe_trim(self.history)
        self.history = _summarize_if_long(self.history)
        self.history.append({"role": "user", "content": user_message})

        system_blocks = self._build_system_blocks(user_message)
        schemas = self._get_routed_schemas(user_message)

        # Extended thinking toggle: phrase-triggered or via preferences.
        _think = self._wants_extended_thinking(user_message)
        thinking_param = None
        if _think:
            budget = self._thinking_budget_for(user_message)
            self.emit("warning", {"message": f"Ragionamento profondo (budget {budget} token)"})
            thinking_param = {"type": "enabled", "budget_tokens": budget}

        def _call_api():
            last_err = None
            for attempt in range(RATE_LIMIT_RETRIES):
                try:
                    kwargs = dict(
                        model=MODEL,
                        max_tokens=MAX_TOKENS,
                        system=system_blocks,
                        tools=schemas,
                        messages=self.history,
                    )
                    if thinking_param:
                        kwargs["thinking"] = thinking_param
                        kwargs["max_tokens"] = max(MAX_TOKENS, 8192)
                    return client.messages.create(**kwargs)
                except RateLimitError as e:
                    last_err = e
                    wait = RATE_LIMIT_BACKOFF_BASE * (2 ** attempt)
                    self.emit("warning", {"message": f"Limite richieste raggiunto, attendo {int(wait)}s..."})
                    time.sleep(wait)
            raise last_err

        try:
            for _ in range(MAX_TOOL_ITERATIONS):
                response = _call_api()

                # Record token usage (including cache hits) + per-caller cost
                try:
                    u = response.usage
                    in_t = getattr(u, "input_tokens", 0) or 0
                    out_t = getattr(u, "output_tokens", 0) or 0
                    cw_t = getattr(u, "cache_creation_input_tokens", 0) or 0
                    cr_t = getattr(u, "cache_read_input_tokens", 0) or 0
                    memory.record_usage(
                        input_tokens=in_t, output_tokens=out_t,
                        cache_write=cw_t, cache_read=cr_t,
                    )
                    try:
                        import cost_tracker
                        cost_tracker.record(
                            caller="brain.ask", model=MODEL,
                            input_tokens=in_t, output_tokens=out_t,
                            cache_read=cr_t, cache_write=cw_t,
                        )
                    except Exception:
                        pass
                except Exception:
                    pass

                self.history.append({"role": "assistant", "content": response.content})

                if response.stop_reason == "tool_use":
                    tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
                    for b in tool_use_blocks:
                        self.emit("tool", {"name": b.name, "args": b.input})
                    # PARALLEL execution when multiple tools called
                    tool_results = _run_tools_parallel(tool_use_blocks, self.emit)
                    self.history.append({"role": "user", "content": tool_results})
                    continue

                text_parts = [b.text for b in response.content if b.type == "text"]
                reply = "\n".join(text_parts).strip()
                # Output filter: re-mask secrets, detect canary leaks
                try:
                    import output_filter
                    reply = output_filter.safe_reply(reply)
                except Exception:
                    pass
                memory.log_exchange(user_message, reply)
                self._episodic_save(user_message, reply)
                return reply

            # max iterations reached
            reply = "Mi sono perso. Riprova in modo piu' diretto."
            return reply

        except RateLimitError as e:
            # Don't reset history on rate limit - user just needs to retry
            # Remove the trailing user message we added so we don't double it
            if self.history and self.history[-1].get("role") == "user":
                self.history.pop()
            raise BrainAPIError(f"Rate limit: {e}") from e
        except (APIError, APIStatusError) as e:
            # On real API errors, reset to recover from possibly bad history
            self.history = []
            raise BrainAPIError(str(e)) from e
        except Exception as e:
            self.history = []
            raise BrainAPIError(str(e)) from e


    def _ask_stream_locked(self, user_message: str):
        """Streaming implementation: pipes sentences as they're generated.
        Yields tuples ('sentence', text) and finally ('final', full_text)."""
        import re
        self.history = _safe_trim(self.history)
        self.history.append({"role": "user", "content": user_message})

        system_blocks = self._build_system_blocks(user_message)
        schemas = self._get_routed_schemas(user_message)

        try:
            full_reply = ""
            for _ in range(MAX_TOOL_ITERATIONS):
                text_buffer = ""
                iteration_text = ""
                final_message = None
                tries_left = RATE_LIMIT_RETRIES
                stream_started = False

                while tries_left > 0 and not stream_started:
                    try:
                        with client.messages.stream(
                            model=MODEL,
                            max_tokens=MAX_TOKENS,
                            system=system_blocks,
                            tools=schemas,
                            messages=self.history,
                        ) as stream:
                            stream_started = True
                            for event in stream:
                                if event.type == "content_block_delta":
                                    delta = event.delta
                                    if getattr(delta, "type", None) == "text_delta":
                                        chunk = delta.text
                                        text_buffer += chunk
                                        iteration_text += chunk
                                        # Yield individual token for UI streaming
                                        # (gives ChatGPT-style word-by-word display)
                                        yield ("token", chunk)
                                        # Yield complete sentences as they form (for TTS)
                                        while True:
                                            sent, rest = _split_sentence(text_buffer)
                                            if sent is None:
                                                break
                                            text_buffer = rest
                                            yield ("sentence", sent)
                            final_message = stream.get_final_message()
                    except RateLimitError as e:
                        tries_left -= 1
                        if tries_left <= 0:
                            raise
                        wait = RATE_LIMIT_BACKOFF_BASE * (2 ** (RATE_LIMIT_RETRIES - tries_left - 1))
                        self.emit("warning", {"message": f"Limite richieste raggiunto, attendo {int(wait)}s..."})
                        time.sleep(wait)

                # Track usage + per-caller cost
                try:
                    u = final_message.usage
                    in_t = getattr(u, "input_tokens", 0) or 0
                    out_t = getattr(u, "output_tokens", 0) or 0
                    cw_t = getattr(u, "cache_creation_input_tokens", 0) or 0
                    cr_t = getattr(u, "cache_read_input_tokens", 0) or 0
                    memory.record_usage(
                        input_tokens=in_t, output_tokens=out_t,
                        cache_write=cw_t, cache_read=cr_t,
                    )
                    try:
                        import cost_tracker
                        cost_tracker.record(
                            caller="brain.ask_stream", model=MODEL,
                            input_tokens=in_t, output_tokens=out_t,
                            cache_read=cr_t, cache_write=cw_t,
                        )
                    except Exception:
                        pass
                except Exception:
                    pass

                # Flush remaining text in the buffer as a final sentence chunk
                if text_buffer.strip():
                    yield ("sentence", text_buffer.strip())
                    text_buffer = ""

                self.history.append({"role": "assistant", "content": final_message.content})
                full_reply += ("\n" + iteration_text) if full_reply else iteration_text

                if final_message.stop_reason == "tool_use":
                    tool_use_blocks = [b for b in final_message.content if b.type == "tool_use"]
                    for b in tool_use_blocks:
                        self.emit("tool", {"name": b.name, "args": b.input})
                    tool_results = _run_tools_parallel(tool_use_blocks, self.emit)
                    self.history.append({"role": "user", "content": tool_results})
                    continue  # loop again

                try:
                    import output_filter
                    full_reply = output_filter.safe_reply(full_reply)
                except Exception:
                    pass
                memory.log_exchange(user_message, full_reply)
                self._episodic_save(user_message, full_reply)
                yield ("final", full_reply.strip())
                return

            yield ("final", full_reply.strip() or "Mi sono perso.")

        except RateLimitError as e:
            if self.history and self.history[-1].get("role") == "user":
                self.history.pop()
            raise BrainAPIError(f"Rate limit: {e}") from e
        except (APIError, APIStatusError) as e:
            self.history = []
            raise BrainAPIError(str(e)) from e
        except Exception as e:
            self.history = []
            raise BrainAPIError(str(e)) from e


class BrainAPIError(Exception):
    """Raised on Claude API failures. History has been reset by this point."""
    pass
