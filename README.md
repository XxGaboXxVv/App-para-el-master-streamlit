# 🛠️ Asistente de Mensajes para Taller · Clasificador PyME

> Aplicación web desarrollada para el módulo **Fundamentos de programación (Python para IA)** del Máster en Inteligencia Artificial de OBS Business School.

---

## 🚀 Pitch del Proyecto (5 Frases)
1. **El problema y quién lo tiene:** El técnico de un taller unipersonal de reparación de celulares pierde cotizaciones y desatiende garantías urgentes porque recibe decenas de mensajes informales por WhatsApp mientras repara y atiende el mostrador al mismo tiempo.
2. **Qué hace la app:** Esta aplicación clasifica instantáneamente los mensajes pegados de WhatsApp por nivel de urgencia y categoría, resume la falla técnica y genera un borrador de respuesta empático y profesional listo para enviar.
3. **Qué aporta la IA:** La IA interpreta lenguaje coloquial, faltas de ortografía y mensajes confusos de clientes para extraer el modelo del equipo, el síntoma exacto y la intención, algo imposible de resolver con filtros de palabras clave u hojas de cálculo.
4. **Qué aprendimos de la prueba:** Validamos que un flujo simple de 1 solo clic para pegar y analizar evita fricción operativa en el taller y permite atender garantías críticas en menos de 30 segundos.
5. **Qué haríamos después:** Integraríamos un webhook oficial de WhatsApp Business API para preclasificar los mensajes entrantes automáticamente en una bandeja de entrada priorizada.

---

## 📋 Estado del Proyecto: Semana 3 (Integración de la IA)
La aplicación cuenta con la integración completa de la API oficial de **Google Gemini (`gemini-3.8-flash`)** mediante el SDK `google-genai`:
- **Inferencia en tiempo real:** Clasificación de urgencia y categoría con salidas estructuradas en JSON nativo (`response_mime_type="application/json"`).
- **Manejo resiliente de errores:** Detección y tratamiento controlado de saturación de cuota (`ResourceExhausted` / 429), fallos de red y validación de formatos.
- **Motor con fallback defensivo:** Si no se detecta la clave de API, el sistema mantiene el modo interactivo de simulación para garantizar que la app nunca falle ante un usuario o evaluador.
- **Seguridad:** La clave se lee exclusivamente de `st.secrets["GEMINI_API_KEY"]` en Streamlit Community Cloud.
- **Carga de casos rápidos:** Botones laterales para probar garantías críticas, cotizaciones, estatus de reparación y casos ambiguos sin teclear.

---

## 🛠️ Instalación y Ejecución Local

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/XxGaboXxVv/App-para-el-master-streamlit.git
   cd App-para-el-master-streamlit
   ```

2. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Iniciar la aplicación:**
   ```bash
   streamlit run app.py
   ```

---

## 🔒 Seguridad y Privacidad
- Este repositorio no contiene claves de API ni credenciales sensibles.
- La clave de Google Gemini se maneja exclusivamente mediante variables de entorno en Streamlit Secrets (`st.secrets["GEMINI_API_KEY"]`).
- Todos los mensajes de prueba y ejemplos son sintéticos y ficticios.
