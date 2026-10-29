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
1. **Texto del mensaje:** Cadena de texto sin procesar copiada directamente desde WhatsApp.
2. **Carga rápida de ejemplos:** Botones preconfigurados con casos típicos de taller para pruebas ágiles sin necesidad de escribir.

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
3. **Resumen Operativo:** Ficha sintética con `Dispositivo`, `Falla / Solicitud` y `Acción recomendada`.
4. **Borrador de Respuesta al Cliente:** Texto listo para copiar con tono profesional, educado y enfocado a la resolución o cita en taller.

### 2.3 Salidas
Estructura de datos mostrada en pantalla:
- Insignia visual de Urgencia (Rojo, Amarillo, Verde).
- Etiqueta de Categoría.
- Tarjeta de Resumen Operativo.
- Cuadro de texto con botón para copiar la respuesta generada.

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

### System Prompt Base para Gemini 2.5 Flash
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
3. **Opción C · API de Google Gemini (`gemini-2.5-flash`) mediante SDK `google-genai` (Opción Seleccionada):**
   - *Rol:* Clasificación zero-shot, extracción contextual de entidades y redacción en una única llamada unificada.
   - *Ventajas:* Latencia ultrabaja (<600 ms), cuota gratuita holgada en Google AI Studio, peso pluma en RAM para Streamlit Cloud, y soporte nativo de *Structured Outputs* (garantía de JSON válido bajo esquema estricto).

### 6.2 Matriz de Comparación Técnica

| Criterio Técnico | Hugging Face Zero-Shot (Local o API) | RAG con Embeddings | Google Gemini 2.5 Flash |
| :--- | :--- | :--- | :--- |
| **Estabilidad en Streamlit Cloud** | 🔴 Riesgosa (OOM o Cold Start 503) | 🟡 Media (consumo de memoria vectorial) | 🟢 Óptima (peso pluma, sin descargas locales) |
| **Latencia de Respuesta** | 🟡 2 a 4 segundos | 🟡 2 a 3 segundos | 🟢 < 600 milisegundos |
| **Capacidades Combinadas** | Solo clasificación de etiquetas | Consulta a documentos | Clasificación + Extracción + Redacción |
| **Garantía de Formato** | Salida numérica de probabilidades | Texto libre dependiente del LLM | JSON Schema nativo con tipado estricto |
| **Riesgo Operativo (Regla 3/10)** | Alto por dependencias externas y RAM | Medio por gestión de índices | Mínimo (alta disponibilidad y SLA) |

### 6.3 Decisión Final y Justificación
Se descarta la arquitectura desacoplada (Hugging Face para clasificar + Gemini para redactar) porque fragmentar la tarea en dos servicios gratuitos duplica los puntos de fallo y multiplica la latencia. Gemini 2.5 Flash resuelve ambos problemas simultáneamente con mayor coherencia semántica: comprende el tono coloquial del cliente de WhatsApp, deduce la urgencia operativa y genera una respuesta contextual impecable en una sola inferencia.

### 6.4 ¿Qué pasa si falla la IA? (Plan de Contingencia)
1. **Agotamiento de cuota (`ResourceExhausted` / 429):** La app captura la excepción de forma controlada y presenta un mensaje explicativo al técnico recomendando esperar 60 segundos, sin interrumpir la sesión.
2. **Fallo de conexión o timeout de red:** Se activa un aviso claro indicando revisar la conexión a internet.
3. **Mensaje sin sentido o indescifrable:** Se clasifica como `No Interpretable` y se emite un borrador estándar solicitando aclaración, sin inventar diagnósticos técnicos ficticios.
