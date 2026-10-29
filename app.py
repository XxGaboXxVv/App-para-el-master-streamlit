import json
import os
import re
import streamlit as st
from typing import Optional, TypedDict

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

MODELOS_DISPONIBLES: list[str] = [
    "gemini-3.8-flash",
]

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

def ejecutar_clasificacion_gemini(mensaje_texto: str, clave_api: str) -> ResultadoClasificacion:
    cliente_genai = genai.Client(api_key=clave_api)
    configuracion = types.GenerateContentConfig(
        system_instruction=PROMPT_SISTEMA_OPERATIVO,
        response_mime_type="application/json",
        temperature=0.1,
    )

    ultimo_error: Optional[Exception] = None
    respuesta = None

    for nombre_modelo in MODELOS_DISPONIBLES:
        try:
            respuesta = cliente_genai.models.generate_content(
                model=nombre_modelo,
                contents=f"Mensaje entrante de WhatsApp:\n\"\"\"\n{mensaje_texto}\n\"\"\"",
                config=configuracion,
            )
            if respuesta and respuesta.text:
                break
        except Exception as error_intento:
            ultimo_error = error_intento
            continue

    if not respuesta or not respuesta.text:
        if ultimo_error:
            raise ultimo_error
        raise ValueError("La API de Gemini devolvió una respuesta vacía.")

    datos_json: dict[str, str] = json.loads(respuesta.text)

    urgencia = str(datos_json.get("urgencia", "BAJA"))
    color = str(datos_json.get("urgencia_color", "info"))
    if color not in ["error", "warning", "info"]:
        color = "error" if "ALTA" in urgencia else "warning" if "MEDIA" in urgencia else "info"

    return {
        "urgencia": urgencia,
        "urgencia_color": color,
        "categoria": str(datos_json.get("categoria", "Consulta General")),
        "dispositivo": str(datos_json.get("dispositivo", "No especificado")),
        "falla_reportada": str(datos_json.get("falla_reportada", "Sin detalle")),
        "accion_recomendada": str(datos_json.get("accion_recomendada", "Revisión en mostrador")),
        "borrador_respuesta": str(datos_json.get("borrador_respuesta", "")),
    }

def configurar_pagina() -> None:
    st.set_page_config(
        page_title="Asistente de Taller · Clasificador PyME",
        page_icon="🛠️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

def renderizar_barra_lateral() -> None:
    with st.sidebar:
        st.header("🛠️ Asistente de Taller")
        st.caption("Clasificador PyME · WhatsApp")
        st.markdown("---")

        st.subheader("💡 Casos de Prueba Rápida")
        st.caption("Selecciona un mensaje predefinido para cargarlo en el editor:")

        for nombre_ejemplo, texto_ejemplo in PRESET_MESSAGES.items():
            if st.button(nombre_ejemplo, use_container_width=True):
                st.session_state["mensaje_input"] = texto_ejemplo

        st.markdown("---")
        st.subheader("📌 Acerca del Sistema")
        st.markdown(
            "Módulo de triaje y respuesta inmediata para talleres de reparación de celulares. "
            "Procesamiento impulsado exclusivamente por **Google Gemini 3.8 Flash**."
        )

def main() -> None:
    configurar_pagina()
    renderizar_barra_lateral()

    st.title("🛠️ Asistente de Mensajes para Taller · Clasificador PyME")
    st.markdown(
        "Pega el texto de un mensaje recibido en WhatsApp para clasificar su urgencia operativa, "
        "extraer detalles técnicos y generar una respuesta profesional en tiempo real."
    )

    if "mensaje_input" not in st.session_state:
        st.session_state["mensaje_input"] = ""

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

        try:
            with st.spinner("🤖 Analizando mensaje con Google Gemini 3.8 Flash..."):
                resultado = ejecutar_clasificacion_gemini(texto_a_evaluar, clave_api)
        except APIError as error_api:
            detalle = str(error_api)
            if "RESOURCE_EXHAUSTED" in detalle or "429" in detalle or getattr(error_api, "code", None) == 429:
                st.error("⏳ **Límite de cuota alcanzado (429):** El servicio de Gemini ha recibido demasiadas peticiones por minuto. Espera 60 segundos antes de reenviar.")
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

        if resultado["categoria"] == "No Interpretable":
            st.warning("⚠️ **Mensaje no concluyente:** La IA determinó que el texto no contiene una consulta técnica o comercial reconocible.")
            st.info(f"**Borrador sugerido:** {resultado['borrador_respuesta']}")
            return

        st.markdown("---")
        st.subheader("📋 Resultado de la Clasificación")

        col_urgencia, col_categoria = st.columns(2)
        with col_urgencia:
            if resultado["urgencia_color"] == "error":
                st.error(f"**Urgencia:** {resultado['urgencia']}")
            elif resultado["urgencia_color"] == "warning":
                st.warning(f"**Urgencia:** {resultado['urgencia']}")
            else:
                st.info(f"**Urgencia:** {resultado['urgencia']}")

        with col_categoria:
            st.success(f"**Categoría:** {resultado['categoria']}")

        col_resumen, col_accion = st.columns(2)
        with col_resumen:
            st.markdown(f"**📱 Dispositivo identificado:** {resultado['dispositivo']}")
            st.markdown(f"**⚠️ Falla reportada:** {resultado['falla_reportada']}")
        with col_accion:
            st.markdown(f"**🎯 Acción recomendada en taller:** {resultado['accion_recomendada']}")

        st.markdown("### ✍️ Borrador de Respuesta para WhatsApp")
        st.caption("Copia y pega este texto directamente en el chat con el cliente:")
        st.code(resultado["borrador_respuesta"], language="text")

if __name__ == "__main__":
    main()
