# app_access_v2.py — Portail d'accès + passage du rôle/email à l'app
import os, streamlit as st

st.set_page_config(page_title="Portail • Monsieur Darmon", layout="wide")

def get_allowed_sets():
    admin = st.secrets.get("ADMIN_EMAIL", "").strip()
    managers = st.secrets.get("MANAGER_EMAILS", "").strip()
    managers_set = set([m.strip().lower() for m in managers.split(",") if m.strip()]) if managers else set()
    return admin.lower() if admin else "", managers_set

def get_current_user_email():
    if hasattr(st, "experimental_user"):
        u = st.experimental_user
        if isinstance(u, dict): return (u.get("email") or "").lower()
        return (getattr(u, "email", "") or "").lower()
    return st.text_input("Email (local/test)").strip().lower()

def gate_access():
    admin_email, manager_set = get_allowed_sets()
    user_email = get_current_user_email()
    st.markdown("### Portail d'accès")
    if not user_email:
        st.info("Connectez-vous pour continuer."); st.stop()
    role = "ADMIN" if (admin_email and user_email == admin_email) else ("MANAGER" if user_email in manager_set else None)
    if role is None:
        st.error("Accès refusé. Managers invités uniquement."); st.stop()
    st.success(f"Accès accordé: {role}"); return role, user_email

role, email = gate_access()
os.environ["MD_ROLE"] = role
os.environ["MD_EMAIL"] = email

try:
    with open("app_v7.py", "r", encoding="utf-8") as f: code = f.read()
    exec(compile(code, "app_v7.py", "exec"), globals(), globals())
except FileNotFoundError:
    st.error("Fichier app_v7.py introuvable à la racine du repo.")
