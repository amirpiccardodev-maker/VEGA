"""Reading mode: load a PDF/text/docx file and read it aloud in chunks.

Saves a 'bookmark' in memory so you can resume across sessions.
The engine reads chunks one at a time, signaling progress.
"""
import os
import re
from pathlib import Path

import memory

TOOLS = [
    {"name": "reading_open",
     "description": "Apre un file (PDF/txt/md/docx) per la lettura ad alta voce. Mostra la lunghezza e parte la lettura dal segnalibro salvato.",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string"},
         "start_from_beginning": {"type": "boolean", "description": "Se true, ignora il bookmark"},
     }, "required": ["path"]}},
    {"name": "reading_continue",
     "description": "Riprende la lettura del documento attualmente aperto, dal segnalibro.",
     "input_schema": {"type": "object", "properties": {
         "chunks": {"type": "integer", "description": "Numero di paragrafi da leggere (default 1)"},
     }}},
    {"name": "reading_status",
     "description": "Mostra lo stato della lettura corrente (file, progresso).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "reading_stop",
     "description": "Termina la sessione di lettura.",
     "input_schema": {"type": "object", "properties": {}}},
]


def _load_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    ext = p.suffix.lower()
    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            r = PdfReader(str(p))
            return "\n\n".join((page.extract_text() or "") for page in r.pages)
        if ext == ".docx":
            import docx
            d = docx.Document(str(p))
            return "\n\n".join(par.text for par in d.paragraphs)
        # txt, md, etc.
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return ""


def _chunks(text: str):
    """Split text into paragraphs (or sentence groups) for streaming reads."""
    # First split into paragraphs
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    # For long paragraphs, split into sentence groups of ~600 chars
    out = []
    for p in paragraphs:
        if len(p) <= 600:
            out.append(p)
        else:
            sentences = re.split(r"(?<=[\.\!\?])\s+", p)
            buf = ""
            for s in sentences:
                if len(buf) + len(s) <= 600:
                    buf = (buf + " " + s).strip()
                else:
                    if buf: out.append(buf)
                    buf = s
            if buf: out.append(buf)
    return out


def _state():
    return memory.get_all().get("reading_state", {})


def _save_state(state):
    def m(d):
        d["reading_state"] = state
    memory.update(m)


def run(name, args):
    if name == "reading_open":
        path = args.get("path", "").strip()
        if not os.path.exists(path):
            return f"File non trovato: {path}"
        text = _load_text(path)
        if not text:
            return "File vuoto o illeggibile."
        chunks = _chunks(text)
        existing = _state()
        bookmark = 0
        if not args.get("start_from_beginning") and existing.get("path") == path:
            bookmark = existing.get("position", 0)
        new_state = {"path": path, "total_chunks": len(chunks),
                     "position": bookmark, "title": os.path.basename(path)}
        _save_state(new_state)
        if bookmark > 0:
            return (f"Apro {new_state['title']}: {len(chunks)} paragrafi totali. "
                    f"Riprendo dal segnalibro (paragrafo {bookmark+1}). "
                    f"Di' 'continua a leggere' per la prossima parte.")
        return (f"Apro {new_state['title']}: {len(chunks)} paragrafi totali. "
                f"Di' 'continua a leggere' per iniziare.")

    if name == "reading_continue":
        st = _state()
        if not st.get("path"):
            return "Nessun documento aperto. Usa reading_open prima."
        path = st["path"]
        text = _load_text(path)
        chunks = _chunks(text)
        pos = st.get("position", 0)
        n = max(1, min(int(args.get("chunks", 1)), 3))
        if pos >= len(chunks):
            return "Hai finito di leggere il documento. Bravo!"
        out_chunks = chunks[pos:pos + n]
        new_pos = pos + n
        st["position"] = new_pos
        _save_state(st)
        progress = int(new_pos / len(chunks) * 100)
        header = f"[Lettura {progress}%]"
        return header + "\n\n" + "\n\n".join(out_chunks)

    if name == "reading_status":
        st = _state()
        if not st.get("path"):
            return "Nessuna lettura in corso."
        progress = int(st.get("position", 0) / max(1, st.get("total_chunks", 1)) * 100)
        return f"Sto leggendo: {st.get('title')}\nProgresso: paragrafo {st.get('position')}/{st.get('total_chunks')} ({progress}%)"

    if name == "reading_stop":
        _save_state({})
        return "Sessione di lettura terminata."

    return "?"
