import os
import requests
from datetime import datetime, timedelta, timezone

# --- 1. CONFIGURACIÓN ---
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "TU_TOKEN_DE_NOTION")
DATABASE_ID = os.getenv("DATABASE_BITACORA_ID", "TU_ID_DE_BASE_DE_DATOS")

notion_headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# --- 2. LÓGICA DE TIEMPO (MES ANTERIOR) ---
cst_tz = timezone(timedelta(hours=-6))
hoy = datetime.now(cst_tz)

primer_dia_mes_actual = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
ultimo_dia_mes_anterior = primer_dia_mes_actual - timedelta(days=1)
primer_dia_mes_anterior = ultimo_dia_mes_anterior.replace(day=1)

fecha_inicio_str = primer_dia_mes_anterior.strftime("%Y-%m-%d")
fecha_fin_str = ultimo_dia_mes_anterior.strftime("%Y-%m-%d")
nombre_mes = primer_dia_mes_anterior.strftime("%B %Y").capitalize()

print(f"🔍 Buscando registros diarios del {fecha_inicio_str} al {fecha_fin_str}...")

# --- 3. CONSULTAR LA BITÁCORA DIARIA (CON PAGINACIÓN) ---
query_payload = {
    "filter": {
        "and": [
            {"property": "Fecha", "date": {"on_or_after": fecha_inicio_str}},
            {"property": "Fecha", "date": {"on_or_before": fecha_fin_str}},
            {
                "property": "Vehículo",
                "title": {"does_not_contain": "Reporte Mensual"}
            }
        ]
    },
    "page_size": 100 
}

resultados = []
has_more = True
next_cursor = None

while has_more:
    if next_cursor:
        query_payload["start_cursor"] = next_cursor
        
    response = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=notion_headers, json=query_payload)
    
    if response.status_code != 200:
        print(f"❌ Error al consultar Notion: {response.text}")
        exit()
        
    data = response.json()
    resultados.extend(data.get("results", []))
    
    has_more = data.get("has_more", False)
    next_cursor = data.get("next_cursor")

if not resultados:
    print("No se encontraron registros diarios para procesar del mes anterior.")
    exit()

print(f"📥 Se recuperaron {len(resultados)} registros en total para procesar.")

# --- 4. AGRUPAR Y CALCULAR POR VEHÍCULO ---
resumen_flotilla = {}

for page in resultados:
    props = page.get("properties", {})
    
    try:
        titulo_arr = props.get("Vehículo", {}).get("title", [])
        vehiculo = titulo_arr[0]["text"]["content"] if titulo_arr else "Desconocido"
    except (KeyError, IndexError):
        vehiculo = "Desconocido"
        
    fecha_registro = props.get("Fecha", {}).get("date", {}).get("start", "Sin fecha")
    km_dia = props.get("Recorrido Diario", {}).get("number") or 0.0
    odo_total = props.get("Odómetro Total", {}).get("number") or 0.0
    ruta_url = props.get("Ruta", {}).get("url") or "#"
        
    if vehiculo not in resumen_flotilla:
        resumen_flotilla[vehiculo] = {
            "km_mensual": 0.0,
            "ultimo_odometro": 0.0,
            "dias_trabajados": [],
            "page_ids_a_borrar": []
        }
        
    resumen_flotilla[vehiculo]["km_mensual"] += km_dia
    if odo_total > resumen_flotilla[vehiculo]["ultimo_odometro"]:
        resumen_flotilla[vehiculo]["ultimo_odometro"] = odo_total
        
    resumen_flotilla[vehiculo]["page_ids_a_borrar"].append(page["id"])
    resumen_flotilla[vehiculo]["dias_trabajados"].append({
        "fecha": fecha_registro,
        "km": km_dia,
        "ruta": ruta_url
    })

# --- 5. CREAR PÁGINA MAESTRA Y EJECUTAR LIMPIEZA ---
for vehiculo, datos in resumen_flotilla.items():
    print(f"\n📦 Empaquetando cierre de {vehiculo}...")
    km_mensual = round(datos["km_mensual"], 2)
    odometro_final = round(datos["ultimo_odometro"], 2)
    
    dias_ordenados = sorted(datos["dias_trabajados"], key=lambda x: x["fecha"])
    bloques_dias = []
    
    for dia in dias_ordenados:
        bloques_dias.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {"type": "text", "text": {"content": f"📅 {dia['fecha']} | Recorrido: {dia['km']} km | "}},
                    {"type": "text", "text": {"content": "Ver Mapa de Ruta", "link": {"url": dia['ruta']}} if dia['ruta'] != "#" else {"content": "Sin mapa"}}
                ]
            }
        })
        
    bloques_dias = bloques_dias[:98]

    notion_payload_mensual = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Vehículo": {"title": [{"text": {"content": f"Reporte Mensual - {vehiculo}"}}]},
            "Recorrido Diario": {"number": km_mensual},
            "Odómetro Total": {"number": odometro_final},
            "Fecha": {
                "date": {
                    "start": fecha_inicio_str,
                    "end": fecha_fin_str
                }
            }
        },
        "children": [
            {
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {"content": f"Desglose de viajes - {nombre_mes}"}}]}
            },
            {
                "object": "block",
                "type": "divider",
                "divider": {}
            }
        ] + bloques_dias
    }

    resp_mensual = requests.post("https://api.notion.com/v1/pages", headers=notion_headers, json=notion_payload_mensual)
    
    if resp_mensual.status_code == 200:
        print(f"✅ Reporte guardado: {vehiculo} ({km_mensual} km recorridos).")
        
        print(f"🧹 Limpiando {len(datos['page_ids_a_borrar'])} registros diarios de {vehiculo}...")
        errores_archivado = 0
        for page_id in datos["page_ids_a_borrar"]:
            archive_payload = {"archived": True}
            resp_arch = requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=notion_headers, json=archive_payload)
            if resp_arch.status_code != 200:
                errores_archivado += 1
                
        if errores_archivado == 0:
            print("🗑️ Todos los registros archivados con éxito.")
        else:
            print(f"⚠ {errores_archivado} registros no pudieron ser archivados.")
            
    else:
        print(f"❌ Error guardando reporte mensual de {vehiculo}: {resp_mensual.text}")

print("\n¡Cierre de mes y limpieza completados exitosamente!")