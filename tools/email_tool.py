"""Gmail tools: list, search, read body, summary."""
import imaplib
import email
from email.header import decode_header
from datetime import datetime

from config import GMAIL_ADDRESS, GMAIL_APP_PASSWORD

TOOLS = [
    {"name": "list_emails", "description": "Email recenti (mittente/oggetto/data).",
     "input_schema": {"type": "object", "properties": {"limit": {"type": "integer"}, "unread_only": {"type": "boolean"}}}},
    {"name": "search_emails", "description": "Cerca email.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "from_address": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]}},
    {"name": "read_email", "description": "Legge il corpo di una email (indice da list_emails).",
     "input_schema": {"type": "object", "properties": {"index": {"type": "integer"}}, "required": ["index"]}},
    {"name": "summarize_inbox", "description": "Riassume le ultime N email.",
     "input_schema": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
]


_LAST_LIST_IDS = []


def _decode(value):
    if value is None:
        return ""
    parts = decode_header(value)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            try:
                out.append(text.decode(enc or "utf-8", errors="replace"))
            except LookupError:
                out.append(text.decode("utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _connect():
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        raise RuntimeError("Credenziali Gmail mancanti")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
    mail.select("INBOX")
    return mail


def _get_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disp:
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                except Exception:
                    continue
        return ""
    try:
        return msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="replace")
    except Exception:
        return ""


def _format_summary(num, msg):
    subject = _decode(msg.get("Subject"))
    sender = _decode(msg.get("From"))
    date = msg.get("Date", "")
    return f"{num}. Da: {sender}\n   Oggetto: {subject}\n   Data: {date}"


def run(name, args):
    global _LAST_LIST_IDS
    if name == "list_emails":
        limit = min(int(args.get("limit", 10)), 30)
        unread = bool(args.get("unread_only", False))
        mail = _connect()
        try:
            criterion = "UNSEEN" if unread else "ALL"
            status, data = mail.search(None, criterion)
            ids = data[0].split()
            recent = ids[-limit:][::-1]
            _LAST_LIST_IDS = recent
            results = []
            for i, msg_id in enumerate(recent, 1):
                _, msg_data = mail.fetch(msg_id, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])
                results.append(_format_summary(i, msg))
            if not results:
                return "Nessuna email."
            return "\n\n".join(results)
        finally:
            mail.close(); mail.logout()

    if name == "search_emails":
        query = args.get("query", "")
        from_addr = args.get("from_address", "")
        limit = min(int(args.get("limit", 10)), 30)
        mail = _connect()
        try:
            criteria = []
            if from_addr:
                criteria += ["FROM", f'"{from_addr}"']
            if query:
                criteria += ["TEXT", f'"{query}"']
            if not criteria:
                criteria = ["ALL"]
            status, data = mail.search(None, *criteria)
            ids = data[0].split()
            recent = ids[-limit:][::-1]
            _LAST_LIST_IDS = recent
            results = []
            for i, msg_id in enumerate(recent, 1):
                _, msg_data = mail.fetch(msg_id, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])
                results.append(_format_summary(i, msg))
            return "\n\n".join(results) if results else "Nessun risultato."
        finally:
            mail.close(); mail.logout()

    if name == "read_email":
        idx = int(args.get("index", 1)) - 1
        if not _LAST_LIST_IDS or idx < 0 or idx >= len(_LAST_LIST_IDS):
            return "Indice non valido. Esegui prima list_emails o search_emails."
        msg_id = _LAST_LIST_IDS[idx]
        mail = _connect()
        try:
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            subject = _decode(msg.get("Subject"))
            sender = _decode(msg.get("From"))
            date = msg.get("Date", "")
            body = _get_body(msg)
            body = body.strip()[:4000]
            return f"Da: {sender}\nOggetto: {subject}\nData: {date}\n\n{body}"
        finally:
            mail.close(); mail.logout()

    if name == "summarize_inbox":
        limit = min(int(args.get("limit", 15)), 30)
        return run("list_emails", {"limit": limit})

    return f"Tool email sconosciuto: {name}"
