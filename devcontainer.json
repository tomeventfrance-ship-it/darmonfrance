# ui_theme.py — complet
# Thème rouge/blanc/noir + Poppins + logo centré (desktop) et visible (mobile)
# À utiliser dans app.py :
#   import ui_theme
#   ui_theme.apply_theme()
import os, base64, pathlib
import streamlit as st

PRIMARY = "#e5093f"
BLACK   = "#0b0b0b"
WHITE   = "#ffffff"

def _logo_b64() -> str:
    p = pathlib.Path("assets/logo.png")
    if p.exists():
        try:
            return base64.b64encode(p.read_bytes()).decode("utf-8")
        except Exception:
            return ""
    return ""

def apply_theme(role: str | None = None):
    # 1) Police Poppins
    st.markdown(
        """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        """, unsafe_allow_html=True
    )
    font_stack = "'Poppins', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

    # 2) Logo encodé
    b64 = _logo_b64()

    # 3) CSS complet (fond + mobile + widgets)
    css = f"""
    <style>
    :root {{
      --md-primary: {PRIMARY};
      --md-black: {BLACK};
      --md-white: {WHITE};
      --md-font: {font_stack};
    }}

    /* Conteneur principal : logo + dégradé */
    [data-testid="stAppViewContainer"] {{
      background:
        url('data:image/png;base64,{b64}') no-repeat center,
        radial-gradient(1200px 600px at 20% 0%, #ff2f5a 0%, #c4002b 40%, #0b0b0b 100%) !important;
      background-size: 28vmax, cover !important;   /* logo, gradient */
      background-attachment: scroll, scroll;        /* compatible mobile */
      color: var(--md-white);
      font-family: var(--md-font) !important;
    }}
    section.main {{ position: relative; z-index: 1; }}

    /* Mobile : repositionne et redimensionne le logo */
    @media (max-width: 768px) {{
      [data-testid="stAppViewContainer"] {{
        background-position: center 32%, center;
        background-size: 60vw, cover !important;
      }}
    }}

    /* Sidebar sombre */
    [data-testid="stSidebar"] > div:first-child {{
        background: #0f0f10 !important;
        border-right: 1px solid rgba(255,255,255,0.06);
        color: var(--md-white);
        font-family: var(--md-font) !important;
    }}

    /* Titres et textes */
    h1, h2, h3, h4, h5, h6 {{ color: var(--md-white); letter-spacing: .2px; font-weight: 600; font-family: var(--md-font) !important; }}
    .stMarkdown, .stText, .stCaption, p, small {{ color: rgba(255,255,255,0.90); font-family: var(--md-font) !important; }}

    /* Boutons */
    .stButton>button {{
        background: var(--md-primary) !important;
        color: var(--md-white) !important;
        border: 0 !important;
        font-weight: 600;
        border-radius: 10px;
        font-family: var(--md-font) !important;
    }}
    .stButton>button:hover {{ filter: brightness(1.06); }}

    /* Boutons de téléchargement */
    .stDownloadButton>button {{
        background: transparent !important;
        border: 1px solid var(--md-primary) !important;
        color: var(--md-primary) !important;
        font-weight: 600;
        border-radius: 10px;
        font-family: var(--md-font) !important;
    }}
    .stDownloadButton>button:hover {{
        background: var(--md-primary) !important;
        color: var(--md-white) !important;
    }}

    /* Onglets */
    .stTabs [data-baseweb="tab-list"] {{ gap: 6px; }}
    .stTabs [data-baseweb="tab"] {{
        background: rgba(255,255,255,0.06);
        border-radius: 10px;
        padding: 8px 14px;
        color: var(--md-white);
        font-weight: 600;
        font-family: var(--md-font) !important;
    }}
    .stTabs [aria-selected="true"] {{
        background: var(--md-primary);
        color: var(--md-white);
    }}

    /* Tableaux */
    .stDataFrame thead tr th {{
        background: #000 !important;
        color: #fff !important;
        font-weight: 700 !important;
        font-family: var(--md-font) !important;
    }}
    .stDataFrame tbody tr:nth-child(odd) td {{ background: rgba(255,255,255,0.06) !important; }}
    .stDataFrame tbody tr:nth-child(even) td {{ background: rgba(255,255,255,0.025) !important; }}

    /* Footer custom si utilisé ailleurs */
    .app-footer {{ color: rgba(255,255,255,0.75) !important; font-family: var(--md-font) !important; }}

    /* Affiche toujours le menu */
    #MainMenu {{ visibility: visible !important; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

    # 4) Badge rôle en haut à droite (si tu utilises MD_ROLE / DEFAULT_ROLE)
    tag = (os.getenv("MD_ROLE", "") or st.secrets.get("DEFAULT_ROLE", "ADMIN")).upper()
    st.markdown(
        '<div style="position:fixed;top:8px;right:12px;padding:4px 10px;'
        'background:rgba(0,0,0,0.35);border:1px solid rgba(255,255,255,0.15);'
        'border-radius:12px;color:#fff;font-size:12px;z-index:1000;">' + tag.title() + ' mode</div>',
        unsafe_allow_html=True,
    )
