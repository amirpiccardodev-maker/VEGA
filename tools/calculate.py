import math

TOOLS = [{
    "name": "calculate",
    "description": "Valuta un'espressione matematica. Supporta funzioni standard (sin, cos, sqrt, log, pi, e, ecc.).",
    "input_schema": {
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
    },
}]

_SAFE = {
    "abs": abs, "round": round, "min": min, "max": max,
    "pi": math.pi, "e": math.e,
    "sqrt": math.sqrt, "log": math.log, "log10": math.log10,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "exp": math.exp, "floor": math.floor, "ceil": math.ceil,
    "pow": pow,
}


def run(name, args):
    expr = args.get("expression", "").strip()
    if not expr:
        return "Espressione vuota."
    try:
        result = eval(expr, {"__builtins__": {}}, _SAFE)
        return f"{expr} = {result}"
    except Exception as e:
        return f"Errore di calcolo: {e}"
