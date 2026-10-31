# Especificación Técnica · Asistente de Mensajes para Taller (Clasificador PyME)

## 1. Problema y Usuario

### 1.1 El Usuario
Técnico propietario de un taller unipersonal de reparación de dispositivos móviles ("Taller Móvil"). Trabaja solo, atendiendo mostrador, realizando micro-soldaduras y cambios de componentes, y gestionando llamadas y WhatsApp al mismo tiempo.

### 1.2 El Problema Concreto
El técnico recibe decenas de mensajes informales de clientes por WhatsApp a lo largo del día. Con las herramientas en mano y atendiendo el mostrador, no puede clasificar la gravedad de cada mensaje. Como resultado:
- Pierde cotizaciones calientes por responder horas después.
- Ignora involuntariamente reclamos de garantías críticas que requieren atención inmediata para no perder al cliente.
- Anota datos de manera caótica en una libreta de papel, perdiendo el hilo de las fallas y modelos.

### 1.3 Alcance: Qué resuelve la IA y qué queda fuera
* **Qué resuelve la IA:**
  - Extrae y normaliza la información operativa clave del mensaje informal (modelo de equipo y síntoma o falla reportada).
  - Determina el nivel de urgencia operativa para priorizar la cola de atención.
  - Clasifica la intención del cliente en una categoría estándar del taller.
  - Redacta un borrador de respuesta empático, profesional y adaptado al contexto, listo para copiar y enviar.
* **Qué queda fuera (No cubierto):**
  - Envío automático de mensajes a WhatsApp (se evita intencionalmente para mantener el control humano y evitar baneos de WhatsApp Business).
  - Cálculo de precios exactos de refacciones o inventario en tiempo real (eso requiere integración con ERP/proveedores externos, fuera del alcance del reto).
  - Gestión de cobros o pasarelas de pago.

---

## 2. Entradas, Funcionalidades y Salidas

### 2.1 Entradas de la Aplicación
1. **Texto del mensaje:** Cadena de texto copiada directamente desde WhatsApp.
2. **Nombre del cliente (opcional):** Identificador de la persona; si se omite, se extrae del encabezado copiado o se registra como no especificado.
3. **Teléfono de WhatsApp (opcional):** Número de contacto con código de país para despacho directo.
4. **Carga rápida de ejemplos:** Botones preconfigurados con casos típicos de taller para pruebas ágiles sin necesidad de escribir.

### 2.2 Funcionalidades
1. **Clasificación de Urgencia y Prioridad:** Asignación de nivel de prioridad:
   - `ALTA / GARANTÍA CRÍTICA`: Reclamos por trabajos previos defectuosos, clientes molestos o equipos bloqueados por reparaciones del taller.
   - `MEDIA`: Cotizaciones con intención clara de reparación y consultas de estatus de equipos ya ingresados.
   - `BAJA`: Preguntas informativas generales, consultas de horarios o mensajes ambiguos.
2. **Categorización:**
   - `Garantía / Reclamo`
   - `Cotización de Reparación`
   - `Estatus de Dispositivo`
   - `Consulta General`
   - `No Interpretable` (Texto sin sentido, caracteres aleatorios o spam)
3. **Resumen Operativo:** Ficha sintética con `Cliente`, `Dispositivo`, `Falla / Solicitud` y `Acción recomendada`.
4. **Borrador de Respuesta al Cliente:** Área de texto multilínea interactiva (`st.text_area`) para previsualizar y editar el mensaje.
5. **Despacho Directo a WhatsApp (Deep Link `wa.me`):** Botón directo que abre la conversación en WhatsApp Web o móvil con el mensaje precargado sin requerir copiar/pegar manual ni APIs de riesgo.
6. **Historial de Mensajes y Contactos:** Vista dedicada navegable desde el menú lateral (`st.sidebar`) con métricas acumuladas, trazabilidad de clientes (nombre/teléfono) y exportación a CSV.
7. **Telemetría de Latencia en Vivo:** Registro y visualización del tiempo de respuesta del modelo en segundos.
8. **Control de Hiperparámetros y Modo Turbo de Inferencia:** Ajuste interactivo en barra lateral de `temperature` (0.0-1.0), modo de razonamiento (`TURBO` ultra-rápido ~1-2s sin thinking deliberativo, `LOW`, `MEDIUM`, `HIGH`) y `max_output_tokens` (500-3000 con soporte de caché en sesión para respuestas instantáneas).
9. **Modalidad Dual de Triaje (Human-in-the-Loop):** Pestañas dedicadas para alternar entre clasificación automática con Gemini 3.8 Flash y registro manual de mostrador, permitiendo gestionar clientes presenciales o sin conexión sin depender exclusivamente de la API.
10. **Gestión Multi-Taller y Acceso con PIN Pad:** Control de turno y sucursal mediante teclado táctil interactivo (estilo terminal POS de taller), con botón de acceso demo inmediato para evaluadores para salvaguardar la disponibilidad operativa.
11. **Módulos Operativos Independientes (Navegación Lateral):** Herramientas operativas de mostrador estructuradas como pantallas completas e independientes en el menú lateral de navegación (`st.sidebar`), evitando desplazamientos verticales innecesarios y manteniendo cada tarea limpia y categorizada:
    - *Tarifario y Catálogo Rápido:* Buscador y filtro por categoría (pantallas, baterías, puertos, diagnóstico) con costos estimados, tiempos de entrega y días de garantía.
    - *Calculadora de Presupuestos:* Desglose transparente de costo de repuesto + mano de obra técnica + margen de garantía, con generación de cotización formal y enlace directo a WhatsApp.
    - *Checklist de Recepción Física de Equipos:* Inspección técnica inicial de 9 puntos clave (encendido, display, táctil, cámaras, carga, audio, biometría, señal, humedad) generando un comprobante de ingreso formal con prevención de reclamos y despacho a WhatsApp.

### 2.3 Salidas
Estructura de datos mostrada en pantalla:
- Ficha de Contacto (Nombre y Teléfono).
- Insignia visual de Urgencia (Rojo, Amarillo, Verde).
- Etiqueta de Categoría.
- Tarjeta de Resumen Operativo.
- Borrador editable con botón de enlace directo a WhatsApp (`wa.me`).
- Historial exportable en CSV con columnas de cliente.
- Cotización técnica desglosada y comprobante de ingreso de equipo con links directos a WhatsApp.

---

## 3. Casos Límite y Manejo de Errores

| Caso Límite | Comportamiento Esperado de la App |
| :--- | :--- |
| **Entrada vacía o solo espacios** | Muestra advertencia: *"El campo está vacío. Pega o escribe un mensaje antes de presionar Clasificar"* y detiene la llamada. |
| **Texto incoherente o teclado aleatorio** (*ej: "hhhggvv"*) | Filtrado por validación léxica previa o clasificado por IA como `No Interpretable`. Se muestra aviso: *"Mensaje no interpretable"* y no se inventan diagnósticos falsos. |
| **Mensaje excesivamente corto o ambiguo** (*ej: "hola", "info"*) | Clasifica en Urgencia `BAJA` y Categoría `Consulta General`. Responde pidiendo cortésmente marca, modelo y falla del equipo. |
| **Garantía o cliente enfadado** (*ej: "me lo dejaron peor, no prende nada"*) | Clasifica automáticamente en `ALTA / GARANTÍA CRÍTICA`. Genera respuesta con máxima prioridad, disculpa empática e invitación a llevar el equipo de inmediato para revisión prioritaria. |
| **Múltiples fallas en un solo mensaje** (*ej: "se cayó, se rompió la pantalla, no carga y la cámara vibra"*) | El resumen operativo lista todas las fallas detectadas en viñetas y el borrador solicita revisión física completa para diagnóstico. |
| **Clave API no configurada** | Detiene la ejecución con aviso administrativo claro: *"Servicio no configurado: No se detectó la clave de API GEMINI_API_KEY"*, sin recurrir a simulaciones encubiertas. |
| **Fallo de conectividad o cuota excedida (`ResourceExhausted`)** | Captura la excepción sin romper la app y muestra: *"Límite de cuota alcanzado (429): Espera 60 segundos antes de reenviar"*. |

---

## 4. Criterios de Aceptación

1. **Criterio 1 (Usabilidad No Técnica):** El técnico puede analizar un mensaje en menos de 2 clics (pegar y analizar) y ver el resultado en una única pantalla legible en móvil.
2. **Criterio 2 (Manejo de Respuestas):** El borrador de respuesta debe estar en un bloque que permita copiarlo con un solo clic.
3. **Criterio 3 (Seguridad Absoluta):** La aplicación no debe contener ninguna API Key en texto plano; debe usar exclusivamente `st.secrets`.
4. **Criterio 4 (Resiliencia ante Casos Vacíos e Ininteligibles):** Ante campos vacíos o cadenas aleatorias, la aplicación no produce errores de ejecución ni diagnósticos ficticios.

---

## 5. Prompts del Sistema Reutilizables (Para Semana 3)

### System Prompt Base para Gemini 3.8 Flash
```text
Eres el asistente de operaciones de un taller especializado en reparación de celulares y tablets.
Tu trabajo es analizar el mensaje crudo enviado por un cliente por WhatsApp y generar una clasificación operativa estructurada.

Debes responder estrictamente en formato JSON con la siguiente estructura:
{
  "urgencia": "ALTA / GARANTÍA CRÍTICA" | "MEDIA" | "BAJA",
  "categoria": "Garantía / Reclamo" | "Cotización de Reparación" | "Estatus de Dispositivo" | "Consulta General" | "No Interpretable",
  "dispositivo": "Marca y modelo identificado, o 'No especificado'",
  "falla_reportada": "Descripción breve del síntoma o daño",
  "accion_recomendada": "Acción que debe tomar el técnico inmediatamente",
  "borrador_respuesta": "Mensaje educado, empático y profesional listo para enviar al cliente por WhatsApp"
}

Reglas obligatorias:
1. Si el texto es incoherente o caracteres aleatorios, clasifica como "No Interpretable" y solicita aclaración sin inventar servicios.
2. Si el cliente menciona que una reparación previa falló o reclama una garantía, la urgencia SIEMPRE es "ALTA / GARANTÍA CRÍTICA".
3. Si el mensaje es ambiguo, pide amablemente los datos faltantes en el borrador de respuesta.
4. El borrador de respuesta debe sonar humano, cercano y profesional.
```

---

## 6. Selección y Justificación de la Pieza de IA (Apartado 4 del Documento Final)

### 6.1 Alternativas Arquitectónicas Evaluadas

1. **Opción A · Modelo Zero-Shot de Hugging Face (`facebook/bart-large-mnli` o `mDeBERTa-v3`):**
   - *Rol:* Clasificar la urgencia y categoría mediante inferencia discriminativa de etiquetas predefinidas.
   - *Ventajas:* Especialización en clasificación supervisada/NLI sin riesgo de alucinación en las categorías.
   - *Desventajas:* No genera el borrador de respuesta ni extrae entidades estructuradas (marca, modelo, cita) sin un modelo generativo adicional. En Streamlit Cloud, alojar los pesos en local excede el límite de 1 GB de RAM (error Out Of Memory), y consumir la Inference API gratuita genera *cold starts* (error HTTP 503 con demoras de 20-30s).
2. **Opción B · Sistema RAG (Retrieval-Augmented Generation):**
   - *Rol:* Búsqueda semántica contra manuales de servicio o lista estática de precios.
   - *Desventajas:* Introduce una base vectorial (Chroma/FAISS) innecesaria para un problema centrado en interpretar mensajes informales y clasificar incidencias rápidamente.
3. **Opción C · API de Google Gemini (`gemini-3.8-flash`) mediante SDK `google-genai` (Opción Seleccionada):**
   - *Rol:* Clasificación zero-shot, extracción contextual de entidades y redacción en una única llamada unificada.
   - *Ventajas:* Latencia ultrabaja (<600 ms), cuota gratuita holgada en Google AI Studio, peso pluma en RAM para Streamlit Cloud, y soporte nativo de *Structured Outputs* (garantía de JSON válido bajo esquema estricto).

### 6.2 Matriz de Comparación Técnica

| Criterio Técnico | Hugging Face Zero-Shot (Local o API) | RAG con Embeddings | Google Gemini 3.8 Flash |
| :--- | :--- | :--- | :--- |
| **Estabilidad en Streamlit Cloud** | 🔴 Riesgosa (OOM o Cold Start 503) | 🟡 Media (consumo de memoria vectorial) | 🟢 Óptima (peso pluma, sin descargas locales) |
| **Latencia de Respuesta** | 🟡 2 a 4 segundos | 🟡 2 a 3 segundos | 🟢 < 600 milisegundos |
| **Capacidades Combinadas** | Solo clasificación de etiquetas | Consulta a documentos | Clasificación + Extracción + Redacción |
| **Garantía de Formato** | Salida numérica de probabilidades | Texto libre dependiente del LLM | JSON Schema nativo con tipado estricto |
| **Riesgo Operativo (Regla 3/10)** | Alto por dependencias externas y RAM | Medio por gestión de índices | Mínimo (alta disponibilidad y SLA) |

### 6.3 Decisión Final y Justificación
Se descarta la arquitectura desacoplada (Hugging Face para clasificar + Gemini para redactar) porque fragmentar la tarea en dos servicios gratuitos duplica los puntos de fallo y multiplica la latencia. Gemini 3.8 Flash resuelve ambos problemas simultáneamente con mayor coherencia semántica: comprende el tono coloquial del cliente de WhatsApp, deduce la urgencia operativa y genera una respuesta contextual impecable en una sola inferencia.

### 6.4 ¿Qué pasa si falla la IA? (Plan de Contingencia y Manejo de Excepciones)
La aplicación implementa una jerarquía de excepciones personalizadas (`ErrorOperativoTaller`) y un módulo de diagnóstico contextual (`clasificar_excepcion_operativa`) que elimina cualquier volcado crudo de errores (*traceback* o mensajes en duro):

1. **Agotamiento de cuota (`ErrorCuotaExcedida` / HTTP 429):** Captura el exceso de tasa por minuto de Google AI Studio y muestra una alerta visual con categoría, diagnóstico amigable y recomendación de esperar 60s o continuar mediante el Triaje Manual sin bloquear la atención al cliente.
2. **Saturación temporal de servidores (`ErrorServidorSaturado` / HTTP 503):** Ejecuta un reintento automático tras 2 segundos; si persiste la congestión, notifica al técnico para reintentar en 15 segundos o usar mostrador manual.
3. **Fallo de credenciales (`ErrorAutenticacionAPI` / HTTP 400, 401, 403):** Diagnostica problemas con `GEMINI_API_KEY` indicando los pasos exactos de configuración en Streamlit Cloud Secrets.
4. **Fallo de red o timeout (`ErrorConexionRed`):** Detecta desconexiones de internet, errores de socket o DNS (`gaierror`) y sugiere verificar la red local.
5. **Respuesta truncada o vacía (`ErrorRespuestaVacia`):** Previene errores cuando el motor de razonamiento de Gemini agota los tokens, aconsejando ampliar el límite a 2,000 tokens o bajar el nivel de thinking a LOW.
6. **Formato no serializable (`ErrorFormatoInvalido`):** Parser tolerante a fallos que remueve etiquetas Markdown (` ```json `), extrae límites `{ ... }` y valida los campos requeridos inyectando valores seguros por defecto.
