import os
import json
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

load_dotenv()
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_BITACORA_ID = os.getenv("DATABASE_BITACORA_ID")
ZEEK_TOKEN, ZEEK_CLIENTE, ZEEK_LICENCIA = os.getenv("ZEEK_TOKEN"), os.getenv("ZEEK_CLIENTE"), os.getenv("ZEEK_LICENCIA")

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

def obtener_km_notion(page_id):
    try:
        resp = requests.get(f"https://api.notion.com/v1/pages/{page_id}", headers=notion_headers)
        return resp.json().get("properties", {}).get("Kilometraje", {}).get("number") or 0.0
    except: return 0.0

def actualizar_km_notion(page_id, km):
    requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=notion_headers, json={"properties": {"Kilometraje": {"number": km}}})

cst_tz = timezone(timedelta(hours=-6))
inicio_ayer = datetime.now(cst_tz).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
fin_ayer = inicio_ayer + timedelta(hours=23, minutes=59, seconds=59)

fecha_ini = inicio_ayer.astimezone(timezone.utc).strftime("%m/%d/%Y %H:%M:%S")
fecha_fin = fin_ayer.astimezone(timezone.utc).strftime("%m/%d/%Y %H:%M:%S")
fecha_iso = inicio_ayer.strftime("%Y-%m-%d")

print("=====================================================")
print("🛠️ PANEL DE DIAGNÓSTICO Y CORRECCIÓN MANUAL")
print("=====================================================")
print(f"Fecha objetivo (Ayer): {fecha_iso}")
print("[1] 🔍 Simular extracción de Zeek y validación de Payload (No modifica nada)")
print("[2] 📖 Consultar Bitácoras existentes en Notion de esa fecha (No modifica nada)")
print("[3] ⚠️ REVERTIR DÍA ANTERIOR (Resta km de tarjeta maestra y borra bitácoras)")
opc = input("Elige (1/2/3): ")

if opc == "1":
    for unidad_id, datos in flotilla.items():
        nombre = datos["nombre"]
        print(f"\n--- Analizando {nombre} ---")
        payload = {"unidadES": "", "unidad": unidad_id, "token": ZEEK_TOKEN, "cliente": ZEEK_CLIENTE, "fechaini": fecha_ini, "fechafin": fecha_fin, "utcOffset": "6", "app": "ZMA", "licencia": ZEEK_LICENCIA}
        
        resp = requests.post(zeek_url, data=payload, headers=zeek_headers)
        i_json, f_json = resp.text.find('['), resp.text.rfind(']') + 1
        
        if i_json == -1:
            print("❌ Zeek no devolvió un JSON válido.")
            continue
            
        viajes = json.loads(resp.text[i_json:f_json])[::-1]
        validos = [v for v in viajes if v.get("listaUbicaciones")]
        print(f"Viajes totales recibidos: {len(viajes)} | Viajes con ubicaciones válidas: {len(validos)}")

        if validos:
            odo_ini = int(validos[0]["listaUbicaciones"][0]["odo"]) / 1000
            odo_fin = int(validos[-1]["listaUbicaciones"][-1]["odo"]) / 1000
            km_dia = round(odo_fin - odo_ini, 2)
            km_actual_notion = obtener_km_notion(datos["notion_page_id"])
            km_simulado = round(km_actual_notion + km_dia, 2)
            
            print(f"Odo Zeek Inicio: {odo_ini} | Odo Zeek Fin: {odo_fin} | KM Calculado Día: {km_dia}")
            print(f"KM Actual en Notion: {km_actual_notion} -> Simulación total Notion: {km_simulado}")
            
            payload_simulado = {
                "parent": {"database_id": DATABASE_BITACORA_ID},
                "properties": {
                    "Vehículo": {"title": [{"text": {"content": nombre}}]},
                    "Recorrido Diario": {"number": km_dia},
                    "Kilometraje Total": {"number": km_simulado},
                    "Ruta": {"url": "https://www.google.com/maps/..."},
                    "Fecha": {"date": {"start": fecha_iso}}
                }
            }
            print("📦 Payload Properties Simulado:")
            print(json.dumps(payload_simulado["properties"], indent=2))
        else:
            print("No hubo movimiento.")

elif opc == "2":
    print(f"\n🔍 Buscando registros en Notion creados para la fecha: {fecha_iso}")
    payload_query = {"filter": {"property": "Fecha", "date": {"equals": fecha_iso}}}
    try:
        resp = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_BITACORA_ID}/query", headers=notion_headers, json=payload_query)
        resp.raise_for_status()
        resultados = resp.json().get("results", [])
        
        if not resultados: print("No se encontraron bitácoras para esta fecha en Notion.")
        else:
            for p in resultados:
                props = p.get("properties", {})
                v = props.get("Vehículo", {}).get("title", [{}])[0].get("text", {}).get("content", "N/A")
                k_d = props.get("Recorrido Diario", {}).get("number", 0)
                k_t = props.get("Kilometraje Total", {}).get("number", 0)
                print(f"📖 ID: {p['id']} | Vehículo: {v} | Recorrido Hoy: {k_d} km | Total: {k_t} km")
                
    except requests.exceptions.RequestException as e:
        print(f"Error consultando Notion: {e}")
        if e.response is not None: print("Detalle:", e.response.text)

elif opc == "3":
    confirm = input("\n🚨 ADVERTENCIA: Esta acción restará kilometraje a los vehículos y borrará bitácoras. ¿Continuar? (s/n): ")
    if confirm.lower() == 's':
        print(f"\n⚠️ Iniciando reversión con datos de Zeek para la fecha: {fecha_iso}...")
        payload_query = {"filter": {"property": "Fecha", "date": {"equals": fecha_iso}}}
        resultados = []
        try:
            resp = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_BITACORA_ID}/query", headers=notion_headers, json=payload_query)
            resultados = resp.json().get("results", [])
        except: pass

        for unidad_id, datos in flotilla.items():
            nombre, page_id_vehiculo = datos["nombre"], datos["notion_page_id"]
            payload = {"unidadES": "", "unidad": unidad_id, "token": ZEEK_TOKEN, "cliente": ZEEK_CLIENTE, "fechaini": fecha_ini, "fechafin": fecha_fin, "utcOffset": "6", "app": "ZMA", "licencia": ZEEK_LICENCIA}
            km_dia = 0.0
            
            try:
                resp = requests.post(zeek_url, data=payload, headers=zeek_headers)
                i_json, f_json = resp.text.find('['), resp.text.rfind(']') + 1
                if i_json != -1 and f_json != 0:
                    viajes = json.loads(resp.text[i_json:f_json])[::-1]
                    validos = [v for v in viajes if v.get("listaUbicaciones")]
                    if validos:
                        odo_ini = int(validos[0]["listaUbicaciones"][0]["odo"]) / 1000
                        odo_fin = int(validos[-1]["listaUbicaciones"][-1]["odo"]) / 1000
                        km_dia = round(odo_fin - odo_ini, 2)
            except Exception as e: print(f"[{nombre}] Error con Zeek: {e}")

            if km_dia > 0:
                print(f"\nRevirtiendo: {nombre} | Km Zeek a restar: {km_dia}")
                km_actual = obtener_km_notion(page_id_vehiculo)
                nuevo_km = round(km_actual - km_dia, 2)
                print(f"   -> Odómetro actual: {km_actual} | Nuevo odómetro será: {nuevo_km}")
                actualizar_km_notion(page_id_vehiculo, nuevo_km)
            else:
                print(f"\n[{nombre}] Sin kilómetros en Zeek para revertir.")

            bitacoras_vehiculo = [p for p in resultados if p.get("properties", {}).get("Vehículo", {}).get("title", [{}])[0].get("text", {}).get("content") == nombre]
            for bitacora in bitacoras_vehiculo:
                try:
                    requests.patch(f"https://api.notion.com/v1/pages/{bitacora['id']}", headers=notion_headers, json={"archived": True})
                    print(f"   -> 🗑️ Bitácora de {nombre} eliminada (archivada) exitosamente.")
                except Exception as e: print(f"   -> ❌ Error al eliminar bitácora: {e}")
        print("\n¡Reversión completada!")
    else:
        print("Operación cancelada.")