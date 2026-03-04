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
# Règles
# -----------------------------------------------------------------------------
THR_CONFIRMED = 150000
ACTIVITY = {'beginner':(7,15),'confirmed':(12,25),'second':(20,80)}

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

def compute_creators(df,hist):
    rows=[]
    hist = hist if hist is not None else pd.DataFrame()

    # niveaux (pour évolution/stagnation)
    LEVELS = [100000,200000,300000,500000,700000,1000000,1600000,2500000,5000000]

    def level_idx(x:float)->int:
        i=0
        for b in LEVELS:
            if x>=b: i+=1
            else: break
        return i

    def activity_rate(days:int, hours:float)->float:
        if days>=22 and hours>=80: return 0.03
        if days>=18 and hours>=60: return 0.02
        if days>=11 and hours>=30: return 0.01
        return 0.0

    def floor_1000(x:float)->int:
        return int(x//1000)*1000

    def prev_month_amount(cid:str)->float:
        if hist is None or hist.empty: return 0.0
        h=hist[hist['creator_id'].astype(str)==str(cid)].copy()
        if h.empty: return 0.0
        h['periode']=h['periode'].astype(str)
        # dernier mois dans l'historique fourni
        last=h.sort_values('periode').iloc[-1]
        return float(last.get('diamants',0) or 0.0)

    def ever_200k(cid:str)->bool:
        if hist is None or hist.empty: return False
        h=hist[hist['creator_id'].astype(str)==str(cid)]
        if h.empty: return False
        return float(h['diamants'].max() or 0) >= 200000

    for _,r in df.iterrows():
        amount=float(r['diamants'])
        days=int(r['jours_live'])
        hours=float(r['heures_live'])

        rate = activity_rate(days, hours)

        # Récompense fixe 50K (uniquement si <100K)
        fixed = 0
        if amount>=50000 and amount<100000:
            if days>=22 and hours>=80: fixed=1000
            elif days>=11 and hours>=30: fixed=500

        eligible_pct = (amount>=100000) and (rate>0)

        # bonus non cumulable (uniquement si éligible %)
        prev_amt = prev_month_amount(r['creator_id'])
        prev_lvl = level_idx(prev_amt)
        cur_lvl = level_idx(amount)

        bonus_rate = 0.0
        bcode = ""

        if eligible_pct and prev_amt>0:
            if cur_lvl > prev_lvl:
                bonus_rate = 0.02
                bcode = "EVOL"
            elif amount < prev_amt:
                bonus_rate = 0.0
                bcode = "BAISSE"
            else:
                passed_200k = (amount>=200000) or (prev_amt>=200000) or ever_200k(r['creator_id'])
                if passed_200k and cur_lvl==prev_lvl and cur_lvl>0:
                    bonus_rate = 0.01
                    bcode = "STAG"

        # Montants
        recomp_pct = floor_1000(amount*rate) if eligible_pct else 0
        bonus_amt = floor_1000(amount*bonus_rate) if eligible_pct else 0

        total = int(recomp_pct + bonus_amt + fixed)

        etat='✅ Actif' if (recomp_pct>0 or fixed>0) else '⚠️ Inactif'
        why=''

        if etat!='✅ Actif':
            if amount<50000:
                why="Diamants < 50 000"
            elif rate<=0:
                why="Activité insuffisante"
            elif amount<100000:
                why="Diamants < 100 000"

        rows.append({
            'creator_id':r['creator_id'],'creator_username':r['creator_username'],'groupe':r['groupe'],'agent':r['agent'],
            'periode':r['periode'],'diamants':amount,'jours_live':days,'heures_live':hours,
            'type_createur':"Nouveau",'etat_activite':etat,'raison_ineligibilite':why if etat!='✅ Actif' else '',
            'recompense_palier_1':recomp_pct,'recompense_palier_2':fixed,'bonus_debutant':bonus_amt,'bonus_code':bcode,
            'total_createur':total,'actif_hierarchie':(total>0)
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

def compute_agents(crea, hist, task_global: str):
    base=totals_hierarchy_by('agent',crea)
    if base.empty:
        return pd.DataFrame(columns=['agent','diamants_mois','tache_progressive','bonus_validé','base_prime','prime_agent','Facture €'])

    # Commission selon tâche globale
    comm_map = {"5%":0.015,"7%":0.02,"9%":0.025}
    commission = comm_map.get(task_global, 0.02)

    base = base.rename(columns={'diamants_hierarchie':'diamants_mois'})
    base['tache_progressive'] = task_global

    # Bonus par agent : auto depuis N-1 (proxy diamants), modifiable
    hist = hist if hist is not None else pd.DataFrame()
    prev = totals_hierarchy_by('agent', compute_creators(hist, pd.DataFrame()) if (not hist.empty) else pd.DataFrame())
    if not prev.empty:
        prev = prev.rename(columns={'diamants_hierarchie':'prev_diamants'})
        prev = prev[['agent','prev_diamants']]
        base = base.merge(prev, on='agent', how='left')
    else:
        base['prev_diamants'] = 0.0

    base['bonus_validé'] = base.apply(lambda x: _auto_bonus_from_progression(float(x['diamants_mois']), float(x.get('prev_diamants',0) or 0)), axis=1)

    # Applique choix précédent sauvegardé si existant pour cette période
    saved = _load_bonus_choices(AGENT_BONUS_FILE, 'agent')
    if not saved.empty:
        saved = saved[saved['periode'].astype(str)==str(crea['periode'].iloc[0])].copy() if (crea is not None and not crea.empty) else saved
        base = base.merge(saved[['agent','bonus_validé']], on='agent', how='left', suffixes=("","_saved"))
        base['bonus_validé'] = base['bonus_validé_saved'].fillna(base['bonus_validé'])
        base.drop(columns=[c for c in base.columns if c.endswith('_saved')], inplace=True)

    # Bonus mapping
    bonus_map = {"0%":0.0,"+0,5%":0.005,"+1%":0.01}
    base['bonus_rate'] = base['bonus_validé'].map(bonus_map).fillna(0.0)

    # Minimum non reportable 200K
    elig = base['diamants_mois'].astype(float) >= 200000
    base['base_prime'] = np.where(elig, base['diamants_mois'].astype(float)*commission, 0.0)
    base['prime_agent'] = np.where(elig, base['diamants_mois'].astype(float)*(commission+base['bonus_rate']), 0.0)

    # Arrondi centaine inférieure
    base['base_prime'] = (np.floor(base['base_prime']/100)*100).astype(int)
    base['prime_agent'] = (np.floor(base['prime_agent']/100)*100).astype(int)

    # Facture € : base_prime * 0.0084 arrondi 5€ inférieur
    base['Facture €'] = (np.floor((base['base_prime'] * 0.0084) / 5) * 5).astype(int)

    cols = ['agent','diamants_mois','tache_progressive','bonus_validé','base_prime','prime_agent','Facture €']
    return base[cols]

def compute_managers(crea, hist, task_global: str):
    base=totals_hierarchy_by('groupe',crea)
    if base.empty:
        return pd.DataFrame(columns=['groupe','diamants_mois','tache_progressive','bonus_validé','base_prime','prime_manager','Facture €'])

    comm_map = {"5%":0.02,"7%":0.03,"9%":0.04}
    commission = comm_map.get(task_global, 0.03)

    base = base.rename(columns={'diamants_hierarchie':'diamants_mois'})
    base['tache_progressive'] = task_global

    hist = hist if hist is not None else pd.DataFrame()
    prev = totals_hierarchy_by('groupe', compute_creators(hist, pd.DataFrame()) if (not hist.empty) else pd.DataFrame())
    if not prev.empty:
        prev = prev.rename(columns={'diamants_hierarchie':'prev_diamants'})
        prev = prev[['groupe','prev_diamants']]
        base = base.merge(prev, on='groupe', how='left')
    else:
        base['prev_diamants'] = 0.0

    base['bonus_validé'] = base.apply(lambda x: _auto_bonus_from_progression(float(x['diamants_mois']), float(x.get('prev_diamants',0) or 0)), axis=1)

    saved = _load_bonus_choices(MANAGER_BONUS_FILE, 'groupe')
    if not saved.empty:
        saved = saved[saved['periode'].astype(str)==str(crea['periode'].iloc[0])].copy() if (crea is not None and not crea.empty) else saved
        base = base.merge(saved[['groupe','bonus_validé']], on='groupe', how='left', suffixes=("","_saved"))
        base['bonus_validé'] = base['bonus_validé_saved'].fillna(base['bonus_validé'])
        base.drop(columns=[c for c in base.columns if c.endswith('_saved')], inplace=True)

    bonus_map = {"0%":0.0,"+0,5%":0.005,"+1%":0.01}
    base['bonus_rate'] = base['bonus_validé'].map(bonus_map).fillna(0.0)

    # Minimum non reportable 1M
    elig = base['diamants_mois'].astype(float) >= 1000000
    base['base_prime'] = np.where(elig, base['diamants_mois'].astype(float)*commission, 0.0)
    base['prime_manager'] = np.where(elig, base['diamants_mois'].astype(float)*(commission+base['bonus_rate']), 0.0)

    base['base_prime'] = (np.floor(base['base_prime']/100)*100).astype(int)
    base['prime_manager'] = (np.floor(base['prime_manager']/100)*100).astype(int)

    base['Facture €'] = (np.floor((base['base_prime'] * 0.0084) / 5) * 5).astype(int)

    cols = ['groupe','diamants_mois','tache_progressive','bonus_validé','base_prime','prime_manager','Facture €']
    return base[cols]

def _load_bonus_choices(path: Path, key_col: str) -> pd.DataFrame:
    if path.exists():
        try:
            return pd.read_csv(path, dtype=str)
        except Exception:
            return pd.DataFrame(columns=[key_col,'periode','bonus_validé'])
    return pd.DataFrame(columns=[key_col,'periode','bonus_validé'])

def _save_bonus_choices(path: Path, df: pd.DataFrame, key_col: str):
    prev = _load_bonus_choices(path, key_col)
    allv = pd.concat([prev, df[[key_col,'periode','bonus_validé']].astype(str)], ignore_index=True)
    allv = allv.drop_duplicates(subset=[key_col,'periode'], keep='last')
    path.parent.mkdir(parents=True, exist_ok=True)
    allv.to_csv(path, index=False)

def _auto_bonus_from_progression(cur: float, prev: float) -> str:
    # progression basée sur l'évolution des diamants vs N-1 (proxy)
    if prev <= 0: 
        return "0%"
    prog = (cur - prev) / prev
    if prog >= 0.20:
        return "+1%"
    if prog > 0:
        return "+0,5%"
    return "0%"

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
    # Remplace l'ancien N-2 par une sélection globale de tâche progressive (appliquée à tous)
    task_global = st.radio('Tâche progressive (globale)', options=['5%','7%','9%'], horizontal=True, key='task_global')
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
    ag = compute_agents(crea, hist, task_global)

    if ag is None or ag.empty:
        st.dataframe(ag, use_container_width=True)
    else:
        st.caption("Bonus Backstage : suggestion auto (vs N-1) mais modifiable. Tâche progressive appliquée globalement.")

        edited = st.data_editor(
            ag,
            hide_index=True,
            use_container_width=True,
            column_config={
                "bonus_validé": st.column_config.SelectboxColumn("bonus_validé", options=["0%","+0,5%","+1%"]),
            },
            disabled=["agent","diamants_mois","tache_progressive","base_prime","prime_agent","Facture €"],
            key="editor_agents_bonus"
        )

        # Recalcul après modification bonus
        # On recompose un petit df pour sauvegarder bonus choisi
        ag = edited.copy()
        # Sauvegarde choix bonus pour la période courante
        if not ag.empty:
            _save_bonus_choices(AGENT_BONUS_FILE, ag.rename(columns={"agent":"agent"}), "agent")

    st.download_button('CSV Agents', ag.to_csv(index=False).encode('utf-8'), 'recompenses_agents.csv', 'text/csv')
    safe_pdf('PDF Agents', 'Récompenses Agents', ag, 'recompenses_agents.pdf')

with t3:
    man = compute_managers(crea, hist, task_global)

    if man is None or man.empty:
        st.dataframe(man, use_container_width=True)
    else:
        st.caption("Bonus Backstage : suggestion auto (vs N-1) mais modifiable. Tâche progressive appliquée globalement.")

        edited = st.data_editor(
            man,
            hide_index=True,
            use_container_width=True,
            column_config={
                "bonus_validé": st.column_config.SelectboxColumn("bonus_validé", options=["0%","+0,5%","+1%"]),
            },
            disabled=["groupe","diamants_mois","tache_progressive","base_prime","prime_manager","Facture €"],
            key="editor_managers_bonus"
        )

        man = edited.copy()
        if not man.empty:
            _save_bonus_choices(MANAGER_BONUS_FILE, man.rename(columns={"groupe":"groupe"}), "groupe")

    st.download_button('CSV Managers', man.to_csv(index=False).encode('utf-8'), 'recompenses_managers.csv', 'text/csv')
    safe_pdf('PDF Managers', 'Récompenses Managers', man, 'recompenses_managers.pdf')


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