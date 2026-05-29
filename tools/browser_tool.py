"""Playwright-based browser automation tool.

Apre browser headless (default) o headed (visible) e:
  - naviga a URL
  - estrae testo / screenshot
  - clicca selector
  - compila form

Richiede: pip install playwright + playwright install chromium (una volta).
"""
import os
import base64
from pathlib import Path


TOOLS = [{
    "name": "browse_url",
    "description": (
        "Naviga una pagina web con un browser reale (Playwright/Chromium). "
        "Esegue JavaScript, gestisce siti dinamici. Restituisce testo estratto + "
        "screenshot. Usalo quando serve scrapare siti che web_search non vede "
        "(SPA, dietro JS, contenuti dinamici)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "action": {
                "type": "string",
                "description": "'extract' (default), 'screenshot', 'click', 'fill'."
            },
            "selector": {"type": "string",
                         "description": "CSS selector per click/fill."},
            "value": {"type": "string", "description": "Testo da scrivere per fill."},
            "headed": {"type": "boolean",
                       "description": "True per browser visibile (default: false=headless)."},
            "max_chars": {"type": "integer",
                          "description": "Max caratteri testo restituiti (default 4000)."},
        },
        "required": ["url"],
    },
}]


def _ensure_browser():
    """Check chromium is installed via playwright."""
    try:
        from playwright.sync_api import sync_playwright
        return True
    except ImportError:
        return False


def run(name, args):
    args = args or {}
    if not _ensure_browser():
        return ("Playwright non installato. Esegui:\n"
                "  pip install playwright\n"
                "  playwright install chromium")
    url = args.get("url", "").strip()
    if not url:
        return "URL mancante."
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    action = args.get("action", "extract")
    headed = bool(args.get("headed", False))
    max_chars = int(args.get("max_chars", 4000))

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=not headed)
            except Exception as e:
                return (f"Browser non avviabile: {e}\n"
                        f"Esegui: playwright install chromium")
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Vega/1.0",
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(1000)  # let JS settle

            result_parts = []

            if action == "click":
                sel = args.get("selector", "").strip()
                if not sel:
                    browser.close()
                    return "Selector mancante per click."
                page.click(sel, timeout=5000)
                page.wait_for_timeout(800)
                result_parts.append(f"Cliccato: {sel}")

            elif action == "fill":
                sel = args.get("selector", "").strip()
                val = args.get("value", "")
                if not sel:
                    browser.close()
                    return "Selector mancante per fill."
                page.fill(sel, val, timeout=5000)
                result_parts.append(f"Compilato {sel} con: {val[:50]}")

            elif action == "screenshot":
                shot = page.screenshot(full_page=True)
                browser.close()
                b64 = base64.b64encode(shot).decode("ascii")
                return [
                    {"type": "image", "source": {"type": "base64",
                                                   "media_type": "image/png", "data": b64}},
                    {"type": "text", "text": f"Screenshot di {url}"},
                ]

            # Always extract text at the end
            try:
                title = page.title()
                text_content = page.evaluate("""
                    () => {
                        const main = document.querySelector('main, article, .content, #content, body');
                        return main ? main.innerText : document.body.innerText;
                    }
                """)
            except Exception:
                title = ""
                text_content = ""

            browser.close()

            result_parts.append(f"PAGINA: {title}")
            result_parts.append(f"URL: {url}")
            result_parts.append("")
            result_parts.append(text_content[:max_chars])
            if len(text_content) > max_chars:
                result_parts.append(f"\n[...troncato a {max_chars} di {len(text_content)} char]")
            return "\n".join(result_parts)

    except Exception as e:
        return f"Errore browser: {e}"
