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
    nivel_thinking: str
    tokens_limite: int
    metodo: str
    taller: str

class RegistroHistorial(TypedDict):
    timestamp: str
    taller: str
    metodo: str
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
    nivel_thinking: str
    tokens_limite: int

TALLERES_REGISTRADOS: dict[str, dict[str, str]] = {
    "Taller Central · FixLab": {
        "pin": "1234",
        "direccion": "Av. Principal #450, Centro",
        "encargado": "Téc. Gabriel Durón",
    },
    "Sucursal Norte · Mobile Express": {
        "pin": "4321",
        "direccion": "Plaza Norte, Local 12",
        "encargado": "Téc. Roberto Gómez",
    },
}

PRESET_MESSAGES: dict[str, dict[str, str]] = {
    "⚠️ Reclamo de Garantía": {
        "nombre": "Roberto Gómez",
        "telefono": "+525512345678",
        "texto": (
            "Hola amigo, ayer recogí mi iPhone 11 que le cambiaste la pantalla "
            "y hoy ya no responde el touch en la mitad de abajo. Me urge resolverlo "
            "porque es mi herramienta de trabajo!"
        ),
    },
    "📱 Cotización de Pantalla": {
        "nombre": "Ana Morales",
        "telefono": "+525587654321",
        "texto": (
            "Buenas tardes, cuánto me saldría el cambio de pantalla de un "
            "Samsung Galaxy A54? Se estrelló pero todavía da imagen. Tienen repuesto?"
        ),
    },
    "⏳ Consulta de Estatus": {
        "nombre": "Luis Hernández",
        "telefono": "+525599887766",
        "texto": (
            "Qué tal, disculpa la molestia. Quería saber si ya quedó listo el "
            "Xiaomi Redmi Note 12 azul que te dejé antier para cambio de centro de carga."
        ),
    },
    "❓ Consulta Ambigua": {
        "nombre": "",
        "telefono": "",
        "texto": "Buenas, arreglan celulares?",
    },
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

ESTILO_CSS_TALLER: str = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
    }

    .header-terminal {
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.95) 0%, rgba(30, 41, 59, 0.85) 100%);
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-radius: 14px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1.5rem;
        box-shadow: 0 8px 24px -4px rgba(0, 0, 0, 0.35);
    }

    .tag-lab {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        background: rgba(56, 189, 248, 0.12);
        color: #38bdf8;
        border: 1px solid rgba(56, 189, 248, 0.35);
        padding: 0.25rem 0.65rem;
        border-radius: 9999px;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        font-family: 'JetBrains Mono', monospace;
    }

    .badge-chip {
        display: inline-block;
        padding: 0.35rem 0.85rem;
        border-radius: 9999px;
        font-size: 0.82rem;
        font-weight: 700;
        letter-spacing: 0.02em;
    }

    .badge-alta {
        background: rgba(239, 68, 68, 0.18);
        color: #f87171;
        border: 1px solid #ef4444;
    }

    .badge-media {
        background: rgba(245, 158, 11, 0.18);
        color: #fbbf24;
        border: 1px solid #f59e0b;
    }

    .badge-baja {
        background: rgba(56, 189, 248, 0.18);
        color: #38bdf8;
        border: 1px solid #0284c7;
    }

    .telemetria-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        background: rgba(15, 23, 42, 0.8);
        border: 1px solid rgba(148, 163, 184, 0.2);
        color: #94a3b8;
        padding: 0.3rem 0.7rem;
        border-radius: 8px;
        font-size: 0.78rem;
        font-family: 'JetBrains Mono', monospace;
    }

    .card-taller {
        background: rgba(30, 41, 59, 0.55);
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 12px;
        padding: 1.1rem 1.3rem;
        margin-bottom: 1rem;
    }

    .pin-display {
        background: #0f172a;
        border: 2px solid #38bdf8;
        border-radius: 12px;
        padding: 1rem;
        text-align: center;
        font-size: 2rem;
        font-weight: 800;
        letter-spacing: 0.5em;
        color: #38bdf8;
        margin-bottom: 1rem;
        font-family: 'JetBrains Mono', monospace;
    }
</style>
"""

def aplicar_estilos_taller() -> None:
    st.markdown(ESTILO_CSS_TALLER, unsafe_allow_html=True)

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
    nivel_thinking: str = "LOW",
    limite_tokens: int = 1500,
    nombre_cliente: str = "No especificado",
    telefono_cliente: str = "No registrado",
    taller_origen: str = "Taller Central · FixLab",
) -> ResultadoClasificacion:
    tiempo_inicio = time.perf_counter()
    cliente_genai = genai.Client(api_key=clave_api)

    configuracion = None
    try:
        configuracion = types.GenerateContentConfig(
            system_instruction=PROMPT_SISTEMA_OPERATIVO,
            response_mime_type="application/json",
            temperature=temperatura,
            max_output_tokens=limite_tokens,
            thinking_config=types.ThinkingConfig(thinking_level=nivel_thinking),
        )
    except Exception:
        try:
            configuracion = types.GenerateContentConfig(
                system_instruction=PROMPT_SISTEMA_OPERATIVO,
                response_mime_type="application/json",
                temperature=temperatura,
                max_output_tokens=limite_tokens,
                thinking_config={"thinking_level": nivel_thinking},
            )
        except Exception:
            configuracion = types.GenerateContentConfig(
                system_instruction=PROMPT_SISTEMA_OPERATIVO,
                response_mime_type="application/json",
                temperature=temperatura,
                max_output_tokens=limite_tokens,
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
        "nivel_thinking": nivel_thinking,
        "tokens_limite": limite_tokens,
        "metodo": "🤖 Gemini 3.8 Flash",
        "taller": taller_origen,
    }

def configurar_pagina() -> None:
    st.set_page_config(
        page_title="TallerFix OS · Terminal de Triaje",
        page_icon="🛠️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

def renderizar_pantalla_login_pin() -> None:
    aplicar_estilos_taller()

    st.markdown(
        """
        <div style="max-width: 480px; margin: 2rem auto 1rem auto; text-align: center;">
            <span class="tag-lab">🔐 CONTROL DE ACCESO</span>
            <h2 style="margin: 0.5rem 0 0.2rem 0; font-weight: 800;">TallerFix Console</h2>
            <p style="color: #94a3b8; font-size: 0.9rem;">
                Selecciona tu taller y digita tu PIN de 4 dígitos para abrir turno de servicio.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_izq, col_centro, col_der = st.columns([1, 2, 1])
    with col_centro:
        with st.container(border=True):
            taller_elegido = st.selectbox(
                "🏢 Selecciona el Taller / Sucursal:",
                options=list(TALLERES_REGISTRADOS.keys()),
                index=0,
                key="login_taller_selector",
            )
            st.session_state["taller_activo"] = taller_elegido
            datos_taller = TALLERES_REGISTRADOS[taller_elegido]

            st.caption(f"📍 {datos_taller['direccion']} · Encargado: {datos_taller['encargado']}")

            pin_actual = st.session_state.get("pin_buffer", "")
            simbolos_pin = " ".join(["●" for _ in pin_actual] + ["○" for _ in range(4 - len(pin_actual))])

            st.markdown(f"<div class='pin-display'>{simbolos_pin}</div>", unsafe_allow_html=True)

            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("1", use_container_width=True, key="pin_1"):
                    if len(pin_actual) < 4:
                        st.session_state["pin_buffer"] += "1"
                        st.rerun()
            with col2:
                if st.button("2", use_container_width=True, key="pin_2"):
                    if len(pin_actual) < 4:
                        st.session_state["pin_buffer"] += "2"
                        st.rerun()
            with col3:
                if st.button("3", use_container_width=True, key="pin_3"):
                    if len(pin_actual) < 4:
                        st.session_state["pin_buffer"] += "3"
                        st.rerun()

            col4, col5, col6 = st.columns(3)
            with col4:
                if st.button("4", use_container_width=True, key="pin_4"):
                    if len(pin_actual) < 4:
                        st.session_state["pin_buffer"] += "4"
                        st.rerun()
            with col5:
                if st.button("5", use_container_width=True, key="pin_5"):
                    if len(pin_actual) < 4:
                        st.session_state["pin_buffer"] += "5"
                        st.rerun()
            with col6:
                if st.button("6", use_container_width=True, key="pin_6"):
                    if len(pin_actual) < 4:
                        st.session_state["pin_buffer"] += "6"
                        st.rerun()

            col7, col8, col9 = st.columns(3)
            with col7:
                if st.button("7", use_container_width=True, key="pin_7"):
                    if len(pin_actual) < 4:
                        st.session_state["pin_buffer"] += "7"
                        st.rerun()
            with col8:
                if st.button("8", use_container_width=True, key="pin_8"):
                    if len(pin_actual) < 4:
                        st.session_state["pin_buffer"] += "8"
                        st.rerun()
            with col9:
                if st.button("9", use_container_width=True, key="pin_9"):
                    if len(pin_actual) < 4:
                        st.session_state["pin_buffer"] += "9"
                        st.rerun()

            col_borrar, col0, col_entrar = st.columns(3)
            with col_borrar:
                if st.button("⌫ Borrar", use_container_width=True, key="pin_del"):
                    st.session_state["pin_buffer"] = ""
                    st.rerun()
            with col0:
                if st.button("0", use_container_width=True, key="pin_0"):
                    if len(pin_actual) < 4:
                        st.session_state["pin_buffer"] += "0"
                        st.rerun()
            with col_entrar:
                if st.button("🔓 Entrar", type="primary", use_container_width=True, key="pin_enter"):
                    if st.session_state["pin_buffer"] == datos_taller["pin"]:
                        st.session_state["usuario_autenticado"] = True
                        st.session_state["pin_buffer"] = ""
                        st.rerun()
                    else:
                        st.error("❌ PIN incorrecto. Intenta nuevamente.")
                        st.session_state["pin_buffer"] = ""

            st.markdown("---")
            st.info(f"💡 **PIN demostrativo para evaluación:** `{datos_taller['pin']}`")

            if st.button("⚡ Acceso Rápido Modo Evaluador (1 Clic)", type="secondary", use_container_width=True):
                st.session_state["usuario_autenticado"] = True
                st.session_state["pin_buffer"] = ""
                st.rerun()

def renderizar_barra_lateral() -> tuple[float, str, int, str]:
    historial: list[RegistroHistorial] = st.session_state.get("historial_mensajes", [])
    conteo_historial = len(historial)
    taller_activo = st.session_state.get("taller_activo", "Taller Central · FixLab")
    datos_taller = TALLERES_REGISTRADOS.get(taller_activo, list(TALLERES_REGISTRADOS.values())[0])

    with st.sidebar:
        st.markdown(
            f"""
            <div style="padding: 0.2rem 0 0.8rem 0;">
                <span class="tag-lab">⚡ SESIÓN ACTIVA</span>
                <h3 style="margin: 0.35rem 0 0.1rem 0; font-size: 1.15rem; font-weight: 800;">{taller_activo}</h3>
                <span style="font-size: 0.8rem; color: #94a3b8;">👨‍🔧 {datos_taller['encargado']}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("🚪 Cerrar Turno / Cambiar Taller", use_container_width=True):
            st.session_state["usuario_autenticado"] = False
            st.session_state["pin_buffer"] = ""
            st.rerun()

        st.markdown("---")

        st.subheader("🧭 Navegación")
        etiqueta_historial = f"📚 Registro Histórico ({conteo_historial})"
        opciones_menu = ["🛠️ Terminal de Triaje", etiqueta_historial]
        vista_seleccionada = st.radio(
            "Selecciona la sección activa:",
            options=opciones_menu,
            index=0,
            label_visibility="collapsed",
        )
        modo_vista = "clasificador" if "Terminal" in vista_seleccionada else "historial"
        st.markdown("---")

        temperatura = 0.2
        nivel_thinking = "LOW"
        limite_tokens = 1500

        if modo_vista == "clasificador":
            st.subheader("⚙️ Motor de Inferencia IA")

            temperatura = st.slider(
                "Creatividad de respuesta (Temperature):",
                min_value=0.0,
                max_value=1.0,
                value=0.2,
                step=0.1,
                help="Valores bajos (0.0-0.2) son deterministas y precisos. Valores mayores dan respuestas más creativas y variadas.",
            )

            opcion_thinking = st.select_slider(
                "Nivel de razonamiento (Thinking):",
                options=["LOW (Rápido)", "MEDIUM (Equilibrado)", "HIGH (Profundo)"],
                value="LOW (Rápido)",
                help="Controla la profundidad del razonamiento interno del modelo. LOW minimiza la latencia para respuestas inmediatas; MEDIUM y HIGH incrementan el análisis pero aumentan el tiempo de espera.",
            )
            mapeo_thinking = {
                "LOW (Rápido)": "LOW",
                "MEDIUM (Equilibrado)": "MEDIUM",
                "HIGH (Profundo)": "HIGH",
            }
            nivel_thinking = mapeo_thinking[opcion_thinking]

            limite_tokens = st.slider(
                "Límite de tokens de salida:",
                min_value=1000,
                max_value=3000,
                value=1500,
                step=100,
                help="Mínimo seguro fijado en 1000 tokens por norma del curso: evita que el razonamiento interno de Gemini agote el cupo y devuelva una respuesta JSON vacía o truncada.",
            )

        else:
            st.subheader("📊 Métricas de Operación")
            criticas = sum(1 for item in historial if "ALTA" in item["urgencia"])
            latencia_media = (
                round(sum(item["latencia_segundos"] for item in historial if item["metodo"] != "✍️ Registro Manual") /
                      max(1, sum(1 for item in historial if item["metodo"] != "✍️ Registro Manual")), 2)
            )
            st.markdown(f"**Total casos atendidos:** `{conteo_historial}`")
            st.markdown(f"**Garantías o urgencias:** `{criticas}`")
            st.markdown(f"**Latencia media de IA:** `{latencia_media}s`")

        st.markdown("---")
        st.markdown(
            """
            <div style="font-size: 0.78rem; color: #64748b; line-height: 1.4;">
                <strong>Módulo:</strong> Fundamentos de Programación para IA<br>
                <strong>Máster en IA:</strong> OBS Business School<br>
                <strong>Backend:</strong> Google Gemini 3.8 Flash
            </div>
            """,
            unsafe_allow_html=True,
        )

        return temperatura, nivel_thinking, limite_tokens, modo_vista

def generar_csv_historial(historial: list[RegistroHistorial]) -> str:
    buffer = io.StringIO()
    campos = [
        "timestamp",
        "taller",
        "metodo",
        "cliente_nombre",
        "cliente_telefono",
        "urgencia",
        "categoria",
        "dispositivo",
        "falla_reportada",
        "accion_recomendada",
        "borrador_respuesta",
        "latencia_segundos",
        "nivel_thinking",
        "tokens_limite",
        "mensaje_original",
    ]
    escritor = csv.DictWriter(buffer, fieldnames=campos)
    escritor.writeheader()
    for fila in historial:
        escritor.writerow(fila)
    return buffer.getvalue()

def renderizar_encabezado_principal() -> None:
    taller_activo = st.session_state.get("taller_activo", "Taller Central · FixLab")
    st.markdown(
        f"""
        <div class="header-terminal">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 0.8rem;">
                <div>
                    <span class="tag-lab">🔧 {taller_activo.upper()}</span>
                    <h1 style="margin: 0.35rem 0 0.2rem 0; font-size: 1.85rem; font-weight: 800; letter-spacing: -0.02em;">
                        Asistente de Triaje Técnico y Respuestas para WhatsApp
                    </h1>
                    <p style="margin: 0; color: #94a3b8; font-size: 0.92rem;">
                        Clasifica incidencias de reparación, diagnostica fallas y redacta respuestas comerciales listas para enviar.
                    </p>
                </div>
                <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
                    <span class="telemetria-pill">🟢 Taller Online</span>
                    <span class="telemetria-pill">🤖 Gemini 3.8 Flash</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def renderizar_vista_historial() -> None:
    renderizar_encabezado_principal()

    st.subheader("📚 Registro Histórico de Casos Atendidos")
    st.caption("Control operativo de todas las consultas analizadas o registradas manualmente durante la sesión.")

    historial: list[RegistroHistorial] = st.session_state.get("historial_mensajes", [])

    if not historial:
        st.info("ℹ️ No hay registros todavía en esta sesión. Ve a la **Terminal de Triaje** desde el menú lateral para procesar o registrar mensajes.")
        return

    col_metrica_total, col_metrica_criticas, col_metrica_latencia, col_metrica_manuales = st.columns(4)
    criticas = sum(1 for item in historial if "ALTA" in item["urgencia"])
    manuales = sum(1 for item in historial if "Manual" in item["metodo"])
    ia_items = [item["latencia_segundos"] for item in historial if "Manual" not in item["metodo"]]
    promedio_latencia = round(sum(ia_items) / len(ia_items), 2) if ia_items else 0.0

    with col_metrica_total:
        st.metric("Casos Registrados", len(historial))
    with col_metrica_criticas:
        st.metric("Garantías / Críticas", criticas)
    with col_metrica_latencia:
        st.metric("Latencia Media IA", f"{promedio_latencia}s")
    with col_metrica_manuales:
        st.metric("Registros Manuales", manuales)

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
        if st.button("🗑️ Vaciar Historial de Sesión", use_container_width=False):
            st.session_state["historial_mensajes"] = []
            st.rerun()

    st.markdown("### 📋 Fichas Detalladas")
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

            urgencia_clase = (
                "badge-alta" if "ALTA" in entrada["urgencia"] else "badge-media" if "MEDIA" in entrada["urgencia"] else "badge-baja"
            )

            with col_encabezado_izq:
                st.markdown(
                    f"**Caso #{len(historial) - indice}** · `{entrada['timestamp']}` · **{entrada['taller']}** · *{entrada['metodo']}* | "
                    f"👤 **{identificador}** | <span class='badge-chip {urgencia_clase}'>{entrada['urgencia']}</span> | "
                    f"**{entrada['categoria']}**",
                    unsafe_allow_html=True,
                )
            with col_encabezado_der:
                if "Manual" in entrada["metodo"]:
                    st.caption("✍️ Manual")
                else:
                    st.caption(f"⚡ {entrada['latencia_segundos']}s · {entrada['nivel_thinking']}")

            col_dev, col_act = st.columns(2)
            with col_dev:
                st.markdown(f"**📱 Dispositivo:** {entrada['dispositivo']} · **Falla:** {entrada['falla_reportada']}")
            with col_act:
                st.markdown(f"**🎯 Acción en taller:** {entrada['accion_recomendada']}")

            st.caption(f"Mensaje registrado: \"{entrada['mensaje_original']}\"")

            st.text_area(
                label=f"Respuesta generada (Caso #{len(historial) - indice})",
                value=entrada["borrador_respuesta"],
                height=85,
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

def renderizar_modo_ia(
    temperatura_seleccionada: float,
    nivel_thinking_seleccionado: str,
    limite_tokens_seleccionado: int,
) -> None:
    st.markdown("#### ⚡ Carga Rápida de Mensajes Típicos")
    st.caption("Haz clic en cualquier caso para precargar el mensaje y datos de prueba:")

    cols_presets = st.columns(4)
    for idx, (nombre_preset, datos_preset) in enumerate(PRESET_MESSAGES.items()):
        with cols_presets[idx % 4]:
            if st.button(nombre_preset, use_container_width=True, key=f"preset_btn_{idx}"):
                st.session_state["mensaje_input"] = datos_preset["texto"]
                st.session_state["cliente_nombre_input"] = datos_preset["nombre"]
                st.session_state["cliente_telefono_input"] = datos_preset["telefono"]
                st.rerun()

    st.markdown("---")

    col_nombre, col_telefono = st.columns(2)
    with col_nombre:
        nombre_ingresado = st.text_input(
            "👤 Nombre del cliente (opcional):",
            value=st.session_state.get("cliente_nombre_input", ""),
            placeholder="Ej: Juan Pérez",
            key="input_ia_nombre",
        )
    with col_telefono:
        telefono_ingresado = st.text_input(
            "📱 Teléfono de WhatsApp (opcional):",
            value=st.session_state.get("cliente_telefono_input", ""),
            placeholder="Ej: +52 55 1234 5678",
            key="input_ia_telefono",
        )

    mensaje_actual = st.text_area(
        label="💬 Mensaje de WhatsApp copiado del cliente:",
        value=st.session_state.get("mensaje_input", ""),
        height=130,
        placeholder="Pega aquí el mensaje del cliente (ej: Hola buenas, cuánto cobran por cambiar la pantalla de un Samsung A54?)...",
        key="input_ia_mensaje",
    )

    columna_analizar, columna_limpiar = st.columns([1, 4])
    with columna_analizar:
        boton_analizar = st.button("🤖 Clasificar con Gemini IA", type="primary", use_container_width=True)
    with columna_limpiar:
        if st.button("🗑️ Limpiar Campos", use_container_width=False, key="btn_limpiar_ia"):
            st.session_state["mensaje_input"] = ""
            st.session_state["cliente_nombre_input"] = ""
            st.session_state["cliente_telefono_input"] = ""
            st.session_state["resultado_actual"] = None
            st.rerun()

    taller_activo = st.session_state.get("taller_activo", "Taller Central · FixLab")

    if boton_analizar:
        texto_a_evaluar = mensaje_actual.strip()

        if not texto_a_evaluar:
            st.warning("⚠️ El campo está vacío. Pega o escribe un mensaje antes de presionar Clasificar.")
            return

        if not validar_coherencia_minima(texto_a_evaluar):
            st.error("⚠️ **Mensaje no interpretable:** El texto ingresado no contiene palabras o frases comprensibles. Introduce una consulta legítima de WhatsApp.")
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
            with st.spinner("⚡ Analizando con Google Gemini 3.8 Flash..."):
                resultado = ejecutar_clasificacion_gemini(
                    mensaje_texto=texto_a_evaluar,
                    clave_api=clave_api,
                    temperatura=temperatura_seleccionada,
                    nivel_thinking=nivel_thinking_seleccionado,
                    limite_tokens=limite_tokens_seleccionado,
                    nombre_cliente=nombre_resuelto,
                    telefono_cliente=telefono_resuelto,
                    taller_origen=taller_activo,
                )
                st.session_state["resultado_actual"] = resultado

                registro_nuevo: RegistroHistorial = {
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "taller": taller_activo,
                    "metodo": "🤖 Gemini 3.8 Flash",
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
                    "nivel_thinking": resultado["nivel_thinking"],
                    "tokens_limite": resultado["tokens_limite"],
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
        st.markdown("---")

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
            urg_estilo = (
                "badge-alta" if "ALTA" in resultado_activo["urgencia"] else "badge-media" if "MEDIA" in resultado_activo["urgencia"] else "badge-baja"
            )

            st.markdown(
                f"""
                <div class="card-taller">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.8rem;">
                        <div style="display: flex; gap: 0.5rem; align-items: center;">
                            <span class="badge-chip {urg_estilo}">{resultado_activo['urgencia']}</span>
                            <span style="font-weight: 700; color: #f1f5f9; font-size: 0.95rem;">🏷️ {resultado_activo['categoria']}</span>
                        </div>
                        <span class="telemetria-pill">⚡ Inferencia: {resultado_activo['latencia_segundos']}s · {resultado_activo['nivel_thinking']} ({resultado_activo['tokens_limite']}t)</span>
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; color: #cbd5e1; font-size: 0.9rem;">
                        <div>
                            <strong>🏢 Taller:</strong> {resultado_activo['taller']}<br>
                            <strong>👤 Cliente:</strong> {resultado_activo['cliente_nombre']} &nbsp;|&nbsp; <strong>📱 Tel:</strong> {resultado_activo['cliente_telefono']}<br>
                            <strong>⚠️ Falla reportada:</strong> {resultado_activo['falla_reportada']}
                        </div>
                        <div>
                            <strong>📱 Dispositivo:</strong> {resultado_activo['dispositivo']}<br>
                            <strong>🎯 Acción recomendada:</strong> {resultado_activo['accion_recomendada']}
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown("##### ✍️ Borrador de Respuesta para WhatsApp")
            st.caption("Previsualiza o ajusta el mensaje antes de enviarlo al chat:")
            borrador_actualizado = st.text_area(
                label="Borrador de respuesta editable",
                value=resultado_activo["borrador_respuesta"],
                height=125,
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

def renderizar_modo_manual() -> None:
    taller_activo = st.session_state.get("taller_activo", "Taller Central · FixLab")

    st.markdown("#### ✍️ Registro de Mostrador y Triaje Manual")
    st.caption(f"Ingresa y clasifica un caso directamente en el mostrador para **{taller_activo}**:")

    col_nom, col_tel = st.columns(2)
    with col_nom:
        nombre_manual = st.text_input(
            "👤 Nombre del cliente:",
            placeholder="Ej: Laura Sánchez",
            key="manual_nombre",
        )
    with col_tel:
        telefono_manual = st.text_input(
            "📱 Teléfono de WhatsApp (con lada):",
            placeholder="Ej: +525544332211",
            key="manual_telefono",
        )

    col_urg, col_cat = st.columns(2)
    with col_urg:
        urgencia_opcion = st.selectbox(
            "⚡ Nivel de Urgencia:",
            options=["MEDIA", "ALTA / GARANTÍA CRÍTICA", "BAJA"],
            index=0,
            key="manual_urgencia",
        )
    with col_cat:
        categoria_opcion = st.selectbox(
            "🏷️ Categoría de Solicitud:",
            options=[
                "Cotización de Reparación",
                "Estatus de Dispositivo",
                "Garantía / Reclamo",
                "Consulta General",
            ],
            index=0,
            key="manual_categoria",
        )

    col_dev, col_falla = st.columns(2)
    with col_dev:
        dispositivo_manual = st.text_input(
            "📱 Dispositivo (Marca y modelo):",
            placeholder="Ej: iPhone 13 Pro Max",
            key="manual_dispositivo",
        )
    with col_falla:
        falla_manual = st.text_input(
            "⚠️ Falla o síntoma reportado:",
            placeholder="Ej: No carga, centro de carga flojo",
            key="manual_falla",
        )

    accion_manual = st.text_input(
        "🎯 Acción a tomar en taller:",
        value="Revisión técnica en mostrador y apertura de orden de servicio",
        key="manual_accion",
    )

    notas_cliente = st.text_area(
        "💬 Mensaje o resumen del cliente:",
        placeholder="Texto del cliente o descripción breve anotada por el técnico...",
        height=90,
        key="manual_notas",
    )

    plantilla_borrador_default = (
        f"Hola {nombre_manual.strip() if nombre_manual.strip() else ''}, "
        f"recibimos tu solicitud en {taller_activo} para el equipo {dispositivo_manual.strip() if dispositivo_manual.strip() else 'reportado'}. "
        "Con gusto lo revisamos en mostrador para darte un diagnóstico formal. ¿Te gustaría agendar tu entrega hoy?"
    )

    st.markdown("##### ✍️ Borrador de Respuesta para WhatsApp")
    borrador_manual = st.text_area(
        label="Borrador manual editable",
        value=plantilla_borrador_default,
        height=110,
        key="manual_borrador",
    )

    col_guardar, col_enviar_wa = st.columns([1, 2])
    with col_guardar:
        if st.button("💾 Guardar en Historial", type="primary", use_container_width=True):
            nom_final = nombre_manual.strip() if nombre_manual.strip() else "No especificado"
            tel_final = telefono_manual.strip() if telefono_manual.strip() else "No registrado"
            dev_final = dispositivo_manual.strip() if dispositivo_manual.strip() else "No especificado"
            fall_final = falla_manual.strip() if falla_manual.strip() else "Sin detalle"
            msg_final = notas_cliente.strip() if notas_cliente.strip() else "Registro manual de mostrador"

            registro_nuevo: RegistroHistorial = {
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "taller": taller_activo,
                "metodo": "✍️ Registro Manual",
                "cliente_nombre": nom_final,
                "cliente_telefono": tel_final,
                "mensaje_original": msg_final,
                "urgencia": urgencia_opcion,
                "categoria": categoria_opcion,
                "dispositivo": dev_final,
                "falla_reportada": fall_final,
                "accion_recomendada": accion_manual.strip(),
                "borrador_respuesta": borrador_manual.strip(),
                "latencia_segundos": 0.0,
                "nivel_thinking": "N/A",
                "tokens_limite": 0,
            }
            st.session_state["historial_mensajes"].insert(0, registro_nuevo)
            st.success(f"✅ Caso manual guardado en {taller_activo}.")
            st.rerun()

    with col_enviar_wa:
        enlace_wa_manual = construir_enlace_whatsapp(telefono_manual, borrador_manual)
        st.link_button(
            label="📲 Abrir y Enviar en WhatsApp",
            url=enlace_wa_manual,
            use_container_width=True,
        )

def renderizar_vista_clasificador(
    temperatura_seleccionada: float,
    nivel_thinking_seleccionado: str,
    limite_tokens_seleccionado: int,
) -> None:
    renderizar_encabezado_principal()

    tab_ia, tab_manual = st.tabs([
        "🤖 Asistente Gemini IA (Automático)",
        "✍️ Triaje Manual de Mostrador",
    ])

    with tab_ia:
        renderizar_modo_ia(
            temperatura_seleccionada,
            nivel_thinking_seleccionado,
            limite_tokens_seleccionado,
        )

    with tab_manual:
        renderizar_modo_manual()

def main() -> None:
    configurar_pagina()

    if "usuario_autenticado" not in st.session_state:
        st.session_state["usuario_autenticado"] = False

    if "pin_buffer" not in st.session_state:
        st.session_state["pin_buffer"] = ""

    if "taller_activo" not in st.session_state:
        st.session_state["taller_activo"] = "Taller Central · FixLab"

    if not st.session_state["usuario_autenticado"]:
        renderizar_pantalla_login_pin()
        return

    aplicar_estilos_taller()

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

    temperatura_seleccionada, nivel_thinking_seleccionado, limite_tokens_seleccionado, modo_vista = renderizar_barra_lateral()

    if modo_vista == "historial":
        renderizar_vista_historial()
    else:
        renderizar_vista_clasificador(
            temperatura_seleccionada,
            nivel_thinking_seleccionado,
            limite_tokens_seleccionado,
        )

if __name__ == "__main__":
    main()
