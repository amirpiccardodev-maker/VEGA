"""Stock quotes via yfinance (lazy import: yfinance is slow to import)."""

TOOLS = [{
    "name": "stock_quote",
    "description": "Quotazione attuale di un titolo o crypto. Esempi di ticker: AAPL, MSFT, GOOGL, TSLA, BTC-USD, ETH-USD, ENI.MI (azioni italiane usa .MI).",
    "input_schema": {
        "type": "object",
        "properties": {
            "tickers": {"type": "array", "items": {"type": "string"}, "description": "Lista ticker"},
        },
        "required": ["tickers"],
    },
}]


def run(name, args):
    try:
        import yfinance as yf
    except Exception:
        return "yfinance non disponibile."
    from tools._shared import emit_card
    tickers = args.get("tickers", [])
    if not tickers:
        return "Specifica almeno un ticker."
    out = []
    card_items = []
    for t in tickers[:8]:
        try:
            tk = yf.Ticker(t)
            info = tk.fast_info
            price = info.get("last_price") if hasattr(info, "get") else info.last_price
            prev = info.get("previous_close") if hasattr(info, "get") else info.previous_close
            curr = info.get("currency", "USD") if hasattr(info, "get") else getattr(info, "currency", "USD")
            if price is None:
                out.append(f"{t}: dati non disponibili")
                continue
            pct = ((price - prev) / prev * 100) if prev else 0
            arrow = "↑" if pct >= 0 else "↓"
            out.append(f"{t}: {price:.2f} {curr} {arrow} {pct:+.2f}%")
            card_items.append({"ticker": t, "price": round(price, 2), "currency": curr, "change_pct": round(pct, 2)})
        except Exception as e:
            out.append(f"{t}: errore ({e})")
    if card_items:
        emit_card("stocks", {"items": card_items})
    return "\n".join(out)
