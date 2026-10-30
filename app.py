import csv
import io
import json
import os
import re
import time
import urllib.parse
from datetime import datetime
from typing import Optional, TypedDict
import streamlit as st

try:
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError
    GENAI_DISPONIBLE = True
except ImportError:
    GENAI_DISPONIBLE = False

class ResultadoClasificacion(TypedDict):
    urgencia: str
    urgencia_color: str
    categoria: str
    dispositivo: str
    falla_reportada: str
    accion_recomendada: str
    borrador_respuesta: str
    latencia_segundos: float
    cliente_nombre: str
    cliente_telefono: str

class RegistroHistorial(TypedDict):
    timestamp: str
    cliente_nombre: str
    cliente_telefono: str
    mensaje_original: str
    urgencia: str
    categoria: str
    dispositivo: str
    falla_reportada: str
    accion_recomendada: str
    borrador_respuesta: str
    latencia_segundos: float

PRESET_MESSAGES: dict[str, str] = {
    "⚠️ Reclamo de Garantía": (
        "Hola amigo, ayer recogí mi iPhone 11 que le cambiaste la pantalla "
        "y hoy ya no responde el touch en la mitad de abajo. Me urge resolverlo "
        "porque es mi herramienta de trabajo!"
    ),
    "📱 Cotización de Pantalla": (
        "Buenas tardes, cuánto me saldría el cambio de pantalla de un "
        "Samsung Galaxy A54? Se estrelló pero todavía da imagen. Tienen repuesto?"
    ),
    "⏳ Consulta de Estatus": (
        "Qué tal, disculpa la molestia. Quería saber si ya quedó listo el "
        "Xiaomi Redmi Note 12 azul que te dejé antier para cambio de centro de carga."
    ),
    "❓ Consulta Ambigua": (
        "Buenas, arreglan celulares?"
    ),
}

MODELO_ACTIVO: str = "gemini-3.8-flash"

PROMPT_SISTEMA_OPERATIVO: str = (
    "Eres el asistente de operaciones de un taller especializado en reparación de celulares y tablets.\n"
    "Tu función es analizar mensajes reales de clientes recibidos por WhatsApp para clasificar su urgencia, "
    "identificar la intención técnica y redactar una respuesta profesional.\n\n"
    "Estructura obligatoria de respuesta en formato JSON:\n"
    "{\n"
    '  "urgencia": "ALTA / GARANTÍA CRÍTICA" | "MEDIA" | "BAJA",\n'
    '  "urgencia_color": "error" | "warning" | "info",\n'
    '  "categoria": "Garantía / Reclamo" | "Cotización de Reparación" | "Estatus de Dispositivo" | "Consulta General" | "No Interpretable",\n'
    '  "dispositivo": "Marca y modelo identificado, o No especificado",\n'
    '  "falla_reportada": "Descripción del problema reportado o No identificable",\n'
    '  "accion_recomendada": "Acción que debe tomar el técnico en mostrador",\n'
    '  "borrador_respuesta": "Mensaje profesional para responder al cliente por WhatsApp"\n'
    "}\n\n"
    "Reglas estrictas de clasificación:\n"
    "1. Si el texto es incoherente, letras al azar (ejemplo: 'hhhggvv'), spam o no tiene sentido comunicativo: "
    "asigna categoria='No Interpretable', urgencia='BAJA', urgencia_color='info', dispositivo='No identificable', "
    "falla_reportada='Texto ininteligible', accion_recomendada='Ignorar o solicitar aclaración al remitente', "
    "y borrador_respuesta='Hola, hemos recibido tu mensaje pero no es claro. ¿Podrías indicarnos en qué podemos ayudarte con tu equipo?'.\n"
    "2. Si el mensaje describe una reparación previa con fallo, pantalla defectuosa tras entrega o reclama garantía: "
    "urgencia='ALTA / GARANTÍA CRÍTICA' y urgencia_color='error'.\n"
    "3. Si es una cotización o consulta de reparación en curso: urgencia='MEDIA' y urgencia_color='warning'.\n"
    "4. Si es un saludo vago o pregunta muy amplia pero comprensible: urgencia='BAJA', categoria='Consulta General' "
    "y en borrador_respuesta solicita amablemente marca, modelo y síntoma.\n"
)

def validar_coherencia_minima(texto: str) -> bool:
    texto_limpio = texto.strip()
    if len(texto_limpio) < 4:
        return False

    vocales = len(re.findall(r"[aeiouáéíóúüAEIOUÁÉÍÓÚÜ]", texto_limpio))
    if vocales == 0:
        return False

    palabras = texto_limpio.split()
    if len(palabras) == 1 and len(texto_limpio) > 8 and vocales == 1:
        return False

    return True

def resolver_datos_contacto(
    texto_mensaje: str, nombre_manual: str, telefono_manual: str
) -> tuple[str, str]:
    nombre_limpio = nombre_manual.strip()
    telefono_limpio = telefono_manual.strip()

    if not nombre_limpio or not telefono_limpio:
        patron_encabezado_whatsapp = (
            r"\[?\d{1,2}:\d{2}(?::\d{2})?(?:\s?[apAP]\.?[mM]\.?)?,?\s?\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\]?\s*([^:]+):"
        )
        coincidencia = re.search(patron_encabezado_whatsapp, texto_mensaje)
        if coincidencia:
            remitente_detectado = coincidencia.group(1).strip()
            if not telefono_limpio and re.search(r"\+?\d[\d\s-]{7,}\d", remitente_detectado):
                telefono_limpio = remitente_detectado
            elif not nombre_limpio:
                nombre_limpio = remitente_detectado

    if not telefono_limpio:
        coincidencia_tel = re.search(
            r"(\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4})", texto_mensaje
        )
        if coincidencia_tel:
            telefono_limpio = coincidencia_tel.group(1).strip()

    nombre_final = nombre_limpio if nombre_limpio else "No especificado"
    telefono_final = telefono_limpio if telefono_limpio else "No registrado"

    return nombre_final, telefono_final

def construir_enlace_whatsapp(telefono: str, texto_respuesta: str) -> str:
    digitos_telefono = re.sub(r"[^\d]", "", telefono)
    texto_codificado = urllib.parse.quote(texto_respuesta)
    if len(digitos_telefono) >= 7:
        return f"https://wa.me/{digitos_telefono}?text={texto_codificado}"
    return f"https://wa.me/?text={texto_codificado}"

def obtener_clave_gemini() -> Optional[str]:
    try:
        if "GEMINI_API_KEY" in st.secrets:
            clave = st.secrets["GEMINI_API_KEY"]
            if isinstance(clave, str) and clave.strip():
                return clave.strip()
    except Exception:
        pass

    clave_entorno = os.environ.get("GEMINI_API_KEY")
    if clave_entorno and clave_entorno.strip():
        return clave_entorno.strip()

    return None

def ejecutar_clasificacion_gemini(
    mensaje_texto: str,
    clave_api: str,
    temperatura: float = 0.2,
    nombre_cliente: str = "No especificado",
    telefono_cliente: str = "No registrado",
) -> ResultadoClasificacion:
    tiempo_inicio = time.perf_counter()
    cliente_genai = genai.Client(api_key=clave_api)

    configuracion = None
    try:
        configuracion = types.GenerateContentConfig(
            system_instruction=PROMPT_SISTEMA_OPERATIVO,
            response_mime_type="application/json",
            temperature=temperatura,
            max_output_tokens=1500,
            thinking_config=types.ThinkingConfig(thinking_level="LOW"),
        )
    except Exception:
        try:
            configuracion = types.GenerateContentConfig(
                system_instruction=PROMPT_SISTEMA_OPERATIVO,
                response_mime_type="application/json",
                temperature=temperatura,
                max_output_tokens=1500,
                thinking_config={"thinking_level": "LOW"},
            )
        except Exception:
            configuracion = types.GenerateContentConfig(
                system_instruction=PROMPT_SISTEMA_OPERATIVO,
                response_mime_type="application/json",
                temperature=temperatura,
                max_output_tokens=1500,
            )

    ultimo_error: Optional[Exception] = None
    respuesta = None

    for intento in range(2):
        try:
            respuesta = cliente_genai.models.generate_content(
                model=MODELO_ACTIVO,
                contents=f"Mensaje entrante de WhatsApp:\n\"\"\"\n{mensaje_texto}\n\"\"\"",
                config=configuracion,
            )
            if respuesta and respuesta.text:
                break
        except Exception as error_intento:
            ultimo_error = error_intento
            detalle_intento = str(error_intento)
            if ("503" in detalle_intento or "UNAVAILABLE" in detalle_intento) and intento == 0:
                time.sleep(2)
                continue
            raise error_intento

    if not respuesta or not respuesta.text:
        if ultimo_error:
            raise ultimo_error
        raise ValueError("La API de Gemini devolvió una respuesta vacía.")

    datos_json: dict[str, str] = json.loads(respuesta.text)

    urgencia = str(datos_json.get("urgencia", "BAJA"))
    color = str(datos_json.get("urgencia_color", "info"))
    if color not in ["error", "warning", "info"]:
        color = "error" if "ALTA" in urgencia else "warning" if "MEDIA" in urgencia else "info"

    latencia_total = round(time.perf_counter() - tiempo_inicio, 2)

    return {
        "urgencia": urgencia,
        "urgencia_color": color,
        "categoria": str(datos_json.get("categoria", "Consulta General")),
        "dispositivo": str(datos_json.get("dispositivo", "No especificado")),
        "falla_reportada": str(datos_json.get("falla_reportada", "Sin detalle")),
        "accion_recomendada": str(datos_json.get("accion_recomendada", "Revisión en mostrador")),
        "borrador_respuesta": str(datos_json.get("borrador_respuesta", "")),
        "latencia_segundos": latencia_total,
        "cliente_nombre": nombre_cliente,
        "cliente_telefono": telefono_cliente,
    }

def configurar_pagina() -> None:
    st.set_page_config(
        page_title="Asistente de Taller · Clasificador PyME",
        page_icon="🛠️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

def renderizar_barra_lateral() -> tuple[float, str]:
    historial: list[RegistroHistorial] = st.session_state.get("historial_mensajes", [])
    conteo_historial = len(historial)

    with st.sidebar:
        st.header("🛠️ Asistente de Taller")
        st.caption("Clasificador PyME · WhatsApp")
        st.markdown("---")

        st.subheader("🧭 Menú de Vistas")
        etiqueta_historial = f"📚 Historial ({conteo_historial})"
        opciones_menu = ["🛠️ Clasificador en Vivo", etiqueta_historial]
        vista_seleccionada = st.radio(
            "Selecciona la sección activa:",
            options=opciones_menu,
            index=0,
            label_visibility="collapsed",
        )
        modo_vista = "clasificador" if "Clasificador" in vista_seleccionada else "historial"
        st.markdown("---")

        temperatura = 0.2
        if modo_vista == "clasificador":
            st.subheader("💡 Casos de Prueba Rápida")
            st.caption("Carga un mensaje típico para probar el clasificador:")

            for nombre_ejemplo, texto_ejemplo in PRESET_MESSAGES.items():
                if st.button(nombre_ejemplo, use_container_width=True):
                    st.session_state["mensaje_input"] = texto_ejemplo

            st.markdown("---")
            st.subheader("⚙️ Parámetros del Modelo")
            temperatura = st.slider(
                "Creatividad de respuesta (Temperature):",
                min_value=0.0,
                max_value=1.0,
                value=0.2,
                step=0.1,
                help="Valores bajos (0.0-0.2) son deterministas y precisos. Valores mayores dan respuestas más creativas y variadas.",
            )
        else:
            st.subheader("📊 Resumen de Sesión")
            criticas = sum(1 for item in historial if "ALTA" in item["urgencia"])
            latencia_media = (
                round(sum(item["latencia_segundos"] for item in historial) / conteo_historial, 2)
                if conteo_historial > 0
                else 0.0
            )
            st.markdown(f"**Mensajes analizados:** {conteo_historial}")
            st.markdown(f"**Garantías o urgencias:** {criticas}")
            st.markdown(f"**Latencia promedio:** {latencia_media}s")

        st.markdown("---")
        st.subheader("📌 Acerca del Sistema")
        st.markdown(
            "Módulo de clasificación y respuesta inmediata para talleres de reparación de celulares. "
            "Procesamiento impulsado exclusivamente por **Google Gemini**."
        )

        return temperatura, modo_vista

def generar_csv_historial(historial: list[RegistroHistorial]) -> str:
    buffer = io.StringIO()
    campos = [
        "timestamp",
        "cliente_nombre",
        "cliente_telefono",
        "urgencia",
        "categoria",
        "dispositivo",
        "falla_reportada",
        "accion_recomendada",
        "borrador_respuesta",
        "latencia_segundos",
        "mensaje_original",
    ]
    escritor = csv.DictWriter(buffer, fieldnames=campos)
    escritor.writeheader()
    for fila in historial:
        escritor.writerow(fila)
    return buffer.getvalue()

def renderizar_vista_historial() -> None:
    st.title("📚 Historial de Mensajes y Casos Clasificados")
    st.markdown("Registro operativo de todas las consultas analizadas durante esta sesión de trabajo.")

    historial: list[RegistroHistorial] = st.session_state.get("historial_mensajes", [])

    if not historial:
        st.info("ℹ️ No hay registros todavía en esta sesión. Ve a la vista de **Clasificador en Vivo** desde el menú lateral para procesar tus primeros mensajes.")
        return

    col_metrica_total, col_metrica_criticas, col_metrica_latencia = st.columns(3)
    criticas = sum(1 for item in historial if "ALTA" in item["urgencia"])
    promedio_latencia = round(sum(item["latencia_segundos"] for item in historial) / len(historial), 2)

    with col_metrica_total:
        st.metric("Mensajes Analizados", len(historial))
    with col_metrica_criticas:
        st.metric("Garantías / Críticas", criticas)
    with col_metrica_latencia:
        st.metric("Latencia Promedio", f"{promedio_latencia}s")

    st.markdown("---")

    col_descargar, col_vaciar = st.columns([2, 5])
    with col_descargar:
        contenido_csv = generar_csv_historial(historial)
        st.download_button(
            label="📥 Exportar Historial (CSV)",
            data=contenido_csv,
            file_name="historial_clasificaciones_taller.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with col_vaciar:
        if st.button("🗑️ Vaciar Historial", use_container_width=False):
            st.session_state["historial_mensajes"] = []
            st.rerun()

    st.markdown("### 📋 Registro Detallado de Consultas")
    for indice, entrada in enumerate(historial):
        with st.container(border=True):
            col_encabezado_izq, col_encabezado_der = st.columns([4, 1])

            nombre = entrada["cliente_nombre"]
            telefono = entrada["cliente_telefono"]
            if nombre != "No especificado" and telefono != "No registrado":
                identificador = f"{nombre} ({telefono})"
            elif telefono != "No registrado":
                identificador = f"Tel: {telefono}"
            elif nombre != "No especificado":
                identificador = nombre
            else:
                identificador = "Cliente no identificado"

            with col_encabezado_izq:
                st.markdown(
                    f"**Caso #{len(historial) - indice}** · Hora: `{entrada['timestamp']}` | "
                    f"👤 **{identificador}** | **{entrada['urgencia']}** | {entrada['categoria']}"
                )
            with col_encabezado_der:
                st.caption(f"⚡ {entrada['latencia_segundos']}s")

            st.markdown(f"**Dispositivo:** {entrada['dispositivo']} | **Falla reportada:** {entrada['falla_reportada']}")
            st.markdown(f"**Acción recomendada en taller:** {entrada['accion_recomendada']}")
            st.caption(f"Mensaje recibido: \"{entrada['mensaje_original']}\"")

            st.text_area(
                label=f"Borrador emitido (Caso #{len(historial) - indice})",
                value=entrada["borrador_respuesta"],
                height=90,
                key=f"historial_borrador_{indice}",
                disabled=True,
            )

            enlace_wa = construir_enlace_whatsapp(telefono, entrada["borrador_respuesta"])
            st.link_button(
                label="📲 Reabrir en WhatsApp",
                url=enlace_wa,
                use_container_width=False,
                key=f"btn_wa_historial_{indice}",
            )

def renderizar_vista_clasificador(temperatura_seleccionada: float) -> None:
    st.title("🛠️ Asistente de Mensajes para Taller · Clasificador PyME")
    st.markdown(
        "Pega el texto de un mensaje recibido en WhatsApp para clasificar su urgencia operativa, "
        "extraer detalles técnicos y generar una respuesta profesional en tiempo real."
    )

    col_nombre, col_telefono = st.columns(2)
    with col_nombre:
        nombre_ingresado = st.text_input(
            "👤 Nombre del cliente (opcional):",
            value=st.session_state.get("cliente_nombre_input", ""),
            placeholder="Ej: Juan Pérez",
            key="cliente_nombre_input",
        )
    with col_telefono:
        telefono_ingresado = st.text_input(
            "📱 Teléfono de WhatsApp (opcional):",
            value=st.session_state.get("cliente_telefono_input", ""),
            placeholder="Ej: +52 55 1234 5678 (con lada)",
            key="cliente_telefono_input",
        )

    mensaje_actual = st.text_area(
        label="💬 Mensaje recibido del cliente:",
        value=st.session_state["mensaje_input"],
        height=140,
        placeholder="Ej: Hola buenas, cuánto me cobran por cambiarle la pantalla a un Samsung A54?...",
    )

    columna_analizar, columna_limpiar = st.columns([1, 4])
    with columna_analizar:
        boton_analizar = st.button("⚡ Clasificar Mensaje", type="primary", use_container_width=True)
    with columna_limpiar:
        if st.button("🗑️ Limpiar", use_container_width=False):
            st.session_state["mensaje_input"] = ""
            st.session_state["cliente_nombre_input"] = ""
            st.session_state["cliente_telefono_input"] = ""
            st.session_state["resultado_actual"] = None
            st.rerun()

    if boton_analizar:
        texto_a_evaluar = mensaje_actual.strip()

        if not texto_a_evaluar:
            st.warning("⚠️ El campo está vacío. Pega o escribe un mensaje antes de presionar Clasificar.")
            return

        if not validar_coherencia_minima(texto_a_evaluar):
            st.error("⚠️ **Mensaje no interpretable:** El texto ingresado no contiene palabras o frases comprensibles. Por favor, introduce una consulta legítima de WhatsApp.")
            return

        clave_api = obtener_clave_gemini()
        if not clave_api:
            st.error(
                "🔒 **Servicio no configurado:** No se detectó la clave de API `GEMINI_API_KEY`. "
                "Para procesar mensajes en vivo, debes registrar el secreto en el panel de Streamlit Cloud "
                "o en tu entorno local."
            )
            return

        if not GENAI_DISPONIBLE:
            st.error("❌ **Dependencia faltante:** El SDK `google-genai` no está instalado en este entorno.")
            return

        nombre_resuelto, telefono_resuelto = resolver_datos_contacto(
            texto_a_evaluar, nombre_ingresado, telefono_ingresado
        )

        try:
            with st.spinner("🤖 Analizando mensaje con Google Gemini..."):
                resultado = ejecutar_clasificacion_gemini(
                    mensaje_texto=texto_a_evaluar,
                    clave_api=clave_api,
                    temperatura=temperatura_seleccionada,
                    nombre_cliente=nombre_resuelto,
                    telefono_cliente=telefono_resuelto,
                )
                st.session_state["resultado_actual"] = resultado

                registro_nuevo: RegistroHistorial = {
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "cliente_nombre": nombre_resuelto,
                    "cliente_telefono": telefono_resuelto,
                    "mensaje_original": texto_a_evaluar,
                    "urgencia": resultado["urgencia"],
                    "categoria": resultado["categoria"],
                    "dispositivo": resultado["dispositivo"],
                    "falla_reportada": resultado["falla_reportada"],
                    "accion_recomendada": resultado["accion_recomendada"],
                    "borrador_respuesta": resultado["borrador_respuesta"],
                    "latencia_segundos": resultado["latencia_segundos"],
                }
                st.session_state["historial_mensajes"].insert(0, registro_nuevo)

        except APIError as error_api:
            detalle = str(error_api)
            if "RESOURCE_EXHAUSTED" in detalle or "429" in detalle or getattr(error_api, "code", None) == 429:
                st.error("⏳ **Límite de cuota alcanzado (429):** El servicio de Gemini ha recibido demasiadas peticiones por minuto. Espera 60 segundos antes de reenviar.")
            elif "UNAVAILABLE" in detalle or "503" in detalle or getattr(error_api, "code", None) == 503:
                st.error("⏳ **Servidores de Gemini saturados (503):** Google está experimentando alta demanda en este momento. Por favor, reintenta en unos instantes.")
            elif "API_KEY_INVALID" in detalle or "400" in detalle or getattr(error_api, "code", None) == 400:
                st.error("🔑 **Clave no válida:** La clave de API configurada fue rechazada por Google AI Studio. Verifica tus credenciales.")
            else:
                st.error(f"⚠️ **Error en servicio de IA:** {detalle}")
            return
        except json.JSONDecodeError:
            st.error("⚠️ **Fallo de deserialización:** La IA no generó una respuesta JSON válida. Intenta de nuevo.")
            return
        except Exception as error_general:
            st.error(f"📡 **Error inesperado de comunicación:** {error_general}")
            return

    resultado_activo = st.session_state.get("resultado_actual")
    if resultado_activo:
        if resultado_activo["categoria"] == "No Interpretable":
            st.warning("⚠️ **Mensaje no concluyente:** La IA determinó que el texto no contiene una consulta técnica o comercial reconocible.")
            st.caption("Borrador sugerido para pedir aclaración:")
            borrador_aclaracion = st.text_area(
                label="Borrador editable de aclaración",
                value=resultado_activo["borrador_respuesta"],
                height=100,
                label_visibility="collapsed",
                key="borrador_no_interpretable",
            )
            enlace_aclaracion = construir_enlace_whatsapp(
                resultado_activo.get("cliente_telefono", "No registrado"),
                borrador_aclaracion,
            )
            st.link_button(
                label="📲 Abrir y Enviar en WhatsApp",
                url=enlace_aclaracion,
                type="primary",
                use_container_width=False,
            )
        else:
            st.markdown("---")
            col_titulo, col_latencia = st.columns([3, 1])
            with col_titulo:
                st.subheader("📋 Resultado de la Clasificación")
            with col_latencia:
                st.caption(f"⚡ Inferencia: {resultado_activo['latencia_segundos']}s")

            col_urgencia, col_categoria = st.columns(2)
            with col_urgencia:
                if resultado_activo["urgencia_color"] == "error":
                    st.error(f"**Urgencia:** {resultado_activo['urgencia']}")
                elif resultado_activo["urgencia_color"] == "warning":
                    st.warning(f"**Urgencia:** {resultado_activo['urgencia']}")
                else:
                    st.info(f"**Urgencia:** {resultado_activo['urgencia']}")

            with col_categoria:
                st.success(f"**Categoría:** {resultado_activo['categoria']}")

            col_cliente, col_dispositivo = st.columns(2)
            with col_cliente:
                cliente_nom = resultado_activo.get("cliente_nombre", "No especificado")
                cliente_tel = resultado_activo.get("cliente_telefono", "No registrado")
                st.markdown(f"**👤 Cliente:** {cliente_nom} | **Tel:** {cliente_tel}")
                st.markdown(f"**⚠️ Falla reportada:** {resultado_activo['falla_reportada']}")
            with col_dispositivo:
                st.markdown(f"**📱 Dispositivo identificado:** {resultado_activo['dispositivo']}")
                st.markdown(f"**🎯 Acción recomendada en taller:** {resultado_activo['accion_recomendada']}")

            st.markdown("### ✍️ Borrador de Respuesta para WhatsApp")
            st.caption("Puedes previsualizar, editar o pulsar directamente para abrir la conversación en WhatsApp:")
            borrador_actualizado = st.text_area(
                label="Borrador de respuesta editable",
                value=resultado_activo["borrador_respuesta"],
                height=130,
                label_visibility="collapsed",
                key="borrador_respuesta_whatsapp",
            )

            telefono_destino = resultado_activo.get("cliente_telefono", "No registrado")
            enlace_wa = construir_enlace_whatsapp(telefono_destino, borrador_actualizado)

            col_btn_wa, col_nota_wa = st.columns([1, 2])
            with col_btn_wa:
                st.link_button(
                    label="📲 Abrir y Enviar en WhatsApp",
                    url=enlace_wa,
                    type="primary",
                    use_container_width=True,
                )
            with col_nota_wa:
                if telefono_destino != "No registrado":
                    st.caption(f"Abre WhatsApp con el chat de **{telefono_destino}** y la respuesta precargada.")
                else:
                    st.caption("Abre WhatsApp para que elijas a cuál cliente enviar la respuesta precargada.")

def main() -> None:
    configurar_pagina()

    if "mensaje_input" not in st.session_state:
        st.session_state["mensaje_input"] = ""

    if "cliente_nombre_input" not in st.session_state:
        st.session_state["cliente_nombre_input"] = ""

    if "cliente_telefono_input" not in st.session_state:
        st.session_state["cliente_telefono_input"] = ""

    if "resultado_actual" not in st.session_state:
        st.session_state["resultado_actual"] = None

    if "historial_mensajes" not in st.session_state:
        st.session_state["historial_mensajes"] = []

    temperatura_seleccionada, modo_vista = renderizar_barra_lateral()

    if modo_vista == "historial":
        renderizar_vista_historial()
    else:
        renderizar_vista_clasificador(temperatura_seleccionada)

if __name__ == "__main__":
    main()
