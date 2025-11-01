# ==================== PAGE CONFIG (MUST BE FIRST) ====================
import streamlit as st
st.set_page_config(page_title="PEPCO Automation App", page_icon="🧾", layout="wide")

# ==================== Imports ====================
import fitz  # PyMuPDF
import pandas as pd
import re
from io import StringIO
import csv as pycsv
from datetime import datetime, timedelta
import os
import requests
import traceback

# ==================== THEME (compact) ====================
THEME_CSS = """
<style>
.block-container{max-width:1120px;padding-top:1rem;padding-bottom:3rem}
section[data-testid="stFileUploader"],div[data-testid="stDataFrameContainer"],div[data-testid="stVerticalBlock"]:has(> div[data-testid="stDataEditor"]){
  background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.12);border-radius:14px;padding:12px 14px}
label{font-weight:600}
</style>
"""

# ==================== PASSWORD GATE ====================
def check_password():
    """Optional password protection"""
    expected = os.environ.get("PEPCO_APP_PASSWORD") or st.secrets.get("app_password", None)
    if not expected:
        return True

    if st.session_state.get("password_ok"):
        return True

    def _password_entered():
        st.session_state["password_ok"] = (st.session_state.get("password") == expected)
        st.session_state.pop("password", None)

    st.text_input("Password", type="password", key="password", on_change=_password_entered)
    if st.session_state.get("password_ok") is False:
        st.error("Wrong password.")
    return st.session_state.get("password_ok", False)

# ==================== CONSTANTS ====================
WASHING_CODES = {
    '1':'১২৩৪৫','2':'১৪৭৮৫','3':'djnst','4':'djnpt','5':'djnqt',
    '6':'djnqt','7':'gjnpt','8':'gjnpu','9':'gjnqt','10':'gjnqu',
    '11':'ijnst','12':'ijnsu','13':'ijnpu','14':'ijnsv','15':'djnsw'
}

# ==================== DATA LOADERS ====================
@st.cache_data(ttl=600)
def load_price_data():
    try:
        url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRdAQmBHwDEWCgmLdEdJc0HsFYpPSyERPHLwmr2tnTYU1BDWdBD6I0ZYfEDzataX0wTNhfLfnm-Te6w/pub?gid=583402611&single=true&output=csv"
        df = pd.read_csv(url)
        if df.empty: return None
        return {c: df[c].dropna().tolist() for c in df.columns}
    except Exception:
        return None

@st.cache_data(ttl=600)
def load_product_translations():
    try:
        sheet_id = "1ue68TSJQQedKa7sVBB4syOc0OXJNaLS7p9vSnV52mKA"
        sheet_name = "SS26 Product_Name"
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={requests.utils.quote(sheet_name)}"
        return pd.read_csv(url)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def load_material_translations():
    try:
        url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRdAQmBHwDEWCgmLdEdJc0HsFYpPSyERPHLwmr2tnTYU1BDWdBD6I0ZYfEDzataX0wTNhfLfnm-Te6w/pub?gid=1096440227&single=true&output=csv"
        df = pd.read_csv(url)
        if df.empty: raise ValueError("empty")
        rows = []
        for _, r in df.iterrows():
            name = r.get('Name', r.iloc[0])
            if pd.isna(name): continue
            for lang in ['AL','MK']:
                rows.append({'material': name, 'language': lang, 'translation': r.get(lang,"") or ""})
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame([{'material':'Cotton','language':'AL','translation':'Cotton'},
                             {'material':'Cotton','language':'MK','translation':'Cotton'}])

# ==================== HELPERS ====================
def format_number(value, currency):
    try:
        value = float(str(value).replace(',', '.'))
        s = f"{value:,.2f}".replace(".", ",")
        if currency in ['EUR','BGN','BAM','RON','PLN']:
            a = s.split(','); a[0] = a[0].replace('.',''); s = ','.join(a)
        return s
    except Exception:
        return str(value)

def find_closest_price(pln_value):
    price_data = load_price_data()
    if not price_data or 'PLN' not in price_data: return None
    try:
        pln_value = float(pln_value)
        ladder = price_data['PLN']
        if pln_value not in ladder: return None
        idx = ladder.index(pln_value)
        return {cur: format_number(vals[idx], cur) for cur, vals in price_data.items() if cur != 'PLN'}
    except Exception:
        return None

def get_classification_type(item_class):
    if not item_class: return None
    ic = item_class.lower()
    if 'baby boys outerwear' in ic: return 'b'
    if 'baby girls outerwear' in ic: return 'a'
    if 'baby boys essentials' in ic: return 'd'
    if 'baby girls essentials' in ic: return 'd_girls'
    if any(k in ic for k in ['younger','older','boys','girls']): return 'yg'
    if 'ladies outerwear' in ic: return 'a'
    if 'mens outerwear' in ic: return 'b'
    return None

def map_item_class_to_dept_label(item_class):
    if not item_class: return None
    ic = item_class.lower()
    if 'baby boys' in ic: return "Baby Boy"
    if 'baby girls' in ic: return "Baby Girl"
    if 'older boys' in ic or 'younger boys' in ic: return "Boys"
    if 'older girls' in ic or 'younger girls' in ic: return "Girls"
    if 'ladies' in ic: return "Women"
    if 'mens' in ic: return "Men"
    return None

def get_dept_value(item_class):
    ic = item_class.lower() if item_class else ""
    if 'baby ' in ic: return "BABY"
    if 'younger' in ic: return "KIDS"
    if 'older' in ic: return "TEENS"
    if 'ladies' in ic: return "WOMEN"
    if 'mens' in ic: return "MEN"
    return ""

def modify_collection(collection, item_class):
    if not item_class: return collection
    ic = item_class.lower()
    if 'boys' in ic: return f"{collection} B"
    if 'girls' in ic: return f"{collection} G"
    return collection

# ==================== COLOUR DETECTION ====================
def extract_colour_from_page2(text, page_number=1):
    try:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        skip_keywords = ["PURCHASE","COLOUR","TOTAL","PANTONE","SUPPLIER","PRICE",
                         "ORDERED","SIZES","TPG","TPX","USD","NIP","PEPCO","Poland","Poznań"]
        skip_sizes = ["XS","S","M","L","XL","XXL","3XL","4XL","5XL","XXXL","1XL","2XL","2X","3X","4X"]
        filtered = []

        for ln in lines:
            t = ln.strip().upper()
            if any(k.lower() in t.lower() for k in skip_keywords): continue
            if re.match(r"^\s*\d+\s*$", t): continue
            if re.match(r"^[\d\s,./-]+$", t): continue
            if t in skip_sizes or re.match(r"^\d*\s*[XSML]{1,3}X?L?$", t): continue
            filtered.append(ln)

        if filtered:
            colour = re.sub(r'[\d\.\)\(]+','', filtered[0]).strip().upper()
            if "MANUAL" in colour:
                return st.text_input(f"Enter Colour (Page {page_number})", key=f"colour_manual_{page_number}").upper()
            return colour or "UNKNOWN"

        st.warning(f"⚠️ Page {page_number}: Colour info not found.")
        return st.text_input(f"Enter Colour (Page {page_number}):", key=f"colour_missing_{page_number}").upper() or "UNKNOWN"

    except Exception as e:
        st.error(f"Colour extraction error: {e}")
        return "UNKNOWN"

# ==================== PRICE DETECTION ====================
def _extract_pl_price(text: str):
    try:
        text = text.replace('\xa0',' ').replace('\u202f',' ')
        text = re.sub(r'\s+',' ',text)
        m_table = re.search(r'Country\s+Item\s+name\s+Sales\s+price(.*?)PRODUCT\s+CHARACTERISTIC', text, re.I | re.S)
        if not m_table:
            m_table = re.search(r'\bPL[^\n\r]{0,300}', text, re.I | re.S)
            block = m_table.group(0) if m_table else ""
        else:
            block = m_table.group(1) if m_table.lastindex else m_table.group(0)
        m_price = re.search(r'\bPL\b[^0-9]{0,40}?(\d{1,4}(?:[.,]\d{2}))', block, re.I)
        return m_price.group(1).replace(',', '.') if m_price else None
    except Exception as e:
        st.error(f"Price extraction error: {e}")
        return None

# ==================== PDF EXTRACTOR ====================
def extract_data_from_pdf(file):
    try:
        doc = fitz.open(stream=file.read(), filetype="pdf")
        if len(doc) < 2: 
            st.error("PDF must have at least 2 pages.")
            return None

        page1 = doc[0].get_text()
        safe = lambda m,g=1,d="UNKNOWN": m.group(g).strip() if m else d

        order_id = re.search(r"Order\s*-\s*ID\s*\.{2,}\s*([A-Z0-9_+-]+)", page1)
        season = re.search(r"Season\s*\.{2,}\s*(\w+)?\s*(\d{2})", page1)
        style = re.search(r"\b\d{6}\b", page1)
        item_class = re.search(r"Item classification\s*\.{2,}\s*(.+)", page1)
        supplier_code = re.search(r"Supplier product code\s*\.{2,}\s*(.+)", page1)
        supplier_name = re.search(r"Supplier name\s*\.{2,}\s*(.+)", page1)
        collection = re.search(r"Collection\s*\.{2,}\s*(.+)", page1)
        season_value = f"{safe(season,1,'')}{safe(season,2,'')}".strip() or "UNKNOWN"

        date_m = re.search(r"Handover\s*date\s*\.{2,}\s*(\d{2}/\d{2}/\d{4})", page1)
        batch = "UNKNOWN"
        if date_m:
            try:
                batch = (datetime.strptime(date_m.group(1), "%d/%m/%Y") - timedelta(days=20)).strftime("%m%Y")
            except: pass

        page2_text = doc[1].get_text()
        colour = extract_colour_from_page2(page2_text, page_number=2)
        page3 = doc[2].get_text() if len(doc)>2 else ""
        page4 = doc[3].get_text() if len(doc)>3 else ""
        auto_pln_price = _extract_pl_price(page3) or _extract_pl_price(page4)

        combined = page3 + page4
        skus = re.findall(r"\b\d{8}\b", combined)
        barcodes = re.findall(r"\b\d{13}\b", combined)

        return {"data": [{
            "Order_ID": safe(order_id),
            "Style": safe(style,0),
            "Colour": colour,
            "Supplier_product_code": safe(supplier_code),
            "Item_classification": safe(item_class),
            "Supplier_name": safe(supplier_name),
            "today_date": datetime.today().strftime('%d-%m-%Y'),
            "Collection": safe(collection),
            "Batch": batch,
            "Season": season_value,
            "SKU": skus[0] if skus else "",
            "barcode": barcodes[0] if barcodes else ""
        }],
        "pln_price": auto_pln_price}

    except Exception as e:
        st.error(f"PDF error: {e}")
        st.text(traceback.format_exc())
        return None

# ==================== UI LOGIC ====================
def pepco_section():
    st.subheader("PEPCO Data Processing")

    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0

    def reset():
        for k in list(st.session_state.keys()):
            if k.startswith(("ui_", "mat_", "pepco_", "colour_")):
                st.session_state.pop(k, None)
        st.session_state.uploader_key += 1
        st.rerun()

    st.button("🔄 New upload", on_click=reset)

    uploaded = st.file_uploader(
        "Upload PEPCO Data file(s)",
        type=["pdf"],
        key=f"pepco_uploader_{st.session_state.uploader_key}",
        accept_multiple_files=True
    )

    # ------------------ Combined PDF Processing ------------------
    if uploaded:
        combined_rows = []
        all_errors = []

        progress = st.progress(0)
        for idx, pdf in enumerate(uploaded, start=1):
            try:
                data_obj = extract_data_from_pdf(pdf)
                if not data_obj:
                    continue

                df = pd.DataFrame(data_obj["data"])
                auto_pln = data_obj.get("pln_price") or ""

                # Add detected PLN to dataframe
                df["Detected_PLN"] = auto_pln

                combined_rows.append(df)

            except Exception as e:
                all_errors.append(f"{pdf.name}: {e}")

            progress.progress(idx / len(uploaded))

        progress.empty()

        # ------------------ Combined Output ------------------
        if combined_rows:
            full_df = pd.concat(combined_rows, ignore_index=True)

            st.success(f"✅ Successfully processed {len(combined_rows)} PDF file(s).")
            st.dataframe(full_df, use_container_width=True)

            # CSV Export
            csv_buf = StringIO()
            full_df.to_csv(csv_buf, index=False)
            csv_data = csv_buf.getvalue().encode('utf-8-sig')

            today = datetime.today().strftime("%Y%m%d")
            st.download_button(
                label="📥 Download Combined CSV",
                data=csv_data,
                file_name=f"PEPCO_Combined_{today}.csv",
                mime="text/csv"
            )
        else:
            st.error("❌ No valid PDF data found.")

        if all_errors:
            st.warning("⚠️ Some files had issues:")
            for err in all_errors:
                st.text(f"• {err}")

# ==================== MAIN ====================
def main():
    st.markdown(THEME_CSS, unsafe_allow_html=True)
    try:
        st.image("https://raw.githubusercontent.com/ovi-ab888/PEPCO_SS26_updated/main/logo.svg", width=260)
    except:
        st.write("🧾 PEPCO Automation App")

    st.title("🧾 PEPCO Automation App")
    if not check_password(): st.stop()
    pepco_section()
    st.markdown("---")
    st.caption("Built with ❤️ by Ovi")

if __name__ == "__main__":
    main()

