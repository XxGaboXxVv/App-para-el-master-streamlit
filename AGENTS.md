# AGENTS.md · Contexto del Agente de Inteligencia Artificial

Este archivo sirve como memoria y guía técnica permanente para cualquier agente de programación (Antigravity, Cursor, Copilot, Claude Code) que trabaje en este repositorio.

---

## 1. Misión del Proyecto
Construir y desplegar **TriageFix**, una aplicación web minimalista y robusta en Streamlit para el triaje y clasificación de mensajes de WhatsApp en un taller de reparación de celulares.

---

## 2. Pila Tecnológica y Dependencias
* **Lenguaje:** Python 3.10+
* **Interfaz:** Streamlit (`streamlit>=1.35.0`)
* **SDK de IA:** Google GenAI (`google-genai>=0.1.1` o `google-generativeai`)
* **Despliegue:** Streamlit Community Cloud (Ruta A)
* **Entorno de Secretos:** `st.secrets["GEMINI_API_KEY"]` en producción, `.streamlit/secrets.toml` en local (ignorado en `.gitignore`).

---

## 3. Reglas Críticas de Seguridad y Desarrollo
1. **PROHIBICIÓN ESTRICTA DE API KEYS:** Jamás escribir una clave de API directamente en el código ni confirmarla en Git. Cualquier clave debe leerse de `st.secrets`.
2. **PRIVACIDAD DE DATOS:** Solo usar datos y ejemplos sintéticos. Ningún dato personal real de clientes debe ingresar a pruebas ni al repositorio.
3. **CÓDIGO AUTO-DOCUMENTADO:** Utilizar nombres de funciones y variables altamente descriptivos y tipado estricto (`typing.TypedDict`, `Optional`, etc.). Evitar comentarios obvios o innecesarios.
4. **MANEJO DE ERRORES RESILIENTE:** Toda llamada a servicios externos debe estar protegida con bloques `try/except` que capturen errores de cuota (`ResourceExhausted`) y fallos de conexión, mostrando mensajes claros y comprensibles para usuarios no técnicos.

---

## 4. División de Responsabilidades: Delegación vs. Supervisión Manual
Para garantizar la calidad y responder a los requerimientos de la rúbrica oficial (Apartado 5):

* **Tareas Delegadas al Agente de IA:**
  - Estructuración de la interfaz en Streamlit (componentes visuales, diseño responsive para móvil).
  - Redacción de la especificación técnica inicial y casos límite.
  - Generación de la lógica de simulación (*mock*) para la Versión 0.
  - Implementación del parser seguro de respuestas JSON de Gemini.
  - Configuración del manejo de excepciones estándar de Python y Streamlit.

* **Tareas Supervisadas y Revisadas a Mano por el Alumno:**
  - Definición del modelo de negocio, tono de respuesta del taller y categorías de urgencia adaptadas a la operación real.
  - Auditoría de seguridad del repositorio para asegurar que ningún archivo `.env` o secreto se incluya en el control de versiones.
  - Pruebas manuales de interfaz simulando el uso real en pantalla de teléfono móvil.
  - Despliegue manual y configuración de los secretos en el panel de Streamlit Community Cloud.
  - Verificación de la URL pública en modo incógnito.

---

## 5. Estructura del Repositorio
```text
App-para-el-master-streamlit/
├── .gitignore               # Exclusión de secretos (.streamlit/secrets.toml) y temporales
├── AGENTS.md                # Guía y contexto para asistentes de programación
├── especificacion.md        # Especificación funcional y casos límite
├── README.md                # Presentación del proyecto y Pitch de 5 frases
├── requirements.txt         # Dependencias de Python para Streamlit Cloud
└── app.py                   # Punto de entrada de la aplicación Streamlit
```

---

## 6. Comandos Habituales
* **Ejecutar en local:**
  ```bash
  streamlit run app.py
  ```
* **Instalar dependencias:**
  ```bash
  pip install -r requirements.txt
  ```
