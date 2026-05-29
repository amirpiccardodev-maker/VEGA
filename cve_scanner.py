"""CVE / vulnerability scanner via pip-audit.

Runs pip-audit on the current venv, parses JSON output, and:
  - publishes 'cve.detected' bus event for each finding
  - emits UI card 'security_cve' if there are CRITICAL/HIGH severity
  - caches last result in data/cve_report.json
  - exposed via /api/security/cve_scan (manual) and run async at boot

Settings:
  - prefs.cve_scan_at_boot: bool (default True)
  - prefs.cve_scan_interval_days: int (default 7) — re-scan on next boot if older
"""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import bus


ROOT = Path(__file__).parent
REPORT_FILE = ROOT / "data" / "cve_report.json"
REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)

SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}


def _run_pip_audit(timeout_sec: int = 180) -> dict:
    """Invoke pip-audit JSON output. Returns parsed dict or {error}."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--format", "json", "--progress-spinner", "off"],
            capture_output=True, text=True, timeout=timeout_sec, encoding="utf-8",
            errors="replace",
        )
        if proc.returncode not in (0, 1):  # 1 = vulnerabilities found
            return {"error": proc.stderr[:500] or f"exit={proc.returncode}"}
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {"error": "pip-audit non-JSON output", "raw": proc.stdout[:300]}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except FileNotFoundError:
        return {"error": "pip-audit non installato"}
    except Exception as e:
        return {"error": str(e)}


def _parse_findings(raw: dict) -> list:
    """Normalize pip-audit output -> [{package, version, id, severity, fix}]."""
    findings = []
    for dep in raw.get("dependencies", []):
        name = dep.get("name", "?")
        version = dep.get("version", "?")
        for vuln in dep.get("vulns", []):
            findings.append({
                "package": name,
                "version": version,
                "id": vuln.get("id", "?"),
                "description": (vuln.get("description") or "")[:300],
                "severity": _guess_severity(vuln),
                "fix_versions": vuln.get("fix_versions", []),
                "aliases": vuln.get("aliases", []),
            })
    findings.sort(key=lambda f: -SEVERITY_ORDER.get(f["severity"], 0))
    return findings


def _guess_severity(vuln: dict) -> str:
    """pip-audit doesn't always include severity; guess from id/description."""
    aliases = vuln.get("aliases", [])
    desc = (vuln.get("description") or "").lower()
    for tag in ("critical", "high", "medium", "low"):
        if tag in desc[:200]:
            return tag.upper()
    # CVE database: rough heuristic
    if any("CRITICAL" in a for a in aliases):
        return "CRITICAL"
    return "UNKNOWN"


def scan_now() -> dict:
    """Run a scan synchronously. Returns the report."""
    started = time.time()
    bus.publish("cve.scan_started", {})
    raw = _run_pip_audit()
    if raw.get("error"):
        report = {"ok": False, "error": raw["error"], "ts": int(started)}
        _save_report(report)
        return report
    findings = _parse_findings(raw)
    report = {
        "ok": True,
        "ts": int(started),
        "duration_sec": round(time.time() - started, 1),
        "total": len(findings),
        "by_severity": _count_by_severity(findings),
        "findings": findings[:50],  # cap to top 50
    }
    _save_report(report)

    # Alert on critical/high
    critical = [f for f in findings if f["severity"] in ("CRITICAL", "HIGH")]
    if critical:
        bus.publish("cve.detected", {
            "count": len(critical),
            "samples": [f["id"] + " " + f["package"] for f in critical[:5]],
        })
        # Emit UI card
        try:
            bus.publish("card", {
                "type": "security_cve",
                "data": {
                    "title": f"⚠️ {len(critical)} vulnerabilità critiche/high rilevate",
                    "summary": ", ".join(f["package"] for f in critical[:5]),
                    "findings": critical[:10],
                    "total": len(findings),
                },
            })
        except Exception:
            pass
        try:
            import audit_log
            audit_log.log("cve.detected", {
                "critical_count": len(critical),
                "total": len(findings),
            })
        except Exception:
            pass
    bus.publish("cve.scan_finished", {"total": len(findings)})
    return report


def _count_by_severity(findings: list) -> dict:
    out = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}
    for f in findings:
        sev = f.get("severity", "UNKNOWN")
        if sev in out:
            out[sev] += 1
    return out


def _save_report(report: dict):
    try:
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def last_report() -> dict:
    if not REPORT_FILE.exists():
        return {"never_scanned": True}
    try:
        with open(REPORT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"error": "report corrotto"}


def scan_async_at_boot(interval_days: int = 7):
    """Run a scan on a background thread if the last one is older than interval_days."""
    def _bg():
        try:
            last = last_report()
            now = int(time.time())
            if last and not last.get("never_scanned"):
                age = now - last.get("ts", 0)
                if age < interval_days * 86400:
                    return
            scan_now()
        except Exception as e:
            bus.publish("error.occurred", {"source": "cve_scanner", "error": str(e)})
    # Delay 60s to not interfere with boot
    threading.Timer(60.0, _bg).start()
