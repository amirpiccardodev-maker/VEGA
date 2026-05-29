"""RAG (Retrieval-Augmented Generation) su documenti personali.

Indicizza file in docs/ (PDF, txt, md, docx) usando sentence-transformers
(modello multilingual italiano-friendly, ~120MB, offline).
Le query trovano i passaggi piu' rilevanti e li restituiscono per Claude.

Workflow tipico:
  1. Utente: "indicizza i miei documenti"
  -> index_docs() scansiona docs/ e crea embeddings
  2. Utente: "quanto pago di affitto?"
  -> search_docs("quanto pago di affitto") trova passaggi del contratto
  3. Claude legge i passaggi e risponde con la cifra giusta.
"""
import os
import json
import re
import time
from pathlib import Path

from tools._shared import emit_card

ROOT = Path(__file__).parent.parent
DOCS_DIR = ROOT / "docs"
INDEX_FILE = ROOT / "docs_index.npz"
META_FILE = ROOT / "docs_index_meta.json"

DOCS_DIR.mkdir(exist_ok=True)

# Lazy globals: only load model when first needed
_MODEL = None
_EMBEDDINGS = None  # numpy array
_CHUNKS = None      # list of dicts {file, page, text}

# Embedding model: multilingual, lightweight (~120MB), runs on CPU
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


TOOLS = [
    {"name": "index_docs",
     "description": "Indicizza i file della cartella docs/ (PDF, txt, md) per ricerche semantiche. Da eseguire ogni volta che aggiungi/modifichi documenti.",
     "input_schema": {"type": "object", "properties": {"force": {"type": "boolean"}}}},
    {"name": "search_docs",
     "description": "Cerca semanticamente nei documenti personali indicizzati e restituisce i passaggi piu' rilevanti. Usalo quando l'utente chiede informazioni che potrebbero essere nei suoi PDF/note (contratti, manuali, ricette, libri, appunti).",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string"},
         "top_k": {"type": "integer", "description": "Numero passaggi (default 5)"},
     }, "required": ["query"]}},
    {"name": "list_docs",
     "description": "Elenca i documenti attualmente nella cartella docs/.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "clear_docs_index",
     "description": "Cancella l'indice dei documenti (non i file).",
     "input_schema": {"type": "object", "properties": {}}},
]


def _get_model():
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer(MODEL_NAME)
    return _MODEL


def _read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    try:
        if suffix in {".txt", ".md", ".markdown", ".log", ".csv"}:
            return path.read_text(encoding="utf-8", errors="replace")
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError:
                return ""
            reader = PdfReader(str(path))
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        if suffix == ".docx":
            try:
                import docx
            except ImportError:
                return ""
            d = docx.Document(str(path))
            return "\n".join(p.text for p in d.paragraphs)
    except Exception:
        return ""
    return ""


def _chunk_text(text: str, max_chars: int = 800, overlap: int = 100):
    """Split text into overlapping chunks suitable for embedding."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return []
    chunks = []
    # First try paragraph splits
    paragraphs = re.split(r"\n\s*\n", text)
    buf = ""
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if len(buf) + len(p) + 1 <= max_chars:
            buf = (buf + "\n" + p) if buf else p
        else:
            if buf:
                chunks.append(buf)
            if len(p) > max_chars:
                # break long paragraph into windows
                for i in range(0, len(p), max_chars - overlap):
                    chunks.append(p[i:i + max_chars])
                buf = ""
            else:
                buf = p
    if buf:
        chunks.append(buf)
    return chunks


def _save_index(embeddings, chunks):
    import numpy as np
    np.savez_compressed(INDEX_FILE, embeddings=embeddings)
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump({"chunks": chunks, "created": time.time(), "model": MODEL_NAME}, f, ensure_ascii=False)


def _load_index():
    global _EMBEDDINGS, _CHUNKS
    if _EMBEDDINGS is not None:
        return True
    if not INDEX_FILE.exists() or not META_FILE.exists():
        return False
    try:
        import numpy as np
        with np.load(INDEX_FILE) as data:
            _EMBEDDINGS = data["embeddings"]
        with open(META_FILE, "r", encoding="utf-8") as f:
            meta = json.load(f)
        _CHUNKS = meta["chunks"]
        return True
    except Exception:
        return False


def _index_all(force: bool = False):
    global _EMBEDDINGS, _CHUNKS
    files = sorted([p for p in DOCS_DIR.iterdir() if p.is_file()
                    and p.suffix.lower() in {".pdf", ".txt", ".md", ".markdown", ".docx", ".csv", ".log"}])
    if not files:
        return "Nessun file in docs/. Mettici PDF, txt o markdown e riprova."

    if not force and INDEX_FILE.exists() and META_FILE.exists():
        # Check if any file is newer than index
        idx_mtime = INDEX_FILE.stat().st_mtime
        if all(f.stat().st_mtime < idx_mtime for f in files):
            _load_index()
            return f"Indice gia' aggiornato ({len(_CHUNKS) if _CHUNKS else 0} passaggi, {len(files)} documenti)."

    chunks_meta = []
    texts = []
    for f in files:
        text = _read_text(f)
        if not text:
            continue
        for chunk in _chunk_text(text):
            chunks_meta.append({"file": f.name, "text": chunk})
            texts.append(chunk)

    if not texts:
        return "Documenti illeggibili o vuoti."

    model = _get_model()
    import numpy as np
    embeddings = model.encode(texts, batch_size=32, show_progress_bar=False,
                              normalize_embeddings=True)
    embeddings = np.asarray(embeddings, dtype=np.float32)
    _save_index(embeddings, chunks_meta)
    _EMBEDDINGS = embeddings
    _CHUNKS = chunks_meta
    return f"Indicizzati {len(files)} documenti in {len(chunks_meta)} passaggi."


def _search(query: str, top_k: int = 5):
    import numpy as np
    if not _load_index():
        return None, "Indice non presente. Esegui index_docs prima."
    model = _get_model()
    qv = model.encode([query], normalize_embeddings=True)
    qv = np.asarray(qv, dtype=np.float32)[0]
    sims = _EMBEDDINGS @ qv  # cosine sim since normalized
    idx = np.argsort(-sims)[:top_k]
    results = []
    for i in idx:
        results.append({
            "file": _CHUNKS[int(i)]["file"],
            "text": _CHUNKS[int(i)]["text"],
            "score": float(sims[int(i)]),
        })
    return results, None


def run(name, args):
    if name == "index_docs":
        force = bool(args.get("force", False))
        return _index_all(force=force)

    if name == "search_docs":
        q = args.get("query", "").strip()
        k = int(args.get("top_k", 5))
        if not q:
            return "Specifica una query."
        results, err = _search(q, k)
        if err:
            return err
        if not results:
            return "Nessun passaggio rilevante."
        # Emit a card with the top results
        emit_card("docs", {
            "query": q,
            "items": [{"file": r["file"], "snippet": r["text"][:240], "score": round(r["score"], 3)}
                      for r in results],
        })
        out = []
        for i, r in enumerate(results, 1):
            out.append(f"[{i}] {r['file']} (score {r['score']:.2f})\n{r['text']}")
        return "\n\n".join(out)

    if name == "list_docs":
        files = [p.name for p in DOCS_DIR.iterdir() if p.is_file()]
        if not files:
            return "Cartella docs/ vuota. Mettici file e poi chiedimi di indicizzarli."
        return "\n".join(f"- {f}" for f in sorted(files))

    if name == "clear_docs_index":
        try:
            if INDEX_FILE.exists(): INDEX_FILE.unlink()
            if META_FILE.exists(): META_FILE.unlink()
            global _EMBEDDINGS, _CHUNKS
            _EMBEDDINGS = None; _CHUNKS = None
            return "Indice cancellato."
        except Exception as e:
            return f"Errore: {e}"

    return "?"
