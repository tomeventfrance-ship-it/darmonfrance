import streamlit as st
st.set_option("runner.fastReruns", False)
# app.py — Monsieur Darmon (admin par e‑mail, validations, historiques)
import io, re, unicodedata, os
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
import yaml
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
# Règles
# -----------------------------------------------------------------------------
def load_cfg() -> dict:
    """Charge config_baremes.yaml (optionnel)."""
    p = Path("config_baremes.yaml")
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


CFG = load_cfg()

# Seuil historique créateurs "confirmés"
THR_CONFIRMED = int((CFG.get("confirmed_threshold_diamants") or 150000))

# Conditions d'activité (lecture existante conservée)
ACTIVITY = {
    'beginner': (
        int(((CFG.get('activation') or {}).get('beginner') or {}).get('days') or 7),
        float(((CFG.get('activation') or {}).get('beginner') or {}).get('hours') or 15),
    ),
    'confirmed': (
        int(((CFG.get('activation') or {}).get('confirmed') or {}).get('days') or 12),
        float(((CFG.get('activation') or {}).get('confirmed') or {}).get('hours') or 25),
    ),
    'second': (
        int(((CFG.get('activation') or {}).get('second') or {}).get('days') or 20),
        float(((CFG.get('activation') or {}).get('second') or {}).get('hours') or 80),
    ),
}

# -----------------------------------------------------------------------------
# Modèle 2026 — "Haute rentabilité" (2 paliers + bonus progression + bonus activité)
# -----------------------------------------------------------------------------
MD = (CFG.get("mr_darmon") or {})
MD_MIN_DAYS = int(MD.get("min_days") or 12)
MD_MIN_HOURS = float(MD.get("min_hours") or 25)
MD_MAX_DAYS = int(MD.get("max_days") or 22)
MD_MAX_HOURS = float(MD.get("max_hours") or 100)

MD_TIER_LOW_MIN = int(MD.get("tier_low_min") or 75000)
MD_TIER_SPLIT = int(MD.get("tier_split") or 400000)
MD_TIER_LOW_RATE = float(MD.get("tier_low_rate") or 0.045)   # 4.5%
MD_TIER_HIGH_RATE = float(MD.get("tier_high_rate") or 0.015)  # 1.5%

MD_BONUS_PROG = float(MD.get("bonus_progression") or 0.01)     # +1%
MD_BONUS_ACTIVITY_MAX = float(MD.get("bonus_activity_max") or 0.005)  # +0.5%
MD_BONUS_CAP = float(MD.get("bonus_cap") or 0.015)             # cap bonus cumul
MD_PAYOUT_CAP = MD.get("payout_cap")
MD_PAYOUT_CAP = int(MD_PAYOUT_CAP) if MD_PAYOUT_CAP not in (None, "", 0, "0") else None

# Barèmes
P1=[(35000,74999,1000),(75000,149999,2500),(150000,199999,5000),(200000,299999,6000),
    (300000,399999,7999),(400000,499999,12000),(500000,599999,15000),(600000,699999,18000),
    (700000,799999,21000),(800000,899999,24000),(900000,999999,26999),(1000000,1499999,30000),
    (1500000,1999999,44999),(2000000,None,'PCT4')]
P2=[(35000,74999,1000),(75000,149999,2500),(150000,199999,6000),(200000,299999,7999),
    (300000,399999,12000),(400000,499999,15000),(500000,599999,20000),(600000,699999,24000),
    (700000,799999,26999),(800000,899999,30000),(900000,999999,35000),(1000000,1499999,39999),
    (1500000,1999999,59999),(2000000,None,'PCT4')]

BONUS_RANK={'':0,'B1':1,'B2':2,'B3':3}

def _norm(s: str) -> str:
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode('ascii')
    s = s.lower().replace('-', ' ').replace('(', ' ').replace(')', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return s

PLUS90 = re.compile(r'(?:\+|>|plus)\s*90')
ELIG_90 = re.compile(r'(?:\ben\s+90\s*j\b|en 90j|90\s*j\b|moins\s+de\s+90\s*j)')

def status_flags(statut_raw: str):
    s = _norm(statut_raw)
    is_confirmed = False
    bonus_block = False
    beginner_eligible = False
    if 'confirme' in s: is_confirmed = True; bonus_block = True
    if 'recrute' in s and 'non debutant' in s: is_confirmed = True; bonus_block = True
    if ('debutant' in s and 'depuis' in s and PLUS90.search(s)): is_confirmed = True; bonus_block = True
    if ('debutant' in s) and ELIG_90.search(s) and not PLUS90.search(s) and 'depuis' not in s and not is_confirmed:
        beginner_eligible = True
    return is_confirmed, bonus_block, beginner_eligible

def highest_bonus_rank(hist: pd.DataFrame, creator_id: str) -> int:
    if hist is None or hist.empty: return 0
    h = hist[hist.get('creator_id','').astype(str)==str(creator_id)]
    if h.empty: return 0
    if 'bonus_code' in h.columns:
        ranks = h['bonus_code'].astype(str).str.upper().map(BONUS_RANK).fillna(0)
        return int(ranks.max())
    return 0

def activity_ok(row, ctype):
    d = int(row.get('jours_live',0)); h = float(row.get('heures_live',0))
    need_d,need_h = ACTIVITY['beginner'] if ctype=='débutant' else ACTIVITY['confirmed']
    ok1=(d>=need_d and h>=need_h)
    ok2=(d>=ACTIVITY['second'][0] and h>=ACTIVITY['second'][1])
    reason=[]
    if not ok1:
        if d<need_d: reason.append('Pas assez de jours')
        if h<need_h: reason.append("Pas assez d'heures")
    return ok1,ok2,', '.join(reason)

def reward(amount,table):
    for lo,hi,val in table:
        if (hi is None and amount>=lo) or (amount>=lo and amount<=hi):
            return round(amount*0.04,2) if val=='PCT4' else float(val)
    return 0.0

def creator_type_and_bonus(row, hist):
    amount=float(row['diamants'])
    statut=row.get('statut_diplome','')
    confirmed_by_status, bonus_block, beginner_eligible = status_flags(statut)
    # type
    if confirmed_by_status:
        ctype='confirmé'
    else:
        ever=False
        if hist is not None and not hist.empty:
            h = hist[hist['creator_id']==row['creator_id']]
            if not h.empty and h['diamants'].max()>=THR_CONFIRMED: ever=True
        ctype='confirmé' if ever else 'débutant'

    # bonus courant
    curr_code=''
    if   75000 <= amount <= 149999:  curr_code='B1'
    elif 150000 <= amount <= 499999: curr_code='B2'
    elif 500000 <= amount <= 2000000: curr_code='B3'
    hist_rank = highest_bonus_rank(hist, row['creator_id'])
    can_bonus = (ctype=='débutant') and beginner_eligible and not bonus_block and BONUS_RANK.get(curr_code,0)>hist_rank
    bval = 500 if curr_code=='B1' else 1088 if curr_code=='B2' else 3000 if curr_code=='B3' else 0.0
    return ctype, (bval if can_bonus else 0.0), (curr_code if can_bonus else '')

def _md_base_rate(diamants: float) -> float:
    if diamants < MD_TIER_LOW_MIN:
        return 0.0
    return MD_TIER_LOW_RATE if diamants < MD_TIER_SPLIT else MD_TIER_HIGH_RATE


def _md_activity_ok_min(jours: int, heures: float) -> bool:
    return (jours >= MD_MIN_DAYS) and (heures >= MD_MIN_HOURS)


def _md_activity_ok_max(jours: int, heures: float) -> bool:
    return (jours >= MD_MAX_DAYS) and (heures >= MD_MAX_HOURS)


def compute_creators(df: pd.DataFrame, hist: pd.DataFrame, prev_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Calcule les récompenses créateurs selon le modèle 2026 (haute rentabilité).

    Lecture/import CSV existants conservés :
      - Diamants : colonne H de l'export (champ normalisé 'diamants')
      - Heures LIVE valides : colonne I (champ normalisé 'heures_live')
      - Jours LIVE valides : colonne J (champ normalisé 'jours_live')

    Le fichier Mois N-1 (prev_df) est utilisé pour détecter la progression (diamants M > diamants M-1).
    """
    rows = []

    # index rapide N-1 pour comparaison
    prev_map = {}
    if prev_df is not None and not prev_df.empty:
        try:
            prev_map = (prev_df.groupby('creator_id')['diamants'].max()).to_dict()
        except Exception:
            prev_map = {}

    for _, r in df.iterrows():
        amount = float(r['diamants'])
        jours = int(r.get('jours_live', 0) or 0)
        heures = float(r.get('heures_live', 0) or 0.0)

        # Type (conservé) — utile affichage
        ctype, _, _ = creator_type_and_bonus(r, hist)

        # Eligibilité activité minimum 2026
        ok_min = _md_activity_ok_min(jours, heures)
        ok_max = _md_activity_ok_max(jours, heures)

        # Progression : compare à N-1 si disponible
        prev_amount = float(prev_map.get(str(r['creator_id']), np.nan))
        is_prog = False
        if not np.isnan(prev_amount):
            is_prog = amount > prev_amount

        base_rate = _md_base_rate(amount)
        bonus_prog = MD_BONUS_PROG if is_prog else 0.0
        bonus_act = MD_BONUS_ACTIVITY_MAX if ok_max else 0.0
        bonus_total = min(bonus_prog + bonus_act, MD_BONUS_CAP)

        # payout
        p_base = amount * base_rate if ok_min else 0.0
        p_bonus = amount * bonus_total if ok_min else 0.0
        total = float(p_base + p_bonus)

        # Cap sécurité
        payout_capped = False
        if MD_PAYOUT_CAP is not None and total > MD_PAYOUT_CAP:
            total = float(MD_PAYOUT_CAP)
            payout_capped = True
            # on garde la ventilation "base/bonus" cohérente (base d'abord)
            p_base = min(p_base, total)
            p_bonus = max(0.0, total - p_base)

        # Arrondi historique (conservé) si gros volume
        if amount >= 2_000_000:
            total = float(np.floor(total / 1000) * 1000)
            p_base = float(np.floor(p_base / 1000) * 1000)
            p_bonus = float(np.floor(p_bonus / 1000) * 1000)

        # Etat / raisons
        if not ok_min:
            etat = '⚠️ Inactif'
            why = []
            if jours < MD_MIN_DAYS:
                why.append('Pas assez de jours')
            if heures < MD_MIN_HOURS:
                why.append("Pas assez d'heures")
            why = ', '.join(why) if why else "Conditions d'activité non remplies"
        elif base_rate <= 0.0:
            etat = '⚠️ Inactif'
            why = f"Diamants < {MD_TIER_LOW_MIN:,}".replace(',', ' ')
        else:
            etat = '✅ Actif'
            why = ''

        # Hiérarchie : on conserve le principe (activité min + >=750)
        actif_hierarchie = ok_min and (amount >= 750)

        rows.append({
            'creator_id': r['creator_id'],
            'creator_username': r['creator_username'],
            'groupe': r['groupe'],
            'agent': r['agent'],
            'periode': r['periode'],
            'diamants': amount,
            'jours_live': jours,
            'heures_live': heures,
            'type_createur': ctype.capitalize(),
            'etat_activite': etat,
            'raison_ineligibilite': why,
            # Colonnes existantes conservées (palier1=base, palier2=bonus)
            'recompense_palier_1': float(p_base),
            'recompense_palier_2': float(p_bonus),
            'bonus_debutant': 0.0,
            'bonus_code': '',
            'total_createur': float(total),
            'actif_hierarchie': actif_hierarchie,
            # Info utile (facultatif) : cap
            'payout_capped': payout_capped,
        })
    return pd.DataFrame(rows)

def totals_hierarchy_by(field,crea):
    if crea is None or crea.empty: return pd.DataFrame(columns=[field,'diamants_hierarchie'])
    base = crea[crea['actif_hierarchie'] == True]
    return base.groupby(field)['diamants'].sum().reset_index().rename(columns={'diamants':'diamants_hierarchie'})

def percent_reward(total):
    if total>=4_000_000:return total*0.03
    if total>=200_000:return total*0.02
    return 0.0

def sum_bonus_for(group_col:str,crea:pd.DataFrame,map_amount:dict)->pd.DataFrame:
    if crea is None or crea.empty: return pd.DataFrame(columns=[group_col,'bonus_additionnel'])
    tmp=crea[['creator_id',group_col,'bonus_code']].copy()
    order={'B3':3,'B2':2,'B1':1,'':0}
    tmp['rank']=tmp['bonus_code'].astype(str).str.upper().map(order).fillna(0)
    tmp=tmp.sort_values(['creator_id','rank'],ascending=[True,False]).drop_duplicates('creator_id')
    tmp['bonus_amount']=tmp['bonus_code'].astype(str).str.upper().map(map_amount).fillna(0)
    agg=tmp.groupby(group_col)['bonus_amount'].sum().reset_index().rename(columns={'bonus_amount':'bonus_additionnel'})
    return agg

def compute_agents(crea):
    base=totals_hierarchy_by('agent',crea)
    if base.empty:return pd.DataFrame(columns=['agent','diamants_mois','base_prime','bonus_additionnel','prime_agent','Facture €'])
    base['base_prime']=base['diamants_hierarchie'].apply(percent_reward)
    base['base_prime']=(np.floor(base['base_prime']/1000)*1000).astype(int)
    b=sum_bonus_for('agent',crea,{'B2':1000,'B3':15000})
    out=base.merge(b,on='agent',how='left').fillna({'bonus_additionnel':0})
    out['prime_agent']=out['base_prime']+out['bonus_additionnel']
    out['prime_agent']=(np.floor(out['prime_agent']/1000)*1000).astype(int)
    out.rename(columns={'diamants_hierarchie':'diamants_mois'},inplace=True)
    out['Facture €'] = (np.floor((out['base_prime'] * 0.0084) / 5) * 5).astype(int)
    cols = ['agent','diamants_mois','base_prime','bonus_additionnel','prime_agent','Facture €']
    return out[cols]

def compute_managers(crea):
    base=totals_hierarchy_by('groupe',crea)
    if base.empty:return pd.DataFrame(columns=['groupe','diamants_mois','base_prime','bonus_additionnel','prime_manager','Facture €'])
    base['base_prime']=base['diamants_hierarchie'].apply(percent_reward)
    base['base_prime']=(np.floor(base['base_prime']/1000)*1000).astype(int)
    b=sum_bonus_for('groupe',crea,{'B2':1000,'B3':5000})
    out=base.merge(b,on='groupe',how='left').fillna({'bonus_additionnel':0})
    out['prime_manager']=out['base_prime']+out['bonus_additionnel']
    out['prime_manager']=(np.floor(out['prime_manager']/1000)*1000).astype(int)
    out.rename(columns={'diamants_hierarchie':'diamants_mois'},inplace=True)
    out['Facture €'] = (np.floor((out['base_prime'] * 0.0084) / 5) * 5).astype(int)
    cols = ['groupe','diamants_mois','base_prime','bonus_additionnel','prime_manager','Facture €']
    return out[cols]

# -----------------------------------------------------------------------------
# PDF
# -----------------------------------------------------------------------------
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
    f_prev2=st.file_uploader('Mois N-2 (historique)',type=['xlsx','xls','csv'],key='prev2')
with c4:
    if st.button('Forcer relecture'):
        st.cache_data.clear(); st.rerun()

if f_cur:
    # lectures
    cur=normalize(read_any(f_cur.getvalue(),f_cur.name))
    hist=pd.DataFrame()
    prev_df = pd.DataFrame()
    if f_prev:
        prev_df = normalize(read_any(f_prev.getvalue(),f_prev.name))
        hist = prev_df
    if f_prev2:
        hist2=normalize(read_any(f_prev2.getvalue(),f_prev2.name))
        hist=pd.concat([hist,hist2],ignore_index=True) if not hist.empty else hist2

    t1,t2,t3=st.tabs(['Créateurs','Agents','Managers'])

    with t1:
        crea=compute_creators(cur,hist,prev_df=prev_df)
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
        ag=compute_agents(crea)
        st.dataframe(ag,use_container_width=True)
        st.download_button('CSV Agents',ag.to_csv(index=False).encode('utf-8'),'recompenses_agents.csv','text/csv')
        safe_pdf('PDF Agents','Récompenses Agents',ag,'recompenses_agents.pdf')

    with t3:
        man=compute_managers(crea)
        st.dataframe(man,use_container_width=True)
        st.download_button('CSV Managers',man.to_csv(index=False).encode('utf-8'),'recompenses_managers.csv','text/csv')
        safe_pdf('PDF Managers','Récompenses Managers',man,'recompenses_managers.pdf')

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
