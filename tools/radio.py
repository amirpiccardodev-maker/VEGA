"""Radio streaming italiane via Radio-Browser API (free, no key).

Cerca una stazione per nome e restituisce uno stream URL che il browser
suona via il proprio audio player.
"""
import requests

from tools._shared import emit_card

# Stazioni preferite con URL diretti (più affidabili)
PRESETS = {
    "rds": ("RDS", "https://stream.rds.it/EU2_RDS.mp3"),
    "radio deejay": ("Radio Deejay", "https://streaming.deejay.it/radiodeejay.mp3"),
    "deejay": ("Radio Deejay", "https://streaming.deejay.it/radiodeejay.mp3"),
    "rai radio 1": ("RAI Radio 1", "https://icestreaming.rai.it/1.mp3"),
    "rai radio 2": ("RAI Radio 2", "https://icestreaming.rai.it/2.mp3"),
    "rai radio 3": ("RAI Radio 3", "https://icestreaming.rai.it/3.mp3"),
    "rai isoradio": ("RAI Isoradio", "https://icestreaming.rai.it/9.mp3"),
    "virgin": ("Virgin Radio", "https://icy.unitedradio.it/Virgin.mp3"),
    "virgin radio": ("Virgin Radio", "https://icy.unitedradio.it/Virgin.mp3"),
    "rtl": ("RTL 102.5", "https://streamingv2.shoutcast.com/rtl-1025"),
    "rtl 102.5": ("RTL 102.5", "https://streamingv2.shoutcast.com/rtl-1025"),
    "r101": ("R101", "https://giga.cloud-services.paas.it/streams/r101.mp3"),
    "kiss kiss": ("Radio Kiss Kiss", "https://kissfm.cdnmdstrm.com/live"),
    "m2o": ("m2o", "https://streaming.m2o.it/m2o.mp3"),
}


TOOLS = [{
    "name": "play_radio",
    "description": "Avvia lo streaming di una radio italiana (RDS, Deejay, RAI 1/2/3, Virgin, RTL, R101, m2o, ecc.).",
    "input_schema": {
        "type": "object",
        "properties": {
            "station": {"type": "string", "description": "Nome della radio"},
        },
        "required": ["station"],
    },
}]


def _search_radio_browser(name: str):
    """Fallback: search via the free radio-browser.info API."""
    try:
        r = requests.get(
            "https://de1.api.radio-browser.info/json/stations/search",
            params={"name": name, "country": "Italy", "limit": 3, "hidebroken": "true",
                    "order": "clickcount", "reverse": "true"},
            timeout=6,
            headers={"User-Agent": "VegaPersonal/1.0"},
        )
        if r.status_code == 200:
            results = r.json()
            for st in results:
                url = st.get("url_resolved") or st.get("url")
                if url:
                    return (st.get("name", name), url)
    except Exception:
        pass
    return None


def run(name, args):
    q = args.get("station", "").strip().lower()
    if not q:
        return "Specifica una radio (es. RDS, Deejay, RAI 1, Virgin)."

    # Try presets first (fast, reliable)
    matched = None
    for key, (label, url) in PRESETS.items():
        if key in q or q in key:
            matched = (label, url)
            break

    # Fallback: search Radio Browser API
    if not matched:
        matched = _search_radio_browser(q)

    if not matched:
        available = ", ".join(set(label for _, (label, _) in PRESETS.items()))
        return f"Radio '{q}' non trovata. Disponibili: {available}"

    label, url = matched
    emit_card("radio", {"station": label, "url": url})
    return f"In riproduzione: {label}."
