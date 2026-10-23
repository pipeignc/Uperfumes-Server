"""PARADIGMA FUNCIONAL: comparación por presupuesto y conversión monetaria.

Funciones puras: entradas explícitas, resultados nuevos, sin red, archivos,
variables globales mutables ni modificación de la colección de entrada.
"""

from decimal import Decimal, ROUND_HALF_UP


def positive_decimal(value):
    number = Decimal(str(value))
    if not number.is_finite() or number <= 0:
        raise ValueError("El monto y el tipo de cambio deben ser positivos y finitos.")
    return number


def usd_to_clp(price_usd, rate):
    return int((positive_decimal(price_usd) * positive_decimal(rate)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP,
    ))


def clp_to_usd(amount_clp, rate):
    return float(positive_decimal(amount_clp) / positive_decimal(rate))


def format_clp(amount):
    return "$" + f"{amount:,}".replace(",", ".") + " CLP"


def priced_perfume(perfume, rate):
    price = usd_to_clp(perfume["price_usd"], rate)
    return {**perfume, "price_clp": price, "price_formatted": format_clp(price)}


def compare_perfumes(perfumes, budget_clp, rate, query="", limit=12):
    """filter → map → sorted; devuelve precios y saldo, nunca stock inventado."""
    budget = positive_decimal(budget_clp)
    exchange = positive_decimal(rate)
    if not 1 <= limit <= 50:
        raise ValueError("limit debe estar entre 1 y 50.")
    search = query.strip().casefold()
    matches = filter(lambda p: search in p["name"].casefold(), perfumes)
    converted = map(lambda p: priced_perfume(p, exchange), matches)
    affordable = filter(lambda p: Decimal(p["price_clp"]) <= budget, converted)
    ordered = sorted(affordable, key=lambda p: (p["price_clp"], p["name"].casefold()))
    results = tuple(map(lambda p: {**p, "remaining_clp": int(budget) - p["price_clp"]}, ordered[:limit]))
    return {"items": results, "total_matches": len(ordered), "budget_clp": int(budget)}
