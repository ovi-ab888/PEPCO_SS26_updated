# theme.py
import os
import streamlit as st

THEME_CSS = """
<style>
:root{
  --card-bg: rgba(255,255,255,.04);
  --card-br: rgba(255,255,255,.12);
  --input-bg: rgba(255,255,255,.08);
  --input-br: rgba(255,255,255,.25);
  --txt:      #E9ECF6;
  --muted:    #C2C8DF;
}
.block-container{max-width:1120px; padding-top:1rem; padding-bottom:3rem;}
h1,h2,h3{font-weight:700;} h1{letter-spacing:.2px;} h2,h3{letter-spacing:.1px;}
section[data-testid="stFileUploader"],
div[data-testid="stDataFrameContainer"],
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stDataEditor"]){
  background:var(--card-bg)!important; border:1px solid var(--card-br)!important;
  border-radius:14px!important; padding:12px 14px; box-shadow:0 1px 8px rgba(0,0,0,.12);
}
label, .stMultiSelect label, .stSelectbox label, .stNumberInput label, .stTextInput label{
  color:var(--txt)!important; font-weight:500;
}
input, textarea{
  color:var(--txt)!important; background:var(--input-bg)!important; border-color:var(--input-br)!important;
}
input::placeholder, textarea::placeholder{ color:var(--muted)!important; opacity:.95; }
div[data-baseweb="select"] > div{ background:var(--input-bg)!important; border-color:var(--input-br)!important; border-radius:12px!important; }
div[data-baseweb="select"] input{ color:var(--txt)!important; } div[data-baseweb="select"] svg{ opacity:.9; }
div[data-testid="stNumberInput"] input{ color:var(--txt)!important; background:var(--input-bg)!important; border-color:var(--input-br)!important; }
.stButton > button{ border-radius:12px; padding:.55rem 1rem; }
[data-testid="stTable"] td,[data-testid="stTable"] th{ padding:.45rem .6rem; }
</style>
"""

def apply_theme():
    st.markdown(THEME_CSS, unsafe_allow_html=True)

def render_header(logo_svg="logo.svg", logo_png="logo.png"):
    left, right = st.columns([3, 10], vertical_alignment="center")
    with left:
        if os.path.exists(logo_svg):
            st.image(logo_svg, width=300)
        elif os.path.exists(logo_png):
            st.image(logo_png, width=300)
        else:
            st.markdown("<div style='font-size:40px'>🏷️</div>", unsafe_allow_html=True)
