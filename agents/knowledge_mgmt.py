"""Knowledge Manager — SOP, lessons learned, post-mortem progetti."""
import json
import time
from datetime import date
from pathlib import Path

from .team_base import TeamAgent


ROOT = Path(__file__).parent.parent
SOP_DIR = ROOT / "data" / "knowledge_base"
SOP_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in s.lower())[:60]


def save_sop(title: str, content: str, tags: list = None) -> dict:
    slug = _slugify(title)
    path = SOP_DIR / f"sop_{slug}.md"
    md = f"# {title}\n\nCreato: {date.today().isoformat()}\nTag: {', '.join(tags or [])}\n\n{content}"
    path.write_text(md, encoding="utf-8")
    return {"title": title, "path": str(path), "size": len(md)}


def save_post_mortem(project: str, content: dict) -> dict:
    slug = _slugify(project)
    path = SOP_DIR / f"pm_{slug}_{date.today().isoformat()}.md"
    md = (
        f"# Post-Mortem Progetto: {project}\n\n"
        f"Data: {date.today().isoformat()}\n\n"
        f"## Cosa è andato bene\n{content.get('what_worked', '_da compilare_')}\n\n"
        f"## Cosa è andato male\n{content.get('what_didnt', '_da compilare_')}\n\n"
        f"## Lessons learned\n{content.get('lessons', '_da compilare_')}\n\n"
        f"## Action items\n{content.get('actions', '_da compilare_')}\n"
    )
    path.write_text(md, encoding="utf-8")
    return {"project": project, "path": str(path)}


def list_kb() -> list:
    out = []
    for p in sorted(SOP_DIR.glob("*.md")):
        out.append({"file": p.name,
                     "title": p.stem.replace("sop_", "").replace("pm_", "")
                                .replace("_", " ").title(),
                     "size": p.stat().st_size,
                     "modified": int(p.stat().st_mtime)})
    return out


def read_kb(filename: str) -> str:
    p = SOP_DIR / filename
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")[:5000]


class KnowledgeMgmtAgent(TeamAgent):
    name = "knowledge_mgmt"
    tier = 2
    icon = "📚"
    description = "SOP, post-mortem, lessons learned, KB ricercabile"
    model_pref = "haiku"
    schedule = "weekly Sunday 19:00"
    subscribes = []

    def run(self, payload):
        payload = payload or {}
        op = payload.get("op", "weekly_review")

        if op == "weekly_review":
            # Use Haiku to suggest 1 new SOP based on recent activity
            mems = self.search_memory("procedura cliente fatturazione", top_k=10)
            mem_text = "\n".join(f"- {m.get('content', '')[:120]}"
                                    for m in mems[:5])
            prompt = (
                f"Sulla base di queste attività recenti:\n{mem_text}\n\n"
                f"Suggerisci UNA SOP (Standard Operating Procedure) che "
                f"potrebbe essere documentata per ridurre lavoro ripetitivo. "
                f"Output JSON: {{'title': '...', 'rationale': '...', "
                f"'sketch': '...'}}"
            )
            sugg = self.call_haiku_json(prompt)
            if sugg and sugg.get("title"):
                self.remember("instruction",
                    f"Suggerimento SOP: {sugg.get('title')}. "
                    f"Razionale: {sugg.get('rationale', '')[:200]}",
                    importance=0.6, tags=["knowledge", "sop_suggestion"])
            return {"ok": True, "sop_suggested": sugg.get("title", "")
                    if sugg else None}

        if op == "save_sop":
            return {"ok": True, "result": save_sop(
                payload.get("title", "SOP"),
                payload.get("content", ""),
                payload.get("tags", []))}

        if op == "post_mortem":
            return {"ok": True, "result": save_post_mortem(
                payload.get("project", "Progetto"),
                payload.get("content", {}))}

        if op == "list":
            return {"ok": True, "kb": list_kb()}

        if op == "read":
            return {"ok": True, "content": read_kb(payload.get("file", ""))}

        if op == "month_lessons":
            # Workflow hook
            return {"ok": True, "note": "month lessons triggered"}

        return {"ok": False, "error": f"op sconosciuta: {op}",
                "available_ops": ["weekly_review", "save_sop", "post_mortem",
                                    "list", "read", "month_lessons"]}


AGENT = KnowledgeMgmtAgent()
