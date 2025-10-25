import json
import os
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st

# =========================
# CONFIG & ESTILO
# =========================
st.set_page_config(page_title="Adivinatobi", page_icon="🔮", layout="wide")

st.markdown(
    """
    <style>
    html, body, [data-testid="stAppViewContainer"] { font-size: 16px; }

    .brand-wrap{
        text-align:center; 
        margin-top: -10px; 
        margin-bottom: 16px; 
        user-select:none;
    }
    .brand-title { 
        font-size: 2.6rem; 
        line-height: 2.6rem;
        font-weight: 900; 
        letter-spacing: 0.5px;
        background: linear-gradient(90deg, #ff6b6b, #f7b801, #6bcdfc, #b76bff);
        -webkit-background-clip: text; 
        -webkit-text-fill-color: transparent; 
        margin: 0;
    }
    .brand-sub { 
        margin: 6px 0 10px 0; 
        color:#666; 
        font-weight:600;
    }

    .pill { 
        display:inline-block; 
        padding:0.15rem 0.55rem; 
        border-radius:999px; 
        font-size:0.8rem; 
        font-weight:700; 
        vertical-align: middle;
        user-select: none;
    }
    .pill-open { background:#eaffea; color:#287d3c; border:1px solid #90ee90; }
    .pill-closed { background:#fff1e6; color:#9f3d04; border:1px solid #f4a261; }

    .trama-card {
        padding: 0.9rem 1.1rem; 
        border-radius: 14px; 
        background: #ffffff;
        border: 2px solid #eee; 
        box-shadow: 0 4px 16px rgba(0,0,0,0.06); 
        margin: 0.6rem 0 0.8rem 0;
        transition: transform 80ms ease, box-shadow 120ms ease, border-color 120ms ease;
        text-decoration: none !important;
        display: block;
        user-select: none;
    }
    .trama-card:hover {
        transform: translateY(-1px);
        box-shadow: 0 8px 22px rgba(0,0,0,0.08);
        border-color: #ddd;
    }
    .trama-card .meta { color:#666; font-size:0.92rem; }
    .trama-card.open { border-color: #90ee90; }
    .trama-card.closed { border-color: #f4a261; }

    .pred-card {
        padding: 0.6rem 0.8rem; 
        border-radius: 10px; 
        background: #f8fbff; 
        border: 1px solid #e6f0ff; 
        margin-bottom: 0.5rem;
    }
    .me { background:#fff7e6; border-color:#ffe0a3; }

    .sidebar-linklike button[kind="secondary"]{
        background: transparent !important;
        border: none !important;
        color: #4a4a4a !important;
        text-align: left !important;
        padding-left: 0 !important;
        font-weight: 800 !important;
        font-size: 1.1rem !important;
    }

    h1, h2, h3 { user-select: none; }
    </style>
    """,
    unsafe_allow_html=True,
)

DATA_FILE = Path("adivinatobi_data.json")


# =========================
# PERSISTENCIA EN JSON
# =========================
def _empty_data():
    return {"tramas": [], "predicciones": []}


def load_data():
    if not DATA_FILE.exists():
        save_data(_empty_data())
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = _empty_data()
        save_data(data)

    # Migración: campo ganador único -> lista de ganadoras
    changed = False
    for t in data["tramas"]:
        if "ganadoras_prediccion_ids" not in t:
            old = t.get("ganadora_prediccion_id")
            t["ganadoras_prediccion_ids"] = [old] if old else []
            if "ganadora_prediccion_id" in t:
                del t["ganadora_prediccion_id"]
            changed = True
    if changed:
        save_data(data)
    return data


def save_data(data: dict):
    tmp_path = DATA_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, DATA_FILE)


# =========================
# UTILIDADES DE NEGOCIO
# =========================
def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_trama(data, trama_id):
    for t in data["tramas"]:
        if t["id"] == trama_id:
            return t
    return None


def list_predicciones_de_trama(data, trama_id):
    return [p for p in data["predicciones"] if p["trama_id"] == trama_id]


def list_predicciones_de_trama_por_usuario(data, trama_id, usuario):
    return [p for p in data["predicciones"] if p["trama_id"] == trama_id and p["autor"] == usuario]


def compute_puntos_por_cantidad(cant_predicciones_del_ganador):
    if cant_predicciones_del_ganador <= 1:
        return 3
    elif cant_predicciones_del_ganador == 2:
        return 2
    return 1


def compute_leaderboard(data):
    scores = {}
    for trama in data["tramas"]:
        if not trama["abierta"]:
            for pred_id in trama.get("ganadoras_prediccion_ids", []):
                pred = next((p for p in data["predicciones"] if p["id"] == pred_id), None)
                if not pred:
                    continue
                autor = pred["autor"]
                cant = len(list_predicciones_de_trama_por_usuario(data, trama["id"], autor))
                pts = compute_puntos_por_cantidad(cant)
                scores[autor] = scores.get(autor, 0) + pts
    leaderboard = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0].lower()))
    return leaderboard


# =========================
# ESTADO DE SESIÓN
# =========================
if "pantalla" not in st.session_state:
    st.session_state.pantalla = "inicio"  # "inicio" | "crear" | "trama"
if "usuario" not in st.session_state:
    st.session_state.usuario = ""
if "usuario_locked" not in st.session_state:
    st.session_state.usuario_locked = False
if "trama_seleccionada" not in st.session_state:
    st.session_state.trama_seleccionada = None
if "editando_pred" not in st.session_state:
    st.session_state.editando_pred = {}  # {pred_id: True/False}

# =========================
# ABRIR TRAMA DESDE ?view=ID (API nueva: st.query_params)
# =========================
qp = st.query_params  # objeto tipo dict (puede devolver str o lista de str según versión)
_id = None
if "view" in qp:
    val = qp["view"]
    _id = (val[0] if isinstance(val, list) else val) or None

if _id:
    st.session_state.pantalla = "trama"
    st.session_state.trama_seleccionada = _id
    # Limpiamos los query params para que no quede pegado ni provoque loops
    try:
        st.query_params.clear()        # Streamlit >= 1.32
    except Exception:
        try:
            # Fallback: sobrescribir a vacío
            st.query_params.update({})
        except Exception:
            pass
    st.rerun()


# =========================
# ACCIONES
# =========================
def goto_inicio():
    st.session_state.pantalla = "inicio"
    st.session_state.trama_seleccionada = None


def goto_crear():
    st.session_state.pantalla = "crear"
    st.session_state.trama_seleccionada = None


def goto_trama(trama_id):
    st.session_state.pantalla = "trama"
    st.session_state.trama_seleccionada = trama_id


def crear_trama(usuario, pregunta, descripcion):
    data = load_data()
    t = {
        "id": str(uuid.uuid4()),
        "pregunta": pregunta.strip(),
        "descripcion": descripcion.strip(),
        "creador": usuario,
        "abierta": True,
        "ganadoras_prediccion_ids": [],
        "creada": timestamp(),
    }
    data["tramas"].insert(0, t)
    save_data(data)
    st.toast("✨ Trama creada")
    goto_inicio()


def agregar_prediccion(usuario, trama_id, texto):
    data = load_data()
    trama = get_trama(data, trama_id)
    if not trama or not trama["abierta"]:
        st.error("La trama no está disponible o ya fue cerrada.")
        return
    existentes = list_predicciones_de_trama_por_usuario(data, trama_id, usuario)
    if len(existentes) >= 3:
        st.warning("Ya tenés 3 predicciones en esta trama.")
        return
    p = {
        "id": str(uuid.uuid4()),
        "trama_id": trama_id,
        "autor": usuario,
        "texto": texto.strip(),
        "creada": timestamp(),
        "ultima_edicion": None,
    }
    data["predicciones"].append(p)
    save_data(data)
    st.success("✅ Predicción agregada.")


def editar_prediccion(pred_id, nuevo_texto, usuario):
    data = load_data()
    pred = next((p for p in data["predicciones"] if p["id"] == pred_id), None)
    trama = get_trama(data, pred["trama_id"]) if pred else None
    if not pred or pred["autor"] != usuario or not trama or not trama["abierta"]:
        st.error("No se pudo editar (permisos o estado de trama).")
        return
    pred["texto"] = nuevo_texto.strip()
    pred["ultima_edicion"] = timestamp()
    save_data(data)
    st.info("✏️ Predicción actualizada.")


def eliminar_prediccion(pred_id, usuario):
    data = load_data()
    pred = next((p for p in data["predicciones"] if p["id"] == pred_id), None)
    trama = get_trama(data, pred["trama_id"]) if pred else None
    if not pred or pred["autor"] != usuario or not trama or not trama["abierta"]:
        st.error("No se pudo eliminar (permisos o estado de trama).")
        return
    data["predicciones"] = [p for p in data["predicciones"] if p["id"] != pred_id]
    save_data(data)
    st.warning("🗑️ Predicción eliminada.")


def cerrar_trama_con_ganadores(trama_id, ganadoras_ids, usuario):
    data = load_data()
    trama = get_trama(data, trama_id)
    if not trama or trama["creador"] != usuario or not trama["abierta"]:
        st.error("No podés cerrar esta trama.")
        return
    trama["abierta"] = False
    trama["ganadoras_prediccion_ids"] = list(ganadoras_ids)
    save_data(data)
    st.success("🏁 Trama cerrada con ganador(es).")


def cerrar_trama_desierta(trama_id, usuario):
    data = load_data()
    trama = get_trama(data, trama_id)
    if not trama or trama["creador"] != usuario or not trama["abierta"]:
        st.error("No podés cerrar esta trama.")
        return
    trama["abierta"] = False
    trama["ganadoras_prediccion_ids"] = []
    save_data(data)
    st.warning("🚫 Trama cerrada como desierta (sin puntos).")


# =========================
# SIDEBAR (LOGO CLIC + USUARIO BLOQUEABLE)
# =========================
def _lock_user():
    if st.session_state.usuario.strip():
        st.session_state.usuario_locked = True

with st.sidebar:
    st.markdown("<div class='adivinatobi-title'>Adivinatobi 🔮</div>", unsafe_allow_html=True)
    with st.container():
        st.markdown("<div class='sidebar-linklike'>", unsafe_allow_html=True)
        st.button("Volver al inicio", on_click=goto_inicio)
        st.markdown("</div>", unsafe_allow_html=True)

    st.text_input(
        "Tu nombre (obligatorio)",
        key="usuario",
        placeholder="Por ej., Guido Morrison",
        on_change=_lock_user,
        disabled=st.session_state.usuario_locked,
    )
    if st.session_state.usuario_locked:
        st.caption("🔒 Nombre bloqueado hasta recargar la página (F5).")

    st.divider()
    st.caption("Elegí una tramatobi o creá una y escribí tu predicción. "
               "Al final, los que acierten ganarán puntos. "
               "Cada usuario puede crear hasta tres predicciones por trama. "
               "El que acierta se lleva 3 puntos si hizo una sola predicción, "
               "2 puntos si hizo dos y 1 punto si hizo una. "
               "Si nadie acierta, la trama queda declarada desierta. ")


# =========================
# CABECERA GLOBAL (título centrado + bienvenida)
# =========================
def cabecera():
    st.markdown(
        """
        <div class="brand-wrap">
          <h1 class="brand-title">Adivinatobi</h1>
          <div class="brand-sub">Bienvenidos al intrincado mundo de la mitomanía</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================
# BLOQUE: TABLA DE POSICIONES (columna derecha)
# =========================
def bloque_tabla_posiciones():
    st.subheader("🏆 Tabla de posiciones")
    data = load_data()
    lb = compute_leaderboard(data)
    if not lb:
        st.caption("Sin puntos todavía. ¡Cerrá una trama con ganador!")
    else:
        for pos, (user, pts) in enumerate(lb, start=1):
            st.write(f"**{pos}. {user}** — {pts} pts")


# =========================
# UI AUX: CARTA CLICKEABLE (HTML + query param)
# =========================
def trama_link_card(trama, total_preds):
    pill_html = f"<span class='pill {'pill-open' if trama['abierta'] else 'pill-closed'}'>" \
                f"{'Abierta' if trama['abierta'] else 'Cerrada'}</span>"
    inner = (
        f"{pill_html}"
        f"<div style='height:6px'></div>"
        f"<div style='font-weight:700; font-size:1.05rem; color:#222'>{trama['pregunta']}</div>"
        f"<div class='meta'>por {trama['creador']} • {trama['creada']} • {total_preds} predicciones</div>"
    )
    css_class = "trama-card open" if trama["abierta"] else "trama-card closed"
    st.markdown(
        f"""<a href="?view={trama['id']}" class="{css_class}" title="Abrir trama">
            {inner}
        </a>""",
        unsafe_allow_html=True,
    )


# =========================
# PANTALLAS
# =========================
def pantalla_inicio():
    cabecera()

    col_left, col_right = st.columns([2.2, 1], gap="large")
    with col_left:
        st.button("➕ Crear trama", type="primary", on_click=goto_crear)

        data = load_data()
        abiertas = [t for t in data["tramas"] if t["abierta"]]
        cerradas = [t for t in data["tramas"] if not t["abierta"]]

        st.markdown("### 🔓 Tramas abiertas")
        if not abiertas:
            st.caption("No hay tramas abiertas por ahora.")
        else:
            for t in abiertas:
                preds = list_predicciones_de_trama(data, t["id"])
                trama_link_card(t, len(preds))

        st.markdown("---")
        st.markdown("### 🔒 Tramas cerradas")
        if not cerradas:
            st.caption("Aún no hay tramas cerradas.")
        else:
            for t in cerradas:
                preds = list_predicciones_de_trama(data, t["id"])
                trama_link_card(t, len(preds))

    with col_right:
        bloque_tabla_posiciones()


def pantalla_crear():
    cabecera()

    if not st.session_state.usuario.strip():
        st.error("Completá tu nombre a la izquierda. Los puntos se asocian al nombre, así que usá siempre el mismo. ")
        if st.button("Volver a las tramas"):
            goto_inicio()
        return

    with st.form("form_crear_trama", clear_on_submit=False):
        pregunta = st.text_input("Pregunta de la trama", placeholder="Por ejemplo: “¿Vuelve con la Verito?”")
        descripcion = st.text_area("Descripción", placeholder="Agregá contexto, fechas, condiciones, etc.")
        col1, col2 = st.columns(2)
        crear = col1.form_submit_button("Crear", type="primary")
        cancelar = col2.form_submit_button("Cancelar")

        if crear:
            if not pregunta.strip():
                st.warning("La pregunta es obligatoria.")
            else:
                crear_trama(st.session_state.usuario.strip(), pregunta, descripcion)
                st.rerun()  # volver a Inicio
        if cancelar:
            goto_inicio()
            st.rerun()


def pantalla_trama():
    cabecera()

    data = load_data()
    trama = get_trama(data, st.session_state.trama_seleccionada)
    if not trama:
        st.error("No se encontró la trama.")
        st.button("Volver al inicio", on_click=goto_inicio)
        return

    estado_pill = "<span class='pill pill-open'>Abierta</span>" if trama["abierta"] else "<span class='pill pill-closed'>Cerrada</span>"
    st.markdown(
        f"{estado_pill} &nbsp; <span class='brand-sub'>por {trama['creador']} • {trama['creada']}</span>",
        unsafe_allow_html=True,
    )
    if trama["descripcion"].strip():
        st.info(trama["descripcion"])

    st.button("⬅️ Volver", on_click=goto_inicio)

    col_left, col_right = st.columns([2, 1], gap="large")

    with col_left:
        st.subheader("🗳️ Predicciones")
        preds = list_predicciones_de_trama(data, trama["id"])
        mis_preds = list_predicciones_de_trama_por_usuario(
            data, trama["id"], st.session_state.usuario.strip()
        ) if st.session_state.usuario.strip() else []

        # Agregar predicción
        if trama["abierta"]:
            if not st.session_state.usuario.strip():
                st.warning("Ingresá tu usuario (arriba a la izquierda) para predecir.")
            else:
                if len(mis_preds) < 3:
                    with st.form("form_add_pred"):
                        texto = st.text_input("Tu predicción", placeholder="Escribí una predicción clara y breve…")
                        enviar = st.form_submit_button("Agregar predicción", type="primary")
                        if enviar:
                            if not texto.strip():
                                st.warning("No podés enviar una predicción vacía.")
                            else:
                                agregar_prediccion(st.session_state.usuario.strip(), trama["id"], texto)
                                st.rerun()
                else:
                    st.caption("Ya hiciste el máximo de 3 predicciones para esta trama.")

        # Listado de predicciones
        if not preds:
            st.caption("Aún no hay predicciones.")
        else:
            for p in sorted(preds, key=lambda x: x["creada"], reverse=True):
                is_me = st.session_state.usuario.strip() and (p["autor"] == st.session_state.usuario.strip())
                with st.container():
                    st.markdown(
                        f"<div class='pred-card {'me' if is_me else ''}'>"
                        f"<strong>{p['autor']}</strong> — <span style='color:#777'>{p['creada']}</span><br>"
                        f"{p['texto']}"
                        + (f"<br><span style='color:#999; font-size:0.85rem'>Editado: {p['ultima_edicion']}</span>" if p['ultima_edicion'] else "")
                        + "</div>",
                        unsafe_allow_html=True,
                    )
                    # Controles de edición con modo explícito
                    if trama["abierta"] and is_me:
                        en_edicion = st.session_state.editando_pred.get(p["id"], False)

                        if not en_edicion:
                            c1, c2 = st.columns(2)
                            if c1.button("Editar predicción", key=f"editbtn_{p['id']}"):
                                st.session_state.editando_pred[p["id"]] = True
                                st.rerun()
                            if c2.button("Borrar predicción", key=f"del_{p['id']}"):
                                eliminar_prediccion(p["id"], st.session_state.usuario.strip())
                                st.rerun()
                        else:
                            new_text = st.text_input("Editar tu predicción", value=p["texto"], key=f"editfield_{p['id']}")
                            c1, c2 = st.columns(2)
                            if c1.button("Guardar", key=f"save_{p['id']}"):
                                if not new_text.strip():
                                    st.warning("El texto no puede quedar vacío.")
                                else:
                                    editar_prediccion(p["id"], new_text, st.session_state.usuario.strip())
                                    st.session_state.editando_pred[p["id"]] = False
                                    st.rerun()
                            if c2.button("Cancelar", key=f"cancel_{p['id']}"):
                                st.session_state.editando_pred[p["id"]] = False
                                st.rerun()

    with col_right:
        # Cierre de trama y tabla de posiciones
        if trama["abierta"]:
            if st.session_state.usuario.strip() == trama["creador"]:
                st.subheader("🏁 Cerrar trama")
                st.caption("Podés elegir una o varias predicciones ganadoras.")
                opciones_dict = {f"{p['texto']} — ({p['autor']})": p["id"] for p in preds} if preds else {}
                seleccion = st.multiselect(
                    "Predicciones ganadoras",
                    options=list(opciones_dict.keys()) if opciones_dict else [],
                )
                c1, c2 = st.columns(2)
                if c1.button("Cerrar con ganador(es)", type="primary", disabled=not seleccion):
                    ids = [opciones_dict[etiqueta] for etiqueta in seleccion]
                    cerrar_trama_con_ganadores(trama["id"], ids, st.session_state.usuario.strip())
                    st.rerun()
                if c2.button("Declarar desierta"):
                    cerrar_trama_desierta(trama["id"], st.session_state.usuario.strip())
                    st.rerun()
            else:
                st.subheader("ℹ️ Trama abierta")
                st.caption("Solo el creador puede cerrarla.")
        else:
            st.subheader("✅ Trama cerrada")
            if trama.get("ganadoras_prediccion_ids"):
                ganadoras = []
                for pid in trama["ganadoras_prediccion_ids"]:
                    pred = next((p for p in data["predicciones"] if p["id"] == pid), None)
                    if pred:
                        cant = len(list_predicciones_de_trama_por_usuario(data, trama["id"], pred["autor"]))
                        pts = compute_puntos_por_cantidad(cant)
                        ganadoras.append(f"**{pred['autor']}** con “{pred['texto']}” → **+{pts} pts**")
                if ganadoras:
                    st.success("Ganadores:\n\n- " + "\n- ".join(ganadoras))
            else:
                st.warning("Cerrada como desierta (no se asignaron puntos).")

        st.divider()
        bloque_tabla_posiciones()


# =========================
# ROUTER
# =========================
if st.session_state.pantalla == "inicio":
    pantalla_inicio()
elif st.session_state.pantalla == "crear":
    pantalla_crear()
else:
    pantalla_trama()
