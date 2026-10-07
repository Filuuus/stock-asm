import os
import json
import requests
from datetime import datetime, timedelta, timezone

# --- 1. CONFIGURACIÓN Y CREDENCIALES (Variables de Entorno) ---
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "TU_TOKEN_DE_NOTION")
DATABASE_BITACORA_ID = os.getenv("DATABASE_BITACORA_ID", "TU_ID_DE_BASE_DE_DATOS")

ZEEK_TOKEN = os.getenv("ZEEK_TOKEN", "TU_TOKEN_ZEEK")
ZEEK_CLIENTE = os.getenv("ZEEK_CLIENTE", "TU_CLIENTE_ZEEK")
ZEEK_LICENCIA = os.getenv("ZEEK_LICENCIA", "TU_LICENCIA_ZEEK")

zeek_url = "https://auto.zeekgps.com/ZeekApiJS/CMovilApi3WS.asmx/Historial_X_Viajes_2019UTC"
zeek_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/x-www-form-urlencoded"
}

notion_headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# Flotilla con los IDs exactos de cada tarjeta maestra en Notion
flotilla = {
    "ZEEK_VEHICLE_ID": {"nombre": "Vehicle Name", "notion_page_id": "NOTION_PAGE_ID"},
}

# --- FUNCIONES DE NOTION Y COORDENADAS ---
def convertir_coordenadas(coord_cruda):
    if coord_cruda == 0: return 0
    absoluto = abs(coord_cruda) / 100000
    grados = int(absoluto)
    minutos = (absoluto - grados) * 100
    decimal = grados + (minutos / 60)
    return decimal if coord_cruda >= 0 else -decimal

def obtener_kilometraje_tarjeta(page_id, nombre_vehiculo):
    try:
        resp = requests.get(f"https://api.notion.com/v1/pages/{page_id}", headers=notion_headers)
        resp.raise_for_status()
        propiedades = resp.json().get("properties", {})
        return propiedades.get("Kilometraje", {}).get("number") or 0.0
    except requests.exceptions.RequestException as e:
        print(f"[{nombre_vehiculo}] Error al leer tarjeta en Notion: {e}")
        return 0.0

def actualizar_kilometraje_tarjeta(page_id, nombre_vehiculo, nuevo_km):
    payload = {
        "properties": {
            "Kilometraje": {"number": nuevo_km}
        }
    }
    try:
        resp = requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=notion_headers, json=payload)
        resp.raise_for_status()
        print(f"[{nombre_vehiculo}] Tarjeta actualizada exitosamente a {nuevo_km} km.")
    except requests.exceptions.RequestException as e:
        print(f"[{nombre_vehiculo}] Error al actualizar tarjeta maestra: {e}")

# --- 2. LÓGICA DE TIEMPO ---
cst_tz = timezone(timedelta(hours=-6))
hoy_cst = datetime.now(cst_tz)

inicio_ayer_cst = hoy_cst.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
fin_ayer_cst = inicio_ayer_cst + timedelta(hours=23, minutes=59, seconds=59)

inicio_utc = inicio_ayer_cst.astimezone(timezone.utc)
fin_utc = fin_ayer_cst.astimezone(timezone.utc)

fecha_ini = inicio_utc.strftime("%m/%d/%Y %H:%M:%S")
fecha_fin = fin_utc.strftime("%m/%d/%Y %H:%M:%S")
fecha_reporte_iso = inicio_ayer_cst.strftime("%Y-%m-%d")

print(f"Buscando historial UTC de {fecha_ini} a {fecha_fin}")

# --- 3. EXTRACCIÓN E INYECCIÓN ---
for unidad_id, datos_vehiculo in flotilla.items():
    nombre_vehiculo = datos_vehiculo["nombre"]
    page_id_vehiculo = datos_vehiculo["notion_page_id"]
    
    payload = {
        "unidadES": "",
        "unidad": unidad_id,
        "token": ZEEK_TOKEN,
        "cliente": ZEEK_CLIENTE,
        "fechaini": fecha_ini,
        "fechafin": fecha_fin,
        "utcOffset": "6",
        "app": "ZMA",
        "licencia": ZEEK_LICENCIA
    }

    response = requests.post(zeek_url, data=payload, headers=zeek_headers)
    
    try:
        inicio_json = response.text.find('[')
        fin_json = response.text.rfind(']') + 1
        
        if inicio_json == -1 or fin_json == 0:
            print(f"[{nombre_vehiculo}] No se encontró JSON válido en Zeek.")
            continue
            
        json_string = response.text[inicio_json:fin_json]
        viajes = json.loads(json_string)
        viajes.reverse() 
        
    except (json.JSONDecodeError, Exception) as e:
        print(f"[{nombre_vehiculo}] Error extrayendo datos de Zeek: {e}")
        continue

    viajes_validos = [v for v in viajes if v.get("listaUbicaciones")]

    if not viajes_validos:
        print(f"[{nombre_vehiculo}] Sin viajes válidos o con ubicación registrada ayer.")
        continue

    bloques_notion = []
    coordenadas_ruta = [] 
    
    try:
        lat_ini = convertir_coordenadas(viajes_validos[0]["listaUbicaciones"][0]["Latitud"])
        lon_ini = convertir_coordenadas(viajes_validos[0]["listaUbicaciones"][0]["Longitud"])
        coordenadas_ruta.append(f"{lat_ini},{lon_ini}")
    except (IndexError, KeyError) as e:
        print(f"[{nombre_vehiculo}] Advertencia: Error extrayendo coordenada inicial: {e}")

    for viaje in viajes_validos:
        lista = viaje["listaUbicaciones"]
        inicio = lista[0]
        fin = lista[-1]
        
        ts_ini_str = "".join(filter(str.isdigit, inicio["Fecha"]))
        ts_fin_str = "".join(filter(str.isdigit, fin["Fecha"]))
        
        if not ts_ini_str or not ts_fin_str:
            continue
            
        ts_ini = int(ts_ini_str) / 1000
        hora_ini = datetime.fromtimestamp(ts_ini, tz=cst_tz).strftime("%I:%M %p")
        
        ts_fin = int(ts_fin_str) / 1000
        hora_fin = datetime.fromtimestamp(ts_fin, tz=cst_tz).strftime("%I:%M %p")
        
        recorrido = viaje.get("recorrido", "0 m")
        tiempo = viaje.get("tiempo", "0 min")
        
        lat = convertir_coordenadas(fin["Latitud"])
        lon = convertir_coordenadas(fin["Longitud"])
        coordenadas_ruta.append(f"{lat},{lon}") 
        
        maps_url_parada = f"https://www.google.com/maps?q={lat},{lon}"
        geocerca = fin.get("ng")
        destino_texto = f" {geocerca}" if geocerca else " Ver ubicación exacta en mapa"

        bloque = {
            "object": "block",
            "type": "callout",
            "callout": {
                "icon": {"emoji": "📍"},
                "color": "gray_background",
                "rich_text": [
                    {"type": "text", "text": {"content": f"🟢 {hora_ini}  ➔  🔴 {hora_fin}\n"}},
                    {"type": "text", "text": {"content": "Destino:"}},
                    {"type": "text", "text": {"content": destino_texto, "link": {"url": maps_url_parada}}},
                    {"type": "text", "text": {"content": f"\n⏱️ {recorrido} recorridos en {tiempo}"}}
                ]
            }
        }
        bloques_notion.append(bloque)
        
    bloques_notion = bloques_notion[:100]

    try:
        odo_ini_zeek = int(viajes_validos[0]["listaUbicaciones"][0]["odo"]) / 1000
        odo_fin_zeek = int(viajes_validos[-1]["listaUbicaciones"][-1]["odo"]) / 1000
        km_dia = round(odo_fin_zeek - odo_ini_zeek, 2)
    except (IndexError, KeyError, ValueError) as e:
        print(f"[{nombre_vehiculo}] Error al calcular km diarios: {e}")
        km_dia = 0.0

    odometro_actual = obtener_kilometraje_tarjeta(page_id_vehiculo, nombre_vehiculo)
    nuevo_odometro_total = round(odometro_actual + km_dia, 2)
    
    actualizar_kilometraje_tarjeta(page_id_vehiculo, nombre_vehiculo, nuevo_odometro_total)

    str_ruta = "/".join(coordenadas_ruta[:20]) 
    enlace_ruta_completa = f"https://www.google.com/maps/dir/{str_ruta}"

    print(f"Subiendo bitácora de {nombre_vehiculo} -> Hoy: {km_dia} km | Odómetro Total: {nuevo_odometro_total} km")

    notion_payload_bitacora = {
        "parent": {"database_id": DATABASE_BITACORA_ID},
        "properties": {
            "Vehículo": {"title": [{"text": {"content": nombre_vehiculo}}]},
            "Recorrido Diario": {"number": km_dia},
            "Odómetro Total": {"number": nuevo_odometro_total}, 
            "Ruta": {"url": enlace_ruta_completa},
            "Fecha": {"date": {"start": fecha_reporte_iso}}
        },
        "children": bloques_notion
    }

    try:
        resp = requests.post("https://api.notion.com/v1/pages", headers=notion_headers, json=notion_payload_bitacora)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[{nombre_vehiculo}] Error al subir bitácora a Notion: {e}")

print("¡Proceso nocturno finalizado: Odómetros actualizados en tarjetas maestras y bitácoras creadas!")