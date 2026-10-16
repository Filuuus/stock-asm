import os
from dotenv import load_dotenv
import json
import requests
from datetime import datetime, timedelta, timezone

# --- 1. CONFIGURACIÓN Y CREDENCIALES (Variables de Entorno) ---

load_dotenv()

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
    "351340480063135": {"nombre": "Hilux 8", "notion_page_id": "3e029480011080b18bacd85e8748d3a5"},
    "351340480025803": {"nombre": "Hilux 4 Servicios", "notion_page_id": "3e029480011080499c03d6fab0e2c8ee"},
    "351340480019525": {"nombre": "Isuzu Bodega", "notion_page_id": "3e0294800110802da8acf54ddbfed200"},
    "351340480019517": {"nombre": "Fiat", "notion_page_id": "3e029480011080238e25d9596d601438"},
    "351340480019442": {"nombre": "Hilux 5 Sencilla", "notion_page_id": "3e0294800110805f9abcf8633a313796"},
    "351340480012264": {"nombre": "F-350", "notion_page_id": "3e0294800110806fb6e0dbcd58d0dce6"},
    "351340480025969": {"nombre": "Hilux 1", "notion_page_id": "3e029480011080aaaed8fa0c7472f7ae"},
    "351340480032015": {"nombre": "Hilux 2", "notion_page_id": "3e029480011080429b83c37591a71d8a"}
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

def revertir_dia_anterior(fecha_iso, fecha_ini_zeek, fecha_fin_zeek):
    """Calcula los km directamente de Zeek para restar a la tarjeta maestra y luego archiva la bitácora."""
    print(f"\n⚠️ Iniciando reversión con datos de Zeek para la fecha: {fecha_iso}...")
    
    # 1. Buscar bitácoras registradas con la fecha a revertir
    payload_busqueda = {"filter": {"property": "Fecha", "date": {"equals": fecha_iso}}}
    try:
        resp = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_BITACORA_ID}/query", headers=notion_headers, json=payload_busqueda)
        resp.raise_for_status()
        resultados = resp.json().get("results", [])
    except requests.exceptions.RequestException as e:
        print(f"Error al consultar la base de datos de bitácoras: {e}")
        resultados = []

    # 2. Recorrer la flotilla, calcular km con Zeek, restar de la maestra y borrar bitácora
    for unidad_id, datos_vehiculo in flotilla.items():
        nombre_vehiculo = datos_vehiculo["nombre"]
        page_id_vehiculo = datos_vehiculo["notion_page_id"]
        
        # Consultar Zeek
        payload = {
            "unidadES": "",
            "unidad": unidad_id,
            "token": ZEEK_TOKEN,
            "cliente": ZEEK_CLIENTE,
            "fechaini": fecha_ini_zeek,
            "fechafin": fecha_fin_zeek,
            "utcOffset": "6",
            "app": "ZMA",
            "licencia": ZEEK_LICENCIA
        }
        
        km_dia = 0.0
        response = requests.post(zeek_url, data=payload, headers=zeek_headers)
        
        try:
            inicio_json = response.text.find('[')
            fin_json = response.text.rfind(']') + 1
            if inicio_json != -1 and fin_json != 0:
                viajes = json.loads(response.text[inicio_json:fin_json])
                viajes.reverse() 
                viajes_validos = [v for v in viajes if v.get("listaUbicaciones")]
                
                if viajes_validos:
                    odo_ini_zeek = int(viajes_validos[0]["listaUbicaciones"][0]["odo"]) / 1000
                    odo_fin_zeek = int(viajes_validos[-1]["listaUbicaciones"][-1]["odo"]) / 1000
                    km_dia = round(odo_fin_zeek - odo_ini_zeek, 2)
        except Exception as e:
            print(f"[{nombre_vehiculo}] Error calculando km en Zeek para revertir: {e}")

        # Restar Kilometraje en la tarjeta maestra
        if km_dia > 0:
            print(f"\nRevirtiendo: {nombre_vehiculo} | Km calculados por Zeek a restar: {km_dia}")
            km_actual = obtener_kilometraje_tarjeta(page_id_vehiculo, nombre_vehiculo)
            nuevo_km = round(km_actual - km_dia, 2)
            print(f"   -> Odómetro actual: {km_actual} | Nuevo odómetro será: {nuevo_km}")
            actualizar_kilometraje_tarjeta(page_id_vehiculo, nombre_vehiculo, nuevo_km)
        else:
            print(f"\n[{nombre_vehiculo}] Sin kilómetros registrados en Zeek para revertir.")

        # Borrar bitácora de este vehículo si existe
        bitacoras_vehiculo = [
            p for p in resultados 
            if p.get("properties", {}).get("Vehículo", {}).get("title", [{}])[0].get("text", {}).get("content") == nombre_vehiculo
        ]
        
        for bitacora in bitacoras_vehiculo:
            try:
                del_resp = requests.patch(f"https://api.notion.com/v1/pages/{bitacora['id']}", headers=notion_headers, json={"archived": True})
                del_resp.raise_for_status()
                print(f"   -> 🗑️ Bitácora de {nombre_vehiculo} eliminada (archivada) exitosamente en Notion.")
            except requests.exceptions.RequestException as e:
                print(f"   -> ❌ Error al eliminar la bitácora: {e}")

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

# --- 3. MENÚ PRINCIPAL ---
if __name__ == "__main__":
    print("=========================================")
    print("SISTEMA DE BITÁCORAS Y KILOMETRAJE")
    print("=========================================")
    print(f"Fecha objetivo (ayer): {fecha_reporte_iso}")
    print("Opciones:")
    print(" [1] Extraer viajes de Zeek y registrar bitácoras")
    print(" [2] DESHACER registros del día de ayer (Recalcula con Zeek, resta y borra bitácoras)")
    
    opcion = input("\nElige una opción (1 o 2): ").strip()

    if opcion == "2":
        revertir_dia_anterior(fecha_reporte_iso, fecha_ini, fecha_fin)
        print("\n¡Proceso de reversión finalizado!")
        exit()
        
    elif opcion == "1":
        print(f"\nBuscando historial UTC de {fecha_ini} a {fecha_fin}")

        # --- 4. EXTRACCIÓN E INYECCIÓN ---
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
                    "Kilometraje Total": {"number": nuevo_odometro_total}, 
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
                if e.response is not None:
                    print(f"❌ DETALLE DEL RECHAZO DE NOTION: {e.response.text}")
                    print(f"📦 PAYLOAD ENVIADO:\n{json.dumps(notion_payload_bitacora, indent=2)}")

        print("\n¡Proceso finalizado: Kilometrajes actualizados en tarjetas maestras y bitácoras creadas!")
        
    else:
        print("Opción no válida. Saliendo del programa.")