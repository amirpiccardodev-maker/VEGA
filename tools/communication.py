"""Comunicazione: notifiche Windows native, voice mail, mobile LAN info."""
import os
import re
import socket
import tempfile
import threading


TOOLS = [
    {"name": "windows_notify",
     "description": "Invia una notifica TOAST Windows nativa (visibile anche se Vega e' minimizzato).",
     "input_schema": {"type": "object", "properties": {
         "title": {"type": "string"},
         "message": {"type": "string"},
         "duration": {"type": "integer", "description": "secondi visibilita' (default 5)"},
     }, "required": ["title", "message"]}},
    {"name": "send_voice_mail",
     "description": "Genera un messaggio vocale MP3 e lo invia come allegato email. Es: 'manda un vocale a marco@example.com dicendo che arrivo in ritardo'.",
     "input_schema": {"type": "object", "properties": {
         "to": {"type": "string"},
         "subject": {"type": "string"},
         "spoken_text": {"type": "string", "description": "Cosa dire nel messaggio vocale"},
     }, "required": ["to", "spoken_text"]}},
    {"name": "lan_url",
     "description": "Mostra l'URL LAN per controllare Vega dal telefono o altro device sulla stessa rete WiFi.",
     "input_schema": {"type": "object", "properties": {}}},
]


def _windows_toast(title: str, msg: str, duration: int = 5):
    """Try multiple paths to show a Windows toast."""
    # 1) win10toast
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(title, msg, duration=duration, threaded=True)
        return True
    except Exception:
        pass
    # 2) PowerShell BurntToast / direct fallback
    try:
        import subprocess
        ps_script = (
            f"$ErrorActionPreference='SilentlyContinue';"
            f"[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime] | Out-Null;"
            f"$xml=New-Object Windows.Data.Xml.Dom.XmlDocument;"
            f"$template='<toast><visual><binding template=\"ToastGeneric\"><text>{title}</text><text>{msg}</text></binding></visual></toast>';"
            f"$xml.LoadXml($template);"
            f"$toast=New-Object Windows.UI.Notifications.ToastNotification $xml;"
            f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Vega').Show($toast)"
        )
        subprocess.Popen(["powershell", "-NoProfile", "-Command", ps_script],
                         creationflags=subprocess.CREATE_NO_WINDOW)
        return True
    except Exception:
        pass
    return False


def run(name, args):
    if name == "windows_notify":
        title = args.get("title", "Vega")
        msg = args.get("message", "")
        duration = int(args.get("duration", 5))
        # Sanitize for safety
        title = re.sub(r"[<>'\"]", "", title)[:60]
        msg = re.sub(r"[<>'\"]", "", msg)[:200]
        ok = _windows_toast(title, msg, duration)
        return "Notifica inviata." if ok else "Impossibile mostrare la notifica Windows."

    if name == "send_voice_mail":
        to = args.get("to", "").strip()
        subject = args.get("subject", "Messaggio vocale da Vega").strip()
        spoken = args.get("spoken_text", "").strip()
        if not to or not spoken:
            return "Servono destinatario e testo da dire."
        # Generate audio
        try:
            import tts as tts_mod
        except Exception:
            return "TTS non disponibile."
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        try:
            tts_mod.synthesize(spoken, tmp.name)
        except Exception as e:
            return f"Errore generazione vocale: {e}"
        # Send email with attachment
        from config import GMAIL_ADDRESS, GMAIL_APP_PASSWORD
        if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
            return "Gmail non configurato."
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        from email.mime.audio import MIMEAudio
        msg = MIMEMultipart()
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(f"Messaggio vocale allegato.\n\nTrascrizione:\n{spoken}", "plain", "utf-8"))
        with open(tmp.name, "rb") as f:
            audio = MIMEAudio(f.read(), _subtype="mpeg")
            audio.add_header("Content-Disposition", "attachment", filename="voicemail.mp3")
            msg.attach(audio)
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
                server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
                server.sendmail(GMAIL_ADDRESS, [to], msg.as_string())
            try: os.unlink(tmp.name)
            except OSError: pass
            return f"Vocale inviato a {to}."
        except Exception as e:
            return f"Errore invio: {e}"

    if name == "lan_url":
        ip = "127.0.0.1"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except Exception:
            pass
        return (f"URL per il tuo telefono: http://{ip}:5252\n"
                f"Connettilo alla stessa rete WiFi del PC e apri questo URL nel browser.")

    return "?"
