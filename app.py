import json
import os
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

PROMPT_SISTEMA_OPERATIVO: str = (
    "Eres el asistente de operaciones de un taller especializado en reparación de celulares y tablets.\n"
    "Tu trabajo es analizar el mensaje crudo enviado por un cliente por WhatsApp y generar una clasificación operativa estructurada junto con un borrador de respuesta.\n\n"
    "Debes responder estrictamente en formato JSON con la siguiente estructura de claves:\n"
    "{\n"
    '  "urgencia": "ALTA / GARANTÍA CRÍTICA" | "MEDIA" | "BAJA",\n'
    '  "urgencia_color": "error" | "warning" | "info",\n'
    '  "categoria": "Garantía / Reclamo" | "Cotización de Reparación" | "Estatus de Dispositivo" | "Consulta General",\n'
    '  "dispositivo": "Marca y modelo identificado, o No especificado",\n'
    '  "falla_reportada": "Descripción concisa del síntoma o daño",\n'
    '  "accion_recomendada": "Acción inmediata que debe tomar el técnico en taller",\n'
    '  "borrador_respuesta": "Mensaje educado, empático y profesional listo para enviar al cliente por WhatsApp"\n'
    "}\n\n"
    "Reglas obligatorias:\n"
    "1. Si el cliente menciona que una reparación previa falló, el touch no funciona tras una entrega, o reclama una garantía, la urgencia es SIEMPRE 'ALTA / GARANTÍA CRÍTICA' y urgencia_color es 'error'.\n"
    "2. Si el mensaje es una cotización o consulta de estatus de un equipo, la urgencia es 'MEDIA' y urgencia_color es 'warning'.\n"
    "3. Si el mensaje es vago, ambiguo o solo un saludo, la urgencia es 'BAJA' y urgencia_color es 'info'. En el borrador_respuesta, solicita amablemente marca, modelo y síntoma.\n"
    "4. El borrador_respuesta debe sonar humano, empático y profesional, listo para copiar y enviar en WhatsApp.\n"
)

def resolver_api_key_gemini() -> Optional[str]:
    try:
        if "GEMINI_API_KEY" in st.secrets:
            clave_secrets = st.secrets["GEMINI_API_KEY"]
            if isinstance(clave_secrets, str) and clave_secrets.strip():
                return clave_secrets.strip()
    except Exception:
        pass

    clave_entorno = os.environ.get("GEMINI_API_KEY")
    if clave_entorno and clave_entorno.strip():
        return clave_entorno.strip()

    clave_manual = st.session_state.get("gemini_api_key_manual")
    if isinstance(clave_manual, str) and clave_manual.strip():
        return clave_manual.strip()

    return None

def clasificar_con_gemini_api(mensaje_texto: str, clave_api: str) -> ResultadoClasificacion:
    cliente_genai = genai.Client(api_key=clave_api)
    configuracion_llamada = types.GenerateContentConfig(
        system_instruction=PROMPT_SISTEMA_OPERATIVO,
        response_mime_type="application/json",
        temperature=0.2,
    )
    prompt_usuario = f"Mensaje del cliente de WhatsApp:\n\"\"\"\n{mensaje_texto}\n\"\"\""

    respuesta = cliente_genai.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt_usuario,
        config=configuracion_llamada,
    )

    if not respuesta.text:
        raise ValueError("La API de Gemini devolvió una respuesta vacía.")

    datos_json: dict[str, str] = json.loads(respuesta.text)

    urgencia_detectada = str(datos_json.get("urgencia", "MEDIA"))
    color_detectado = str(datos_json.get("urgencia_color", ""))
    if not color_detectado:
        if "ALTA" in urgencia_detectada:
            color_detectado = "error"
        elif "MEDIA" in urgencia_detectada:
            color_detectado = "warning"
        else:
            color_detectado = "info"

    return {
        "urgencia": urgencia_detectada,
        "urgencia_color": color_detectado,
        "categoria": str(datos_json.get("categoria", "Consulta General")),
        "dispositivo": str(datos_json.get("dispositivo", "No especificado")),
        "falla_reportada": str(datos_json.get("falla_reportada", "Sin detalle técnico")),
        "accion_recomendada": str(datos_json.get("accion_recomendada", "Revisión en mostrador")),
        "borrador_respuesta": str(datos_json.get("borrador_respuesta", "Hola, gracias por comunicarte con nuestro taller.")),
    }

def simular_clasificacion_mensaje(mensaje_texto: str) -> ResultadoClasificacion:
    texto_minusculas = mensaje_texto.lower()

    if any(palabra in texto_minusculas for palabra in ["garantía", "garantia", "ayer", "no responde", "touch", "falló", "peor"]):
        return {
            "urgencia": "ALTA / GARANTÍA CRÍTICA",
            "urgencia_color": "error",
            "categoria": "Garantía / Reclamo",
            "dispositivo": "Apple iPhone 11",
            "falla_reportada": "Falla táctil tras reparación previa (zona inferior no responde)",
            "accion_recomendada": "Revisión inmediata sin costo. Dar prioridad en mesa de trabajo.",
            "borrador_respuesta": (
                "¡Hola! Lamento mucho el inconveniente con tu iPhone 11. En nuestro taller todos nuestros "
                "trabajos cuentan con garantía total. Por favor tráelo de inmediato hoy mismo; "
                "le daremos prioridad inmediata en mesa para revisarlo y dejarlo al 100%. Te esperamos."
            ),
        }

    if any(palabra in texto_minusculas for palabra in ["cuánto", "cuanto", "precio", "costo", "sale", "pantalla", "cotización", "cotizacion"]):
        return {
            "urgencia": "MEDIA",
            "urgencia_color": "warning",
            "categoria": "Cotización de Reparación",
            "dispositivo": "Samsung Galaxy A54",
            "falla_reportada": "Cristal roto / daño físico en display frontal",
            "accion_recomendada": "Consultar stock de refacción OLED/Incell y enviar rango de precio con tiempo de entrega.",
            "borrador_respuesta": (
                "¡Hola! Claro que sí, con gusto te cotizamos. Para el Samsung Galaxy A54 manejamos "
                "pantalla de calidad original con garantía de 30 días. El servicio incluye instalación "
                "y queda listo en aproximadamente 2 horas previa confirmación. ¿Te gustaría agendar una hora para recibirlo?"
            ),
        }

    if any(palabra in texto_minusculas for palabra in ["estatus", "cómo va", "como va", "listo", "recoger", "quedó"]):
        return {
            "urgencia": "MEDIA",
            "urgencia_color": "warning",
            "categoria": "Estatus de Dispositivo",
            "dispositivo": "Xiaomi Redmi Note 12",
            "falla_reportada": "Centro de carga",
            "accion_recomendada": "Verificar prueba final de carga y notificar retiro en mostrador.",
            "borrador_respuesta": (
                "¡Hola! Qué gusto saludarte. Tu Xiaomi Redmi Note 12 se encuentra en la fase final "
                "de pruebas de voltaje para garantizar que cargue de forma óptima. En unos momentos te confirmamos "
                "la hora para que puedas pasar a recogerlo con tu nota de servicio."
            ),
        }

    return {
        "urgencia": "BAJA",
        "urgencia_color": "info",
        "categoria": "Consulta General",
        "dispositivo": "No especificado",
        "falla_reportada": "Solicitud general de información de servicios",
        "accion_recomendada": "Solicitar marca, modelo y falla específica para dar diagnóstico preliminar.",
        "borrador_respuesta": (
            "¡Hola! Gracias por comunicarte con nuestro taller. Sí, reparamos dispositivos de todas las "
            "marcas principales (pantallas, baterías, centros de carga y fallas de placa). ¿Qué modelo "
            "de equipo tienes y qué falla presenta para orientarte mejor?"
        ),
    }

def configurar_pagina() -> None:
    st.set_page_config(
        page_title="Asistente para Taller · Clasificador PyME",
        page_icon="🛠️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

def renderizar_barra_lateral(clave_activa: Optional[str]) -> None:
    with st.sidebar:
        st.header("🛠️ Asistente para Taller")
        st.caption("Clasificador PyME · WhatsApp")
        st.markdown("---")

        if clave_activa and GENAI_DISPONIBLE:
            st.success("🟢 **Motor IA:** Google Gemini 2.5 Flash conectado")
        else:
            st.info("🟡 **Motor IA:** Modo Simulación interactivo")
            st.caption(
                "Para activar Gemini en vivo en producción, configura `GEMINI_API_KEY` en los Secrets de Streamlit Cloud."
            )
            st.text_input(
                "Ingresar clave temporal para pruebas:",
                type="password",
                key="gemini_api_key_manual",
                help="Clave para pruebas locales. No se almacena en el repositorio.",
            )

        st.markdown("---")
        st.subheader("💡 Casos de Prueba Rápida")
        st.caption("Carga un caso típico en el editor con un solo clic:")

        for nombre_ejemplo, texto_ejemplo in PRESET_MESSAGES.items():
            if st.button(nombre_ejemplo, use_container_width=True):
                st.session_state["mensaje_input"] = texto_ejemplo

        st.markdown("---")
        st.subheader("📌 Acerca del Proyecto")
        st.markdown(
            "Herramienta de atención inteligente para talleres unipersonales de reparación de celulares. "
            "Clasifica prioridades, detecta fallas y redacta respuestas profesionales en segundos."
        )

def main() -> None:
    configurar_pagina()
    clave_activa = resolver_api_key_gemini()
    renderizar_barra_lateral(clave_activa)

    st.title("🛠️ Asistente de Mensajes para Taller · Clasificador PyME")
    st.markdown(
        "Pega el texto del mensaje recibido en WhatsApp para clasificar su urgencia, "
        "obtener un resumen técnico y generar un borrador de respuesta al instante."
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
        if not mensaje_actual.strip():
            st.warning("⚠️ Por favor pega o escribe el texto de un mensaje antes de presionar Clasificar.")
            return

        resultado: Optional[ResultadoClasificacion] = None

        if clave_activa and GENAI_DISPONIBLE:
            try:
                with st.spinner("🤖 Procesando mensaje con Google Gemini 2.5 Flash..."):
                    resultado = clasificar_con_gemini_api(mensaje_actual, clave_activa)
            except APIError as error_api:
                detalle_error = str(error_api)
                if "RESOURCE_EXHAUSTED" in detalle_error or "429" in detalle_error or error_api.code == 429:
                    st.error(
                        "⏳ **Límite de cuota gratuita alcanzado (429 / ResourceExhausted):** "
                        "Se ha excedido el límite de peticiones por minuto de Gemini. Por favor espera 60 segundos antes de reintentar."
                    )
                elif "API_KEY_INVALID" in detalle_error or "400" in detalle_error or error_api.code == 400:
                    st.error(
                        "🔑 **Error de Clave de API:** La clave GEMINI_API_KEY no es válida o no tiene permisos en Google AI Studio. "
                        "Verifica su configuración en los secretos de la plataforma."
                    )
                else:
                    st.error(f"⚠️ **Error en la API de Gemini:** {detalle_error}")
                return
            except json.JSONDecodeError:
                st.error("⚠️ **Error de formato:** La respuesta de la IA no pudo procesarse como JSON estructurado. Por favor intenta nuevamente.")
                return
            except Exception as error_general:
                st.error(f"📡 **Error de comunicación o red con el servicio de IA:** {error_general}")
                return
        else:
            with st.spinner("Procesando mensaje con motor de simulación..."):
                resultado = simular_clasificacion_mensaje(mensaje_actual)

        if not resultado:
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
