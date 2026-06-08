"""Multi-provider LLM abstraction for VEGA.

Run VEGA on Anthropic Claude (default), OpenAI, or Google Gemini — chosen manually
in Settings. Anthropic is a native passthrough (keeps prompt caching + extended
thinking). OpenAI & Gemini share one OpenAI-compatible client (Gemini via its
OpenAI-compatible endpoint), with on-the-fly translation of the Anthropic-style
message/tool format so brain.py's agentic loop and history stay unchanged.

The Brain keeps its internal history in Anthropic block format (text / tool_use /
tool_result). This layer converts to/from OpenAI format at the call boundary and
returns normalized objects that mimic the Anthropic SDK response/stream interface:
  .content  -> list of blocks with .type ('text'|'tool_use'), .text, .id, .name, .input
  .stop_reason -> 'tool_use' | 'end_turn'
  .usage    -> .input_tokens / .output_tokens / .cache_* (0 for non-Anthropic)

Public API (used by brain.py and fast_brain.py):
    active_provider() -> 'anthropic' | 'openai' | 'gemini'
    main_model() / fast_model() -> resolved model name for the active provider
    provider_status() -> dict for UI/diagnostics
    create(model, system, tools, messages, max_tokens, thinking=None) -> normalized response
    stream(model, system, tools, messages, max_tokens, thinking=None) -> context manager
"""
import json

import config

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Sensible fallbacks if the user hasn't typed a model name in Settings.
_DEFAULTS = {
    "anthropic": {"main": config.MODEL, "fast": config.MODEL_FAST},
    "openai": {"main": "gpt-4o", "fast": "gpt-4o-mini"},
    "gemini": {"main": "gemini-2.0-flash", "fast": "gemini-2.0-flash"},
}
_MODEL_PREF_KEY = {"anthropic": "anthropic_model", "openai": "openai_model", "gemini": "gemini_model"}


# ----- provider / model resolution -------------------------------------------

def _prefs():
    try:
        import memory
        return memory.get_preferences() or {}
    except Exception:
        return {}


def active_provider():
    p = (_prefs().get("llm_provider") or "anthropic").strip().lower()
    return p if p in ("anthropic", "openai", "gemini") else "anthropic"


def _model(tier):
    prov = active_provider()
    prefs = _prefs()
    base_key = _MODEL_PREF_KEY[prov]
    if tier == "fast":
        if prov == "anthropic":
            return config.MODEL_FAST
        return (prefs.get(base_key + "_fast") or prefs.get(base_key) or _DEFAULTS[prov]["fast"]).strip()
    return (prefs.get(base_key) or _DEFAULTS[prov]["main"]).strip()


def main_model():
    return _model("main")


def fast_model():
    return _model("fast")


def provider_status():
    return {
        "active": active_provider(),
        "anthropic": bool(config.ANTHROPIC_API_KEY),
        "openai": bool(getattr(config, "OPENAI_API_KEY", "")),
        "gemini": bool(getattr(config, "GEMINI_API_KEY", "")),
    }


# ----- lazy clients (never instantiate without an active need) ----------------

_anthropic_client = None
_openai_clients = {}


def _anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import Anthropic
        _anthropic_client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _anthropic_client


def _openai_compatible(provider):
    if provider not in _openai_clients:
        from openai import OpenAI
        if provider == "gemini":
            _openai_clients[provider] = OpenAI(
                api_key=getattr(config, "GEMINI_API_KEY", "") or "", base_url=GEMINI_BASE_URL)
        else:
            _openai_clients[provider] = OpenAI(api_key=getattr(config, "OPENAI_API_KEY", "") or "")
    return _openai_clients[provider]


# ----- normalized objects (mimic Anthropic SDK shapes) ------------------------

class _Block:
    __slots__ = ("type", "text", "id", "name", "input")

    def __init__(self, type, text=None, id=None, name=None, input=None):
        self.type = type
        self.text = text
        self.id = id
        self.name = name
        self.input = input


class _Usage:
    __slots__ = ("input_tokens", "output_tokens",
                 "cache_creation_input_tokens", "cache_read_input_tokens")

    def __init__(self, i=0, o=0, cw=0, cr=0):
        self.input_tokens = i
        self.output_tokens = o
        self.cache_creation_input_tokens = cw
        self.cache_read_input_tokens = cr


class _Response:
    __slots__ = ("content", "stop_reason", "usage")

    def __init__(self, content, stop_reason, usage):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = usage


class _Delta:
    __slots__ = ("type", "text")

    def __init__(self, type, text):
        self.type = type
        self.text = text


class _Event:
    __slots__ = ("type", "delta")

    def __init__(self, type, delta):
        self.type = type
        self.delta = delta


# ----- Anthropic <-> OpenAI conversion ----------------------------------------

def _attr(b, name, default=None):
    return b.get(name, default) if isinstance(b, dict) else getattr(b, name, default)


def _system_to_text(system):
    if not system:
        return ""
    if isinstance(system, str):
        return system
    parts = []
    for blk in system:
        parts.append(_attr(blk, "text", "") or "")
    return "\n\n".join(p for p in parts if p)


def _content_to_str(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            t = _attr(b, "type")
            if t == "tool_result":
                c = _attr(b, "content", "")
                out.append(c if isinstance(c, str) else _content_to_str(c))
            else:
                out.append(_attr(b, "text", "") or "")
        return "\n".join(out)
    return str(content)


def _messages_to_openai(system, messages):
    out = []
    sys_txt = _system_to_text(system)
    if sys_txt:
        out.append({"role": "system", "content": sys_txt})
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        if role == "assistant":
            text_parts, tool_calls = [], []
            for b in content:
                t = _attr(b, "type")
                if t == "text":
                    text_parts.append(_attr(b, "text", "") or "")
                elif t == "tool_use":
                    tool_calls.append({
                        "id": _attr(b, "id"),
                        "type": "function",
                        "function": {
                            "name": _attr(b, "name"),
                            "arguments": json.dumps(_attr(b, "input", {}) or {}),
                        },
                    })
            msg = {"role": "assistant", "content": ("\n".join(text_parts) or None)}
            if tool_calls:
                msg["tool_calls"] = tool_calls
            out.append(msg)
        else:  # user role: may carry tool_result blocks
            text_parts, tool_msgs = [], []
            for b in content:
                t = _attr(b, "type")
                if t == "tool_result":
                    tool_msgs.append({
                        "role": "tool",
                        "tool_call_id": _attr(b, "tool_use_id"),
                        "content": _content_to_str(_attr(b, "content", "")) or "(no output)",
                    })
                elif t == "text":
                    text_parts.append(_attr(b, "text", "") or "")
            if text_parts:
                out.append({"role": "user", "content": "\n".join(text_parts)})
            out.extend(tool_msgs)
    return out


def _tools_to_openai(tools):
    out = []
    for s in tools or []:
        name = _attr(s, "name")
        if not name:
            continue
        out.append({"type": "function", "function": {
            "name": name,
            "description": _attr(s, "description", "") or "",
            "parameters": _attr(s, "input_schema", None) or {"type": "object", "properties": {}},
        }})
    return out


def _openai_message_to_blocks(message):
    blocks = []
    txt = getattr(message, "content", None)
    if txt:
        blocks.append(_Block("text", text=txt))
    for tc in (getattr(message, "tool_calls", None) or []):
        try:
            args = json.loads(tc.function.arguments or "{}")
        except Exception:
            args = {}
        blocks.append(_Block("tool_use", id=tc.id, name=tc.function.name, input=args))
    return blocks


def _usage_from_openai(u):
    if not u:
        return _Usage()
    return _Usage(getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0)


# ----- public: non-streaming --------------------------------------------------

def create(model, system, tools, messages, max_tokens, thinking=None):
    prov = active_provider()
    if prov == "anthropic":
        kwargs = dict(model=model, max_tokens=max_tokens,
                      system=system, tools=tools, messages=messages)
        if thinking:
            kwargs["thinking"] = thinking
        return _anthropic().messages.create(**kwargs)
    client = _openai_compatible(prov)
    req = dict(model=model, max_tokens=max_tokens,
               messages=_messages_to_openai(system, messages))
    oai_tools = _tools_to_openai(tools)
    if oai_tools:
        req["tools"] = oai_tools
    resp = client.chat.completions.create(**req)
    choice = resp.choices[0]
    blocks = _openai_message_to_blocks(choice.message)
    has_tools = bool(getattr(choice.message, "tool_calls", None)) or choice.finish_reason == "tool_calls"
    return _Response(blocks, "tool_use" if has_tools else "end_turn",
                     _usage_from_openai(getattr(resp, "usage", None)))


# ----- public: streaming ------------------------------------------------------

class _OpenAIStream:
    """Mimics anthropic's `client.messages.stream(...)` context manager:
    iterating yields content_block_delta/text_delta events; get_final_message()
    returns a normalized _Response after iteration completes."""

    def __init__(self, client, model, system, tools, messages, max_tokens):
        self._client = client
        self._model = model
        self._system = system
        self._tools = tools
        self._messages = messages
        self._max_tokens = max_tokens
        self._stream = None
        self._final = None

    def __enter__(self):
        req = dict(model=self._model, max_tokens=self._max_tokens,
                   messages=_messages_to_openai(self._system, self._messages),
                   stream=True, stream_options={"include_usage": True})
        oai_tools = _tools_to_openai(self._tools)
        if oai_tools:
            req["tools"] = oai_tools
        self._stream = self._client.chat.completions.create(**req)
        return self

    def __exit__(self, *exc):
        try:
            self._stream.close()
        except Exception:
            pass
        return False

    def __iter__(self):
        text_acc = []
        tool_acc = {}   # index -> {"id","name","args"}
        finish = None
        usage = None
        for chunk in self._stream:
            if getattr(chunk, "usage", None):
                usage = chunk.usage
            if not getattr(chunk, "choices", None):
                continue
            ch = chunk.choices[0]
            d = ch.delta
            piece = getattr(d, "content", None)
            if piece:
                text_acc.append(piece)
                yield _Event("content_block_delta", _Delta("text_delta", piece))
            for tc in (getattr(d, "tool_calls", None) or []):
                slot = tool_acc.setdefault(tc.index, {"id": None, "name": None, "args": ""})
                if getattr(tc, "id", None):
                    slot["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn:
                    if getattr(fn, "name", None):
                        slot["name"] = fn.name
                    if getattr(fn, "arguments", None):
                        slot["args"] += fn.arguments
            if getattr(ch, "finish_reason", None):
                finish = ch.finish_reason
        blocks = []
        full = "".join(text_acc)
        if full:
            blocks.append(_Block("text", text=full))
        for idx in sorted(tool_acc):
            s = tool_acc[idx]
            try:
                args = json.loads(s["args"] or "{}")
            except Exception:
                args = {}
            blocks.append(_Block("tool_use", id=s["id"] or ("call_" + str(idx)),
                                 name=s["name"], input=args))
        stop = "tool_use" if (tool_acc or finish == "tool_calls") else "end_turn"
        self._final = _Response(blocks, stop, _usage_from_openai(usage))

    def get_final_message(self):
        return self._final


def stream(model, system, tools, messages, max_tokens, thinking=None):
    prov = active_provider()
    if prov == "anthropic":
        kwargs = dict(model=model, max_tokens=max_tokens,
                      system=system, tools=tools, messages=messages)
        if thinking:
            kwargs["thinking"] = thinking
        return _anthropic().messages.stream(**kwargs)
    return _OpenAIStream(_openai_compatible(prov), model, system, tools, messages, max_tokens)
