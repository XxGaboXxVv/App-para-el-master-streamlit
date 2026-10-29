import streamlit as st
from typing import TypedDict

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

def renderizar_barra_lateral() -> None:
    with st.sidebar:
        st.header("🛠️ Asistente para Taller")
        st.caption("Clasificador PyME · WhatsApp")
        st.markdown("---")

        st.subheader("📌 Acerca del Proyecto")
        st.markdown(
            "Herramienta inteligente de apoyo para talleres unipersonales de reparación de celulares. "
            "Permite clasificar urgencias, resumir fallas técnicas y redactar respuestas profesionales en segundos."
        )

        st.markdown("---")
        st.subheader("💡 Ejemplos de Prueba Rápida")
        st.caption("Selecciona un caso para cargarlo en el editor:")

        for nombre_ejemplo, texto_ejemplo in PRESET_MESSAGES.items():
            if st.button(nombre_ejemplo, use_container_width=True):
                st.session_state["mensaje_input"] = texto_ejemplo

        st.markdown("---")
        st.info("ℹ️ **Versión 0 (Semana 2)**: Flujo de interfaz validado con lógica simulada (mock). La integración con la API de Gemini se activará en Semana 3.")

def main() -> None:
    configurar_pagina()
    renderizar_barra_lateral()

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

        with st.spinner("Analizando y clasificando mensaje..."):
            resultado = simular_clasificacion_mensaje(mensaje_actual)

        st.markdown("---")
        st.subheader("📋 Resultado de la Clasificación")

        col1, col2 = st.columns(2)

        with col1:
            if resultado["urgencia_color"] == "error":
                st.error(f"**Urgencia:** {resultado['urgencia']}")
            elif resultado["urgencia_color"] == "warning":
                st.warning(f"**Urgencia:** {resultado['urgencia']}")
            else:
                st.info(f"**Urgencia:** {resultado['urgencia']}")

        with col2:
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
