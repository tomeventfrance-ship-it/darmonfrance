# app.py — Monsieur Darmon (admin par e‑mail, validations, historiques)
import io, re, unicodedata, os
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Monsieur Darmon", layout="wide")

# Thème facultatif
try:
    import ui_theme  # fichier séparé
    ui_theme.apply_theme()
except Exception:
    pass

# Dossiers
HIST_DIR = Path("data/historique")
HIST_DIR.mkdir(parents=True, exist_ok=True)
HIST_FILE = HIST_DIR / "historique_createurs.csv"

# -----------------------------------------------------------------------------
# Outils accès/identité
# -----------------------------------------------------------------------------
import re, os

def _get_user_email() -> str:
    try:
        u = st.experimental_user  # Streamlit Cloud
        return (u.email or "").strip().lower() if u else ""
    except Exception:
        return ""

def is_admin() -> bool:
    email = _get_user_email()
    admin_secret = str(st.secrets.get("ADMIN_EMAIL", "")).strip().lower()
    admin_mode = bool(st.secrets.get("access", {}).get("admin_mode", False))
    return bool(admin_mode and admin_secret and email == admin_secret)

def is_manager() -> bool:
    email = _get_user_email()
    allowed = str(st.secrets.get("MANAGER_EMAILS", "")).lower()
    allowed_list = [e.strip() for e in re.split(r"[,\s]+", allowed) if e.strip()]
    return email in allowed_list

# -----------------------------------------------------------------------------
# I/O
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def read_any(file_bytes: bytes, name: str) -> pd.DataFrame:
    bio = io.BytesIO(file_bytes); n = name.lower()
    if n.endswith(('.xlsx', '.xls')): 
        return pd.read_excel(bio)
    return pd.read_csv(bio)

def to_numeric_safe(x):
    if pd.isna(x): return 0.0
    s = str(x).strip().replace(' ', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

def parse_duration_to_hours(x) -> float:
    if pd.isna(x): return 0.0
    s = str(x).strip().lower()
    try: return float(s.replace(',', '.'))
    except: pass
    if re.match(r'^\d{1,2}:\d{1,2}(:\d{1,2})?$', s):
        parts = [int(p) for p in s.split(':')]
        h = parts[0]; m = parts[1] if len(parts)>1 else 0; sec = parts[2] if len(parts)>2 else 0
        return h + m/60 + sec/3600
    h = re.search(r'(\d+)\s*h', s); m = re.search(r'(\d+)\s*m', s)
    if h or m:
        hh = int(h.group(1)) if h else 0; mm = int(m.group(1)) if m else 0
        return hh + mm/60
    mm = re.search(r'(\d+)\s*min', s)
    if mm: return int(mm.group(1))/60
    return 0.0

# -----------------------------------------------------------------------------
# Normalisation colonnes
# -----------------------------------------------------------------------------
COLS = {
    'periode': "Période des données",
    'creator_username': "Nom d'utilisateur du/de la créateur(trice)",
    'groupe': 'Groupe',
    'agent': 'Agent',
    'date_relation': "Date d'établissement de la relation",
    'diamants': 'Diamants',
    'duree_live': 'Durée de LIVE',
    'jours_live': 'Jours de passage en LIVE valides',
    'statut_diplome': 'Statut du diplôme',
}

def normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    for k, v in COLS.items():
        out[k] = df[v] if v in df.columns else (0 if k in ['diamants','jours_live'] else '')
    out['diamants'] = out['diamants'].apply(to_numeric_safe)
    out['jours_live'] = out['jours_live'].apply(lambda x: int(to_numeric_safe(x)))
    if COLS['duree_live'] in df.columns:
        out['heures_live'] = df[COLS['duree_live']].apply(parse_duration_to_hours)
    else:
        out['heures_live'] = 0.0
    # ID créateur si dispo sinon username
    out['creator_id'] = df.get('ID créateur(trice)', out['creator_username']).astype(str)
    for c in ['creator_username','groupe','agent','statut_diplome','periode','date_relation']:
        out[c] = out[c].astype(str)
    return out

# -----------------------------------------------------------------------------
# Règles (NOUVELLE RÉMUNÉRATION 2026)
# -----------------------------------------------------------------------------
# Créateurs
CREATOR_MIN_DIAMONDS = 100_000

# Paliers activité (jours/heures -> %)
CREATOR_ACTIVITY_LEVELS = [
    {"label": "11j / 30h", "days": 11, "hours": 30, "rate": 0.01},
    {"label": "18j / 60h", "days": 18, "hours": 60, "rate": 0.02},
    {"label": "22j / 80h", "days": 22, "hours": 80, "rate": 0.03},
]

# Niveaux diamants pour déterminer l'évolution/stagnation
CREATOR_LEVEL_BASES = [100_000, 200_000, 300_000, 500_000, 700_000, 1_000_000, 1_600_000, 2_500_000, 5_000_000]

# Bonus (non cumulable) ajouté AU POURCENTAGE (si éligible)
CREATOR_BONUS_EVOLUTION = 0.02
CREATOR_BONUS_STAGNATION = 0.01

# Bonus fixes 50K (uniquement sous 100K, pour éviter un cumul incohérent avec la rémunération %)
CREATOR_FIXED_MIN = 50_000
CREATOR_FIXED_11_30 = 500
CREATOR_FIXED_22_80 = 1000

# Agents
AGENT_MIN_DIAMONDS = 200_000  # non reportable
AGENT_COMMISSION_BY_TASK = {"5%": 0.015, "7%": 0.02, "9%": 0.025}
BONUS_CHOICES = {"0%": 0.0, "+0,5%": 0.005, "+1%": 0.01}  # non cumulable

def bonus_label_from_progression(progress_pct: float) -> str:
    """Automatisme bonus (non cumulable) basé sur la progression vs N-1."""
    if progress_pct is None or np.isnan(progress_pct):
        return '0%'
    if progress_pct >= 20:
        return '+1%'
    if progress_pct > 0:
        return '+0,5%'
    return '0%'


# Managers
MANAGER_MIN_DIAMONDS = 1_000_000  # non reportable
MANAGER_COMMISSION_BY_TASK = {"5%": 0.02, "7%": 0.03, "9%": 0.04}

def floor_1000(x: float) -> int:
    """Arrondi au millième inférieur."""
    return int(x // 1000) * 1000

def floor_100(x: float) -> int:
    """Arrondi à la centaine inférieure."""
    return int(x // 100) * 100

def creator_activity_rate(days: int, hours: float) -> float:
    """Retourne le meilleur % d'activité atteint."""
    rate = 0.0
    for lvl in CREATOR_ACTIVITY_LEVELS:
        if days >= lvl["days"] and hours >= lvl["hours"]:
            rate = max(rate, lvl["rate"])
    return rate

def creator_level_index(diamonds: float) -> int:
    """Index du niveau (0 si <100K)."""
    d = float(diamonds or 0)
    idx = 0
    for base in CREATOR_LEVEL_BASES:
        if d >= base:
            idx += 1
        else:
            break
    return idx  # 0..len(bases)

def ever_passed_200k(creator_id: str, hist: pd.DataFrame) -> bool:
    """Vrai si le créateur a déjà dépassé 200K dans l'historique fourni."""
    if hist is None or hist.empty:
        return False
    h = hist[hist["creator_id"].astype(str) == str(creator_id)]
    if h.empty:
        return False
    return float(h["diamants"].max() or 0) >= 200_000

def prev_month_diamonds(creator_id: str, hist: pd.DataFrame) -> float:
    """Diamants du mois précédent (approx : max période dans hist pour ce creator)."""
    if hist is None or hist.empty:
        return 0.0
    h = hist[hist["creator_id"].astype(str) == str(creator_id)].copy()
    if h.empty:
        return 0.0
    # On prend la dernière période lexicographiquement (souvent AAAA-MM)
    h["periode"] = h["periode"].astype(str)
    last = h.sort_values("periode").iloc[-1]
    return float(last["diamants"] or 0.0)

def compute_creators(df: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
    """Calcule les récompenses créateurs (nouvelle rémunération).

    Colonnes conservées pour compatibilité UI/admin :
    - recompense_palier_1 : récompense % (base)
    - recompense_palier_2 : récompense fixe 50K (si applicable)
    - bonus_debutant       : bonus % (évolution/stagnation) converti en diamants
    - bonus_code           : 'EVOL' / 'STAG' / 'BAISSE' / ''
    - total_createur       : total arrondi au millième inférieur
    """
    rows = []
    hist = hist if hist is not None else pd.DataFrame()

    for _, r in df.iterrows():
        creator_id = str(r["creator_id"])
        amount = float(r["diamants"] or 0.0)
        days = int(r["jours_live"] or 0)
        hours = float(r["heures_live"] or 0.0)

        # activité
        act_rate = creator_activity_rate(days, hours)

        # Éligibilité % (à partir de 100K et activité valide)
        eligible_pct = (amount >= CREATOR_MIN_DIAMONDS) and (act_rate > 0)

        # Bonus fixe 50K (uniquement si <100K, pour éviter double rémunération)
        fixed_bonus = 0
        if (amount >= CREATOR_FIXED_MIN) and (amount < CREATOR_MIN_DIAMONDS):
            if days >= 22 and hours >= 80:
                fixed_bonus = CREATOR_FIXED_22_80
            elif days >= 11 and hours >= 30:
                fixed_bonus = CREATOR_FIXED_11_30

        # Bonus évolution / stagnation / baisse (non cumulable)
        prev_d = prev_month_diamonds(creator_id, hist)
        prev_lvl = creator_level_index(prev_d)
        cur_lvl = creator_level_index(amount)

        bonus_rate = 0.0
        bonus_code = ""
        if eligible_pct:
            if cur_lvl > prev_lvl and prev_d > 0:
                bonus_rate = CREATOR_BONUS_EVOLUTION
                bonus_code = "EVOL"
            elif amount < prev_d and prev_d > 0:
                bonus_rate = 0.0
                bonus_code = "BAISSE"
            else:
                # stagnation possible uniquement si déjà passé 200K (même hors agence)
                passed_200k = (amount >= 200_000) or (prev_d >= 200_000) or ever_passed_200k(creator_id, hist)
                if passed_200k and cur_lvl == prev_lvl and cur_lvl > 0:
                    bonus_rate = CREATOR_BONUS_STAGNATION
                    bonus_code = "STAG"

        # Récompenses
        recomp_pct = amount * act_rate if eligible_pct else 0.0
        bonus_pct = amount * bonus_rate if eligible_pct else 0.0

        total_pct = floor_1000(recomp_pct) + floor_1000(bonus_pct)
        total = total_pct + int(fixed_bonus)

        etat = "✅ Actif" if (eligible_pct or fixed_bonus > 0) else "⚠️ Inactif"
        why = ""
        if etat != "✅ Actif":
            if amount < CREATOR_FIXED_MIN:
                why = "Diamants < 50 000"
            elif act_rate <= 0:
                why = "Activité insuffisante"
            elif amount < CREATOR_MIN_DIAMONDS:
                why = "Diamants < 100 000"

        rows.append({
            "creator_id": creator_id,
            "creator_username": r["creator_username"],
            "groupe": r["groupe"],
            "agent": r["agent"],
            "periode": r["periode"],
            "diamants": amount,
            "jours_live": days,
            "heures_live": hours,
            "type_createur": "Nouveau",
            "etat_activite": etat,
            "raison_ineligibilite": why if etat != "✅ Actif" else "",
            "recompense_palier_1": floor_1000(recomp_pct),
            "recompense_palier_2": int(fixed_bonus),
            "bonus_debutant": floor_1000(bonus_pct),
            "bonus_code": bonus_code,
            "total_createur": int(total),
            "actif_hierarchie": True if (eligible_pct or fixed_bonus > 0) else False,
        })

    return pd.DataFrame(rows)

def totals_hierarchy_by(field: str, crea: pd.DataFrame) -> pd.DataFrame:
    if crea is None or crea.empty:
        return pd.DataFrame(columns=[field, "diamants_hierarchie"])
    base = crea[crea["actif_hierarchie"] == True]
    return base.groupby(field)["diamants"].sum().reset_index().rename(columns={"diamants": "diamants_hierarchie"})

def apply_agent_manager_settings(base_df: pd.DataFrame, kind: str, task_global: str) -> pd.DataFrame:
    """Applique la tâche progressive (globale) + bonus (par ligne) et recalcule les primes.

    - Tâche progressive : un seul choix pour tous (Agents & Managers)
    - Bonus : non cumulable, modifiable par ligne
    - Minimum non reportable : Agent 200K / Manager 1M
    - Arrondi : centaine inférieure
    - Facture € : conversion à 0,0084 (arrondie à 5€ inférieur, basé sur base_prime)
    """
    if base_df is None or base_df.empty:
        if kind == "agent":
            return pd.DataFrame(columns=["agent","diamants_mois","tache_progressive","bonus_validé","base_prime","prime_agent","taux_change","Facture €"])
        return pd.DataFrame(columns=["groupe","diamants_mois","tache_progressive","bonus_validé","base_prime","prime_manager","taux_change","Facture €"])

    if kind == "agent":
        min_d = AGENT_MIN_DIAMONDS
        commissions = AGENT_COMMISSION_BY_TASK
        label_col = "agent"
        prime_col = "prime_agent"
    else:
        min_d = MANAGER_MIN_DIAMONDS
        commissions = MANAGER_COMMISSION_BY_TASK
        label_col = "groupe"
        prime_col = "prime_manager"

    out = base_df.copy()

    # Tâche progressive globale
    task_global = str(task_global) if task_global in commissions else "7%"
    out["tache_progressive"] = task_global

    # Bonus par ligne (sécurisé)
    out["bonus_validé"] = out["bonus_validé"].astype(str).where(out["bonus_validé"].isin(BONUS_CHOICES.keys()), "0%")

    commission_rate = commissions[task_global]
    out["commission_rate"] = commission_rate
    out["bonus_rate"] = out["bonus_validé"].map(BONUS_CHOICES).fillna(0.0)
    out["taux_total"] = out["commission_rate"] + out["bonus_rate"]

    # Minimum non reportable
    out["base_prime"] = np.where(out["diamants_hierarchie"] >= min_d, out["diamants_hierarchie"] * out["commission_rate"], 0.0)
    out["prime_total"] = np.where(out["diamants_hierarchie"] >= min_d, out["diamants_hierarchie"] * out["taux_total"], 0.0)

    # Arrondi centaine inférieure
    out["base_prime"] = out["base_prime"].apply(floor_100).astype(int)
    out["prime_total"] = out["prime_total"].apply(floor_100).astype(int)

    # Facture (taux 0,0084) arrondi à 5€ inférieur
    out["taux_change"] = 0.0084
    out["Facture €"] = (np.floor((out["base_prime"] * out["taux_change"]) / 5) * 5).astype(int)

    out = out.rename(columns={"diamants_hierarchie": "diamants_mois"})
    out[prime_col] = out["prime_total"]

    cols = [label_col, "diamants_mois", "tache_progressive", "bonus_validé", "base_prime", prime_col, "taux_change", "Facture €"]
    return out[cols]
def make_pdf(title,df):
    buf=io.BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=landscape(A4),leftMargin=18,rightMargin=18,topMargin=18,bottomMargin=18)
    styles=getSampleStyleSheet()
    els=[Paragraph(title,styles['Title']),Spacer(1,12)]
    data=[list(df.columns)]+df.astype(str).values.tolist()
    t=Table(data,repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.black),('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('GRID',(0,0),(-1,-1),0.25,colors.grey),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.whitesmoke,colors.lightgrey])]))
    els.append(t)
    doc.build(els)
    buf.seek(0)
    return buf.read()

def safe_pdf(label,title,df,file):
    if df is None or df.empty: st.button(label,disabled=True)
    else: st.download_button(label,make_pdf(title,df),file,'application/pdf')

# -----------------------------------------------------------------------------
# Historique validations
# -----------------------------------------------------------------------------
def load_validations() -> pd.DataFrame:
    if HIST_FILE.exists():
        try:
            return pd.read_csv(HIST_FILE, dtype=str)
        except Exception:
            return pd.DataFrame(columns=['creator_id','periode','valide_recompense','valide_bonus','timestamp_iso'])
    return pd.DataFrame(columns=['creator_id','periode','valide_recompense','valide_bonus','timestamp_iso'])

def save_validations(df_vals: pd.DataFrame):
    prev = load_validations()
    allv = pd.concat([prev, df_vals], ignore_index=True)
    allv['timestamp_iso'] = allv['timestamp_iso'].fillna(datetime.utcnow().isoformat())
    allv = (allv.sort_values('timestamp_iso')
                 .drop_duplicates(subset=['creator_id','periode'], keep='last'))
    allv.to_csv(HIST_FILE, index=False)

# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.markdown("<h1 style='text-align:center;margin:0 0 10px;'>Monsieur Darmon</h1>", unsafe_allow_html=True)

c1,c2,c3,c4=st.columns(4)
with c1:
    f_cur=st.file_uploader('Mois courant (XLSX/CSV)',type=['xlsx','xls','csv'],key='cur')
with c2:
    f_prev=st.file_uploader('Mois N-1 (historique)',type=['xlsx','xls','csv'],key='prev')
with c3:
    task_global = st.radio('Tâche progressive (Agents & Managers)', options=['5%','7%','9%'], horizontal=True, index=1, key='task_global')
with c4:
    if st.button('Forcer relecture'):
        st.cache_data.clear(); st.rerun()

if f_cur:
    # lectures
    cur=normalize(read_any(f_cur.getvalue(),f_cur.name))
    hist=pd.DataFrame()
    if f_prev: hist=normalize(read_any(f_prev.getvalue(),f_prev.name))
    t1,t2,t3=st.tabs(['Créateurs','Agents','Managers'])

    with t1:
        crea=compute_creators(cur,hist)
        st.dataframe(crea,use_container_width=True)
        st.download_button('CSV Créateurs',crea.to_csv(index=False).encode('utf-8'),'recompenses_createurs.csv','text/csv')
        safe_pdf('PDF Créateurs','Récompenses Créateurs',crea,'recompenses_createurs.pdf')

        # ---- panneau admin UNIQUEMENT si is_admin() ----
        if is_admin():
            st.subheader("Validation admin")
            vals_old = load_validations()

            edit_df = crea[['creator_id','creator_username','periode','recompense_palier_1','recompense_palier_2','bonus_debutant']].copy()
            edit_df['valide_recompense'] = False
            edit_df['valide_bonus'] = False
            if not vals_old.empty:
                m = vals_old[['creator_id','periode','valide_recompense','valide_bonus']].copy()
                m['valide_recompense'] = m['valide_recompense'].astype(str).str.lower().isin(['true','1','yes','oui'])
                m['valide_bonus'] = m['valide_bonus'].astype(str).str.lower().isin(['true','1','yes','oui'])
                edit_df = edit_df.merge(m, on=['creator_id','periode'], how='left', suffixes=('','_hist'))
                edit_df['valide_recompense'] = np.where(edit_df['valide_recompense_hist'].notna(), edit_df['valide_recompense_hist'], edit_df['valide_recompense'])
                edit_df['valide_bonus'] = np.where(edit_df['valide_bonus_hist'].notna(), edit_df['valide_bonus_hist'], edit_df['valide_bonus'])
                edit_df.drop(columns=['valide_recompense_hist','valide_bonus_hist'], inplace=True)

            edited = st.data_editor(
                edit_df,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "valide_recompense": st.column_config.CheckboxColumn("Valider récompense", default=False),
                    "valide_bonus": st.column_config.CheckboxColumn("Valider bonus", default=False),
                },
                disabled=['creator_id','creator_username','periode','recompense_palier_1','recompense_palier_2','bonus_debutant'],
                key="editor_validations"
            )

            if st.button("Enregistrer les validations"):
                out = edited[['creator_id','periode','valide_recompense','valide_bonus']].copy()
                out['valide_recompense'] = out['valide_recompense'].astype(bool)
                out['valide_bonus'] = out['valide_bonus'].astype(bool)
                out['timestamp_iso'] = datetime.utcnow().isoformat()
                save_validations(out)
                try: st.toast("✅ Données enregistrées", icon="✅")
                except Exception: st.success("Données enregistrées")

with t2:
    st.caption("Tâche progressive (globale) sélectionnée en haut. Bonus Backstage : auto vs N-1, modifiable par ligne. Minimum 200K (non reportable).")

    # Base : diamants hiérarchie par agent (Mois courant)
    base = totals_hierarchy_by('agent', crea)

    # Historique N-1 : estimation automatique du bonus
    prev_base = pd.DataFrame(columns=['agent','diamants_hierarchie'])
    if f_prev:
        crea_prev = compute_creators(hist, pd.DataFrame())
        prev_base = totals_hierarchy_by('agent', crea_prev)

    if base.empty:
        ag = pd.DataFrame(columns=["agent","diamants_mois","tache_progressive","bonus_validé","base_prime","prime_agent","taux_change","Facture €"])
        st.dataframe(ag, use_container_width=True)
    else:
        # Progression vs N-1
        if not prev_base.empty:
            tmp = base.merge(prev_base, on="agent", how="left", suffixes=("", "_prev")).fillna({"diamants_hierarchie_prev": 0})
            tmp["progress_pct"] = np.where(
                tmp["diamants_hierarchie_prev"] > 0,
                (tmp["diamants_hierarchie"] - tmp["diamants_hierarchie_prev"]) / tmp["diamants_hierarchie_prev"] * 100.0,
                np.nan
            )
        else:
            tmp = base.copy()
            tmp["progress_pct"] = np.nan

        tmp["bonus_validé"] = tmp["progress_pct"].apply(bonus_label_from_progression)

        edited = st.data_editor(
            tmp[["agent","diamants_hierarchie","progress_pct","bonus_validé"]],
            hide_index=True,
            use_container_width=True,
            column_config={
                "progress_pct": st.column_config.NumberColumn("Progression vs N-1 (%)", format="%.1f", disabled=True),
                "bonus_validé": st.column_config.SelectboxColumn("Bonus validé", options=list(BONUS_CHOICES.keys())),
            },
            disabled=["agent","diamants_hierarchie","progress_pct"],
            key="editor_agents_bonus"
        )

        # Recalcule primes avec tâche globale + bonus édité
        base_for_calc = base.merge(edited[["agent","bonus_validé"]], on="agent", how="left").fillna({"bonus_validé":"0%"})
        ag = apply_agent_manager_settings(base_for_calc, kind="agent", task_global=task_global)

        st.dataframe(ag, use_container_width=True)

    st.download_button('CSV Agents', ag.to_csv(index=False).encode('utf-8'), 'recompenses_agents.csv', 'text/csv')
    safe_pdf('PDF Agents', 'Récompenses Agents', ag, 'recompenses_agents.pdf')

# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------
st.markdown("""
<style>
#MainMenu {visibility: visible !important;}
footer {visibility:hidden;}
.app-footer {position: fixed; left: 0; right: 0; bottom: 0;
padding: 6px 12px; text-align: center; background: rgba(0,0,0,0.05); font-size: 12px;}
</style>
<div class='app-footer'>logiciels récompense by tom Consulting & Event</div>
""", unsafe_allow_html=True)