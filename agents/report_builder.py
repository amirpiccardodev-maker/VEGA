"""Report Builder — genera report cliente in markdown + export Word/PDF."""
import json
import time
from datetime import date
from pathlib import Path

from .team_base import TeamAgent


ROOT = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "data" / "client_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


TEMPLATES = {
    "weekly": (
        "# Report Settimanale — {client}\n"
        "**Periodo**: {period}\n\n"
        "## Sintesi esecutiva\n{summary}\n\n"
        "## Attività svolte\n{activities}\n\n"
        "## Prossimi passi\n{next_steps}\n\n"
        "## KPI\n{kpis}\n"
    ),
    "monthly": (
        "# Report Mensile — {client}\n"
        "**Periodo**: {period}\n\n"
        "## Highlights\n{highlights}\n\n"
        "## Risultati raggiunti\n{results}\n\n"
        "## Sfide e mitigazioni\n{challenges}\n\n"
        "## Roadmap mese successivo\n{roadmap}\n\n"
        "## KPI dashboard\n{kpis}\n"
    ),
    "project_final": (
        "# Report Finale Progetto — {client}\n"
        "**Progetto**: {project}\n"
        "**Periodo**: {period}\n\n"
        "## Obiettivi vs Risultati\n{objectives_vs_results}\n\n"
        "## Deliverable consegnati\n{deliverables}\n\n"
        "## Lessons learned\n{lessons}\n\n"
        "## Raccomandazioni\n{recommendations}\n"
    ),
}


def _gather_memory_for(client: str, period_days: int = 7) -> list:
    """Cerca memorie correlate al cliente nell'ultimo periodo."""
    try:
        import memory_graph as mg
        results = mg.search(client, top_k=20, min_similarity=0.30)
        # Filter recent
        cutoff = time.time() - (period_days * 86400)
        return [r for r in results
                if (r.get("created_at") or 0) >= cutoff]
    except Exception:
        return []


class ReportBuilderAgent(TeamAgent):
    name = "report_builder"
    tier = 2
    icon = "📑"
    description = "Genera report cliente weekly/monthly/final da template"
    model_pref = "haiku"
    schedule = "weekly Friday 17:00"
    subscribes = []

    def _fill_with_llm(self, template_key: str, client: str,
                         memories: list, extra: dict) -> str:
        """Use Haiku to fill template fields based on memories."""
        mem_text = "\n".join(f"- [{m.get('kind')}] {m.get('content', '')[:200]}"
                                for m in memories[:15])
        prompt = (
            f"Genera contenuto per un report {template_key} su cliente {client}.\n"
            f"Dati disponibili dalla memoria:\n{mem_text}\n\n"
            f"Output: SOLO JSON con le seguenti chiavi: "
            f"{list(self._fields_for(template_key))}. "
            f"Ogni valore: max 300 caratteri, in italiano, professional but readable."
        )
        result = self.call_haiku_json(prompt)
        if not isinstance(result, dict):
            result = {}
        # Defaults
        for field in self._fields_for(template_key):
            result.setdefault(field, "_da compilare_")
        # Add fixed fields
        result["client"] = client
        result["period"] = extra.get("period",
            f"{date.today().strftime('%d %B %Y')}")
        result.update({k: v for k, v in extra.items()
                        if k not in result})
        return TEMPLATES[template_key].format(**result)

    def _fields_for(self, template_key: str) -> list:
        if template_key == "weekly":
            return ["summary", "activities", "next_steps", "kpis"]
        if template_key == "monthly":
            return ["highlights", "results", "challenges", "roadmap", "kpis"]
        if template_key == "project_final":
            return ["objectives_vs_results", "deliverables",
                    "lessons", "recommendations", "project"]
        return []

    def _save_report(self, client: str, kind: str, content: str) -> str:
        fname = (f"{client.lower().replace(' ', '_')}_"
                 f"{kind}_{date.today().isoformat()}.md")
        path = REPORTS_DIR / fname
        path.write_text(content, encoding="utf-8")
        return str(path)

    def run(self, payload):
        payload = payload or {}
        op = payload.get("op", "weekly_reports")

        if op == "weekly_reports":
            # Genera weekly per ogni cliente attivo
            try:
                from . import client_onboarding
                clients = client_onboarding.list_clients(status="active")
            except Exception:
                clients = []
            if not clients:
                # Fallback: cerca clienti dalla memoria
                try:
                    import memory_graph as mg
                    res = mg.search("cliente", kinds=["fact"], top_k=10)
                    clients = [{"name": r.get("content", "")[:40]}
                                for r in res]
                except Exception:
                    clients = []
            generated = []
            for c in clients[:5]:
                name = c.get("name", "")
                if not name:
                    continue
                mems = _gather_memory_for(name, period_days=7)
                content = self._fill_with_llm("weekly", name, mems, {})
                path = self._save_report(name, "weekly", content)
                generated.append({"client": name, "path": path,
                                    "size": len(content)})
                self._emit("report_generated", {"client": name, "kind": "weekly"})
            return {"ok": True, "generated": generated}

        if op == "monthly_reports":
            try:
                from . import client_onboarding
                clients = client_onboarding.list_clients(status="active")
            except Exception:
                clients = []
            generated = []
            for c in clients[:10]:
                name = c.get("name", "")
                if not name:
                    continue
                mems = _gather_memory_for(name, period_days=30)
                content = self._fill_with_llm("monthly", name, mems, {})
                path = self._save_report(name, "monthly", content)
                generated.append({"client": name, "path": path})
            return {"ok": True, "generated": generated}

        if op == "final_report":
            client = payload.get("client", "")
            project = payload.get("project", "")
            if not client:
                return {"ok": False, "error": "client richiesto"}
            mems = _gather_memory_for(client, period_days=180)
            content = self._fill_with_llm("project_final", client, mems,
                                            {"project": project})
            path = self._save_report(client, "final", content)
            return {"ok": True, "client": client, "path": path}

        if op == "list_reports":
            files = sorted(REPORTS_DIR.glob("*.md"), reverse=True)
            return {"ok": True, "reports":
                [{"file": f.name, "size": f.stat().st_size,
                   "modified": int(f.stat().st_mtime)}
                 for f in files[:30]]}

        if op == "read_report":
            fname = payload.get("file", "")
            path = REPORTS_DIR / fname
            if not path.exists():
                return {"ok": False, "error": "report non trovato"}
            return {"ok": True, "content": path.read_text(encoding="utf-8")[:3000]}

        return {"ok": False, "error": f"op sconosciuta: {op}",
                "available_ops": ["weekly_reports", "monthly_reports",
                                    "final_report", "list_reports", "read_report"]}


AGENT = ReportBuilderAgent()
