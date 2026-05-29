import imaplib
import email
from email.header import decode_header
from config import GMAIL_ADDRESS, GMAIL_APP_PASSWORD


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


def fetch_recent_emails(limit: int = 10) -> str:
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        return "Credenziali Gmail non configurate nel file .env"

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        mail.select("INBOX")

        status, data = mail.search(None, "ALL")
        if status != "OK":
            return "Errore nella ricerca delle email."

        ids = data[0].split()
        recent = ids[-limit:][::-1]

        results = []
        for i, msg_id in enumerate(recent, 1):
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            subject = _decode(msg.get("Subject"))
            sender = _decode(msg.get("From"))
            date = msg.get("Date", "")
            results.append(f"{i}. Da: {sender}\n   Oggetto: {subject}\n   Data: {date}")

        mail.close()
        mail.logout()

        if not results:
            return "Nessuna email trovata."
        return "\n\n".join(results)
    except Exception as e:
        return f"Errore lettura email: {e}"
