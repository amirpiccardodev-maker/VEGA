"""Send email via Gmail SMTP using app password."""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import GMAIL_ADDRESS, GMAIL_APP_PASSWORD

TOOLS = [{
    "name": "send_email",
    "description": "Invia una email dall'account Gmail dell'utente. Usalo quando l'utente chiede 'manda una mail a X dicendo Y'. Conferma sempre il contenuto a voce prima.",
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Indirizzo destinatario"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
}]


def run(name, args):
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        return "Credenziali Gmail non configurate."
    to = args.get("to", "").strip()
    subject = args.get("subject", "").strip()
    body = args.get("body", "").strip()
    if not (to and subject and body):
        return "Mancano destinatario, oggetto o corpo."

    msg = MIMEMultipart()
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, [to], msg.as_string())
        return f"Email inviata a {to}."
    except Exception as e:
        return f"Errore invio: {e}"
