"""Self-signed TLS certificate for Vega local server.

Crea un cert+key autofirmati alla prima esecuzione, validi 5 anni.
SAN include localhost + 127.0.0.1 + LAN IPs rilevati.

Uso:
    ctx = tls_setup.get_ssl_context()
    app.run(..., ssl_context=ctx)
"""
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa


ROOT = Path(__file__).parent
CERT_DIR = ROOT / "data" / "cert"
CERT_DIR.mkdir(parents=True, exist_ok=True)
CERT_PATH = CERT_DIR / "vega.crt"
KEY_PATH = CERT_DIR / "vega.key"


def _detect_lan_ips() -> list:
    """Best-effort discovery of LAN IPs to include in SAN."""
    ips = ["127.0.0.1"]
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if "." in ip and ip not in ips and not ip.startswith("169.254."):
                ips.append(ip)
    except Exception:
        pass
    try:
        # Probe outbound socket to discover primary interface IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            primary = s.getsockname()[0]
            if primary not in ips:
                ips.append(primary)
    except Exception:
        pass
    return ips


def _generate_cert():
    """Create self-signed cert+key. Saves in CERT_DIR."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subj = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "vega.local"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Vega Personal"),
    ])
    lan_ips = _detect_lan_ips()
    san = [
        x509.DNSName("localhost"),
        x509.DNSName("vega.local"),
    ]
    import ipaddress
    for ip in lan_ips:
        try:
            san.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except Exception:
            pass
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subj)
        .issuer_name(subj)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365 * 5))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, key_encipherment=True, key_agreement=False,
            content_commitment=False, data_encipherment=False, key_cert_sign=False,
            crl_sign=False, encipher_only=False, decipher_only=False,
        ), critical=True)
        .sign(key, hashes.SHA256())
    )
    KEY_PATH.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    import os
    try:
        os.chmod(KEY_PATH, 0o600)
    except Exception:
        pass


def get_ssl_context():
    """Return an ssl.SSLContext ready to plug into Flask.app.run(ssl_context=ctx)."""
    if not (CERT_PATH.exists() and KEY_PATH.exists()):
        _generate_cert()
    import ssl
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(CERT_PATH), keyfile=str(KEY_PATH))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def get_cert_pem() -> bytes:
    """Return the PEM cert bytes (for download)."""
    if not CERT_PATH.exists():
        _generate_cert()
    return CERT_PATH.read_bytes()
