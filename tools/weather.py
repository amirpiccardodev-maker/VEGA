import requests
import urllib.parse
import memory
from tools._shared import emit_card

TOOLS = [{"name": "get_weather", "description": "Meteo (usa citta salvata se non specificata).",
    "input_schema": {"type": "object", "properties": {"location": {"type": "string"}, "days": {"type": "integer"}}}}]


def run(name, args):
    location = args.get("location", "").strip()
    if not location:
        location = memory.get_preferences().get("home_location", "").strip()
    if not location:
        return ("Non ho ancora la tua citta' di residenza. Dimmi 'abito a [citta']' "
                "oppure 'imposta meteo a [citta']' e me la ricordero' per sempre.")
    days = max(0, min(int(args.get("days", 0)), 3))
    loc_url = urllib.parse.quote(location) if location else ""
    fmt = "j1"
    url = f"https://wttr.in/{loc_url}?format={fmt}&lang=it"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        d = r.json()
    except Exception as e:
        return f"Meteo non disponibile: {e}"

    area = d.get("nearest_area", [{}])[0]
    city = area.get("areaName", [{}])[0].get("value", location or "posizione attuale")
    region = area.get("region", [{}])[0].get("value", "")

    cur = d.get("current_condition", [{}])[0]
    desc = cur.get("lang_it", [{}])[0].get("value", cur.get("weatherDesc", [{}])[0].get("value", ""))
    temp = cur.get("temp_C", "?")
    feels = cur.get("FeelsLikeC", "?")
    humid = cur.get("humidity", "?")
    wind = cur.get("windspeedKmph", "?")

    out = [f"Meteo per {city} {region}".strip(),
           f"Ora: {desc}, {temp}°C (percepiti {feels}°C), umidita' {humid}%, vento {wind} km/h"]

    forecast = []
    for i, day in enumerate(d.get("weather", [])[:4]):
        date = day.get("date", "")
        mx = day.get("maxtempC")
        mn = day.get("mintempC")
        hourly = day.get("hourly", [])
        midday = hourly[4] if len(hourly) > 4 else (hourly[0] if hourly else {})
        ddesc = midday.get("lang_it", [{}])[0].get("value", midday.get("weatherDesc", [{}])[0].get("value", ""))
        forecast.append({"date": date, "min": mn, "max": mx, "desc": ddesc})
        if i > 0 and i < days + 1:
            out.append(f"{date}: {ddesc}, min {mn}°C / max {mx}°C")

    emit_card("weather", {
        "city": city,
        "region": region,
        "temp": temp,
        "feels": feels,
        "desc": desc,
        "humidity": humid,
        "wind": wind,
        "forecast": forecast,
    })
    return "\n".join(out)
