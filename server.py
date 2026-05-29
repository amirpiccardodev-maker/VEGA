"""Flask + WebSocket server for the Vega UI."""
import sys
import json
import threading
import webbrowser
import subprocess
import os
import time
import io


# When launched by pythonw.exe (no console), sys.stdout / sys.stderr are None,
# and any print() that tries to flush would crash with a NoneType error.
# Replace them with safe sinks that also log fatal errors to a file.
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(ROOT_DIR, "vega_error.log")


class _SafeStream(io.TextIOBase):
    def __init__(self, log_path):
        self._log_path = log_path
    def write(self, s):
        try:
            if not s or s.isspace():
                return len(s) if s else 0
            # Mask secrets BEFORE writing to log
            try:
                import security as _sec
                s = _sec.mask_secrets(s)
            except Exception:
                pass
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(s)
            return len(s)
        except Exception:
            return 0
    def flush(self):
        pass


if sys.stdout is None or sys.stderr is None:
    sys.stdout = _SafeStream(LOG_FILE)
    sys.stderr = _SafeStream(LOG_FILE)
else:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# Crash logger: catch any unhandled exception during startup
def _crash_handler(exc_type, exc_value, exc_tb):
    import traceback
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("\n=== CRASH ===\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
    except Exception:
        pass


sys.excepthook = _crash_handler

from flask import Flask, send_from_directory, jsonify, request
from flask_sock import Sock
from werkzeug.utils import secure_filename

from engine import Engine
import memory

ROOT = os.path.dirname(__file__)
UI_DIR = os.path.join(ROOT, "ui")
ASSETS_DIR = os.path.join(ROOT, "assets")
MUSIC_DIR = os.path.join(ASSETS_DIR, "music")
os.makedirs(MUSIC_DIR, exist_ok=True)
PORT = 5252

ALLOWED_AUDIO = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB per file

app = Flask(__name__, static_folder=UI_DIR)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
sock = Sock(app)


import auth as _auth

# Allowed CORS origins. Localhost variants + LAN IPs are accepted dynamically.
_ALLOWED_CORS_ORIGINS_STATIC = {
    "http://localhost:5252", "http://127.0.0.1:5252",
    "https://localhost:5252", "https://127.0.0.1:5252",
    "null",  # file:// page (boot loading.html)
}


def _is_lan_origin(origin: str) -> bool:
    """Accept origins on private RFC1918 ranges (LAN)."""
    if not origin:
        return False
    try:
        from urllib.parse import urlparse
        host = urlparse(origin).hostname or ""
        # Private ranges
        if host.startswith("192.168.") or host.startswith("10."):
            return True
        if host.startswith("172."):
            try:
                second = int(host.split(".")[1])
                if 16 <= second <= 31:
                    return True
            except Exception:
                pass
        return False
    except Exception:
        return False


@app.before_request
def _trace_init():
    """Assign a trace_id for the duration of the request."""
    try:
        import tracing
        tid = request.headers.get("X-Trace-Id") or tracing.new_trace_id()
        tracing.set(tid)
        tracing.record_span("http.request", {
            "method": request.method,
            "path": request.path,
            "remote": request.remote_addr,
        })
    except Exception:
        pass


@app.after_request
def _trace_finish(response):
    try:
        import tracing
        tid = tracing.current()
        if tid:
            response.headers["X-Trace-Id"] = tid
            tracing.record_span("http.response", {"status": response.status_code})
            tracing.clear()
    except Exception:
        pass
    return response


@app.before_request
def _authn_gate():
    """Bearer token auth + rate limiting for non-localhost requests."""
    if request.method == "OPTIONS":
        return None
    # Rate limit FIRST (cheap, before auth check)
    try:
        import rate_limit
        if not rate_limit.check_request(request.remote_addr or "?"):
            return jsonify({"error": "rate_limit_exceeded"}), 429
    except Exception:
        pass
    if not _auth.verify(request):
        return jsonify({"error": "unauthorized",
                        "hint": "Bearer token required for non-localhost. POST /api/auth/login with PIN to obtain it."}), 401
    return None


@app.after_request
def _add_cors(response):
    """Restrict CORS to known origins (localhost + LAN). Drops the previous '*'."""
    origin = request.headers.get("Origin", "")
    if (origin in _ALLOWED_CORS_ORIGINS_STATIC
            or _is_lan_origin(origin)
            or origin.startswith("http://localhost")
            or origin.startswith("http://127.0.0.1")):
        response.headers["Access-Control-Allow-Origin"] = origin or "null"
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Auth-Token"
    response.headers["Cache-Control"] = "no-cache"
    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "geolocation=(self), microphone=(self), camera=(self), "
        "interest-cohort=(), browsing-topics=()"
    )
    # CSP: allow self + Google Fonts + Pollinations images + Anthropic API (none direct from browser)
    # Inline allowed because vega.js has small inline event handlers; tighten later by moving to addEventListener.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: blob: https://image.pollinations.ai https://*.wikipedia.org "
        "https://upload.wikimedia.org https://*.bbci.co.uk https://*.repubblica.it "
        "https://*.ansa.it https://*.ilpost.it https:; "
        "connect-src 'self' wss: ws:; "
        "media-src 'self' blob: data:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self';"
    )
    # HSTS only when serving HTTPS
    if request.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

_clients = []
_clients_lock = threading.Lock()
_last_client_time = time.time()
NO_CLIENT_SHUTDOWN_SEC = 90  # if no browser connected for this long, exit


def broadcast(event, payload):
    msg = json.dumps({"event": event, "payload": payload})
    with _clients_lock:
        dead = []
        for ws in _clients:
            try:
                ws.send(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            _clients.remove(ws)


engine = Engine(emit=broadcast)

# Apply persisted privacy mode at startup
try:
    import security as _sec
    _sec.set_privacy_mode(bool(memory.get_preferences().get("privacy_mode", False)))
except Exception:
    pass


# ---- UI ----
@app.route("/")
def index():
    return send_from_directory(UI_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(UI_DIR, path)


# ---- Assets (music, startup, etc.) ----
@app.route("/assets/<path:path>")
def assets(path):
    return send_from_directory(ASSETS_DIR, path)


# Serve TTS audio files generated by the engine, so the browser can play
# them with Web Audio API (giving us live waveform visualization).
@app.route("/tts/<token>")
def tts_audio(token):
    """Serve a TTS audio file by token. Tokens are short-lived URLs created
    by the engine after generating audio."""
    import tempfile
    safe = "".join(c for c in token if c.isalnum() or c in "._-")
    path = os.path.join(tempfile.gettempdir(), f"vega_tts_{safe}.mp3")
    if not os.path.exists(path):
        return "Not found", 404
    response = send_from_directory(os.path.dirname(path), os.path.basename(path))
    return response


# ---- Engine controls ----
@app.route("/api/text", methods=["POST"])
def api_text():
    data = request.get_json(force=True)
    text = (data or {}).get("text", "").strip()
    if text:
        engine.text_input(text)
    return jsonify({"ok": True})


@app.route("/api/interrupt", methods=["POST"])
def api_interrupt():
    engine.interrupt()
    return jsonify({"ok": True})


@app.route("/api/wake", methods=["POST"])
def api_wake():
    engine.request_wake()
    return jsonify({"ok": True})


@app.route("/api/listen/pause", methods=["POST"])
def api_listen_pause():
    engine.pause_vega()
    return jsonify({"ok": True})


@app.route("/api/listen/resume", methods=["POST"])
def api_listen_resume():
    engine.resume_vega()
    return jsonify({"ok": True})


@app.route("/api/listen/toggle", methods=["POST"])
def api_listen_toggle():
    if engine.is_active():
        engine.pause_vega()
    else:
        engine.resume_vega()
    return jsonify({"ok": True, "active": engine.is_active()})


@app.route("/api/weather", methods=["GET"])
def api_weather():
    """Proxy wttr.in server-side to avoid CORS/network issues in Chrome app mode."""
    loc = memory.get_preferences().get("home_location", "")
    if not loc:
        return jsonify({"error": "home_location non configurata"}), 400
    try:
        from urllib.parse import quote as _quote
        from urllib.request import urlopen, Request as _Req
        import json as _json
        url = f"https://wttr.in/{_quote(loc)}?format=j1&lang=it"
        req = _Req(url, headers={"User-Agent": "Vega/1.0"})
        with urlopen(req, timeout=8) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        return jsonify(data)
    except Exception as e:
        # Fallback: try with requests if available
        try:
            import requests as _req
            r = _req.get(
                f"https://wttr.in/{_req.utils.quote(loc)}?format=j1&lang=it",
                timeout=8, headers={"User-Agent": "Vega/1.0"}
            )
            r.raise_for_status()
            return jsonify(r.json())
        except Exception as e2:
            return jsonify({"error": f"wttr.in: {e} / {e2}"}), 502


@app.route("/api/state", methods=["GET"])
def api_state():
    prefs = memory.get_preferences()
    return jsonify({
        "state": engine.state,
        "active": engine.is_active(),
        "boot_progress": getattr(engine, "_boot_progress", 0),
        "boot_message": getattr(engine, "_state_message", "") or "",
        "ready": engine.state not in ("boot", "loading"),
        "todos": memory.get_todos(),
        "notes": memory.get_notes()[-5:],
        "home_location": prefs.get("home_location", ""),
    })


@app.route("/api/usage", methods=["GET"])
def api_usage():
    summary = memory.get_usage_summary()
    summary["tts"] = memory.get_tts_usage()
    return jsonify(summary)


@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    return jsonify(memory.get_preferences())


@app.route("/api/settings", methods=["POST"])
def api_settings_set():
    data = request.get_json(force=True) or {}
    allowed = {"voice", "voice_rate", "personality", "mode", "home_location",
               "startup_music", "tts_provider", "eleven_voice",
               "sounds_enabled", "privacy_mode", "voice_interrupt",
               "always_on", "always_on_window_sec",
               "local_brain_enabled", "local_llm_enabled", "team_mode",
               "sync_voice_text"}
    for k, v in data.items():
        if k in allowed:
            memory.set_preference(k, v)
    # If privacy_mode toggled, apply immediately to running engine
    if "privacy_mode" in data:
        try:
            import security as _sec
            _sec.set_privacy_mode(bool(data["privacy_mode"]))
        except Exception:
            pass
    return jsonify({"ok": True, "prefs": memory.get_preferences()})


@app.route("/api/workflows", methods=["GET"])
def api_workflows_list():
    import workflow_engine
    return jsonify({"items": workflow_engine.list_workflows()})


@app.route("/api/workflows/<wf_id>", methods=["GET"])
def api_workflow_get(wf_id):
    import workflow_engine
    wf = workflow_engine.load_workflow(wf_id)
    if not wf:
        return jsonify({"error": "not found"}), 404
    return jsonify(wf)


@app.route("/api/workflows/<wf_id>/run", methods=["POST"])
def api_workflow_run(wf_id):
    import workflow_engine
    result = workflow_engine.execute(wf_id, emit=broadcast)
    return jsonify(result)


@app.route("/api/workflows/<wf_id>", methods=["DELETE"])
def api_workflow_delete(wf_id):
    import workflow_engine
    ok = workflow_engine.delete_workflow(wf_id)
    return jsonify({"ok": ok})


# ============ Multi-step agent fabric ============
_agent_lock = threading.Lock()
_agent_running = {"active": False, "goal": None, "started": None}


@app.route("/api/agent/run", methods=["POST"])
def api_agent_run():
    """Kick off an agent_fabric multi-step run. Returns immediately; events
    stream via WS as 'agent_progress' frames."""
    data = request.get_json(force=True) or {}
    goal = (data.get("goal") or "").strip()
    if not goal:
        return jsonify({"ok": False, "error": "missing goal"}), 400
    with _agent_lock:
        if _agent_running["active"]:
            return jsonify({"ok": False, "error": "another agent run in progress",
                            "current": _agent_running["goal"]}), 409
        _agent_running.update({"active": True, "goal": goal, "started": time.time()})

    def _run():
        import agent_fabric
        run_id = f"ag_{int(time.time())}"
        def _on_event(kind, data):
            broadcast("agent_progress", {"run_id": run_id, "goal": goal,
                                          "kind": kind, "data": data})
        broadcast("agent_progress", {"run_id": run_id, "goal": goal,
                                      "kind": "started", "data": {}})
        try:
            result = agent_fabric.run(goal, on_event=_on_event)
        except Exception as e:
            result = {"ok": False, "summary": f"Errore agent: {e}"}
        broadcast("agent_progress", {"run_id": run_id, "goal": goal,
                                      "kind": "finished", "data": result})
        # Speak the summary if engine is around
        try:
            summary = result.get("summary") or ""
            if summary and getattr(engine, "_speak", None):
                threading.Thread(target=engine._speak, args=(summary,), daemon=True).start()
        except Exception:
            pass
        with _agent_lock:
            _agent_running.update({"active": False, "goal": None, "started": None})

    threading.Thread(target=_run, daemon=True, name=f"agent_run").start()
    return jsonify({"ok": True, "running": True, "goal": goal})


@app.route("/api/agent/status", methods=["GET"])
def api_agent_status():
    with _agent_lock:
        return jsonify(dict(_agent_running))


# ============ Proactive: accept suggestion ============
@app.route("/api/proactive/accept", methods=["POST"])
def api_proactive_accept():
    """Accept a proactive suggestion: create the automation it proposes."""
    try:
        import automations
        data = request.get_json(force=True) or {}
        auto = data.get("automation") or {}
        if not auto.get("name") or not auto.get("command"):
            return jsonify({"ok": False, "error": "missing name or command"}), 400
        auto.setdefault("enabled", True)
        auto.setdefault("mode", "voice")
        auto.setdefault("created_at", int(time.time()))
        auto.setdefault("source", "proactive_accept")
        automations.upsert(auto)
        broadcast("notification", {"text": f"Automazione '{auto['name']}' creata"})
        return jsonify({"ok": True, "automation": auto})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============ Instructions panel (memory_graph instruction kind) ============
@app.route("/api/instructions", methods=["GET"])
def api_instructions_list():
    """List saved instructions (suggestions/self-healing proposals)."""
    try:
        import memory_graph as mg
        items = mg.list_by_kind("instruction", limit=50) if hasattr(mg, "list_by_kind") else []
        return jsonify({"items": items})
    except Exception as e:
        return jsonify({"items": [], "error": str(e)})


# ============ Net guard ============
@app.route("/api/net_guard/status", methods=["GET"])
def api_net_guard_status():
    import net_guard
    return jsonify(net_guard.status())


@app.route("/api/net_guard/mode", methods=["POST"])
def api_net_guard_mode():
    import net_guard
    data = request.get_json(force=True) or {}
    mode = data.get("mode", "observe")
    return jsonify({"ok": net_guard.set_mode(mode), "mode": mode})


@app.route("/api/net_guard/host", methods=["POST"])
def api_net_guard_add_host():
    import net_guard
    data = request.get_json(force=True) or {}
    host = data.get("host", "").strip().lower()
    if not host:
        return jsonify({"ok": False, "error": "missing host"}), 400
    return jsonify({"ok": net_guard.add_host(host)})


@app.route("/api/net_guard/host/<host>", methods=["DELETE"])
def api_net_guard_remove_host(host):
    import net_guard
    return jsonify({"ok": net_guard.remove_host(host)})


@app.route("/api/net_guard/recent", methods=["GET"])
def api_net_guard_recent():
    import net_guard
    return jsonify({"events": net_guard.recent_outbound(limit=200)})


# ============ ACL: consent grant/revoke ============
@app.route("/api/acl/status", methods=["GET"])
def api_acl_status():
    try:
        import tool_acl
        import prompt_shield
        return jsonify({
            "acl": tool_acl.status(),
            "shield": {
                "categories": list({c for cs in []
                                     for c in cs}),  # placeholder
            },
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/acl/consent", methods=["POST"])
def api_acl_consent():
    try:
        import tool_acl
        data = request.get_json(force=True) or {}
        tool = data.get("tool", "").strip()
        ttl = int(data.get("ttl_sec", 300))
        if not tool:
            return jsonify({"ok": False, "error": "missing tool"}), 400
        tool_acl.register_consent(tool, ttl)
        return jsonify({"ok": True, "tool": tool, "ttl_sec": ttl})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/backup_enc/create", methods=["POST"])
def api_backup_enc_create():
    import encrypted_backup
    data = request.get_json(force=True) or {}
    pin = (data.get("pin") or "").strip()
    return jsonify(encrypted_backup.create_backup(pin))


@app.route("/api/backup_enc/list", methods=["GET"])
def api_backup_enc_list():
    import encrypted_backup
    return jsonify({"backups": encrypted_backup.list_backups()})


@app.route("/api/backup_enc/verify", methods=["POST"])
def api_backup_enc_verify():
    import encrypted_backup
    data = request.get_json(force=True) or {}
    return jsonify(encrypted_backup.verify_backup(
        data.get("name", ""), data.get("pin", "")))


@app.route("/api/backup_enc/delete", methods=["POST"])
def api_backup_enc_delete():
    import encrypted_backup
    data = request.get_json(force=True) or {}
    return jsonify({"ok": encrypted_backup.delete_backup(data.get("name", ""))})


# ============ Morning Briefing ============
@app.route("/api/briefing/morning", methods=["GET"])
def api_briefing_morning():
    """Returns today's briefing payload + whether to show it now."""
    import briefing
    client_id = request.args.get("client_id", request.remote_addr or "default")
    payload = briefing.build_morning_briefing()
    should = briefing.should_show_today(client_id)
    return jsonify({
        "briefing": payload,
        "should_show": should,
        "client_id": client_id,
    })


@app.route("/api/briefing/mark_shown", methods=["POST"])
def api_briefing_mark():
    import briefing
    data = request.get_json(force=True) or {}
    briefing.mark_shown(data.get("client_id", request.remote_addr or "default"))
    return jsonify({"ok": True})


# ============ Team agents (Tier 0-3) ============
@app.route("/api/team/status", methods=["GET"])
def api_team_status():
    try:
        from agents import team_registry
        return jsonify({"agents": team_registry.status_all()})
    except Exception as e:
        return jsonify({"agents": [], "error": str(e)})


@app.route("/api/team/run", methods=["POST"])
def api_team_run():
    """Manually trigger an agent: {agent: name, payload: {...}}"""
    try:
        from agents import team_registry
        data = request.get_json(force=True) or {}
        return jsonify(team_registry.run(data.get("agent", ""),
                                            data.get("payload", {})))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/team/<name>/enable", methods=["POST"])
def api_team_enable(name):
    from agents import team_registry
    return jsonify({"ok": team_registry.enable(name)})


@app.route("/api/team/<name>/disable", methods=["POST"])
def api_team_disable(name):
    from agents import team_registry
    return jsonify({"ok": team_registry.disable(name)})


@app.route("/api/team/messages", methods=["GET"])
def api_team_messages():
    """Recent inter-agent messages from bus history."""
    try:
        import bus
        hist = bus.history()
        team_msgs = [e for e in hist if e.get("topic") == "team.message"]
        return jsonify({"messages": team_msgs[-100:]})
    except Exception as e:
        return jsonify({"messages": [], "error": str(e)})


@app.route("/api/team/dpo/register", methods=["GET"])
def api_team_dpo_register():
    try:
        from agents import dpo
        return jsonify({"ok": True, "register": dpo._load_register()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/team/ciso/incidents", methods=["GET"])
def api_team_ciso_incidents():
    try:
        from agents import ciso
        status = request.args.get("status")
        return jsonify({"ok": True, "incidents": ciso.AGENT.list_incidents(status)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============ Agent Architect ============
@app.route("/api/architect/templates", methods=["GET"])
def api_architect_templates():
    from agents import team_registry
    a = team_registry.get("architect")
    if not a:
        return jsonify({"ok": False, "error": "architect non disponibile"}), 500
    return jsonify({"ok": True, "templates": a.list_templates()})


@app.route("/api/architect/template/<tid>", methods=["GET"])
def api_architect_template(tid):
    from agents import team_registry
    a = team_registry.get("architect")
    t = a.get_template(tid) if a else None
    return jsonify({"ok": bool(t), "template": t})


@app.route("/api/architect/discovery/start", methods=["POST"])
def api_architect_discovery_start():
    from agents import team_registry
    a = team_registry.get("architect")
    return jsonify({"ok": True, **a.start_discovery()})


@app.route("/api/architect/discovery/answer", methods=["POST"])
def api_architect_discovery_answer():
    from agents import team_registry
    a = team_registry.get("architect")
    data = request.get_json(force=True) or {}
    return jsonify(a.discovery_answer(data.get("session_id", ""),
                                         data.get("answer")))


@app.route("/api/architect/blueprint", methods=["POST"])
def api_architect_blueprint():
    from agents import team_registry
    a = team_registry.get("architect")
    data = request.get_json(force=True) or {}
    return jsonify(a.build_blueprint(
        template_id=data.get("template_id"),
        discovery_answers=data.get("discovery_answers"),
        customizations=data.get("customizations"),
    ))


@app.route("/api/architect/blueprints", methods=["GET"])
def api_architect_blueprints():
    from agents import team_registry
    a = team_registry.get("architect")
    return jsonify({"ok": True, "blueprints": a.list_blueprints()})


@app.route("/api/architect/deploy", methods=["POST"])
def api_architect_deploy():
    """Generate code + smoke test + hot-reload. Sensitive endpoint: requires localhost OR PIN session."""
    import security as _sec
    if not (_auth.is_local(request) or _sec.has_valid_pin_session()):
        return jsonify({"ok": False, "error": "richiede localhost o PIN session attiva"}), 403
    from agents import team_registry
    a = team_registry.get("architect")
    data = request.get_json(force=True) or {}
    return jsonify(a.deploy_blueprint(
        data.get("blueprint_id", ""),
        dry_run=bool(data.get("dry_run", False)),
    ))


@app.route("/api/team/dashboard/<agent>", methods=["GET"])
def api_team_dashboard(agent):
    """Detailed dashboard data for one agent."""
    from agents import team_registry
    a = team_registry.get(agent)
    if not a:
        return jsonify({"ok": False, "error": "agent not found"}), 404
    return jsonify({"ok": True, "data": a.dashboard_data()})


@app.route("/api/team/<agent>/action", methods=["POST"])
def api_team_agent_action(agent):
    """Execute a named action on an agent."""
    from agents import team_registry
    a = team_registry.get(agent)
    if not a:
        return jsonify({"ok": False, "error": "agent not found"}), 404
    data = request.get_json(force=True) or {}
    action = data.get("action", "default")
    args = data.get("args", {})
    return jsonify({"ok": True, "result": a.execute_action(action, args)})


@app.route("/api/team/hierarchy", methods=["GET"])
def api_team_hierarchy():
    """Return the org chart."""
    from agents import team_base
    return jsonify({"ok": True, "hierarchy": team_base._load_hierarchy()})


@app.route("/api/team/overview", methods=["GET"])
def api_team_overview():
    """Steward-level overview of all team."""
    from agents import team_registry
    steward = team_registry.get("steward")
    if not steward:
        return jsonify({"ok": False})
    return jsonify({"ok": True, "overview": steward.team_overview()})


@app.route("/api/team/personas", methods=["GET"])
def api_team_personas():
    from agents import chat_personas
    return jsonify({"personas": chat_personas.list_personas()})


_chat_histories = {}  # agent_name -> [messages]
_chat_lock = threading.Lock()


@app.route("/api/team/chat", methods=["POST"])
def api_team_chat():
    """Chat 1:1 con un agente in-character. Mantiene history per agent."""
    from agents import chat_personas
    import config
    data = request.get_json(force=True) or {}
    agent = data.get("agent", "").strip()
    user_msg = (data.get("message") or "").strip()
    persona = chat_personas.get_persona(agent)
    if not persona:
        # Fallback: cerca l'agente nel team_registry e usa fallback_persona
        try:
            from agents import team_registry
            ag = team_registry.get(agent)
            if ag:
                persona = chat_personas.fallback_persona(
                    agent, ag.description, ag.icon)
        except Exception:
            persona = None
    if not persona:
        return jsonify({"ok": False, "error": f"agente {agent} non trovato"}), 404
    if not user_msg:
        return jsonify({"ok": False, "error": "messaggio vuoto"}), 400
    with _chat_lock:
        history = _chat_histories.setdefault(agent, [])
        history.append({"role": "user", "content": user_msg})
        # Cap history to last 20 messages
        if len(history) > 40:
            history = history[-40:]
            _chat_histories[agent] = history
    # Call Claude with persona system prompt
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-haiku-4-5",   # Haiku for cheap agent chat
            max_tokens=800,
            system=persona["system"],
            messages=history,
        )
        reply = "\n".join(b.text for b in response.content if b.type == "text").strip()
    except Exception as e:
        return jsonify({"ok": False, "error": f"LLM: {e}"}), 500
    with _chat_lock:
        history.append({"role": "assistant", "content": reply})
    # Audit (no content, only metadata)
    try:
        import audit_log
        audit_log.log("team.chat", {"agent": agent, "user_chars": len(user_msg),
                                      "reply_chars": len(reply)})
    except Exception:
        pass
    return jsonify({"ok": True, "agent": agent, "reply": reply,
                    "history_length": len(history)})


@app.route("/api/team/chat/<agent>/history", methods=["GET"])
def api_team_chat_history(agent):
    with _chat_lock:
        return jsonify({"messages": _chat_histories.get(agent, [])})


@app.route("/api/team/chat/<agent>/clear", methods=["POST"])
def api_team_chat_clear(agent):
    with _chat_lock:
        if agent in _chat_histories:
            del _chat_histories[agent]
    return jsonify({"ok": True})


@app.route("/api/workflows/team/list", methods=["GET"])
def api_workflows_team_list():
    """Lista workflow del team (dai template Architect)."""
    import workflow_runner
    return jsonify({"workflows": workflow_runner.list_workflows(),
                     "recent_runs": workflow_runner.list_recent_runs()})


@app.route("/api/workflows/team/run", methods=["POST"])
def api_workflows_team_run():
    """Esegue un workflow del team."""
    import workflow_runner
    data = request.get_json(force=True) or {}
    name = data.get("workflow", "")
    overrides = data.get("payload", {}) or {}
    return jsonify(workflow_runner.run(name, overrides))


@app.route("/api/workflows/team/run/<run_id>", methods=["GET"])
def api_workflows_team_run_detail(run_id):
    import workflow_runner
    return jsonify(workflow_runner.get_run(run_id))


@app.route("/api/team/compliance_report", methods=["GET"])
def api_team_compliance_report():
    try:
        from agents import audit_watcher
        return jsonify({"ok": True, "report": audit_watcher.AGENT.monthly_report()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/security/cve_scan", methods=["POST"])
def api_security_cve_scan():
    import cve_scanner
    return jsonify(cve_scanner.scan_now())


@app.route("/api/security/cve_report", methods=["GET"])
def api_security_cve_report():
    import cve_scanner
    return jsonify(cve_scanner.last_report())


@app.route("/api/security/honeypot/rotate", methods=["POST"])
def api_security_honeypot_rotate():
    import honeypot
    honeypot.rotate_canaries()
    return jsonify(honeypot.stats())


@app.route("/api/security/overview", methods=["GET"])
def api_security_overview():
    """One-shot summary for the UI Security panel."""
    import security as _sec
    import rate_limit, tool_acl, net_guard, vault, audit_log
    out = {
        "auth": {
            "token_set": bool(_auth.get_token()),
            "pin_set": _sec.pin_is_set(),
            "pin_session_active": _sec.has_valid_pin_session(),
            "is_local": _auth.is_local(request),
        },
        "rate_limit": rate_limit.status(),
        "acl": tool_acl.status(),
        "net_guard": net_guard.status(),
        "vault": vault.status(),
        "audit": {
            "verified": audit_log.verify_integrity(),
        },
        "security": _sec.get_security_status(),
    }
    return jsonify(out)


@app.route("/api/vault/status", methods=["GET"])
def api_vault_status():
    import vault
    return jsonify(vault.status())


@app.route("/api/vault/encrypt", methods=["POST"])
def api_vault_encrypt():
    """Encrypt the current .env with PIN."""
    if not _auth.is_local(request):
        return jsonify({"ok": False, "error": "solo da localhost"}), 403
    import vault
    data = request.get_json(force=True) or {}
    pin = (data.get("pin") or "").strip()
    return jsonify(vault.encrypt_env_from_plain(pin))


@app.route("/api/vault/unlock", methods=["POST"])
def api_vault_unlock():
    """Unlock .env.enc with PIN, load secrets into env."""
    import vault
    try:
        import rate_limit
        if not rate_limit.check_pin_lockout(request.remote_addr or "?"):
            return jsonify({"ok": False, "error": "lockout"}), 429
    except Exception:
        pass
    data = request.get_json(force=True) or {}
    pin = (data.get("pin") or "").strip()
    result = vault.unlock(pin)
    if not result.get("ok"):
        try:
            rate_limit.register_pin_fail(request.remote_addr or "?")
        except Exception:
            pass
        try:
            import audit_log
            audit_log.log("vault.unlock_fail", {"ip": request.remote_addr})
        except Exception:
            pass
    else:
        try:
            import audit_log
            audit_log.log("vault.unlocked", {"ip": request.remote_addr})
        except Exception:
            pass
    return jsonify(result)


@app.route("/api/vault/rotate", methods=["POST"])
def api_vault_rotate():
    import vault
    if not _auth.is_local(request):
        return jsonify({"ok": False, "error": "solo da localhost"}), 403
    data = request.get_json(force=True) or {}
    return jsonify(vault.rotate_pin(data.get("old_pin", ""), data.get("new_pin", "")))


@app.route("/api/audit/tail", methods=["GET"])
def api_audit_tail():
    import audit_log
    n = int(request.args.get("n", 100))
    return jsonify({"records": audit_log.tail(n=n)})


@app.route("/api/audit/verify", methods=["GET"])
def api_audit_verify():
    import audit_log
    return jsonify(audit_log.verify_integrity())


@app.route("/api/acl/revoke", methods=["POST"])
def api_acl_revoke():
    try:
        import tool_acl
        data = request.get_json(force=True) or {}
        tool = data.get("tool", "").strip()
        return jsonify({"ok": tool_acl.revoke_consent(tool)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============ Cert download ============
@app.route("/-/cert", methods=["GET"])
def api_get_cert():
    try:
        import tls_setup
        pem = tls_setup.get_cert_pem()
        from flask import Response
        return Response(pem, mimetype="application/x-pem-file",
                        headers={"Content-Disposition": "attachment; filename=vega.crt"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============ Auth ============
@app.route("/api/auth/info", methods=["GET"])
def api_auth_info():
    import security as _sec
    return jsonify({
        "pin_required": _sec.pin_is_set(),
        "is_local": _auth.is_local(request),
    })


@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    """Exchange PIN for Bearer token. If PIN not set, only loopback can get token."""
    import security as _sec
    try:
        import rate_limit
        if not rate_limit.check_pin_lockout(request.remote_addr or "?"):
            return jsonify({"ok": False,
                            "error": "Troppi tentativi PIN. Account bloccato 15 minuti."}), 429
    except Exception:
        pass
    try:
        import audit_log
    except Exception:
        audit_log = None
    data = request.get_json(force=True) or {}
    pin = (data.get("pin") or "").strip()
    remote = request.remote_addr or "?"
    if _sec.pin_is_set():
        token = _auth.verify_pin_and_issue_token(pin)
        if not token:
            try:
                rate_limit.register_pin_fail(remote)
            except Exception:
                pass
            if audit_log:
                audit_log.log("auth.login_fail", {"ip": remote})
            return jsonify({"ok": False, "error": "PIN errato"}), 403
        if audit_log:
            audit_log.log("auth.login_ok", {"ip": remote})
        try:
            rate_limit.clear_pin_fails(remote)
        except Exception:
            pass
        return jsonify({"ok": True, "token": token})
    # No PIN set -> only localhost can get token (security via locality)
    if _auth.is_local(request):
        if audit_log:
            audit_log.log("auth.login_ok", {"ip": remote, "no_pin": True})
        return jsonify({"ok": True, "token": _auth.get_token(),
                        "warning": "Nessun PIN impostato. Imposta un PIN per accesso remoto sicuro."})
    if audit_log:
        audit_log.log("auth.login_fail", {"ip": remote, "reason": "no_pin_remote"})
    return jsonify({"ok": False, "error": "PIN non configurato; usa localhost per inizializzare"}), 403


@app.route("/api/auth/rotate", methods=["POST"])
def api_auth_rotate():
    """Rotate the bearer token (invalidates all existing sessions)."""
    new = _auth.rotate_token()
    broadcast("notification", {"text": "Token API ruotato. Tutti i client devono ri-autenticarsi."})
    return jsonify({"ok": True, "token": new})


# ============ Web Push (PWA mobile notifications) ============
@app.route("/api/push/public_key", methods=["GET"])
def api_push_public_key():
    try:
        import web_push
        return jsonify({"public_key": web_push.public_key()})
    except Exception as e:
        return jsonify({"public_key": "", "error": str(e)})


@app.route("/api/push/subscribe", methods=["POST"])
def api_push_subscribe():
    try:
        import web_push
        sub = request.get_json(force=True)
        web_push.add_subscription(sub)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/push/send", methods=["POST"])
def api_push_send():
    try:
        import web_push
        data = request.get_json(force=True) or {}
        return jsonify(web_push.push(
            title=data.get("title", "Vega"),
            body=data.get("body", ""),
            url=data.get("url"),
        ))
    except Exception as e:
        return jsonify({"sent": 0, "error": str(e)}), 500


@app.route("/api/voice_id/enroll", methods=["POST"])
def api_voice_id_enroll():
    """Record N seconds of mic and enroll for user_id. POST JSON: {user_id, seconds}."""
    try:
        import voice_id
        import sounddevice as sd
        import numpy as np
        data = request.get_json(force=True) or {}
        user_id = (data.get("user_id") or "").strip().lower()
        seconds = float(data.get("seconds", 4.0))
        if not user_id:
            return jsonify({"ok": False, "error": "user_id mancante"}), 400
        sr = 16000
        rec = sd.rec(int(seconds * sr), samplerate=sr, channels=1, dtype="int16", blocking=True)
        audio = rec.flatten()
        return jsonify(voice_id.enroll(user_id, audio))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/voice_id/list", methods=["GET"])
def api_voice_id_list():
    try:
        import voice_id
        return jsonify({"users": voice_id.list_users()})
    except Exception as e:
        return jsonify({"users": [], "error": str(e)})


@app.route("/api/voice_id/<uid>", methods=["DELETE"])
def api_voice_id_delete(uid):
    try:
        import voice_id
        return jsonify({"ok": voice_id.delete(uid)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/voice/clone", methods=["POST"])
def api_voice_clone():
    """Upload one or more audio samples and create a custom ElevenLabs voice.
    Saves the resulting voice_id into preferences (eleven_custom_voice_id)."""
    try:
        from config import ELEVENLABS_API_KEY as _ek
    except Exception:
        _ek = os.getenv("ELEVENLABS_API_KEY", "")
    if not _ek:
        return jsonify({"ok": False, "error": "ELEVENLABS_API_KEY non configurata"}), 400
    if "file" not in request.files and "files" not in request.files:
        return jsonify({"ok": False, "error": "no file"}), 400
    files = request.files.getlist("files") or [request.files["file"]]
    name = request.form.get("name", "Custom_Vega_Voice")
    try:
        from elevenlabs.client import ElevenLabs
        client_e = ElevenLabs(api_key=_ek)
        # Save samples to tmp paths
        import tempfile
        sample_paths = []
        for f in files:
            ext = os.path.splitext(f.filename or "sample.wav")[1] or ".wav"
            tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
            tmp.close()
            f.save(tmp.name)
            sample_paths.append(tmp.name)
        # API differs across SDK versions; try the IVC (Instant Voice Cloning) call
        try:
            voice = client_e.voices.ivc.create(name=name, files=sample_paths,
                                                description="Custom voice for Vega user")
        except AttributeError:
            voice = client_e.voices.add(name=name, files=sample_paths,
                                         description="Custom voice for Vega user")
        voice_id = getattr(voice, "voice_id", None) or voice.get("voice_id")
        memory.set_preference("eleven_custom_voice_id", voice_id)
        memory.set_preference("tts_provider", "elevenlabs")
        broadcast("notification", {"text": f"Voce clonata: {voice_id}"})
        return jsonify({"ok": True, "voice_id": voice_id, "name": name})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/voice/clone/reset", methods=["POST"])
def api_voice_clone_reset():
    memory.set_preference("eleven_custom_voice_id", "")
    return jsonify({"ok": True})


@app.route("/api/local_brain/status", methods=["GET"])
def api_local_brain_status():
    try:
        import local_brain
        return jsonify({
            "available": local_brain.is_available(),
            "host": local_brain.OLLAMA_HOST,
            "models": local_brain.list_models(),
            "current_model": local_brain.get_model(),
            "enabled": memory.get_preferences().get("local_brain_enabled", False),
        })
    except Exception as e:
        return jsonify({"available": False, "error": str(e)})


@app.route("/api/episodic/list", methods=["GET"])
def api_episodic_list():
    try:
        import episodic_memory as _em
        return jsonify({"items": _em.list_all(limit=100), "stats": _em.stats()})
    except Exception as e:
        return jsonify({"items": [], "error": str(e)})


@app.route("/api/episodic/search", methods=["POST"])
def api_episodic_search():
    try:
        import episodic_memory as _em
        data = request.get_json(force=True) or {}
        q = (data.get("query") or "").strip()
        if not q:
            return jsonify({"results": []})
        return jsonify({"results": _em.search(q, limit=int(data.get("limit", 8)))})
    except Exception as e:
        return jsonify({"results": [], "error": str(e)}), 500


@app.route("/api/episodic/<mid>", methods=["DELETE"])
def api_episodic_delete(mid):
    try:
        import episodic_memory as _em
        return jsonify({"ok": _em.delete(mid)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/instructions/<iid>", methods=["DELETE"])
def api_instructions_delete(iid):
    try:
        import memory_graph as mg
        if hasattr(mg, "delete"):
            ok = mg.delete(iid)
        else:
            ok = False
        return jsonify({"ok": bool(ok)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/tasks", methods=["GET"])
def api_tasks():
    import task_queue
    status = request.args.get("status")
    limit = int(request.args.get("limit", 50))
    return jsonify({
        "items": task_queue.list_tasks(status=status, limit=limit),
        "stats": task_queue.stats(),
    })


@app.route("/api/bus/history", methods=["GET"])
def api_bus_history():
    import bus
    return jsonify({"events": bus.history(100)})


@app.route("/api/capabilities/search", methods=["GET"])
def api_capabilities_search():
    import capabilities
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"results": []})
    return jsonify({"results": capabilities.search(q, top_k=10)})


@app.route("/api/memory_graph/search", methods=["GET"])
def api_memory_graph_search():
    import memory_graph
    q = request.args.get("q", "").strip()
    kinds = request.args.get("kinds", "").split(",") if request.args.get("kinds") else None
    if not q:
        return jsonify({"results": []})
    return jsonify({"results": memory_graph.search(q, kinds=kinds, top_k=10)})


@app.route("/api/memory_graph/stats", methods=["GET"])
def api_memory_graph_stats():
    import memory_graph
    return jsonify(memory_graph.stats())


@app.route("/api/metrics", methods=["GET"])
def api_metrics():
    import observability
    return jsonify(observability.get_metrics_summary())


@app.route("/api/trace/<trace_id>", methods=["GET"])
def api_trace_detail(trace_id):
    import tracing
    return jsonify({"trace_id": trace_id, "spans": tracing.get_spans(trace_id)})


@app.route("/api/trace/recent", methods=["GET"])
def api_trace_recent():
    import tracing
    return jsonify({"traces": tracing.recent_traces(
        limit=int(request.args.get("limit", 20)))})


@app.route("/api/health", methods=["GET"])
def api_health():
    """Overall health summary (status: healthy/degraded/unhealthy)."""
    import health
    return jsonify(health.overall())


@app.route("/api/health/live", methods=["GET"])
def api_health_live():
    import health
    return jsonify(health.liveness())


@app.route("/api/health/ready", methods=["GET"])
def api_health_ready():
    import health
    r = health.readiness()
    return jsonify(r), (200 if r["ready"] else 503)


@app.route("/api/metrics/cache", methods=["GET"])
def api_metrics_cache():
    """Cache hit rate metrics (Anthropic prompt caching)."""
    return jsonify(memory.get_cache_metrics())


@app.route("/api/metrics/tools", methods=["GET"])
def api_metrics_tools():
    """Per-tool health + usage stats."""
    try:
        import tool_health
        import observability
        health = tool_health.status()
        obs = observability.get_metrics_summary()
        return jsonify({
            "health": health,
            "observability": obs.get("tools", {}),
            "cache_entries": _safe_tool_cache_stats(),
        })
    except Exception as e:
        return jsonify({"error": str(e)})


def _safe_tool_cache_stats():
    try:
        import tool_cache
        return tool_cache.stats()
    except Exception:
        return {}


@app.route("/api/tools/<name>/enable", methods=["POST"])
def api_tool_enable(name):
    import tool_health
    return jsonify({"ok": tool_health.enable(name)})


@app.route("/api/tools/<name>/disable", methods=["POST"])
def api_tool_disable(name):
    import tool_health
    data = request.get_json(force=True) or {}
    tool_health.disable(name, reason=data.get("reason", "manual"),
                          duration_sec=int(data.get("duration_sec", 1800)))
    return jsonify({"ok": True})


@app.route("/api/metrics/costs", methods=["GET"])
def api_metrics_costs():
    """Costo breakdown per caller (agent/tool/general)."""
    try:
        import cost_tracker
        return jsonify(cost_tracker.get_breakdown())
    except Exception as e:
        return jsonify({"error": str(e)})


# ============ Batch API (opt-in, 50% sconto su workload async) ============
@app.route("/api/batch/submit", methods=["POST"])
def api_batch_submit():
    try:
        import batch_brain
        data = request.get_json(force=True) or {}
        bid = batch_brain.submit(data.get("requests", []),
                                    label=data.get("label", "untitled"))
        return jsonify({"ok": True, "batch_id": bid})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/batch/<batch_id>/status", methods=["GET"])
def api_batch_status(batch_id):
    import batch_brain
    return jsonify(batch_brain.status(batch_id))


@app.route("/api/batch/<batch_id>/results", methods=["GET"])
def api_batch_results(batch_id):
    import batch_brain
    return jsonify({"results": batch_brain.results(batch_id)})


@app.route("/api/batch/pending", methods=["GET"])
def api_batch_pending():
    import batch_brain
    return jsonify({"jobs": batch_brain.pending()})


@app.route("/api/backup/list", methods=["GET"])
def api_backup_list():
    import backup
    return jsonify({"backups": backup.list_backups()})


@app.route("/api/backup/create", methods=["POST"])
def api_backup_create():
    import backup
    path = backup.make_backup()
    return jsonify({"ok": bool(path), "path": path})


@app.route("/api/help", methods=["GET"])
def api_help():
    """List all available tools grouped by category for the help page."""
    import tools as tool_registry
    schemas = tool_registry.all_schemas()

    # Categorize tools by name prefix / heuristics
    categories = {
        "Email": [],
        "Notizie & Web": [],
        "Meteo & Wikipedia": [],
        "Musica & Radio": [],
        "Sistema PC": [],
        "Finestre & App": [],
        "Tempo & Promemoria": [],
        "Memoria & Note": [],
        "File & Documenti": [],
        "Foto & Immagini": [],
        "Borsa & Sport": [],
        "Calcoli & Dati": [],
        "Lettura & Podcast": [],
        "Inglese": [],
        "Automazioni & Scene": [],
        "Privacy & Sicurezza": [],
        "Configurazione": [],
        "Comunicazione": [],
        "Timer": [],
        "Altro": [],
    }
    examples_map = {
        "list_emails": ["leggi le email", "che mail ho"],
        "get_news": ["dimmi le notizie", "rassegna stampa"],
        "get_weather": ["che tempo fa", "meteo domani"],
        "wikipedia": ["chi era Leonardo", "cosa e' la fotosintesi"],
        "play_radio": ["metti RDS", "metti radio deejay"],
        "system_info": ["come va il pc"],
        "set_volume": ["metti volume al 50"],
        "open_application": ["apri Chrome", "apri Spotify"],
        "get_time": ["che ore sono"],
        "set_timer": ["timer pasta 8 minuti"],
        "remember_fact": ["ricordati che lavoro da casa"],
        "add_todo": ["aggiungi alla lista comprare il latte"],
        "find_files": ["trova file budget"],
        "take_screenshot": ["fai uno screenshot"],
        "analyze_screen": ["guarda lo schermo"],
        "generate_image": ["crea immagine di un robot"],
        "web_images": ["foto del colosseo"],
        "stock_quote": ["prezzo Apple", "quanto vale bitcoin"],
        "sports_news": ["notizie sport"],
        "calculate": ["quanto fa 17 per 23"],
        "code_exec": ["codice: somma di 1 a 100"],
        "analyze_spreadsheet": ["analizza vendite.xlsx"],
        "read_article_aloud": ["leggi questo articolo: URL"],
        "english_tutor_start": ["sessione di conversazione in inglese"],
        "create_automation": ["crea automazione briefing ogni mattina alle 8"],
        "activate_scene": ["attiva modalita' lavoro"],
        "privacy_mode": ["attiva modalita' privata"],
        "set_voice": ["cambia voce Isabella"],
        "windows_notify": ["mandami una notifica"],
        "lan_url": ["url per il telefono"],
        "timer_create": ["timer pasta 5 minuti"],
        "organize_downloads": ["organizza i download"],
        "search_docs": ["cerca nei documenti"],
    }

    def categorize(name: str):
        n = name.lower()
        if any(k in n for k in ["email", "mail", "inbox"]): return "Email"
        if any(k in n for k in ["news", "rss", "web_search", "read_webpage", "youtube"]): return "Notizie & Web"
        if "weather" in n or "wikipedia" in n: return "Meteo & Wikipedia"
        if any(k in n for k in ["radio", "music"]): return "Musica & Radio"
        if any(k in n for k in ["volume", "brightness", "lock_pc", "shutdown", "system_info", "mute"]): return "Sistema PC"
        if any(k in n for k in ["window", "open_app", "minimize", "focus_window", "close_window"]): return "Finestre & App"
        if any(k in n for k in ["timer"]): return "Timer"
        if any(k in n for k in ["time", "reminder"]): return "Tempo & Promemoria"
        if any(k in n for k in ["note", "todo", "fact", "instruction"]): return "Memoria & Note"
        if any(k in n for k in ["file", "pdf", "clipboard", "screenshot", "docs", "organize"]): return "File & Documenti"
        if any(k in n for k in ["image", "vision", "analyze_screen", "gallery"]): return "Foto & Immagini"
        if any(k in n for k in ["stock", "sports"]): return "Borsa & Sport"
        if any(k in n for k in ["calculate", "code_exec", "spreadsheet", "chart", "make_chart"]): return "Calcoli & Dati"
        if any(k in n for k in ["read_article", "podcast", "reading"]): return "Lettura & Podcast"
        if "english" in n: return "Inglese"
        if any(k in n for k in ["automation", "scene", "macro", "alias", "workflow"]): return "Automazioni & Scene"
        if any(k in n for k in ["privacy", "security", "pin", "clear_conversation"]): return "Privacy & Sicurezza"
        if any(k in n for k in ["set_voice", "set_personality", "set_mode", "set_home", "show_settings", "toggle", "preference"]): return "Configurazione"
        if any(k in n for k in ["notify", "voice_mail", "lan"]): return "Comunicazione"
        return "Altro"

    for s in schemas:
        nm = s.get("name", "")
        desc = s.get("description", "")
        cat = categorize(nm)
        item = {"name": nm, "description": desc}
        if nm in examples_map:
            item["examples"] = examples_map[nm]
        categories[cat].append(item)
    # Remove empty
    categories = {k: v for k, v in categories.items() if v}
    return jsonify({"tool_count": len(schemas), "categories": categories})


@app.route("/api/search", methods=["GET"])
def api_search():
    """Global search across conversations, notes, todos, facts, automations, ecc."""
    q = (request.args.get("q") or "").lower().strip()
    if len(q) < 2:
        return jsonify({"results": []})

    results = []
    data = memory.get_all()
    # Conversations
    for ex in data.get("conversation_log", []):
        if q in (ex.get("user", "") + " " + ex.get("assistant", "")).lower():
            ts = ex.get("ts", "")
            results.append({"category": "💬 Conversazione",
                            "text": f"{ex.get('user','')[:80]} → {ex.get('assistant','')[:80]}",
                            "timestamp": ts[:16] if ts else ""})
    # Facts
    for f in data.get("user_facts", []):
        if q in f.get("text", "").lower():
            results.append({"category": "🧠 Fatto", "text": f["text"], "timestamp": f.get("ts", "")[:16]})
    # Notes
    for n in data.get("notes", []):
        if q in n.get("text", "").lower():
            results.append({"category": "📝 Nota", "text": n["text"], "timestamp": n.get("ts", "")[:16]})
    # Todos
    for t in data.get("todos", []):
        if q in t.get("text", "").lower():
            done = "✓ " if t.get("done") else "○ "
            results.append({"category": "✅ Todo", "text": done + t["text"], "timestamp": t.get("ts", "")[:16]})
    # Reminders
    for r in data.get("reminders", []):
        if q in r.get("text", "").lower():
            results.append({"category": "⏰ Promemoria", "text": r["text"], "timestamp": r.get("when", "")[:16]})
    # Custom instructions
    for i in data.get("custom_instructions", []):
        if q in i.get("text", "").lower():
            results.append({"category": "⚙️ Regola", "text": i["text"], "timestamp": i.get("ts", "")[:16]})
    # Automations
    try:
        import automations
        for it in automations.list_all():
            if q in it.get("name", "").lower() or q in it.get("command", "").lower():
                results.append({"category": "🤖 Automazione",
                                "text": f"{it['name']}: {it.get('command', '')[:80]} ({it.get('schedule')})",
                                "timestamp": ""})
    except Exception:
        pass

    # Limit
    return jsonify({"results": results[:40]})


@app.route("/api/diagnose", methods=["GET"])
def api_diagnose():
    """Run a self-check and return health status of all subsystems."""
    import socket as _s
    checks = {}

    # 1. Anthropic API key valid?
    try:
        from config import ANTHROPIC_API_KEY
        checks["anthropic_key"] = {"status": "ok" if ANTHROPIC_API_KEY and ANTHROPIC_API_KEY.startswith("sk-ant") else "missing"}
    except Exception as e:
        checks["anthropic_key"] = {"status": "error", "detail": str(e)}

    # 2. Gmail configured?
    try:
        from config import GMAIL_ADDRESS, GMAIL_APP_PASSWORD
        checks["gmail"] = {"status": "ok" if GMAIL_ADDRESS and GMAIL_APP_PASSWORD else "missing"}
    except Exception:
        checks["gmail"] = {"status": "error"}

    # 3. Whisper model loaded?
    try:
        checks["whisper"] = {"status": "ok" if engine.whisper is not None else "not_loaded"}
    except Exception:
        checks["whisper"] = {"status": "error"}

    # 4. Wake word model
    try:
        checks["wake_word"] = {"status": "ok" if engine.wake is not None else "not_loaded"}
    except Exception:
        checks["wake_word"] = {"status": "error"}

    # 5. Microphone available?
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        input_devs = [d for d in devices if d.get("max_input_channels", 0) > 0]
        checks["microphone"] = {"status": "ok" if input_devs else "no_input_device",
                                "count": len(input_devs)}
    except Exception as e:
        checks["microphone"] = {"status": "error", "detail": str(e)}

    # 6. Internet reachable?
    try:
        s = _s.create_connection(("8.8.8.8", 53), timeout=3)
        s.close()
        checks["internet"] = {"status": "ok"}
    except Exception:
        checks["internet"] = {"status": "unreachable"}

    # 7. Disk space available?
    try:
        import shutil as _sh
        total, used, free = _sh.disk_usage(ROOT)
        free_gb = free / 1e9
        checks["disk_space"] = {"status": "ok" if free_gb > 1 else "low",
                                "free_gb": round(free_gb, 1)}
    except Exception:
        checks["disk_space"] = {"status": "error"}

    # 8. Modules count
    try:
        import tools
        checks["tools"] = {"status": "ok", "count": len(tools.all_schemas())}
    except Exception as e:
        checks["tools"] = {"status": "error", "detail": str(e)}

    # 9. Engine state
    checks["engine"] = {"status": "ok" if engine.state in ("idle", "speaking", "listening", "thinking") else "boot",
                       "current_state": engine.state}

    # 10. Memory file
    try:
        mem_size = os.path.getsize(os.path.join(ROOT, "memory.json")) if os.path.exists(os.path.join(ROOT, "memory.json")) else 0
        checks["memory_file"] = {"status": "ok", "size_kb": round(mem_size / 1024, 1)}
    except Exception:
        checks["memory_file"] = {"status": "error"}

    overall = "ok" if all(c.get("status") == "ok" for c in checks.values()) else "warnings"
    return jsonify({"overall": overall, "checks": checks})


@app.route("/api/logs", methods=["GET"])
def api_logs():
    """Return last lines of vega_error.log."""
    log_path = os.path.join(ROOT, "vega_error.log")
    if not os.path.exists(log_path):
        return jsonify({"lines": [], "size": 0})
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        # mask secrets
        try:
            import security as _sec
            content = _sec.mask_secrets(content)
        except Exception:
            pass
        lines = content.splitlines()
        return jsonify({"lines": lines[-200:], "size": len(content)})
    except Exception as e:
        return jsonify({"lines": [f"errore: {e}"], "size": 0})


@app.route("/api/logs", methods=["DELETE"])
def api_logs_clear():
    log_path = os.path.join(ROOT, "vega_error.log")
    try:
        if os.path.exists(log_path):
            open(log_path, "w").close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/lan_info", methods=["GET"])
def api_lan_info():
    """Return the LAN IP so the user can connect from their phone."""
    import socket
    ip = "127.0.0.1"
    try:
        # Trick: connect to remote, get our outbound IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass
    return jsonify({
        "lan_ip": ip,
        "port": PORT,
        "lan_url": f"http://{ip}:{PORT}",
        "qr_text": f"http://{ip}:{PORT}",
    })


@app.route("/api/pc_stats", methods=["GET"])
def api_pc_stats():
    """Detailed PC monitoring metrics."""
    import psutil
    import platform as plt

    cpu_per_core = psutil.cpu_percent(interval=0.3, percpu=True)
    cpu_overall = sum(cpu_per_core) / len(cpu_per_core) if cpu_per_core else 0
    cpu_freq = psutil.cpu_freq()

    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    disks = []
    for part in psutil.disk_partitions():
        if "cdrom" in part.opts or part.fstype == "":
            continue
        try:
            u = psutil.disk_usage(part.mountpoint)
            disks.append({
                "mount": part.mountpoint,
                "fs": part.fstype,
                "total_gb": round(u.total / 1e9, 1),
                "used_gb": round(u.used / 1e9, 1),
                "free_gb": round(u.free / 1e9, 1),
                "percent": u.percent,
            })
        except Exception:
            pass

    net = psutil.net_io_counters()

    # Top 10 processes by CPU
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            procs.append({
                "pid": p.info["pid"],
                "name": p.info.get("name") or "?",
                "cpu": p.info.get("cpu_percent") or 0,
                "mem": round(p.info.get("memory_percent") or 0, 1),
            })
        except Exception:
            pass
    procs.sort(key=lambda x: x["cpu"], reverse=True)
    top_procs = procs[:10]

    # Battery
    battery = None
    try:
        b = psutil.sensors_battery()
        if b:
            battery = {
                "percent": round(b.percent, 0),
                "plugged": bool(b.power_plugged),
                "time_left_min": (b.secsleft // 60) if b.secsleft not in (-1, -2) else None,
            }
    except Exception:
        pass

    # Boot time / uptime
    import time as _t
    uptime_sec = int(_t.time() - psutil.boot_time())

    return jsonify({
        "system": f"{plt.system()} {plt.release()}",
        "machine": plt.machine(),
        "processor": plt.processor()[:60],
        "cpu_count": psutil.cpu_count(logical=True),
        "cpu_physical": psutil.cpu_count(logical=False),
        "cpu_per_core": cpu_per_core,
        "cpu_overall": round(cpu_overall, 1),
        "cpu_freq_mhz": round(cpu_freq.current, 0) if cpu_freq else 0,
        "memory": {
            "total_gb": round(mem.total / 1e9, 1),
            "used_gb": round(mem.used / 1e9, 1),
            "available_gb": round(mem.available / 1e9, 1),
            "percent": mem.percent,
        },
        "swap": {
            "total_gb": round(swap.total / 1e9, 1),
            "used_gb": round(swap.used / 1e9, 1),
            "percent": swap.percent,
        },
        "disks": disks,
        "network": {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
        },
        "top_processes": top_procs,
        "battery": battery,
        "uptime_sec": uptime_sec,
        "uptime_str": f"{uptime_sec // 86400}g {(uptime_sec % 86400) // 3600}h {(uptime_sec % 3600) // 60}m",
    })


@app.route("/api/stats", methods=["GET"])
def api_stats():
    """Aggregated stats for the dashboard."""
    from datetime import datetime
    data = memory.get_all()
    convs = data.get("conversation_log", [])
    facts = data.get("user_facts", [])
    todos = data.get("todos", [])
    notes = data.get("notes", [])
    instr = data.get("custom_instructions", [])
    usage = data.get("usage", {})

    # Tool usage counts from recent conversation_log (a rough proxy)
    # We don't track tool calls explicitly per call, so estimate from logs.
    today = datetime.now().date().isoformat()
    today_usage = usage.get("daily", {}).get(today, {})

    # Per-day totals (last 14 days)
    daily = usage.get("daily", {})
    history = []
    for date in sorted(daily.keys())[-14:]:
        d = daily[date]
        history.append({
            "date": date,
            "calls": d.get("calls", 0),
            "cost": memory.estimate_cost(d),
            "input": d.get("input", 0),
            "output": d.get("output", 0),
            "cache_read": d.get("cache_read", 0),
            "cache_write": d.get("cache_write", 0),
        })

    total_calls = usage.get("total", {}).get("calls", 0)
    total_cost = memory.estimate_cost(usage.get("total", {}))

    # Cache hit rate today
    cr = today_usage.get("cache_read", 0)
    cw = today_usage.get("cache_write", 0)
    direct = today_usage.get("input", 0)
    total_in_today = cr + cw + direct
    cache_hit_pct = round(cr / total_in_today * 100) if total_in_today else 0

    return jsonify({
        "facts_count": len(facts),
        "todos_open": sum(1 for t in todos if not t.get("done")),
        "todos_total": len(todos),
        "notes_count": len(notes),
        "instructions_count": len(instr),
        "conversations_logged": len(convs),
        "total_calls": total_calls,
        "total_cost_usd": total_cost,
        "today_calls": today_usage.get("calls", 0),
        "today_cost_usd": memory.estimate_cost(today_usage),
        "cache_hit_pct": cache_hit_pct,
        "history": history,
    })


@app.route("/api/shutdown", methods=["POST"])
def api_shutdown():
    def kill():
        engine.interrupt()
        engine.stop()
        time.sleep(0.6)
        os._exit(0)
    threading.Thread(target=kill, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/restart", methods=["POST"])
def api_restart():
    """Restart Vega: spawn a new process, then exit current one.
    Browser auto-reconnects when new server is ready."""
    def do_restart():
        try:
            engine.interrupt()
            engine.stop()
        except Exception:
            pass
        time.sleep(0.5)
        # Clean up lock so new instance doesn't refuse to start
        try:
            lock = os.path.join(ROOT, ".vega.lock")
            if os.path.exists(lock):
                os.unlink(lock)
        except Exception:
            pass
        # Spawn new process using the same Python (pythonw or python)
        try:
            pythonw = os.path.join(ROOT, "venv", "Scripts", "pythonw.exe")
            python_to_use = pythonw if os.path.exists(pythonw) else sys.executable
            subprocess.Popen(
                [python_to_use, "-X", "utf8", os.path.join(ROOT, "server.py")],
                cwd=ROOT,
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        except Exception:
            pass
        time.sleep(0.3)
        os._exit(0)
    threading.Thread(target=do_restart, daemon=True).start()
    return jsonify({"ok": True})


# ---- Music library ----
@app.route("/api/music/library", methods=["GET"])
def api_music_library():
    items = []
    # Pin the Clash intro track at the top of the library so it's always playable
    intro_path = os.path.join(ASSETS_DIR, "startup.mp3")
    if os.path.exists(intro_path):
        items.append({
            "name": "The Clash - Should I Stay or Should I Go",
            "filename": "__intro__",
            "url": "/assets/startup.mp3",
            "size": os.path.getsize(intro_path),
            "pinned": True,
        })
    for fn in sorted(os.listdir(MUSIC_DIR)):
        full = os.path.join(MUSIC_DIR, fn)
        if not os.path.isfile(full):
            continue
        ext = os.path.splitext(fn)[1].lower()
        if ext not in ALLOWED_AUDIO:
            continue
        items.append({
            "name": os.path.splitext(fn)[0],
            "filename": fn,
            "url": f"/assets/music/{fn}",
            "size": os.path.getsize(full),
        })
    return jsonify({"items": items})


@app.route("/api/music/upload", methods=["POST"])
def api_music_upload():
    if "files" not in request.files and "file" not in request.files:
        return jsonify({"ok": False, "error": "no file"}), 400
    files = request.files.getlist("files") if "files" in request.files else [request.files["file"]]
    saved = []
    skipped = []
    for f in files:
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_AUDIO:
            skipped.append(f.filename)
            continue
        safe = secure_filename(f.filename) or f"track_{int(time.time())}{ext}"
        dest = os.path.join(MUSIC_DIR, safe)
        # avoid overwriting
        if os.path.exists(dest):
            base, e = os.path.splitext(safe)
            safe = f"{base}_{int(time.time())}{e}"
            dest = os.path.join(MUSIC_DIR, safe)
        f.save(dest)
        saved.append(safe)
    return jsonify({"ok": True, "saved": saved, "skipped": skipped})


@app.route("/api/analyze_file", methods=["POST"])
def api_analyze_file():
    """Receive a dropped file and have Vega analyze it.
    Supported: PDF, txt, md, csv, images (jpg/png/gif)."""
    import tempfile
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "no file"}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "empty"}), 400
    safe = secure_filename(f.filename) or "dropped"
    ext = os.path.splitext(safe)[1].lower()

    target_dir = os.path.join(tempfile.gettempdir(), "vega_drops")
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, safe)
    f.save(target)

    # Build a command for the engine based on file type
    if ext == ".pdf":
        cmd = f"Leggi e riassumi il PDF a questo percorso: {target}"
    elif ext in {".txt", ".md", ".markdown", ".log", ".csv"}:
        # Read text and pass content
        try:
            content = open(target, "r", encoding="utf-8", errors="replace").read()[:5000]
        except Exception:
            content = ""
        cmd = f"Analizza e riassumi questo testo (file {safe}):\n\n{content}"
    elif ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
        # Use vision tool to actually SEE the image
        cmd = (f"Analizza questa immagine usando il tool analyze_image con "
               f"path='{target}'. Descrivi cosa contiene in italiano. "
               f"Se l'utente ha aggiunto domande, rispondile.")
    else:
        cmd = f"Ho ricevuto un file ({safe}, tipo {ext}). Tipo non supportato per analisi diretta. Salvato in {target}."

    engine.text_input(cmd)
    return jsonify({"ok": True, "filename": safe, "path": target})


@app.route("/api/music/delete", methods=["POST"])
def api_music_delete():
    data = request.get_json(force=True) or {}
    fn = data.get("filename", "")
    if not fn:
        return jsonify({"ok": False, "error": "no filename"}), 400
    if fn == "__intro__":
        return jsonify({"ok": False, "error": "Brano predefinito non eliminabile"}), 403
    safe = secure_filename(fn)
    target = os.path.join(MUSIC_DIR, safe)
    if os.path.exists(target) and os.path.isfile(target):
        try:
            os.unlink(target)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": False, "error": "not found"}), 404


# ---- WebSocket ----
@sock.route("/ws")
def ws_handler(ws):
    global _last_client_time
    with _clients_lock:
        _clients.append(ws)
        _last_client_time = time.time()
    try:
        ws.send(json.dumps({"event": "state", "payload": {"state": engine.state}}))
        ws.send(json.dumps({"event": "vega_active", "payload": {"active": engine.is_active()}}))
        import ws_guard
        while True:
            msg = ws.receive()
            if msg is None:
                break
            try:
                data = json.loads(msg)
                # Replay protection (opt-in: if client sends nonce+ts envelope)
                is_replay, reason = ws_guard.is_replay(data)
                if is_replay:
                    try:
                        import audit_log
                        audit_log.log("ws.replay_blocked", {"reason": reason})
                    except Exception:
                        pass
                    continue
                if data.get("event") == "text_input":
                    engine.text_input(data["payload"]["text"])
                elif data.get("event") == "interrupt":
                    engine.interrupt()
                elif data.get("event") == "wake":
                    engine.request_wake()
            except Exception:
                pass
    finally:
        with _clients_lock:
            if ws in _clients:
                _clients.remove(ws)
            _last_client_time = time.time()


def _ui_file_watcher():
    """Poll ui/ directory for file changes. When detected, broadcast a
    'reload' WS event so all connected browsers refresh automatically.
    Pure stdlib - no watchdog dependency needed."""
    import glob as _glob
    mtimes = {}
    exts = (".html", ".css", ".js")
    # Initialize baseline (don't reload on the first scan)
    for path in _glob.glob(os.path.join(UI_DIR, "**", "*"), recursive=True):
        if os.path.isfile(path) and path.endswith(exts):
            try:
                mtimes[path] = os.path.getmtime(path)
            except OSError:
                pass
    while True:
        time.sleep(2)
        try:
            for path in _glob.glob(os.path.join(UI_DIR, "**", "*"), recursive=True):
                if not os.path.isfile(path) or not path.endswith(exts):
                    continue
                try:
                    mt = os.path.getmtime(path)
                except OSError:
                    continue
                prev = mtimes.get(path)
                mtimes[path] = mt
                if prev is not None and mt > prev + 0.1:
                    fname = os.path.basename(path)
                    print(f"[hot-reload] {fname} changed, broadcasting reload")
                    broadcast("reload", {"file": fname})
                    break  # one reload per cycle
        except Exception:
            pass


def _shutdown_watcher():
    """Auto-shutdown if no browser client connected for NO_CLIENT_SHUTDOWN_SEC.
    Closes the ghost server when user closes the browser window."""
    global _last_client_time
    while True:
        time.sleep(15)
        with _clients_lock:
            connected = len(_clients)
            elapsed = time.time() - _last_client_time
        if connected == 0 and elapsed > NO_CLIENT_SHUTDOWN_SEC:
            print(f"[Browser chiuso da {int(elapsed)}s, spengo Vega.]")
            try:
                engine.interrupt()
                engine.stop()
            except Exception:
                pass
            os._exit(0)


def setup_global_hotkey():
    try:
        import keyboard
        keyboard.add_hotkey("ctrl+alt+j", lambda: engine.request_wake())
        keyboard.add_hotkey("ctrl+alt+space", lambda: engine.request_wake())
        def _toggle_pause():
            if engine.is_active():
                engine.pause_vega()
            else:
                engine.resume_vega()
        keyboard.add_hotkey("ctrl+alt+m", _toggle_pause)
    except Exception as e:
        print(f"[Hotkey not available: {e}]")


def launch_browser():
    url = f"http://localhost:{PORT}"
    edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    for exe in (chrome, edge):
        if os.path.exists(exe):
            subprocess.Popen([
                exe,
                f"--app={url}",
                "--start-fullscreen",
                "--window-size=1920,1080",
                "--disable-features=TranslateUI",
            ])
            return
    webbrowser.open(url)


# ---- Single instance lock ----
def _ensure_single_instance():
    lock_file = os.path.join(ROOT, ".vega.lock")
    if os.path.exists(lock_file):
        try:
            with open(lock_file, "r") as f:
                old_pid = int(f.read().strip())
            import psutil
            if psutil.pid_exists(old_pid):
                proc = psutil.Process(old_pid)
                try:
                    cmdline = " ".join(proc.cmdline()).lower()
                except Exception:
                    cmdline = ""
                # only refuse to start if it's truly OUR server (not just any python)
                if "server.py" in cmdline and "vega" in cmdline:
                    print(f"[Vega gia' in esecuzione (PID {old_pid}). Esco.]")
                    sys.exit(0)
        except Exception:
            pass
    try:
        with open(lock_file, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

    import atexit
    @atexit.register
    def _cleanup_lock():
        try:
            if os.path.exists(lock_file):
                with open(lock_file, "r") as f:
                    pid = int(f.read().strip())
                if pid == os.getpid():
                    os.unlink(lock_file)
        except Exception:
            pass


def _init_new_architecture_async():
    """Initialize new layers in a BACKGROUND thread.
    The server starts serving HTTP immediately; new features become available
    progressively as their init completes. Stuck initializations never block
    the main loop."""
    def _bg():
        try:
            import bus as _bus
            _bus.publish("system.boot", {"stage": "init"}, persist=True)

            # Light tasks first (no I/O heavy)
            try:
                import task_queue, task_dispatch
                task_queue.start_workers(task_dispatch.dispatch, n=2)
            except Exception as e:
                print(f"[init] task_queue error: {e}")

            # Capabilities: auto-register is fast IF we batch save
            try:
                import capabilities as _cap
                _cap.auto_register_from_tools()
                # Warm up index in a separate thread (sentence-transformers load is heavy)
                threading.Thread(target=_cap.warm_up, daemon=True).start()
            except Exception as e:
                print(f"[init] capabilities error: {e}")

            # Memory graph migration (also runs sentence-transformers first time)
            # NOT blocking: pure async
            def _migrate_mem():
                try:
                    import memory_graph
                    memory_graph.migrate_from_json_if_needed()
                except Exception as e:
                    print(f"[init] memory_graph migrate error: {e}")
            threading.Thread(target=_migrate_mem, daemon=True).start()

            # Desktop intelligence (opt-in)
            try:
                import desktop_observer as di
                if memory.get_preferences().get("desktop_intelligence", False):
                    di.start()
            except Exception as e:
                print(f"[init] desktop_observer error: {e}")

            # Proactive layer: pattern suggestions + daily briefing
            try:
                import proactive
                proactive.start()
            except Exception as e:
                print(f"[init] proactive error: {e}")

            # Self-healing: analizza errori ricorrenti e propone fix
            try:
                import self_healing
                self_healing.start()
            except Exception as e:
                print(f"[init] self_healing error: {e}")

            # Shared embedder pre-warm (1 model loaded once, used by all)
            try:
                import shared_embedder
                shared_embedder.warm_up_async()
            except Exception as e:
                print(f"[init] shared_embedder error: {e}")

            # Episodic memory (Mem0): warm-up in background
            try:
                import episodic_memory
                episodic_memory.warm_up()
            except Exception as e:
                print(f"[init] episodic_memory error: {e}")

            # News RAG: continuous RSS ingestion
            try:
                import news_graph
                news_graph.start()
            except Exception as e:
                print(f"[init] news_graph error: {e}")

            # Net guard: outbound logging (observe mode by default, opt-in strict)
            try:
                import net_guard
                net_guard.install()
            except Exception as e:
                print(f"[init] net_guard error: {e}")

            # Audit log: subscribe to security-sensitive bus events
            try:
                import audit_log
                audit_log.start()
            except Exception as e:
                print(f"[init] audit_log error: {e}")

            # Honeypot canaries (seed once)
            try:
                import honeypot
                honeypot.seed_if_first_boot()
            except Exception as e:
                print(f"[init] honeypot error: {e}")

            # CVE scanner: opt-in, async, runs once a week
            try:
                if memory.get_preferences().get("cve_scan_at_boot", True):
                    import cve_scanner
                    cve_scanner.scan_async_at_boot(interval_days=7)
            except Exception as e:
                print(f"[init] cve_scanner error: {e}")

            # Team agents (Tier 0-3): boot in background
            try:
                from agents import team_registry
                team_registry._load_all()
                # Forward team.message bus events to WS for live UI
                import bus as _bus
                def _forward_team_msg(evt):
                    try:
                        broadcast("team_message", evt.get("payload", {}))
                    except Exception:
                        pass
                _bus.subscribe("team.message", _forward_team_msg)
                # Also forward agent_progress already forwarded earlier;
                # the cards from agents go via 'card' topic which is also forwarded.
                def _forward_card(evt):
                    try:
                        broadcast("card", evt.get("payload", {}))
                    except Exception:
                        pass
                _bus.subscribe("card", _forward_card)
            except Exception as e:
                print(f"[init] team agents error: {e}")

            _bus.publish("system.boot", {"stage": "done"}, persist=True)
        except Exception as e:
            print(f"[init] fatal: {e}")

    threading.Thread(target=_bg, daemon=True).start()


if __name__ == "__main__":
    _ensure_single_instance()
    _init_new_architecture_async()
    # Browser is launched by Vega.vbs BEFORE Python imports finish,
    # so user sees the loading page within ~1s of double-click.
    # Only launch_browser ourselves if running standalone (e.g. Vega.bat).
    import sys as _sys
    if _sys.stdout.isatty():
        threading.Timer(1.5, launch_browser).start()
    threading.Thread(target=setup_global_hotkey, daemon=True).start()
    threading.Thread(target=_shutdown_watcher, daemon=True).start()
    threading.Thread(target=_ui_file_watcher, daemon=True).start()
    # Auto-extract facts from conversations every 30 min
    try:
        import fact_extractor
        _fact_stop = threading.Event()
        threading.Thread(
            target=fact_extractor.background_loop,
            args=(_fact_stop,), daemon=True,
        ).start()
    except Exception:
        pass
    # Backup automatico settimanale
    try:
        import backup
        _backup_stop = threading.Event()
        threading.Thread(
            target=backup.background_loop, args=(_backup_stop,), daemon=True,
        ).start()
    except Exception as _e:
        print(f"[backup] startup error: {_e}")
    # Automations scheduler
    try:
        import automations
        automations.set_executor(
            lambda cmd, mode, name: engine.run_automation_command(cmd, mode, name),
            engine,
        )
        _auto_stop = threading.Event()
        threading.Thread(
            target=automations.background_loop,
            args=(_auto_stop,), daemon=True,
        ).start()
    except Exception as _e:
        print(f"[automations] startup error: {_e}")
    engine.start()
    # Bind on all interfaces so you can reach Vega from your phone on LAN
    # (http://<PC-LAN-IP>:5252)
    # TLS opt-in: enable with VEGA_TLS=1 env var or prefs.tls_enabled
    _ssl_ctx = None
    try:
        _tls_on = (os.environ.get("VEGA_TLS") == "1"
                   or memory.get_preferences().get("tls_enabled", False))
        if _tls_on:
            import tls_setup
            _ssl_ctx = tls_setup.get_ssl_context()
            print(f"[server] TLS enabled (self-signed). Download cert at https://<host>:{PORT}/-/cert")
    except Exception as _e:
        print(f"[server] TLS setup failed, falling back to HTTP: {_e}")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False,
            ssl_context=_ssl_ctx)
