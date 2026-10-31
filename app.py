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
import streamlit.components.v1 as components

try:
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError
    GENAI_DISPONIBLE = True
except ImportError:
    GENAI_DISPONIBLE = False
    genai = None  # type: ignore
    types = None  # type: ignore
    class APIError(Exception):  # type: ignore
        code: Optional[int] = None
        message: str = ""

class ErrorOperativoTaller(Exception):
    def __init__(self, mensaje: str, accion_sugerida: str = "") -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.accion_sugerida = accion_sugerida

class ErrorCuotaExcedida(ErrorOperativoTaller):
    pass

class ErrorServidorSaturado(ErrorOperativoTaller):
    pass

class ErrorAutenticacionAPI(ErrorOperativoTaller):
    pass

class ErrorConexionRed(ErrorOperativoTaller):
    pass

class ErrorRespuestaVacia(ErrorOperativoTaller):
    pass

class ErrorFormatoInvalido(ErrorOperativoTaller):
    pass

class DiagnosticoIncidencia(TypedDict):
    categoria: str
    titulo: str
    descripcion: str
    accion_sugerida: str
    icono: str
    es_recuperable_manual: bool

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

CATALOGO_SERVICIOS = [
    {
        "servicio": "Cambio de Pantalla OLED (Gama Media)",
        "categoria": "Pantallas",
        "costo_aprox": "$45 - $75 USD",
        "tiempo": "45 - 90 min",
        "garantia": "60 días",
    },
    {
        "servicio": "Cambio de Pantalla OLED Premium / iPhone",
        "categoria": "Pantallas",
        "costo_aprox": "$85 - $170 USD",
        "tiempo": "60 - 90 min",
        "garantia": "90 días",
    },
    {
        "servicio": "Reemplazo de Batería Original OEM",
        "categoria": "Baterías",
        "costo_aprox": "$25 - $45 USD",
        "tiempo": "30 - 45 min",
        "garantia": "90 días",
    },
    {
        "servicio": "Reparación de Centro de Carga Tipo C",
        "categoria": "Puertos / Carga",
        "costo_aprox": "$20 - $35 USD",
        "tiempo": "40 min",
        "garantia": "30 días",
    },
    {
        "servicio": "Limpieza por Humedad (Baño Ultrasónico)",
        "categoria": "Diagnóstico / Software",
        "costo_aprox": "$25 - $40 USD",
        "tiempo": "2 - 4 horas",
        "garantia": "Sin garantía húmedos",
    },
    {
        "servicio": "Flasheo y Restauración de Sistema Operativo",
        "categoria": "Diagnóstico / Software",
        "costo_aprox": "$15 - $30 USD",
        "tiempo": "60 min",
        "garantia": "15 días",
    },
]

MODELO_ACTIVO: str = "gemini-3.8-flash"

PROMPT_SISTEMA_OPERATIVO: str = (
    "Eres el asistente de operaciones de un taller especializado en reparación de celulares y tablets.\n"
    "Tu función es analizar mensajes reales de clientes recibidos por WhatsApp para clasificar su urgencia, "
    "identificar la intención técnica, extraer datos del remitente y redactar una respuesta profesional.\n\n"
    "Estructura obligatoria de respuesta en formato JSON:\n"
    "{\n"
    '  "urgencia": "ALTA / GARANTÍA CRÍTICA" | "MEDIA" | "BAJA",\n'
    '  "urgencia_color": "error" | "warning" | "info",\n'
    '  "categoria": "Garantía / Reclamo" | "Cotización de Reparación" | "Estatus de Dispositivo" | "Consulta General" | "No Interpretable",\n'
    '  "dispositivo": "Marca y modelo identificado, o No especificado",\n'
    '  "falla_reportada": "Descripción del problema reportado o No identificable",\n'
    '  "accion_recomendada": "Acción que debe tomar el técnico en mostrador",\n'
    '  "cliente_nombre_detectado": "Nombre propio del cliente si se menciona en el mensaje (ej: Gabriel Durón), o No especificado",\n'
    '  "cliente_telefono_detectado": "Teléfono de contacto si se menciona en el mensaje, o No registrado",\n'
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
    "5. Si el cliente indica su nombre (ej: 'me llamo Gabriel Durón', 'soy Carlos', 'le escribe Ana'): "
    "extrae el nombre con mayúsculas iniciales en 'cliente_nombre_detectado'. Si indica un teléfono, extráelo en 'cliente_telefono_detectado'.\n"
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

    # 1. Extracción de encabezados de chat exportados de WhatsApp (ej: [14:20, 20/10/2026] Juan: mensaje)
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

    # 2. Extracción conversacional de nombre en lenguaje natural
    if not nombre_limpio:
        patrones_nombre = [
            r"(?:me llamo|mi nombre es|le escribe|habla|atentamente|atte\.?:?|soy)\s+([A-ZÁÉÍÓÚa-záéíóúñ]{2,}(?:\s+[A-ZÁÉÍÓÚa-záéíóúñ]{2,}){0,3})",
        ]
        palabras_corte = {
            "y", "que", "tengo", "queria", "quisiera", "pero", "con", "para", "porque",
            "mi", "mis", "su", "sus", "el", "la", "los", "las", "un", "una", "unos", "unas",
            "cel", "celular", "tel", "telefono", "whatsapp", "movil", "contacto",
            "del", "al", "de", "es", "les", "le", "buenos", "buenas", "dias", "tardes",
            "nuevo", "nueva", "cliente", "usuario", "dueno", "dueño", "tecnico", "técnico",
            "por", "favor", "saludos", "hola"
        }
        for patron in patrones_nombre:
            match_nom = re.search(patron, texto_mensaje, re.IGNORECASE)
            if match_nom:
                candidato = match_nom.group(1).strip()
                palabras_candidato = candidato.split()
                if palabras_candidato and palabras_candidato[0].lower() not in palabras_corte:
                    palabras_finales = []
                    for p in palabras_candidato:
                        if p.lower() in palabras_corte:
                            break
                        palabras_finales.append(p)
                    if palabras_finales:
                        nombre_limpio = " ".join(palabras_finales).title()
                        break

    # 3. Extracción de teléfono (contextual con etiqueta o formato numérico amplio)
    if not telefono_limpio:
        patron_tel_etiqueta = r"(?:tel(?:éfono)?|cel(?:ular)?|whatsapp|móvil|contacto|al)[:\s]+(\+?\d[\d\s\-\(\)]{7,}\d)"
        match_tel_etq = re.search(patron_tel_etiqueta, texto_mensaje, re.IGNORECASE)
        if match_tel_etq:
            telefono_limpio = match_tel_etq.group(1).strip()
        else:
            coincidencia_tel = re.search(
                r"(\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4})", texto_mensaje
            )
            if coincidencia_tel:
                candidato_tel = coincidencia_tel.group(1).strip()
                solo_digitos = re.sub(r"\D", "", candidato_tel)
                if len(solo_digitos) >= 8:
                    telefono_limpio = candidato_tel

    nombre_final = nombre_limpio if nombre_limpio else "No especificado"
    telefono_final = telefono_limpio if telefono_limpio else "No registrado"

    return nombre_final, telefono_final

def construir_enlace_whatsapp(telefono: str, texto_respuesta: str) -> str:
    try:
        digitos_telefono = re.sub(r"[^\d]", "", str(telefono or ""))
        texto_codificado = urllib.parse.quote(str(texto_respuesta or ""))
        if len(digitos_telefono) >= 7:
            return f"https://wa.me/{digitos_telefono}?text={texto_codificado}"
        return f"https://wa.me/?text={texto_codificado}"
    except Exception:
        return "https://wa.me/"

def obtener_clave_gemini() -> Optional[str]:
    try:
        if "GEMINI_API_KEY" in st.secrets:
            clave = st.secrets["GEMINI_API_KEY"]
            if isinstance(clave, str) and clave.strip():
                return clave.strip()
    except Exception:
        pass

    try:
        clave_entorno = os.environ.get("GEMINI_API_KEY")
        if clave_entorno and clave_entorno.strip():
            return clave_entorno.strip()
    except Exception:
        pass

    return None

def limpiar_y_parsear_json_gemini(texto_crudo: str) -> dict[str, str]:
    if not texto_crudo or not texto_crudo.strip():
        raise ErrorRespuestaVacia("El modelo devolvió una respuesta vacía sin texto.")

    texto_limpio = texto_crudo.strip()
    if texto_limpio.startswith("```json"):
        texto_limpio = texto_limpio[7:]
    elif texto_limpio.startswith("```"):
        texto_limpio = texto_limpio[3:]
    if texto_limpio.endswith("```"):
        texto_limpio = texto_limpio[:-3]
    texto_limpio = texto_limpio.strip()

    datos: Optional[dict[str, object]] = None
    try:
        resultado = json.loads(texto_limpio)
        if isinstance(resultado, dict):
            datos = resultado
    except json.JSONDecodeError:
        pass

    if datos is None:
        inicio = texto_limpio.find("{")
        fin = texto_limpio.rfind("}")
        if inicio != -1 and fin != -1 and fin > inicio:
            try:
                resultado = json.loads(texto_limpio[inicio : fin + 1])
                if isinstance(resultado, dict):
                    datos = resultado
            except json.JSONDecodeError:
                pass

    if datos is None:
        raise ErrorFormatoInvalido(
            "La respuesta del modelo de IA no pudo ser interpretada en formato JSON válido.",
            accion_sugerida="Reintenta la consulta o ajusta los parámetros de temperatura y límite de tokens."
        )

    urgencia = str(datos.get("urgencia", "BAJA")).strip()
    if not urgencia:
        urgencia = "BAJA"

    categoria = str(datos.get("categoria", "Consulta General")).strip()
    if not categoria:
        categoria = "Consulta General"

    dispositivo = str(datos.get("dispositivo", "No especificado")).strip()
    if not dispositivo:
        dispositivo = "No especificado"

    falla = str(datos.get("falla_reportada", "Sin detalle")).strip()
    if not falla:
        falla = "Sin detalle"

    accion = str(datos.get("accion_recomendada", "Revisión técnica en mostrador")).strip()
    if not accion:
        accion = "Revisión técnica en mostrador"

    borrador = str(datos.get("borrador_respuesta", "")).strip()
    if not borrador:
        borrador = "Hola, recibimos tu mensaje en taller. Con gusto te ayudamos con tu equipo."

    color = str(datos.get("urgencia_color", "")).strip().lower()
    if color not in ("error", "warning", "info"):
        color = "error" if "ALTA" in urgencia else "warning" if "MEDIA" in urgencia else "info"

    nombre_detectado = str(datos.get("cliente_nombre_detectado", "No especificado")).strip()
    if not nombre_detectado or nombre_detectado.lower() in ("no especificado", "ninguno", "null", "none"):
        nombre_detectado = "No especificado"

    telefono_detectado = str(datos.get("cliente_telefono_detectado", "No registrado")).strip()
    if not telefono_detectado or telefono_detectado.lower() in ("no registrado", "ninguno", "null", "none"):
        telefono_detectado = "No registrado"

    return {
        "urgencia": urgencia,
        "urgencia_color": color,
        "categoria": categoria,
        "dispositivo": dispositivo,
        "falla_reportada": falla,
        "accion_recomendada": accion,
        "borrador_respuesta": borrador,
        "cliente_nombre_detectado": nombre_detectado,
        "cliente_telefono_detectado": telefono_detectado,
    }

def clasificar_excepcion_operativa(excepcion: Exception) -> DiagnosticoIncidencia:
    mensaje_error = str(excepcion)
    nombre_tipo = type(excepcion).__name__

    if (
        isinstance(excepcion, ErrorCuotaExcedida)
        or "429" in mensaje_error
        or "RESOURCE_EXHAUSTED" in mensaje_error
        or getattr(excepcion, "code", None) == 429
    ):
        return {
            "categoria": "Cuota de Servicio",
            "titulo": "Límite de Consultas de IA Alcanzado (HTTP 429)",
            "descripcion": (
                "La clave gratuita de Google AI Studio ha alcanzado el límite de peticiones por minuto. "
                "Los servidores de Google han pausado temporalmente nuevas solicitudes automáticas."
            ),
            "accion_sugerida": (
                "Espera 60 segundos antes de volver a consultar, o utiliza la pestaña '✍️ Triaje Manual de Mostrador' "
                "para registrar y despachar al cliente de inmediato sin depender de la nube."
            ),
            "icono": "⏳",
            "es_recuperable_manual": True,
        }

    if (
        isinstance(excepcion, ErrorServidorSaturado)
        or "503" in mensaje_error
        or "UNAVAILABLE" in mensaje_error
        or getattr(excepcion, "code", None) == 503
    ):
        return {
            "categoria": "Disponibilidad del Servidor",
            "titulo": "Servidores de Google Gemini en Alta Demanda (HTTP 503)",
            "descripcion": (
                "Los centros de datos de Google están experimentando una sobrecarga temporal de tráfico. "
                "El sistema ejecutó un reintento automático pero el servicio continúa congestionado."
            ),
            "accion_sugerida": (
                "Por favor, aguarda entre 10 y 15 segundos y presiona nuevamente 'Clasificar con Gemini IA'. "
                "Si la atención en mostrador apremia, puedes registrar el caso manualmente en la pestaña contigua."
            ),
            "icono": "⚡",
            "es_recuperable_manual": True,
        }

    if (
        isinstance(excepcion, ErrorAutenticacionAPI)
        or "API_KEY_INVALID" in mensaje_error
        or "PERMISSION_DENIED" in mensaje_error
        or "INVALID_ARGUMENT" in mensaje_error
        or "401" in mensaje_error
        or "403" in mensaje_error
        or getattr(excepcion, "code", None) in (400, 401, 403)
    ):
        return {
            "categoria": "Autenticación y Credenciales",
            "titulo": "Credenciales de Google AI Rechazadas",
            "descripcion": (
                "La clave de API (GEMINI_API_KEY) configurada en los secretos del taller no es válida, "
                "está suspendida o carece de permisos para el modelo activo."
            ),
            "accion_sugerida": (
                "Verifica la configuración de 'GEMINI_API_KEY' en el panel de Streamlit Cloud (Settings > Secrets) "
                "o en tu archivo local .streamlit/secrets.toml. Mientras tanto, el Triaje Manual está 100% operativo."
            ),
            "icono": "🔑",
            "es_recuperable_manual": True,
        }

    patrones_red = ("connect", "timeout", "socket", "gaierror", "connectionrefused", "httpx", "urllib", "network")
    if (
        isinstance(excepcion, ErrorConexionRed)
        or any(p in mensaje_error.lower() for p in patrones_red)
        or any(p in nombre_tipo.lower() for p in patrones_red)
    ):
        return {
            "categoria": "Conectividad de Red",
            "titulo": "Imposible Conectar con el Servicio de IA",
            "descripcion": (
                "La estación de trabajo no pudo establecer comunicación con los servidores de Google. "
                "Puede deberse a pérdida de internet local, problemas de DNS o restricciones de red."
            ),
            "accion_sugerida": (
                "Comprueba la conexión a internet de tu equipo. Si la falla persiste, puedes seguir atendiendo "
                "clientes usando la modalidad de Triaje Manual de Mostrador."
            ),
            "icono": "🌐",
            "es_recuperable_manual": True,
        }

    if isinstance(excepcion, ErrorRespuestaVacia) or "respuesta vacía" in mensaje_error.lower():
        return {
            "categoria": "Parámetros de Inferencia",
            "titulo": "Respuesta Truncada o Sin Contenido",
            "descripcion": (
                "El modelo de IA agotó su cuota de razonamiento interno antes de emitir la ficha en formato estructurado. "
                "Esto suele ocurrir cuando el límite de tokens es muy bajo para el nivel de pensamiento seleccionado."
            ),
            "accion_sugerida": (
                "Aumenta el control de 'Límite de tokens de salida' a 2,000 o 2,500 en la barra lateral izquierda, "
                "o ajusta el 'Nivel de razonamiento (Thinking)' a LOW para acelerar la respuesta."
            ),
            "icono": "📏",
            "es_recuperable_manual": True,
        }

    if isinstance(excepcion, (ErrorFormatoInvalido, json.JSONDecodeError)):
        return {
            "categoria": "Formato de Datos",
            "titulo": "Respuesta No Deserializable",
            "descripcion": (
                "El modelo devolvió una respuesta pero no se pudo estructurar en los campos requeridos para la ficha técnica."
            ),
            "accion_sugerida": (
                "Presiona 'Clasificar con Gemini IA' de nuevo para solicitar una nueva generación. "
                "Si el mensaje original del cliente es muy complejo, prueba dividiéndolo en dos frases."
            ),
            "icono": "🧩",
            "es_recuperable_manual": True,
        }

    if isinstance(excepcion, ErrorOperativoTaller):
        return {
            "categoria": "Incidencia Operativa",
            "titulo": "Incidencia en Servicio de IA",
            "descripcion": excepcion.mensaje,
            "accion_sugerida": (
                excepcion.accion_sugerida
                if excepcion.accion_sugerida
                else "Puedes reintentar la operación o alternar a la pestaña de '✍️ Triaje Manual de Mostrador'."
            ),
            "icono": "🛡️",
            "es_recuperable_manual": True,
        }

    return {
        "categoria": "Incidencia Operativa",
        "titulo": "Incidencia al Procesar la Consulta",
        "descripcion": (
            f"Se produjo un evento no contemplado durante la ejecución ({nombre_tipo}). "
            "El sistema ha protegido los datos de la sesión para evitar pérdida de información."
        ),
        "accion_sugerida": (
            "Puedes reintentar la operación o alternar a la pestaña de '✍️ Triaje Manual de Mostrador' "
            "para despachar al cliente de inmediato sin interrupciones."
        ),
        "icono": "🛡️",
        "es_recuperable_manual": True,
    }

def renderizar_alerta_incidencia(diagnostico: DiagnosticoIncidencia) -> None:
    st.markdown(
        f"""
        <div style="background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.35); border-radius: 12px; padding: 1.25rem 1.4rem; margin: 1.2rem 0; box-shadow: 0 4px 16px rgba(0,0,0,0.25);">
            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem;">
                <span style="font-size: 1.5rem;">{diagnostico['icono']}</span>
                <div>
                    <span style="font-size: 0.72rem; text-transform: uppercase; font-family: 'JetBrains Mono', monospace; letter-spacing: 0.08em; color: #f87171; font-weight: 700;">{diagnostico['categoria']}</span>
                    <h4 style="margin: 0; color: #fecaca; font-weight: 800; font-size: 1.05rem;">{diagnostico['titulo']}</h4>
                </div>
            </div>
            <p style="color: #cbd5e1; font-size: 0.92rem; margin: 0.4rem 0 0.85rem 0; line-height: 1.5;">
                {diagnostico['descripcion']}
            </p>
            <div style="background: rgba(15, 23, 42, 0.7); border-left: 3px solid #38bdf8; padding: 0.7rem 0.95rem; border-radius: 8px;">
                <strong style="color: #38bdf8; font-size: 0.85rem;">💡 Acción recomendada para el técnico:</strong>
                <p style="margin: 0.25rem 0 0 0; color: #f1f5f9; font-size: 0.88rem; line-height: 1.4;">{diagnostico['accion_sugerida']}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def ejecutar_clasificacion_gemini(
    mensaje_texto: str,
    clave_api: str,
    temperatura: float = 0.2,
    nivel_thinking: str = "LOW",
    limite_tokens: int = 1500,
    nombre_cliente: str = "No especificado",
    telefono_cliente: str = "No registrado",
    taller_origen: str = "Taller Central · FixLab",
    modelo_preferido: str = "gemini-3.8-flash",
) -> ResultadoClasificacion:
    tiempo_inicio = time.perf_counter()

    cliente_genai = None
    try:
        if hasattr(types, "HttpOptions"):
            opciones_http = types.HttpOptions(timeout=60000)
            cliente_genai = genai.Client(api_key=clave_api, http_options=opciones_http)
        else:
            cliente_genai = genai.Client(api_key=clave_api)
    except Exception:
        try:
            cliente_genai = genai.Client(api_key=clave_api)
        except Exception as error_cliente:
            raise ErrorAutenticacionAPI(
                f"Fallo al inicializar cliente de Google GenAI: {error_cliente}",
                accion_sugerida="Comprueba que la clave GEMINI_API_KEY tenga formato válido."
            )

    todos_modelos = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"]
    modelos_candidatos = [modelo_preferido] + [m for m in todos_modelos if m != modelo_preferido]

    ultimo_error: Optional[Exception] = None
    respuesta = None
    modelo_utilizado = modelo_preferido
    auto_recuperado = False

    for modelo_evaluar in modelos_candidatos:
        soporta_thinking = ("3.8" in modelo_evaluar or "2." in modelo_evaluar) and nivel_thinking != "OFF"
        tokens_efectivos = max(limite_tokens, 4000) if soporta_thinking else limite_tokens

        configuracion = None
        if soporta_thinking:
            try:
                configuracion = types.GenerateContentConfig(
                    system_instruction=PROMPT_SISTEMA_OPERATIVO,
                    response_mime_type="application/json",
                    temperature=temperatura,
                    max_output_tokens=tokens_efectivos,
                    thinking_config=types.ThinkingConfig(thinking_level=nivel_thinking),
                )
            except Exception:
                configuracion = types.GenerateContentConfig(
                    system_instruction=PROMPT_SISTEMA_OPERATIVO,
                    response_mime_type="application/json",
                    temperature=temperatura,
                    max_output_tokens=tokens_efectivos,
                )
        else:
            configuracion = types.GenerateContentConfig(
                system_instruction=PROMPT_SISTEMA_OPERATIVO,
                response_mime_type="application/json",
                temperature=temperatura,
                max_output_tokens=tokens_efectivos,
            )

        try:
            res_intento = cliente_genai.models.generate_content(
                model=modelo_evaluar,
                contents=f"Mensaje entrante de WhatsApp:\n\"\"\"\n{mensaje_texto}\n\"\"\"",
                config=configuracion,
            )
            if res_intento and hasattr(res_intento, "text") and res_intento.text and res_intento.text.strip():
                respuesta = res_intento
                modelo_utilizado = modelo_evaluar
                break
        except Exception as error_intento:
            ultimo_error = error_intento
            detalle_intento = str(error_intento)

            if any(k in detalle_intento for k in ("API_KEY_INVALID", "PERMISSION_DENIED", "UNAUTHENTICATED", "401", "403")):
                raise ErrorAutenticacionAPI("Clave de API inválida o denegada.")

            continue

    texto_respuesta_valido = False
    if respuesta and hasattr(respuesta, "text") and respuesta.text:
        try:
            if respuesta.text.strip():
                texto_respuesta_valido = True
        except Exception:
            texto_respuesta_valido = False

    if not texto_respuesta_valido:
        for modelo_rescate in ["gemini-3.8-flash", "gemini-3.5-flash-lite"]:
            try:
                config_rescate = types.GenerateContentConfig(
                    system_instruction=PROMPT_SISTEMA_OPERATIVO,
                    response_mime_type="application/json",
                    temperature=0.2,
                    max_output_tokens=1500,
                )
                res_rescate = cliente_genai.models.generate_content(
                    model=modelo_rescate,
                    contents=f"Mensaje entrante de WhatsApp:\n\"\"\"\n{mensaje_texto}\n\"\"\"",
                    config=config_rescate,
                )
                if res_rescate and hasattr(res_rescate, "text") and res_rescate.text and res_rescate.text.strip():
                    respuesta = res_rescate
                    modelo_utilizado = modelo_rescate
                    auto_recuperado = True
                    texto_respuesta_valido = True
                    break
            except Exception as error_rescate:
                ultimo_error = error_rescate
                continue

    if not texto_respuesta_valido or not respuesta:
        if ultimo_error:
            detalle_u = str(ultimo_error)
            if "RESOURCE_EXHAUSTED" in detalle_u or "429" in detalle_u:
                raise ErrorCuotaExcedida("Límite de cuota alcanzado (HTTP 429).")
            elif "UNAVAILABLE" in detalle_u or "503" in detalle_u:
                raise ErrorServidorSaturado("Servidores de Gemini saturados (HTTP 503).")
            elif any(k in detalle_u for k in ("API_KEY_INVALID", "PERMISSION_DENIED", "UNAUTHENTICATED", "401", "403")):
                raise ErrorAutenticacionAPI("Clave de API no válida o rechazada.")
            elif any(p in detalle_u.lower() for p in ("timeout", "timed out", "connection", "connect")):
                raise ErrorConexionRed(f"Tiempo de espera de red agotado: {detalle_u}")
            elif "404" in detalle_u or "not found" in detalle_u.lower():
                raise ErrorOperativoTaller(
                    f"El modelo no está disponible en la API: {detalle_u}",
                    accion_sugerida="Asegúrate de seleccionar 'gemini-3.8-flash' en el panel lateral."
                )
            else:
                raise ErrorOperativoTaller(
                    f"Incidencia técnica del servicio de IA: {detalle_u}",
                    accion_sugerida="Prueba reintentar en Modo TURBO o utiliza el Triaje Manual de Mostrador."
                )
        raise ErrorRespuestaVacia("La API devolvió una respuesta vacía o sin texto legible.")

    datos_json = limpiar_y_parsear_json_gemini(respuesta.text)

    nombre_final = nombre_cliente
    if nombre_final == "No especificado" and datos_json.get("cliente_nombre_detectado", "No especificado") != "No especificado":
        nombre_final = datos_json["cliente_nombre_detectado"]

    telefono_final = telefono_cliente
    if telefono_final == "No registrado" and datos_json.get("cliente_telefono_detectado", "No registrado") != "No registrado":
        telefono_final = datos_json["cliente_telefono_detectado"]

    latencia_total = round(time.perf_counter() - tiempo_inicio, 2)
    sufijo_recuperado = " (Auto-Recuperado Turbo)" if auto_recuperado else ""

    return {
        "urgencia": datos_json["urgencia"],
        "urgencia_color": datos_json["urgencia_color"],
        "categoria": datos_json["categoria"],
        "dispositivo": datos_json["dispositivo"],
        "falla_reportada": datos_json["falla_reportada"],
        "accion_recomendada": datos_json["accion_recomendada"],
        "borrador_respuesta": datos_json["borrador_respuesta"],
        "latencia_segundos": latencia_total,
        "cliente_nombre": nombre_final,
        "cliente_telefono": telefono_final,
        "nivel_thinking": nivel_thinking,
        "tokens_limite": limite_tokens,
        "metodo": f"🤖 {modelo_utilizado}{sufijo_recuperado}",
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

            # Input nativo con auto-foco para ingreso instantáneo con teclado numérico
            pin_teclado = st.text_input(
                "⌨️ Ingreso rápido con teclado numérico:",
                type="password",
                max_chars=4,
                key="input_pin_teclado_fisico",
                placeholder="••••  (Digita 4 números y pulsa Enter)",
                help="Puedes escribir directamente los 4 dígitos con el teclado numérico de tu computadora (0-9) y pulsar Enter para validar de inmediato.",
            )

            if pin_teclado and len(pin_teclado) == 4:
                if pin_teclado == datos_taller["pin"]:
                    st.session_state["usuario_autenticado"] = True
                    st.session_state["pin_buffer"] = ""
                    st.rerun()
                else:
                    st.error(f"❌ PIN incorrecto para {taller_elegido}. PIN demo: `{datos_taller['pin']}`")

            pin_actual = st.session_state.get("pin_buffer", "")
            if len(pin_actual) == 4:
                if pin_actual == datos_taller["pin"]:
                    st.session_state["usuario_autenticado"] = True
                    st.session_state["pin_buffer"] = ""
                    st.rerun()
                else:
                    st.error(f"❌ PIN incorrecto para {taller_elegido}. PIN demo: `{datos_taller['pin']}`")
                    st.session_state["pin_buffer"] = ""
                    pin_actual = ""

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
                    st.session_state["pin_buffer"] = st.session_state.get("pin_buffer", "")[:-1]
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
                        st.error(f"❌ PIN incorrecto para {taller_elegido}. Recuerda que puedes consultar el PIN demo `{datos_taller['pin']}` o pulsar el botón de Acceso Rápido inferior.")
                        st.session_state["pin_buffer"] = ""

            st.markdown("---")
            st.info(f"💡 **PIN demostrativo para evaluación:** `{datos_taller['pin']}`")

            if st.button("⚡ Acceso Rápido Modo Evaluador (1 Clic)", type="secondary", use_container_width=True):
                st.session_state["usuario_autenticado"] = True
                st.session_state["pin_buffer"] = ""
                st.rerun()

    # Inyección de script para auto-enfoque y captura de teclado numérico físico
    components.html(
        """
        <script>
        (function() {
            try {
                const pdoc = window.parent.document;
                
                // 1. Auto-enfocar el campo de texto del PIN al cargar con auto-submit al 4to dígito
                setTimeout(() => {
                    const pinInput = pdoc.querySelector('input[type="password"]');
                    if (pinInput) {
                        if (pdoc.activeElement !== pinInput) {
                            pinInput.focus();
                        }
                        if (!pinInput._tallerfix_has_auto_blur) {
                            pinInput._tallerfix_has_auto_blur = true;
                            pinInput.addEventListener('input', function() {
                                if (this.value && this.value.length >= 4) {
                                    this.blur();
                                }
                            });
                        }
                    }
                }, 150);

                // 2. Listener global de teclado numérico (Numpad + Teclas numéricas superiores)
                if (!pdoc._tallerfix_pin_listener_v4) {
                    pdoc._tallerfix_pin_listener_v4 = true;
                    pdoc.addEventListener('keydown', function(event) {
                        const pinDisplay = pdoc.querySelector('.pin-display');
                        if (!pinDisplay) return; // Solo activo en la pantalla de PIN

                        const active = pdoc.activeElement;
                        if (active && active.tagName === 'INPUT' && active.type === 'password') {
                            return; // El usuario ya está escribiendo en el campo nativo enfocado
                        }

                        const k = event.key;
                        if (k >= '0' && k <= '9') {
                            event.preventDefault();
                            const btns = Array.from(pdoc.querySelectorAll('button'));
                            const numBtn = btns.find(b => b.innerText.trim() === k);
                            if (numBtn) numBtn.click();
                        } else if (k === 'Backspace' || k === 'Delete') {
                            event.preventDefault();
                            const btns = Array.from(pdoc.querySelectorAll('button'));
                            const delBtn = btns.find(b => b.innerText.includes('Borrar'));
                            if (delBtn) delBtn.click();
                        } else if (k === 'Enter') {
                            event.preventDefault();
                            const btns = Array.from(pdoc.querySelectorAll('button'));
                            const enterBtn = btns.find(b => b.innerText.includes('Entrar'));
                            if (enterBtn) enterBtn.click();
                        }
                    });
                }
            } catch (e) {
                console.log("PIN Pad Keyboard Listener:", e);
            }
        })();
        </script>
        """,
        height=0,
        width=0,
    )

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

        st.subheader("🧭 Módulos del Sistema")
        opciones_menu = [
            "🛠️ Terminal de Triaje",
            "💵 Tarifario y Catálogo",
            "🧮 Calculadora de Cotizaciones",
            "📋 Checklist de Recepción",
            "📚 Registro Histórico",
        ]
        if "pending_modulo_seleccionado" in st.session_state:
            st.session_state["radio_modulo_seleccionado"] = st.session_state.pop("pending_modulo_seleccionado")

        if "radio_modulo_seleccionado" not in st.session_state:
            st.session_state["radio_modulo_seleccionado"] = opciones_menu[0]

        vista_seleccionada = st.radio(
            "Selecciona el módulo a operar:",
            options=opciones_menu,
            key="radio_modulo_seleccionado",
            label_visibility="collapsed",
        )

        if conteo_historial > 0:
            st.caption(f"📁 **{conteo_historial}** casos registrados en la sesión actual.")

        if "Terminal" in vista_seleccionada:
            modo_vista = "clasificador"
        elif "Tarifario" in vista_seleccionada:
            modo_vista = "tarifario"
        elif "Calculadora" in vista_seleccionada:
            modo_vista = "calculadora"
        elif "Checklist" in vista_seleccionada:
            modo_vista = "checklist"
        else:
            modo_vista = "historial"

        st.markdown("---")

        temperatura = 0.2
        nivel_thinking = "LOW"
        limite_tokens = 1500
        modelo_seleccionado = "gemini-3.8-flash"

        if modo_vista == "clasificador":
            st.subheader("⚙️ Parámetros del Asistente")

            modelo_opcion = st.selectbox(
                "Motor de Inferencia Gemini:",
                options=[
                    "gemini-3.8-flash (Flagship Oficial · Producción)",
                    "gemini-3.5-flash-lite (Flash-Lite · Máxima Velocidad)",
                    "gemini-2.5-flash (Versión Anterior)",
                ],
                index=0,
                help="gemini-3.8-flash es el modelo oficial vigente de Google para inferencia de alto rendimiento y clasificación estructurada.",
            )
            modelo_seleccionado = modelo_opcion.split(" ")[0]

            temperatura = st.slider(
                "Creatividad de respuesta (Temperature):",
                min_value=0.0,
                max_value=1.0,
                value=0.2,
                step=0.1,
                help="Valores bajos (0.0-0.2) son deterministas y precisos. Valores mayores dan respuestas más creativas y variadas.",
            )

            opcion_thinking = st.select_slider(
                "Velocidad y Modo de IA:",
                options=[
                    "⚡ TURBO (1-2s · Directo)",
                    "LOW (~15s · Ligero)",
                    "MEDIUM (~25s · Equilibrado)",
                    "HIGH (~35s · Profundo)",
                ],
                value="⚡ TURBO (1-2s · Directo)",
                help="⚡ TURBO genera la respuesta inmediata en 1 a 2 segundos (inferencia directa sin razonamiento interno, idéntico a apps de viajes o e-commerce). LOW, MEDIUM y HIGH activan deliberación interna reflexiva si se requiere análisis forense.",
            )
            mapeo_thinking = {
                "⚡ TURBO (1-2s · Directo)": "OFF",
                "LOW (~15s · Ligero)": "LOW",
                "MEDIUM (~25s · Equilibrado)": "MEDIUM",
                "HIGH (~35s · Profundo)": "HIGH",
            }
            nivel_thinking = mapeo_thinking[opcion_thinking]

            limite_tokens = st.slider(
                "Límite de tokens de salida:",
                min_value=500,
                max_value=3000,
                value=1200,
                step=100,
                help="En modo TURBO, entre 500 y 1200 tokens maximizan la velocidad. Si activas razonamiento reflexivo (LOW/MEDIUM/HIGH), el sistema recomienda mantener 1000 tokens o más.",
            )

        elif modo_vista == "historial":
            st.subheader("📊 Métricas de Operación")
            criticas = sum(1 for item in historial if "ALTA" in str(item.get("urgencia", "")))
            latencia_media = (
                round(sum(float(item.get("latencia_segundos", 0.0)) for item in historial if "Manual" not in str(item.get("metodo", ""))) /
                      max(1, sum(1 for item in historial if "Manual" not in str(item.get("metodo", "")))), 2)
            )
            st.markdown(f"**Total casos atendidos:** `{conteo_historial}`")
            st.markdown(f"**Garantías o urgencias:** `{criticas}`")
            st.markdown(f"**Latencia media de IA:** `{latencia_media}s`")
        elif modo_vista == "tarifario":
            st.subheader("📋 Catálogo de Servicios")
            st.markdown(f"**Servicios registrados:** `{len(CATALOGO_SERVICIOS)}`")
            st.markdown("**Garantías ofrecidas:** `15 a 90 días`")
            st.caption("Consulta rápida de precios promedio de repuestos y tiempos estándar de mano de obra.")
        elif modo_vista == "calculadora":
            st.subheader("🧮 Control de Presupuestos")
            st.caption("Desglose técnico de costo de repuesto + mano de obra + fondo de imprevistos con cotización directa a WhatsApp.")
        elif modo_vista == "checklist":
            st.subheader("📋 Recepción Técnica")
            st.caption("Verificación de 9 puntos de hardware para comprobante de ingreso formal y prevención de reclamos falsos.")

        st.markdown("---")
        st.markdown(
            """
            <div style="font-size: 0.78rem; color: #64748b; line-height: 1.4;">
                <strong>Módulo:</strong> Fundamentos de Programación para IA<br>
                <strong>Máster en IA:</strong> OBS Business School<br>
                <strong>Backend:</strong> Google Gemini 3.8 Flash (Producción)
            </div>
            """,
            unsafe_allow_html=True,
        )

        return temperatura, nivel_thinking, limite_tokens, modo_vista, modelo_seleccionado

def generar_csv_historial(historial: list[RegistroHistorial]) -> str:
    try:
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
        escritor = csv.DictWriter(buffer, fieldnames=campos, extrasaction="ignore")
        escritor.writeheader()
        for fila in historial:
            escritor.writerow(fila)
        return buffer.getvalue()
    except Exception:
        return "timestamp,taller,error\n00:00:00,General,Error al exportar registros"

def renderizar_encabezado_principal(modelo_activo: str = "gemini-3.8-flash") -> None:
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
                    <span class="telemetria-pill">🤖 {modelo_activo}</span>
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
    criticas = sum(1 for item in historial if "ALTA" in str(item.get("urgencia", "")))
    manuales = sum(1 for item in historial if "Manual" in str(item.get("metodo", "")))
    ia_items = [
        float(item.get("latencia_segundos", 0.0))
        for item in historial
        if "Manual" not in str(item.get("metodo", ""))
    ]
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
        try:
            with st.container(border=True):
                col_encabezado_izq, col_encabezado_der = st.columns([4, 1])

                nombre = str(entrada.get("cliente_nombre", "No especificado"))
                telefono = str(entrada.get("cliente_telefono", "No registrado"))
                if nombre != "No especificado" and telefono != "No registrado":
                    identificador = f"{nombre} ({telefono})"
                elif telefono != "No registrado":
                    identificador = f"Tel: {telefono}"
                elif nombre != "No especificado":
                    identificador = nombre
                else:
                    identificador = "Cliente no identificado"

                urgencia = str(entrada.get("urgencia", "BAJA"))
                urgencia_clase = (
                    "badge-alta" if "ALTA" in urgencia else "badge-media" if "MEDIA" in urgencia else "badge-baja"
                )

                with col_encabezado_izq:
                    st.markdown(
                        f"**Caso #{len(historial) - indice}** · `{entrada.get('timestamp', '--:--')}` · **{entrada.get('taller', 'Taller')}** · *{entrada.get('metodo', 'Registro')}* | "
                        f"👤 **{identificador}** | <span class='badge-chip {urgencia_clase}'>{urgencia}</span> | "
                        f"**{entrada.get('categoria', 'General')}**",
                        unsafe_allow_html=True,
                    )
                with col_encabezado_der:
                    if "Manual" in str(entrada.get("metodo", "")):
                        st.caption("✍️ Manual")
                    else:
                        st.caption(f"⚡ {entrada.get('latencia_segundos', 0.0)}s · {entrada.get('nivel_thinking', 'LOW')}")

                col_dev, col_act = st.columns(2)
                with col_dev:
                    st.markdown(f"**📱 Dispositivo:** {entrada.get('dispositivo', 'No especificado')} · **Falla:** {entrada.get('falla_reportada', 'Sin detalle')}")
                with col_act:
                    st.markdown(f"**🎯 Acción en taller:** {entrada.get('accion_recomendada', 'Revisión técnica')}")

                st.caption(f"Mensaje registrado: \"{entrada.get('mensaje_original', '')}\"")

                borrador = str(entrada.get("borrador_respuesta", ""))
                st.text_area(
                    label=f"Respuesta generada (Caso #{len(historial) - indice})",
                    value=borrador,
                    height=85,
                    key=f"historial_borrador_{indice}",
                    disabled=True,
                )

                enlace_wa = construir_enlace_whatsapp(telefono, borrador)
                st.link_button(
                    label="📲 Reabrir en WhatsApp",
                    url=enlace_wa,
                    use_container_width=False,
                    key=f"btn_wa_historial_{indice}",
                )
        except Exception:
            st.warning(f"⚠️ No fue posible renderizar la ficha #{len(historial) - indice}.")

def callback_cargar_preset_ia(texto: str, nombre: str, telefono: str) -> None:
    st.session_state["input_ia_mensaje"] = texto
    st.session_state["input_ia_nombre"] = nombre
    st.session_state["input_ia_telefono"] = telefono
    st.session_state.pop("pending_set_input_ia_nombre", None)
    st.session_state.pop("pending_set_input_ia_telefono", None)
    st.session_state["mensaje_input"] = texto
    st.session_state["cliente_nombre_input"] = nombre
    st.session_state["cliente_telefono_input"] = telefono
    st.session_state["disparar_clasificacion_automatica"] = True
    st.session_state["borrador_respuesta_whatsapp"] = ""
    st.session_state["borrador_no_interpretable"] = ""

def callback_limpiar_formulario_ia() -> None:
    st.session_state["input_ia_mensaje"] = ""
    st.session_state["input_ia_nombre"] = ""
    st.session_state["input_ia_telefono"] = ""
    st.session_state.pop("pending_set_input_ia_nombre", None)
    st.session_state.pop("pending_set_input_ia_telefono", None)
    st.session_state["mensaje_input"] = ""
    st.session_state["cliente_nombre_input"] = ""
    st.session_state["cliente_telefono_input"] = ""
    st.session_state["resultado_actual"] = None
    st.session_state["mostrar_bloque_copia"] = False
    st.session_state["borrador_respuesta_whatsapp"] = ""
    st.session_state["borrador_no_interpretable"] = ""

def renderizar_modo_ia(
    temperatura_seleccionada: float,
    nivel_thinking_seleccionado: str,
    limite_tokens_seleccionado: int,
    modelo_seleccionado: str = "gemini-3.8-flash",
) -> None:
    if "pending_set_input_ia_nombre" in st.session_state:
        st.session_state["input_ia_nombre"] = st.session_state.pop("pending_set_input_ia_nombre")
    if "pending_set_input_ia_telefono" in st.session_state:
        st.session_state["input_ia_telefono"] = st.session_state.pop("pending_set_input_ia_telefono")
    st.markdown("#### ⚡ Acciones Rápidas · Casos Frecuentes")
    st.caption("Selecciona cualquier caso para precargar datos y clasificar automáticamente en 1 clic:")

    cols_presets = st.columns(4)
    for idx, (nombre_preset, datos_preset) in enumerate(PRESET_MESSAGES.items()):
        with cols_presets[idx % 4]:
            st.button(
                nombre_preset,
                use_container_width=True,
                key=f"preset_btn_{idx}",
                on_click=callback_cargar_preset_ia,
                args=(datos_preset["texto"], datos_preset["nombre"], datos_preset["telefono"]),
                help=f"Precargar y clasificar: {datos_preset['texto'][:60]}...",
            )

    st.markdown("---")

    col_nombre, col_telefono = st.columns(2)
    with col_nombre:
        nombre_ingresado = st.text_input(
            "👤 Nombre del cliente (opcional):",
            placeholder="Ej: Juan Pérez",
            key="input_ia_nombre",
        )
    with col_telefono:
        telefono_ingresado = st.text_input(
            "📱 Teléfono de WhatsApp (opcional):",
            placeholder="Ej: +52 55 1234 5678",
            key="input_ia_telefono",
        )

    mensaje_actual = st.text_area(
        label="💬 Mensaje de WhatsApp copiado del cliente:",
        height=130,
        placeholder="Pega aquí el mensaje del cliente (ej: Hola buenas, cuánto cobran por cambiar la pantalla de un Samsung A54?)...",
        key="input_ia_mensaje",
    )

    columna_analizar, columna_limpiar = st.columns([1, 4])
    with columna_analizar:
        boton_analizar = st.button("🤖 Clasificar con Gemini IA", type="primary", use_container_width=True)
    with columna_limpiar:
        st.button(
            "🗑️ Limpiar Campos",
            use_container_width=False,
            key="btn_limpiar_ia",
            on_click=callback_limpiar_formulario_ia,
        )

    taller_activo = st.session_state.get("taller_activo", "Taller Central · FixLab")

    disparar_auto = st.session_state.pop("disparar_clasificacion_automatica", False)

    if boton_analizar or disparar_auto:
        texto_a_evaluar = mensaje_actual.strip()

        if not texto_a_evaluar:
            st.warning("⚠️ **Entrada vacía:** Pega o escribe el mensaje recibido por WhatsApp antes de presionar Clasificar.")
            return

        if not validar_coherencia_minima(texto_a_evaluar):
            diagnostico_coherencia: DiagnosticoIncidencia = {
                "categoria": "Validación de Contenido",
                "titulo": "Mensaje Ininteligible o Sin Contexto Comunicativo",
                "descripcion": (
                    "El texto ingresado contiene una secuencia de caracteres sin sentido o letras al azar "
                    "que no constituyen una consulta técnica legítima para el taller."
                ),
                "accion_sugerida": (
                    "Verifica el mensaje copiado de WhatsApp. Si el cliente envió una imagen o nota de voz, "
                    "solicita que detalle su falla por texto o regístralo mediante la pestaña '✍️ Triaje Manual de Mostrador'."
                ),
                "icono": "🔍",
                "es_recuperable_manual": True,
            }
            renderizar_alerta_incidencia(diagnostico_coherencia)
            return

        clave_api = obtener_clave_gemini()
        if not clave_api:
            diagnostico_clave: DiagnosticoIncidencia = {
                "categoria": "Configuración del Sistema",
                "titulo": "Servicio de IA Pendiente de Configuración (GEMINI_API_KEY)",
                "descripcion": (
                    "No se detectó la clave de API de Google Gemini en las variables de entorno ni en los secretos del taller."
                ),
                "accion_sugerida": (
                    "Registra 'GEMINI_API_KEY' en el panel de Streamlit Cloud (Settings > Secrets) "
                    "o en tu archivo local .streamlit/secrets.toml. Mientras tanto, el taller continúa 100% operativo "
                    "utilizando la pestaña '✍️ Triaje Manual de Mostrador'."
                ),
                "icono": "🔒",
                "es_recuperable_manual": True,
            }
            renderizar_alerta_incidencia(diagnostico_clave)
            return

        if not GENAI_DISPONIBLE:
            diagnostico_sdk: DiagnosticoIncidencia = {
                "categoria": "Entorno de Ejecución",
                "titulo": "Librería de Inferencia No Disponible",
                "descripcion": (
                    "El paquete oficial 'google-genai' no se encuentra instalado en el entorno de ejecución actual."
                ),
                "accion_sugerida": (
                    "Instala las dependencias necesarias ejecutando 'pip install -r requirements.txt' en la terminal de tu servidor."
                ),
                "icono": "📦",
                "es_recuperable_manual": True,
            }
            renderizar_alerta_incidencia(diagnostico_sdk)
            return

        nombre_resuelto, telefono_resuelto = resolver_datos_contacto(
            texto_a_evaluar, nombre_ingresado, telefono_ingresado
        )

        if "cache_consultas_ia" not in st.session_state:
            st.session_state["cache_consultas_ia"] = {}

        clave_cache = f"{texto_a_evaluar.strip()}_{modelo_seleccionado}_{nivel_thinking_seleccionado}_{temperatura_seleccionada}"

        if clave_cache in st.session_state["cache_consultas_ia"]:
            resultado_cached = st.session_state["cache_consultas_ia"][clave_cache]
            nom_detectado = resultado_cached.get("cliente_nombre", "No especificado")
            tel_detectado = resultado_cached.get("cliente_telefono", "No registrado")
            nom_final = nombre_resuelto if nombre_resuelto != "No especificado" else nom_detectado
            tel_final = telefono_resuelto if telefono_resuelto != "No registrado" else tel_detectado

            resultado = {
                "urgencia": resultado_cached["urgencia"],
                "urgencia_color": resultado_cached["urgencia_color"],
                "categoria": resultado_cached["categoria"],
                "dispositivo": resultado_cached["dispositivo"],
                "falla_reportada": resultado_cached["falla_reportada"],
                "accion_recomendada": resultado_cached["accion_recomendada"],
                "borrador_respuesta": resultado_cached["borrador_respuesta"],
                "latencia_segundos": 0.05,
                "cliente_nombre": nom_final,
                "cliente_telefono": tel_final,
                "nivel_thinking": nivel_thinking_seleccionado,
                "tokens_limite": limite_tokens_seleccionado,
                "metodo": f"{resultado_cached['metodo']} (Caché)",
                "taller": taller_activo,
            }
            st.session_state["resultado_actual"] = resultado
            st.session_state["borrador_respuesta_whatsapp"] = resultado["borrador_respuesta"]
            st.session_state["borrador_no_interpretable"] = resultado["borrador_respuesta"]

            registro_nuevo: RegistroHistorial = {
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "taller": taller_activo,
                "metodo": f"{resultado['metodo']}",
                "cliente_nombre": nom_final,
                "cliente_telefono": tel_final,
                "mensaje_original": texto_a_evaluar,
                "urgencia": resultado["urgencia"],
                "categoria": resultado["categoria"],
                "dispositivo": resultado["dispositivo"],
                "falla_reportada": resultado["falla_reportada"],
                "accion_recomendada": resultado["accion_recomendada"],
                "borrador_respuesta": resultado["borrador_respuesta"],
                "latencia_segundos": 0.05,
                "nivel_thinking": resultado["nivel_thinking"],
                "tokens_limite": resultado["tokens_limite"],
            }
            st.session_state["historial_mensajes"].insert(0, registro_nuevo)

            cambio_inputs = False
            if not nombre_ingresado and nom_final != "No especificado":
                st.session_state["pending_set_input_ia_nombre"] = nom_final
                cambio_inputs = True
            if not telefono_ingresado and tel_final != "No registrado":
                st.session_state["pending_set_input_ia_telefono"] = tel_final
                cambio_inputs = True

            if cambio_inputs:
                st.rerun()
        else:
            try:
                mensaje_spinner = (
                    f"⚡ Analizando en Modo TURBO con {modelo_seleccionado}..."
                    if nivel_thinking_seleccionado == "OFF"
                    else f"🧠 Analizando con razonamiento reflexivo en {modelo_seleccionado}..."
                )
                with st.spinner(mensaje_spinner):
                    resultado = ejecutar_clasificacion_gemini(
                        mensaje_texto=texto_a_evaluar,
                        clave_api=clave_api,
                        temperatura=temperatura_seleccionada,
                        nivel_thinking=nivel_thinking_seleccionado,
                        limite_tokens=limite_tokens_seleccionado,
                        nombre_cliente=nombre_resuelto,
                        telefono_cliente=telefono_resuelto,
                        taller_origen=taller_activo,
                        modelo_preferido=modelo_seleccionado,
                    )
                    st.session_state["resultado_actual"] = resultado
                    st.session_state["borrador_respuesta_whatsapp"] = resultado["borrador_respuesta"]
                    st.session_state["borrador_no_interpretable"] = resultado["borrador_respuesta"]
                    st.session_state["cache_consultas_ia"][clave_cache] = resultado

                    registro_nuevo_ia: RegistroHistorial = {
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "taller": taller_activo,
                        "metodo": resultado["metodo"],
                        "cliente_nombre": resultado["cliente_nombre"],
                        "cliente_telefono": resultado["cliente_telefono"],
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
                    st.session_state["historial_mensajes"].insert(0, registro_nuevo_ia)

                    cambio_inputs = False
                    if not nombre_ingresado and resultado["cliente_nombre"] != "No especificado":
                        st.session_state["pending_set_input_ia_nombre"] = resultado["cliente_nombre"]
                        cambio_inputs = True
                    if not telefono_ingresado and resultado["cliente_telefono"] != "No registrado":
                        st.session_state["pending_set_input_ia_telefono"] = resultado["cliente_telefono"]
                        cambio_inputs = True

                    if cambio_inputs:
                        st.rerun()

            except Exception as error_capturado:
                diagnostico = clasificar_excepcion_operativa(error_capturado)
                renderizar_alerta_incidencia(diagnostico)
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

            st.markdown("##### ⚡ Acciones Rápidas del Caso")
            col_act1, col_act2, col_act3, col_act4 = st.columns(4)
            with col_act1:
                st.link_button(
                    label="📲 Enviar WhatsApp",
                    url=enlace_wa,
                    type="primary",
                    use_container_width=True,
                )
            with col_act2:
                if st.button("📋 Copiar Respuesta", use_container_width=True, key="btn_copiar_borrador"):
                    st.session_state["mostrar_bloque_copia"] = not st.session_state.get("mostrar_bloque_copia", False)
                    st.rerun()
            with col_act3:
                if st.button("🧮 Cotizar en Calculadora", use_container_width=True, key="btn_llevar_calculadora"):
                    st.session_state["pending_calc_equipo"] = resultado_activo.get("dispositivo", "")
                    st.session_state["pending_calc_concepto"] = resultado_activo.get("falla_reportada", "")
                    tel_val = resultado_activo.get("cliente_telefono", "")
                    st.session_state["pending_calc_tel"] = tel_val if tel_val != "No registrado" else ""
                    st.session_state["pending_modulo_seleccionado"] = "🧮 Calculadora de Cotizaciones"
                    st.rerun()
            with col_act4:
                if st.button("📋 Abrir Checklist", use_container_width=True, key="btn_abrir_checklist"):
                    nom_val = resultado_activo.get("cliente_nombre", "")
                    st.session_state["pending_ch_cliente"] = nom_val if nom_val != "No especificado" else ""
                    dev_val = resultado_activo.get("dispositivo", "")
                    st.session_state["pending_ch_equipo"] = dev_val if dev_val != "No identificable" else ""
                    tel_val = resultado_activo.get("cliente_telefono", "")
                    st.session_state["pending_ch_tel"] = tel_val if tel_val != "No registrado" else ""
                    st.session_state["pending_modulo_seleccionado"] = "📋 Checklist de Recepción"
                    st.rerun()

            if st.session_state.get("mostrar_bloque_copia", False):
                st.code(borrador_actualizado, language="text")
                st.caption("💡 Haz clic en el icono superior derecho del cuadro gris para copiar el texto al portapapeles.")

            if telefono_destino != "No registrado":
                st.caption(f"📲 WhatsApp configurado para abrir el chat de **{telefono_destino}** con el borrador precargado.")

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

def renderizar_vista_tarifario() -> None:
    renderizar_encabezado_principal()

    st.subheader("💵 Tarifario y Catálogo Rápido de Reparaciones")
    st.caption("Consulta precios de referencia, tiempos estimados de entrega y coberturas de garantía por tipo de servicio:")

    col_busqueda, col_filtro = st.columns([2, 1])
    with col_busqueda:
        termino_busqueda = st.text_input(
            "🔍 Buscar repuesto o servicio:",
            placeholder="Ej: pantalla, batería, carga...",
            key="filtro_tarifas",
        )
    with col_filtro:
        categoria_filtro = st.selectbox(
            "Filtrar por categoría:",
            ["Todos", "Pantallas", "Baterías", "Puertos / Carga", "Diagnóstico / Software"],
            key="filtro_cat_tarifas",
        )

    servicios_filtrados = [
        s for s in CATALOGO_SERVICIOS
        if (categoria_filtro == "Todos" or s["categoria"] == categoria_filtro)
        and (not termino_busqueda or termino_busqueda.lower() in s["servicio"].lower())
    ]

    for s in servicios_filtrados:
        with st.container(border=True):
            col_s1, col_s2, col_s3, col_s4 = st.columns([3, 2, 2, 2])
            with col_s1:
                st.markdown(f"**{s['servicio']}**")
                st.caption(f"Categoría: {s['categoria']}")
            with col_s2:
                st.markdown(f"💰 `{s['costo_aprox']}`")
            with col_s3:
                st.markdown(f"⏱️ `{s['tiempo']}`")
            with col_s4:
                st.markdown(f"🛡️ `{s['garantia']}`")

def renderizar_vista_calculadora() -> None:
    if "pending_calc_equipo" in st.session_state:
        st.session_state["calc_equipo"] = st.session_state.pop("pending_calc_equipo")
    if "pending_calc_concepto" in st.session_state:
        st.session_state["calc_concepto"] = st.session_state.pop("pending_calc_concepto")
    if "pending_calc_tel" in st.session_state:
        st.session_state["calc_tel"] = st.session_state.pop("pending_calc_tel")

    if "calc_equipo" not in st.session_state:
        st.session_state["calc_equipo"] = "Samsung Galaxy A54"
    if "calc_concepto" not in st.session_state:
        st.session_state["calc_concepto"] = "Cambio de pantalla display original"

    renderizar_encabezado_principal()

    st.subheader("🧮 Calculadora de Presupuestos y Cotizaciones")
    st.caption("Calcula el precio final para el cliente desglosando repuesto, mano de obra e imprevistos:")

    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1:
        costo_repuesto = st.number_input(
            "Costo del repuesto ($ USD):",
            min_value=0.0,
            value=35.0,
            step=5.0,
            key="calc_repuesto",
        )
    with col_c2:
        mano_obra = st.number_input(
            "Mano de obra técnica ($ USD):",
            min_value=0.0,
            value=25.0,
            step=5.0,
            key="calc_mano_obra",
        )
    with col_c3:
        margen_garantia = st.number_input(
            "Fondo de garantía / Imprevistos ($ USD):",
            min_value=0.0,
            value=10.0,
            step=2.5,
            key="calc_garantia",
        )

    total_presupuesto = costo_repuesto + mano_obra + margen_garantia
    st.markdown(f"#### 💵 Total Presupuesto Sugerido: **${total_presupuesto:,.2f} USD**")

    col_eq, col_conc = st.columns(2)
    with col_eq:
        dispositivo_cot = st.text_input("Equipo a cotizar:", key="calc_equipo")
    with col_conc:
        concepto_cot = st.text_input("Concepto:", key="calc_concepto")

    garantia_meses = st.selectbox(
        "Garantía ofrecida:",
        ["30 días de garantía", "60 días de garantía", "90 días de garantía"],
        index=1,
        key="calc_gar_meses",
    )

    texto_cotizacion = (
        f"Hola, te compartimos tu cotización formal para {dispositivo_cot}:\n"
        f"🔧 Servicio: {concepto_cot}\n"
        f"💰 Costo total: ${total_presupuesto:,.2f} USD (incluye repuesto e instalación profesional)\n"
        f"🛡️ Cobertura: {garantia_meses}\n"
        "¿Te gustaría apartar tu repuesto y agendar tu recepción hoy?"
    )
    st.text_area("Borrador de cotización para WhatsApp:", value=texto_cotizacion, height=120, key="calc_borrador")

    col_tel_cot, col_btn_cot = st.columns([2, 1])
    with col_tel_cot:
        tel_cot = st.text_input("Teléfono WhatsApp del cliente (opcional):", placeholder="Ej: +525512345678", key="calc_tel")
    with col_btn_cot:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        enlace_cot = construir_enlace_whatsapp(tel_cot, texto_cotizacion)
        st.link_button("📲 Enviar Cotización por WhatsApp", url=enlace_cot, type="primary", use_container_width=True)

def renderizar_vista_checklist() -> None:
    if "pending_ch_cliente" in st.session_state:
        st.session_state["ch_cliente"] = st.session_state.pop("pending_ch_cliente")
    if "pending_ch_equipo" in st.session_state:
        st.session_state["ch_equipo"] = st.session_state.pop("pending_ch_equipo")
    if "pending_ch_tel" in st.session_state:
        st.session_state["ch_tel"] = st.session_state.pop("pending_ch_tel")

    renderizar_encabezado_principal()

    st.subheader("📋 Checklist de Recepción Física de Equipos")
    st.caption("Verifica el estado físico del equipo antes de recibirlo para proteger al taller de reclamos injustificados:")

    col_ch1, col_ch2, col_ch3 = st.columns(3)
    with col_ch1:
        ch_enciende = st.checkbox("Enciende correctamente", value=True, key="ch_enc")
        ch_pantalla = st.checkbox("Pantalla da imagen nítida", value=True, key="ch_pant")
        ch_touch = st.checkbox("Touchscreen responde 100%", value=False, key="ch_touch")
    with col_ch2:
        ch_camaras = st.checkbox("Cámaras frontal y trasera ok", value=True, key="ch_cam")
        ch_carga = st.checkbox("Carga y detecta cable", value=True, key="ch_carga")
        ch_audio = st.checkbox("Bocinas y micrófono ok", value=True, key="ch_audio")
    with col_ch3:
        ch_biometria = st.checkbox("Face ID / Huella digital ok", value=True, key="ch_bio")
        ch_senial = st.checkbox("Lee chip SIM / WiFi ok", value=True, key="ch_sim")
        ch_humedad = st.checkbox("Sin rastros de humedad/óxido", value=True, key="ch_hum")

    col_cli_ck, col_eq_ck = st.columns(2)
    with col_cli_ck:
        cliente_check = st.text_input("Nombre del cliente para constancia:", placeholder="Ej: Carlos Pérez", key="ch_cliente")
    with col_eq_ck:
        equipo_check = st.text_input("Equipo recibido (marca y modelo):", placeholder="Ej: iPhone 11 negro 64GB", key="ch_equipo")

    detalles_esteticos = st.text_input(
        "Detalles estéticos previos (rayones, golpes, tapa estrellada):",
        placeholder="Ej: Golpe visible en esquina superior derecha, tapa trasera despostillada",
        key="ch_detalles",
    )

    estados_fallas = []
    if not ch_enciende:
        estados_fallas.append("No enciende al recibir")
    if not ch_pantalla:
        estados_fallas.append("Falla de display/pantalla")
    if not ch_touch:
        estados_fallas.append("Falla en táctil/touch")
    if not ch_camaras:
        estados_fallas.append("Falla en cámaras")
    if not ch_carga:
        estados_fallas.append("Falla en puerto de carga")
    if not ch_audio:
        estados_fallas.append("Falla de audio/micrófono")
    if not ch_biometria:
        estados_fallas.append("Biometría dañada")
    if not ch_senial:
        estados_fallas.append("Sin señal / sin WiFi")
    if not ch_humedad:
        estados_fallas.append("Presencia de sulfato o humedad")

    resumen_fallas = ", ".join(estados_fallas) if estados_fallas else "Sin fallas secundarias detectadas"
    nota_recepcion = (
        f"📋 *COMPROBANTE DE RECEPCIÓN TÉCNICA · TALLERFIX*\n"
        f"👤 Cliente: {cliente_check if cliente_check else 'Cliente'}\n"
        f"📱 Dispositivo: {equipo_check if equipo_check else 'Dispositivo'}\n"
        f"🔍 Estado inicial en mostrador: {resumen_fallas}\n"
        f"⚠️ Detalles estéticos previos: {detalles_esteticos if detalles_esteticos else 'Ninguno registrado'}\n"
        "Equipo ingresado formalmente a revisión en taller."
    )

    st.text_area("Comprobante de recepción para WhatsApp:", value=nota_recepcion, height=120, key="ch_borrador")

    col_tel_ck, col_btn_ck = st.columns([2, 1])
    with col_tel_ck:
        tel_check = st.text_input("Teléfono del cliente para enviar comprobante:", placeholder="Ej: +525512345678", key="ch_tel")
    with col_btn_ck:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        enlace_check = construir_enlace_whatsapp(tel_check, nota_recepcion)
        st.link_button("📲 Enviar Comprobante por WhatsApp", url=enlace_check, type="primary", use_container_width=True)

def renderizar_vista_clasificador(
    temperatura_seleccionada: float,
    nivel_thinking_seleccionado: str,
    limite_tokens_seleccionado: int,
    modelo_seleccionado: str = "gemini-3.8-flash",
) -> None:
    renderizar_encabezado_principal(modelo_seleccionado)

    tab_ia, tab_manual = st.tabs([
        "🤖 Asistente Gemini IA (Automático)",
        "✍️ Triaje Manual de Mostrador",
    ])

    with tab_ia:
        renderizar_modo_ia(
            temperatura_seleccionada,
            nivel_thinking_seleccionado,
            limite_tokens_seleccionado,
            modelo_seleccionado,
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

    if "input_ia_mensaje" not in st.session_state:
        st.session_state["input_ia_mensaje"] = ""

    if "input_ia_nombre" not in st.session_state:
        st.session_state["input_ia_nombre"] = ""

    if "input_ia_telefono" not in st.session_state:
        st.session_state["input_ia_telefono"] = ""

    if "radio_modulo_seleccionado" not in st.session_state:
        st.session_state["radio_modulo_seleccionado"] = "🛠️ Terminal de Triaje"

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

    (
        temperatura_seleccionada,
        nivel_thinking_seleccionado,
        limite_tokens_seleccionado,
        modo_vista,
        modelo_seleccionado,
    ) = renderizar_barra_lateral()

    if modo_vista == "historial":
        renderizar_vista_historial()
    elif modo_vista == "tarifario":
        renderizar_vista_tarifario()
    elif modo_vista == "calculadora":
        renderizar_vista_calculadora()
    elif modo_vista == "checklist":
        renderizar_vista_checklist()
    else:
        renderizar_vista_clasificador(
            temperatura_seleccionada,
            nivel_thinking_seleccionado,
            limite_tokens_seleccionado,
            modelo_seleccionado,
        )

if __name__ == "__main__":
    main()
