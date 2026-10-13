"""Estimated kg per ERP sale unit. Order: ERP unit (meter/liter/kilogram), weight in the
product name, GEA portal weight (single-piece units only), then keyword estimates, then a
default. Each result says where it came from so the page can show how much tonnage is
estimated. Weights typed in by management (ProductWeight) override all of this.

The ERP's own weight field (CPESOPRODUCTO) is 0 for every product, hence the guessing.
First built for the Bionat profitability report (2026-10)."""
import json
import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings

NAME_RE = re.compile(r'(\d+(?:[.,]\d+)?)\s*(KGS?|KILOS?|LTS?|LITROS?|L|GRS?|G|ML)\b')
CAPACITY_WORDS = ('REGULADOR', 'TANQUE', 'BOMBA', 'RECIPIENTE', 'TERMO', 'CUBETA VACIA')
GEA_SUFFIXES = 'WNTHAIC'  # ERP variants of a plain GEA code (portal redirects them)
GEA_SINGLE_UNITS = ('PZA', 'EA', 'ST', 'PC', 'PCE', '')
MIN_PESOS_PER_KG = 5  # cheaper than this per kg = the weight is a pack/roll/capacity, not the unit sold

# (keywords, kg per unit sold) - estimates for products with no usable weight
KEYWORD_KG = [
    (('VENTILADOR',), 100.0),        # 72" barn fans, ~90-130 kg
    (('TAPETE', 'ALFOMBRA'), 46.0),  # 4x6 ft 3/4" rubber mat; GEA's own MaxGrip 3/4 weighs 46.04 kg
    (('PEZONERA',), 0.15),           # one rubber/silicone liner
    (('MANGUERA', 'CABLE'), 0.15),   # per meter
]
PER_METER_KG = 0.15  # hose / cable sold by the meter
PER_LITER_KG = {'ACEITE': 0.87}  # turbine oil density; other liquids ~1 kg/L
DEFAULT_KG = 0.3  # small parts: gaskets, valves, clamps, filters


# Scraped from GEA's parts portal for the catalog; gitignored (exports/gea), so a deployment
# without it simply skips the GEA step.
GEA_PRODUCTS_FILE = Path(settings.BASE_DIR) / 'exports' / 'gea' / 'gea_products.json'


@lru_cache(maxsize=1)
def load_gea():
    try:
        return json.loads(GEA_PRODUCTS_FILE.read_text())
    except FileNotFoundError:
        return {}


def gea_lookup(code, gea):
    code = (code or '').strip()
    keys = [code] + ([code[:-1]] if code[-1:] in GEA_SUFFIXES else [])
    for k in keys:
        p = gea.get(k)
        if p and p.get('kg'):
            return float(p['kg']), (p.get('unit') or '').upper()
    return None, None


def estimate_kg(code, name, price, gea, erp_unit=''):
    name = (name or '').upper()
    erp_unit = (erp_unit or '').upper()
    if erp_unit == 'METRO':
        return PER_METER_KG, 'estimado'
    if erp_unit == 'LITRO':
        return next((kg for w, kg in PER_LITER_KG.items() if w in name), 1.0), 'estimado'
    if erp_unit == 'KILOGRAMO':
        return 1.0, 'unidad'
    m = NAME_RE.search(name)
    if m and not any(w in name for w in CAPACITY_WORDS):
        v = float(m.group(1).replace(',', '.'))
        kg = v / 1000 if m.group(2) in ('G', 'GR', 'GRS', 'ML') else v
        if 0 < kg <= 300 and price / kg >= MIN_PESOS_PER_KG:
            return kg, 'nombre'
    kg, unit = gea_lookup(code, gea)
    if kg and unit in GEA_SINGLE_UNITS and price / kg >= MIN_PESOS_PER_KG:
        return kg, 'GEA'
    for words, est in KEYWORD_KG:
        if any(w in name for w in words):
            return est, 'estimado'
    return DEFAULT_KG, 'estimado'

