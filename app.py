import streamlit as st

st.title("Clasificador PyME - Hola Mundo 👋")
nombre = st.text_input("¿Cómo te llamas?")
if nombre:
    st.write(f"¡Hola, {nombre}! Esta es mi primera app en internet.")
