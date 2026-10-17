import os
import json
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

# --- CONFIGURACIÓN Y CREDENCIALES ---
load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "TU_TOKEN_DE_NOTION")
DATABASE_BITACORA_ID = os.getenv("DATABASE_BITACORA_ID", "TU_ID_DE_BASE_DE_DATOS")
ZEEK_TOKEN = os.getenv("ZEEK_TOKEN", "TU_TOKEN_ZEEK")
ZEEK_CLIENTE = os.getenv("ZEEK_CLIENTE", "TU_CLIENTE_ZEEK")
ZEEK_LICENCIA = os.getenv("ZEEK_LICENCIA", "TU_LICENCIA_ZEEK")

zeek_url = "https://auto.zeekgps.com/ZeekApiJS/CMovilApi3WS.asmx/Historial_X_Viajes_2019UTC"
zeek_headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded"}
notion_headers = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

flotilla = {
    "351340480063135": {"nombre": "Hilux 8", "notion_page_id": "3e029480011080b18bacd85e8748d3a5"},
    "351340480025803": {"nombre": "Hilux 4 Servicios", "notion_page_id": "3e029480011080499c03d6fab0e2c8ee"},
    "351340480019525": {"nombre": "Isuzu Bodega", "notion_page_id": "3e0294800110802da8acf54ddbfed200"},
    "351340480019517": {"nombre": "Fiat", "notion_page_id": "3e029480011080238e25d9596d601438"},
    "351340480019442": {"nombre": "Hilux 5 Sencilla", "notion_page_id": "3e0294800110805f9abcf8633a313796"},
    "351340480012264": {"nombre": "F-350", "notion_page_id": "3e0294800110806fb6e0dbcd58d0dce6"},
    "351340480025969": {"nombre": "Hilux 1", "notion_page_id": "3e029480011080aaaed8fa0c7472f7ae"},
    "351340480032015": {"nombre": "Hilux 2", "notion_page_id": "3e029480011080429b83c37591a71d8a"}
}

# --- FUNCIONES AUXILIARES ---
def convertir_coordenadas(coord):
    if coord == 0: return 0
    absoluto = abs(coord) / 100000
    grados = int(absoluto)
    return (grados + ((absoluto - grados) * 100) / 60) * (1 if coord >= 0 else -1)

def obtener_km_notion(page_id):
    try:
        resp = requests.get(f"https://api.notion.com/v1/pages/{page_id}", headers=notion_headers)
        resp.raise_for_status()
        return resp.json().get("properties", {}).get("Kilometraje", {}).get("number") or 0.0
    except: return 0.0

def actualizar_km_notion(page_id, km):
    requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=notion_headers, json={"properties": {"Kilometraje": {"number": km}}})

# --- LÓGICA DE TIEMPO (Día de Ayer) ---
cst_tz = timezone(timedelta(hours=-6))
inicio_ayer = datetime.now(cst_tz).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
fin_ayer = inicio_ayer + timedelta(hours=23, minutes=59, seconds=59)

fecha_ini = inicio_ayer.astimezone(timezone.utc).strftime("%m/%d/%Y %H:%M:%S")
fecha_fin = fin_ayer.astimezone(timezone.utc).strftime("%m/%d/%Y %H:%M:%S")
fecha_iso = inicio_ayer.strftime("%Y-%m-%d")

print(f"🚀 Iniciando registro automático de bitácoras para el {fecha_iso}")

# --- PROCESAMIENTO ---
for unidad_id, datos in flotilla.items():
    nombre, page_id = datos["nombre"], datos["notion_page_id"]
    payload = {"unidadES": "", "unidad": unidad_id, "token": ZEEK_TOKEN, "cliente": ZEEK_CLIENTE, "fechaini": fecha_ini, "fechafin": fecha_fin, "utcOffset": "6", "app": "ZMA", "licencia": ZEEK_LICENCIA}
    
    try:
        resp = requests.post(zeek_url, data=payload, headers=zeek_headers)
        i_json, f_json = resp.text.find('['), resp.text.rfind(']') + 1
        if i_json == -1 or f_json == 0: continue
        viajes = json.loads(resp.text[i_json:f_json])[::-1]
        validos = [v for v in viajes if v.get("listaUbicaciones")]
        
        if not validos:
            print(f"[{nombre}] Sin viajes válidos.")
            continue

        bloques, coords = [], []
        for v in validos:
            lst = v["listaUbicaciones"]
            ini, fin = lst[0], lst[-1]
            ts_ini = int("".join(filter(str.isdigit, ini["Fecha"]))) / 1000
            ts_fin = int("".join(filter(str.isdigit, fin["Fecha"]))) / 1000
            h_ini = datetime.fromtimestamp(ts_ini, tz=cst_tz).strftime("%I:%M %p")
            h_fin = datetime.fromtimestamp(ts_fin, tz=cst_tz).strftime("%I:%M %p")
            lat, lon = convertir_coordenadas(fin["Latitud"]), convertir_coordenadas(fin["Longitud"])
            coords.append(f"{lat},{lon}")
            
            geo = fin.get("ng")
            bloques.append({
                "object": "block", "type": "callout",
                "callout": {
                    "icon": {"emoji": "📍"}, "color": "gray_background",
                    "rich_text": [
                        {"type": "text", "text": {"content": f"🟢 {h_ini}  ➔  🔴 {h_fin}\nDestino: "}},
                        {"type": "text", "text": {"content": f"{geo if geo else 'Ver mapa'}", "link": {"url": f"https://www.google.com/maps?q={lat},{lon}"}}},
                        {"type": "text", "text": {"content": f"\n⏱️ {v.get('recorrido','0m')} en {v.get('tiempo','0m')}"}}
                    ]
                }
            })

        km_dia = round((int(validos[-1]["listaUbicaciones"][-1]["odo"]) - int(validos[0]["listaUbicaciones"][0]["odo"])) / 1000, 2)
        km_total = round(obtener_km_notion(page_id) + km_dia, 2)

        actualizar_km_notion(page_id, km_total)
        print(f"✅ [{nombre}] Tarjeta: {km_total} km (+{km_dia} km)")

        notion_payload = {
            "parent": {"database_id": DATABASE_BITACORA_ID},
            "properties": {
                "Vehículo": {"title": [{"text": {"content": nombre}}]},
                "Recorrido Diario": {"number": km_dia},
                "Kilometraje Total": {"number": km_total},
                "Ruta": {"url": f"https://www.google.com/maps/dir/{'/'.join(coords[:20])}"},
                "Fecha": {"date": {"start": fecha_iso}}
            },
            "children": bloques[:100]
        }
        
        req = requests.post("https://api.notion.com/v1/pages", headers=notion_headers, json=notion_payload)
        req.raise_for_status()

    except Exception as e:
        print(f"❌ Error en {nombre}: {e}")

print("🎉 Registro finalizado.")