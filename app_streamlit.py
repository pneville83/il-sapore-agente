import os
import streamlit as st
import requests

FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:8000")

st.set_page_config(page_title="Il Sapore Agente", page_icon="🍔")
st.title("🍔 Il Sapore - Asistente")

# --- LOGIN ---
if "usuario" not in st.session_state:
    st.session_state.usuario = None

# Si la sesión viene de antes del cambio (sin token), se fuerza re-login.
if st.session_state.usuario is not None and not st.session_state.usuario.get("token"):
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
                timeout=60
            )
            if response.status_code == 200:
                st.session_state.usuario = response.json()  # incluye el token
                st.session_state.historial = []
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

if "historial" not in st.session_state:
    st.session_state.historial = []

for msg in st.session_state.historial:
    if msg["role"] == "user":
        st.chat_message("user").write(msg["content"])
    elif msg["role"] == "assistant":
        st.chat_message("assistant").write(msg["content"])

pregunta = st.chat_input("Escribe tu pregunta...")

if pregunta:
    st.chat_message("user").write(pregunta)
    st.session_state.historial.append({"role": "user", "content": pregunta})

    payload = {
        "texto": pregunta,
        "historial": st.session_state.historial[:-1],
    }
    headers = {
        "Authorization": f"Bearer {st.session_state.usuario.get('token', '')}"
    }

    try:
        response = requests.post(
            f"{FASTAPI_URL}/preguntar",
            json=payload,
            headers=headers,
            timeout=120
        )

        if response.status_code == 401:
            st.session_state.usuario = None
            st.session_state.historial = []
            st.error("Tu sesión expiró. Vuelve a iniciar sesión.")
            st.stop()
        elif response.status_code != 200:
            respuesta = f"Error del servidor ({response.status_code}): {response.text[:300]}"
        else:
            respuesta = response.json().get(
                "respuesta", "El agente no devolvió respuesta."
            )

    except Exception as e:
        respuesta = f"Error: {str(e)}"

    st.chat_message("assistant").write(respuesta)
    st.session_state.historial.append({"role": "assistant", "content": respuesta})