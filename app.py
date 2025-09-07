# ======================== PAGE CONFIG (MUST BE FIRST) ========================
import streamlit as st
st.set_page_config(page_title="PEPCO Data Processor", page_icon="📑", layout="wide")

# ======================== Imports ========================
# ---- Robust PDF backends (PyMuPDF → pdfplumber → pypdf) ----
PDF_BACKEND = None
try:
    import fitz  # PyMuPDF import name
    PDF_BACKEND = "pymupdf"
except Exception:  # ModuleNotFoundError or other import failure
    fitz = None
    try:
        import pdfplumber  # pure-Python (pdfminer.six)
        PDF_BACKEND = "pdfplumber"
    except Exception:
        pdfplumber = None
        try:
            from pypdf import PdfReader  # pure-Python
            PDF_BACKEND = "pypdf"
        except Exception:
            PdfReader = None
            st.error(
                "No PDF backend available. Please add `pymupdf==1.24.10` or `pdfplumber` or `pypdf` to requirements.txt and redeploy."
            )
            st.stop()

import pandas as pd
import re
from io import StringIO
import csv as pycsv
from datetime import datetime, timedelta
import os
import requests

# ======================== Local modules (optional) ========================
# If these modules are not present, we create lightweight fallbacks below
try:
    from auth import check_password as _check_password
except Exception:
    _check_password = None

try:
    from theme import apply_theme as _apply_theme, render_header as _render_header
except Exception:
    _apply_theme = None
    _render_header = None

# ======================== Optional external config ========================
# If a local config.py exists, these values will override defaults
try:
    from config import WASHING_CODES as CFG_WC, COLLECTION_MAPPING as CFG_CM
    from config import PRICE_SHEET_CSV, PRODUCT_TRANSLATION_SHEET, MATERIAL_TRANSLATION_CSV
except Exception:
    CFG_WC = CFG_CM = None
    # ↓ Public CSV endpoints expected to be set in your own config.py.
    #    Keep placeholders here to avoid leaking private links.
    PRICE_SHEET_CSV = ""
    PRODUCT_TRANSLATION_SHEET = ""
    MATERIAL_TRANSLATION_CSV = ""

# ======================== Fallback mappings (used if config not provided) ========================
WASHING_CODES = CFG_WC or {
    # Example mapping (extend as you need)
    "9": "WASH_9",
    "41": "WASH_41",
    "42": "WASH_42",
}
COLLECTION_MAPPING = CFG_CM or {
    # Example season/collection normalization – extend/replace with your own rules
    "AW": "Autumn/Winter",
    "SS": "Spring/Summer",
}

# ======================== Utilities ========================
@st.cache_data(show_spinner=False)
def load_csv_from_url(url: str) -> pd.DataFrame:
    if not url:
        return pd.DataFrame()
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(show_spinner=False)
def load_product_translations() -> pd.DataFrame:
    return load_csv_from_url(PRODUCT_TRANSLATION_SHEET)

@st.cache_data(show_spinner=False)
def load_material_translations() -> pd.DataFrame:
    # Expect either long format: material,language,translation
    # or wide format: material, AL, BG, MK, RS
    df = load_csv_from_url(MATERIAL_TRANSLATION_CSV)
    if df.empty:
        return df
    # Normalize columns
    cols = [c.strip() for c in df.columns]
    df.columns = cols
    if set(["material", "language", "translation"]).issubset(set(cols)):
        return df
    # Otherwise pivot wide → long if languages exist as columns
    langs = [c for c in cols if c.upper() in ["AL", "BG", "MK", "RS"]]
    if langs:
        long_rows = []
        for _, row in df.iterrows():
            material = str(row.get("material") or row.get("Material") or "").strip()
            for lang in langs:
                tr = str(row.get(lang, "")).strip()
                if material and tr:
                    long_rows.append({"material": material, "language": lang.upper(), "translation": tr})
        return pd.DataFrame(long_rows)
    return df

@st.cache_data(show_spinner=False)
def load_price_ladder() -> pd.DataFrame:
    return load_csv_from_url(PRICE_SHEET_CSV)

@st.cache_data(show_spinner=False)
def find_closest_price(pln: float) -> dict | None:
    sheet = load_price_ladder()
    if sheet.empty or "PLN" not in sheet.columns:
        return None
    try:
        sheet["PLN_num"] = pd.to_numeric(sheet["PLN"].astype(str).str.replace(",", "."), errors="coerce")
        sheet = sheet.dropna(subset=["PLN_num"])  # type: ignore
        idx = (sheet["PLN_num"] - float(pln)).abs().idxmin()
        row = sheet.loc[idx]
        # Return every currency column except helper
        out = {c: row[c] for c in sheet.columns if c not in ["PLN_num"]}
        # Ensure string formatting for money-like values
        for k, v in out.items():
            if isinstance(v, (int, float)):
                out[k] = f"{v}"
        return out
    except Exception:
        return None

def format_number(n, suffix=None):
    try:
        val = float(str(n).replace(",", "."))
        s = ("{:.2f}".format(val)).rstrip("0").rstrip(".")
        return f"{s} {suffix}" if suffix else s
    except Exception:
        return str(n)

# ---------- PDF helpers ----------
def read_pdf_text(uploaded_file) -> str:
    """Return full text of PDF using the first available backend."""
    # Streamlit uploads are file-like; reset pointer
    pos = uploaded_file.tell()
    uploaded_file.seek(0)

    if PDF_BACKEND == "pymupdf":
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")  # type: ignore
        pages = [page.get_text() for page in doc]
        doc.close()
        text = "\n".join(pages)

    elif PDF_BACKEND == "pdfplumber":
        with pdfplumber.open(uploaded_file) as pdf:  # type: ignore
            pages = [(p.extract_text() or "") for p in pdf.pages]
        text = "\n".join(pages)

    else:  # pypdf
        reader = PdfReader(uploaded_file)  # type: ignore
        pages = [(page.extract_text() or "") for page in reader.pages]
        text = "\n".join(pages)

    uploaded_file.seek(pos)  # restore pointer
    return text

# A very lenient parser – adapt this to your actual PDFs later
ORDER_RE = re.compile(r"Order\s*(?:No\.|ID|#)?\s*[:\-]?\s*(\S+)", re.I)
SUPPLIER_RE = re.compile(r"Supplier\s*[:\-]?\s*(.+)", re.I)
STYLE_RE = re.compile(r"Style\s*[:\-]?\s*(\S+)", re.I)
COLOUR_RE = re.compile(r"Colour\s*[:\-]?\s*(.+)", re.I)


def extract_data_from_pdf(uploaded_file) -> list[dict]:
    text = read_pdf_text(uploaded_file)
    # Split per page-ish chunks to pick first occurrence
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    blob = " \n ".join(lines)

    def _find(rx, default=""):
        m = rx.search(blob)
        return (m.group(1).strip() if m else default)

    order_id = _find(ORDER_RE, os.path.splitext(uploaded_file.name)[0])
    supplier = _find(SUPPLIER_RE, "")
    style = _find(STYLE_RE, "")
    colour = _find(COLOUR_RE, "")

    row = {
        "Order_ID": order_id,
        "Supplier_name": supplier,
        "Style": style,
        "Colour": colour,
        "Supplier_product_code": "",
        "Item_classification": "",
        "Collection": "",
        "today_date": datetime.now().strftime("%d-%m-%Y"),
        "Colour_SKU": "",
        "Style_Merch_Season": "",
        "Batch": "",
        "barcode": "",
    }
    return [row]

# ---------- Simple helpers for dept/collection ----------
def get_dept_value(item_classification: str) -> str:
    s = (item_classification or "").upper()
    if "GIRL" in s:
        return "Baby girl"
    if "BOY" in s:
        return "Baby boy"
    return "Baby"


def modify_collection(collection_raw: str, item_classification: str) -> str:
    # Adjust using COLLECTION_MAPPING if short tags present
    c = (collection_raw or "").strip()
    for short, full in COLLECTION_MAPPING.items():
        if short.upper() in (c.upper() or ""):
            return full
    return c

# ======================== UI pieces ========================
def check_password() -> bool:
    if _check_password:
        return _check_password()
    # Fallback – very light password gate via st.secrets
    secret = st.secrets.get("app_password") if hasattr(st, "secrets") else None
    if not secret:
        st.warning("App password not configured. Set 'app_password' in .streamlit/secrets.toml or Streamlit Secrets.")
        return True  # allow running without password if not set
    if "_authed" not in st.session_state:
        with st.form("login", clear_on_submit=False):
            pwd = st.text_input("Enter password", type="password")
            ok = st.form_submit_button("Login")
        if ok:
            st.session_state._authed = (pwd == secret)
        else:
            st.stop()
    if not st.session_state.get("_authed", False):
        st.error("Wrong password")
        st.stop()
    return True


def apply_theme():
    if _apply_theme:
        _apply_theme()
    else:
        # Minimal dark theme tweaks
        st.markdown(
            """
            <style>
            .stButton>button { border-radius: 10px; padding: 0.5rem 0.9rem; }
            </style>
            """,
            unsafe_allow_html=True,
        )


def render_header():
    if _render_header:
        _render_header()
    else:
        st.markdown("# PEPCO Automation App")
        st.caption(f"PDF backend in use: **{PDF_BACKEND}**")


# ======================== Material Composition UI ========================
def material_composition_ui(material_translations_df: pd.DataFrame):
    st.markdown("### Material Composition (%)")

    if "mat_rows" not in st.session_state:
        st.session_state.mat_rows = 1
    if "mat_data" not in st.session_state:
        st.session_state.mat_data = [{"mat": "—", "pct": 100}]

    materials_list = (
        material_translations_df["material"].dropna().unique().tolist()
        if not material_translations_df.empty and "material" in material_translations_df.columns
        else []
    )

    def _ensure_row(i):
        while i >= len(st.session_state.mat_data):
            st.session_state.mat_data.append({"mat": "—", "pct": 0})

    for i in range(st.session_state.mat_rows):
        _ensure_row(i)
        prev_total = sum(r.get("pct", 0) for r in st.session_state.mat_data[:i])
        remain = max(0, 100 - prev_total)
        cA, cB = st.columns([3, 1.2])
        with cA:
            st.session_state.mat_data[i]["mat"] = st.selectbox(
                "Select Material(s)" if i == 0 else f"Select Material(s) #{i+1}",
                ["—"] + materials_list,
                index=(["—"] + materials_list).index(st.session_state.mat_data[i]["mat"]) if st.session_state.mat_data[i]["mat"] in (["—"] + materials_list) else 0,
                key=f"mat_sel_{i}",
            )
        with cB:
            default_pct = 100 if (i == 0 and prev_total == 0) else min(st.session_state.mat_data[i].get("pct", 0), remain)
            st.session_state.mat_data[i]["pct"] = st.number_input(
                "Composition (%)" if i == 0 else f"Composition (%) #{i+1}",
                min_value=0,
                max_value=remain,
                value=default_pct,
                step=1,
                key=f"mat_pct_{i}",
            )

    valid_rows = [r for r in st.session_state.mat_data[: st.session_state.mat_rows] if r["mat"] not in (None, "—") and r["pct"] > 0]
    running_total = sum(r["pct"] for r in valid_rows)

    if running_total < 100 and st.session_state.mat_rows < 5:
        last = st.session_state.mat_data[st.session_state.mat_rows - 1]
        if last["mat"] not in (None, "—") and last["pct"] > 0:
            st.session_state.mat_rows += 1
            _ensure_row(st.session_state.mat_rows - 1)
            st.experimental_rerun()

    if running_total >= 100 and st.session_state.mat_rows > len(valid_rows):
        st.session_state.mat_rows = len(valid_rows)

    if st.session_state.mat_rows == 1 and valid_rows and valid_rows[0]["pct"] == 100:
        st.info("✅ 100% selected — নতুন material যোগ করার প্রয়োজন নেই.")
    elif running_total > 100:
        st.error("⚠️ Total exceeds 100%")

    st.write(f"**Total: {running_total}%**")

    # Outputs
    selected_materials = [r["mat"] for r in valid_rows]
    cotton_value = "Y" if (len(valid_rows) == 1 and valid_rows[0]["mat"].lower() == "cotton" and valid_rows[0]["pct"] == 100) else ""

    # Build translations per language if we have the table
    material_trans_dict, material_compositions = {}, {}
    if selected_materials and not material_translations_df.empty:
        for lang in ["AL", "BG", "MK", "RS"]:
            names, comp = [], []
            for r in valid_rows:
                t = material_translations_df[
                    (material_translations_df["material"] == r["mat"]) &
                    (material_translations_df["language"].str.upper() == lang)
                ]
                if not t.empty:
                    tr = t["translation"].iloc[0]
                    names.append(tr)
                    comp.append(f"{r['pct']}% {tr}")
            if names:
                material_trans_dict[lang] = ", ".join(names)
            if comp:
                material_compositions[lang] = ", ".join(comp)

    return selected_materials, cotton_value, material_trans_dict, material_compositions


# ======================== Main Processing ========================
def process_pepco_pdf():
    translations_df = load_product_translations()
    material_translations_df = load_material_translations()

    # Uploader
    st.subheader("PEPCO Data Processing")
    up = st.file_uploader("Upload PEPCO Data file", type=["pdf"], accept_multiple_files=True)

    # Quick controls
    c_top = st.container()
    c_dep, c_prod, c_wash, c_pln = st.columns([1, 1, 1, 1])

    # Department / Product options from translations sheet if available
    if not translations_df.empty and "DEPARTMENT" in translations_df.columns:
        depts = sorted(translations_df["DEPARTMENT"].dropna().unique().tolist())
    else:
        depts = ["Baby boy", "Baby girl", "Baby"]

    with c_dep:
        selected_dept = st.selectbox("Select Department", depts)

    # Filter products by dept if sheet present
    if not translations_df.empty and {"DEPARTMENT", "PRODUCT_NAME"}.issubset(translations_df.columns):
        filtered = translations_df[translations_df["DEPARTMENT"] == selected_dept]
        products = filtered["PRODUCT_NAME"].dropna().unique().tolist()
    else:
        filtered = pd.DataFrame()
        products = ["T-shirt", "Bodysuit", "Romper"]

    with c_prod:
        product_type = st.selectbox("Select Product Type", products)

    with c_wash:
        washing_code_key = st.selectbox("Select Washing Code", options=list(WASHING_CODES.keys()))

    with c_pln:
        pln_price_raw = st.text_input("Enter PLN Price")
        pln_price = None
        if pln_price_raw.strip():
            try:
                pln_price = float(pln_price_raw.replace(",", "."))
                if pln_price < 0:
                    st.error("❌ Price can't be negative.")
                    pln_price = None
            except ValueError:
                st.error("❌ Please enter a valid number like 12.50 or 12,50")
                pln_price = None

    # Material Composition UI
    selected_materials, cotton_value, material_trans_dict, material_compositions = material_composition_ui(material_translations_df)

    st.markdown("---")
    st.subheader("Edit Before Download")

    rows = []
    for f in up or []:
        rows.extend(extract_data_from_pdf(f))

    if not rows:
        st.info("Upload one or more PDFs to extract data.")
        return

    df = pd.DataFrame(rows)

    # Enrich
    df["Dept"] = df["Item_classification"].apply(get_dept_value)
    df["Cotton"] = cotton_value
    df["Collection"] = df.apply(lambda r: modify_collection(r.get("Collection", ""), r.get("Item_classification", "")), axis=1)

    # Build product name translations if we have the sheet
    if not filtered.empty and not translations_df.empty:
        product_row = filtered[filtered["PRODUCT_NAME"] == product_type]
        if not product_row.empty:
            base = product_type
            df["product_name"] = base
        else:
            df["product_name"] = product_type
    else:
        df["product_name"] = product_type

    df["washing_code"] = WASHING_CODES.get(washing_code_key, washing_code_key)

    # Price ladder
    currency_values = find_closest_price(pln_price) if pln_price is not None else None
    if currency_values:
        for cur in ["EUR", "BGN", "BAM", "PLN", "RON", "CZK", "MKD", "RSD", "HUF"]:
            if cur in currency_values:
                df[cur] = str(currency_values[cur])

    final_cols = [
        "Order_ID",
        "Style",
        "Colour",
        "Supplier_product_code",
        "Item_classification",
        "Supplier_name",
        "today_date",
        "Collection",
        "Colour_SKU",
        "Style_Merch_Season",
        "Batch",
        "barcode",
        "washing_code",
        "EUR",
        "BGN",
        "BAM",
        "PLN",
        "RON",
        "CZK",
        "MKD",
        "RSD",
        "HUF",
        "product_name",
        "Dept",
        "Cotton",
    ]

    # Show editable table
    show_cols = [c for c in final_cols if c in df.columns]
    edited_df = st.data_editor(df[show_cols], use_container_width=True)

    # Download CSV (semicolon delimited, quoted)
    csv_buffer = StringIO()
    writer = pycsv.writer(csv_buffer, delimiter=';', quoting=pycsv.QUOTE_ALL)
    writer.writerow(show_cols)
    for row in edited_df.itertuples(index=False):
        writer.writerow(list(row))

    st.download_button(
        "📥 Download CSV",
        data=csv_buffer.getvalue().encode('utf-8-sig'),
        file_name=f"pepco_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )


# ======================== App Entrypoint ========================
def main():
    apply_theme()
    render_header()
    if check_password():
        # New upload / reset button
        if st.button("🔄 New upload", help="Clear current selections and start fresh"):
            for k in list(st.session_state.keys()):
                if k.startswith("mat_") or k in ("mat_rows", "mat_data"):
                    st.session_state.pop(k)
            st.experimental_rerun()
        process_pepco_pdf()


if __name__ == "__main__":
    main()
