import os
import streamlit as st
import requests

FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:8000")

st.set_page_config(page_title="Il Sapore Agente", page_icon="🍔")
st.title("🍔 Il Sapore - Asistente")

# --- LOGIN ---
if "usuario" not in st.session_state:
    st.session_state.usuario = None

if st.session_state.usuario is None:
    st.subheader("Iniciar sesión")
    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")
    
    if st.button("Entrar"):
        try:
            response = requests.post(
                f"{FASTAPI_URL}/login",
                json={"username": username, "password": password},
                timeout=10
            )
            if response.status_code == 200:
                st.session_state.usuario = response.json()
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos")
        except Exception as e:
            st.error(f"Error de conexión: {str(e)}")
    st.stop()

# --- CHAT (solo si está logueado) ---
usuario = st.session_state.usuario
st.write(f"Bienvenido, **{usuario['username']}** ({usuario['rol']})")

if st.button("Cerrar sesión"):
    st.session_state.usuario = None
    st.session_state.historial = []
    st.rerun()

# Inicializar historial
if "historial" not in st.session_state:
    st.session_state.historial = []

# Mostrar historial
for msg in st.session_state.historial:
    if msg["role"] == "user":
        st.chat_message("user").write(msg["content"])
    elif msg["role"] == "assistant":
        st.chat_message("assistant").write(msg["content"])

# Campo de pregunta
pregunta = st.chat_input("Escribe tu pregunta...")

if pregunta:
    st.chat_message("user").write(pregunta)
    st.session_state.historial.append({"role": "user", "content": pregunta})
    
    try:
        payload = {
            "texto": pregunta,
            "usuario_id": st.session_state.usuario["id"],
            "historial": st.session_state.historial[:-1]
        }
        response = requests.post(
            f"{FASTAPI_URL}/preguntar",
            json=payload,
            timeout=120
        )
        respuesta = response.json()["respuesta"]
    except Exception as e:
        respuesta = f"Error: {str(e)}"
    
    st.chat_message("assistant").write(respuesta)
    st.session_state.historial.append({"role": "assistant", "content": respuesta})