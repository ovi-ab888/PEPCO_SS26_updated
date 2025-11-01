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

# ==================== THEME (compact) ====================
THEME_CSS = """
<style>
.block-container{max-width:1120px;padding-top:1rem;padding-bottom:3rem}
section[data-testid="stFileUploader"],div[data-testid="stDataFrameContainer"],div[data-testid="stVerticalBlock"]:has(> div[data-testid="stDataEditor"]){
  background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.12);border-radius:14px;padding:12px 14px}
label{font-weight:600}
</style>
"""

# ==================== Password gate (optional) ====================
def check_password():
    """Set st.secrets['app_password'] or env PEPCO_APP_PASSWORD to enable; else skip."""
    expected = None
    try:
        expected = st.secrets.get("app_password", None)
    except Exception:
        expected = None
    if expected is None:
        expected = os.environ.get("PEPCO_APP_PASSWORD")

    # If no password configured, allow straight-through.
    if expected is None:
        return True

    def _password_entered():
        st.session_state["password_ok"] = (st.session_state.get("password") == expected)
        try: del st.session_state["password"]
        except Exception: pass

    if st.session_state.get("password_ok"):
        return True

    st.text_input("Password", type="password", key="password", on_change=_password_entered)
    if st.session_state.get("password_ok") is False:
        st.error("Wrong password.")
    return False

# ==================== Constants / Mappings ====================
WASHING_CODES = {
    '1':'১২৩৪৫','2':'১৪৭৮৫','3':'djnst','4':'djnpt','5':'djnqt',
    '6':'djnqt','7':'gjnpt','8':'gjnpu','9':'gjnqt','10':'gjnqu',
    '11':'ijnst','12':'ijnsu','13':'ijnpu','14':'ijnsv','15':'djnsw'
}

COLLECTION_MAPPING = {
    'b': {'CROCO CLUB':'MODERN 1','LITTLE SAILOR':'MODERN 2','EXPLORE THE WORLD':'MODERN 3',
          'JURASIC ADVENTURE':'MODERN 4','WESTERN SPIRIT':'CLASSIC 1','SUMMER FUN':'CLASSIC 2'},
    'a': {'Rainbow Girl':'MODERN 1','NEONS PICNIC':'MODERN 2','COUNTRY SIDE':'ROMANTIC 2','ESTER GARDENG':'ROMANTIC 3'},
    'd': {'LITTLE TREASURE':'MODERN 1','DINO FRIENDS':'CLASSIC 1','EXOTIC ANIMALS':'CLASSIC 2'},
    'd_girls': {'SWEEET PASTELS':'MODERN 1','PORCELAIN':'ROMANTIC 2','SUMMER VIBE':'ROMANTIC 3'},
    'yg': {'CUTE_JUMP':'COLLECTION_1','SWEET_HEART':'COLLECTION_2','DAISY':'COLLECTION_3',
           'SPECIAL OCC':'COLLECTION_4','LILALOV':'COLLECTION_5','COOL GIRL':'COLLECTION_6','DEL MAR':'COLLECTION_7'}
}

# ==================== Data Loaders ====================
@st.cache_data(ttl=600)
def load_price_data():
    try:
        url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRdAQmBHwDEWCgmLdEdJc0HsFYpPSyERPHLwmr2tnTYU1BDWdBD6I0ZYfEDzataX0wTNhfLfnm-Te6w/pub?gid=583402611&single=true&output=csv"
        df = pd.read_csv(url)
        if df.empty: return None
        price = {c: df[c].dropna().tolist() for c in df.columns}
        return price
    except Exception:
        return None

@st.cache_data(ttl=600)
def load_product_translations():
    try:
        sheet_id = "1ue68TSJQQedKa7sVBB4syOc0OXJNaLS7p9vSnV52mKA"
        sheet_name = "SS26 Product_Name"
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={requests.utils.quote(sheet_name)}"
        df = pd.read_csv(url)
        return df if not df.empty else pd.DataFrame()
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
                rows.append({'material':name,'language':lang,'translation':r.get(lang,"") if pd.notna(r.get(lang,"")) else ""})
        return pd.DataFrame(rows) if rows else pd.DataFrame([{'material':'Cotton','language':'AL','translation':'Cotton'},{'material':'Cotton','language':'MK','translation':'Cotton'}])
    except Exception:
        return pd.DataFrame([{'material':'Cotton','language':'AL','translation':'Cotton'},
                             {'material':'Cotton','language':'MK','translation':'Cotton'}])

# ==================== Helpers ====================
def format_number(value, currency):
    try:
        if isinstance(value, str): value = float(value.replace(',', '.'))
        if currency in ['EUR','BGN','BAM','RON','PLN']:
            s = f"{float(value):,.2f}".replace(".", ",")
            if ',' in s:
                a = s.split(','); a[0] = a[0].replace('.',''); s = ','.join(a)
            return s
        return str(int(float(value)))
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
    if not item_class: return ""
    ic = item_class.lower()
    if 'baby ' in ic: return "BABY"
    if 'younger' in ic: return "KIDS"
    if 'older' in ic: return "TEENS"
    if 'ladies' in ic: return "WOMEN"
    if 'mens' in ic: return "MEN"
    return ""

def modify_collection(collection, item_class):
    if not item_class: return collection
    ic = item_class.lower()
    if any(x in ic for x in ['boys']): return f"{collection} B"
    if any(x in ic for x in ['girls']): return f"{collection} G"
    return collection

def extract_colour_from_page2(text, page_number=1):
    try:
        # Split and clean all lines
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        # Skip words that are never colour names
        skip_keywords = [
            "PURCHASE", "COLOUR", "TOTAL", "PANTONE", "SUPPLIER", "PRICE",
            "ORDERED", "SIZES", "TPG", "TPX", "USD", "NIP", "PEPCO",
            "Poland", "Poznań"
        ]

        # Skip common size names (expanded)
        skip_sizes = [
            "XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL", "5XL",
            "XXXL", "1XL", "2XL", "2X", "3X", "4X"
        ]

        filtered = []
        for ln in lines:
            line_clean = ln.strip().upper()

            # Skip lines with unwanted keywords
            if any(k.lower() in ln.lower() for k in skip_keywords):
                continue

            # Skip if only digits (1, 2, 3, etc.)
            if re.match(r"^\s*\d+\s*$", line_clean):
                continue

            # Skip purely numeric or symbol-based lines
            if re.match(r"^[\d\s,./-]+$", line_clean):
                continue

            # Skip known size indicators (XS, XL, 3XL, etc.)
            if line_clean in skip_sizes:
                continue

            # Skip patterns like "3 XL", "2XL", "4X"
            if re.match(r"^\d*\s*[XSML]{1,3}X?L?$", line_clean):
                continue

            filtered.append(ln)

        if filtered:
            colour = re.sub(r'[\d\.\)\(]+', '', filtered[0]).strip().upper()
            if "MANUAL" in colour:
                manual = st.text_input(f"Enter Colour (Page {page_number})", key=f"colour_manual_{page_number}")
                return (manual or "UNKNOWN").upper()
            return colour or "UNKNOWN"

        # If no colour found, show input box
        st.warning(f"⚠️ Page {page_number}: Colour information not found in PDF")
        manual = st.text_input(f"Enter Colour (Page {page_number}):", key=f"colour_missing_{page_number}")
        return (manual or "UNKNOWN").upper()

    except Exception as e:
        st.error(f"Colour extraction error: {e}")
        return "UNKNOWN"


# ==================== PRICE DETECTION (Robust) ====================
def _extract_pl_price(text: str):
    """
    Robust PLN price extractor for PEPCO OrderSupp PDFs.
    Works even if table cells break lines or spacing is weird.
    """
    text = text.replace('\xa0', ' ').replace('\u202f', ' ')
    text = re.sub(r'\s+', ' ', text)

    # 1) Try to isolate the table block
    m_table = re.search(r'Country\s+Item\s+name\s+Sales\s+price(.*?)PRODUCT\s+CHARACTERISTIC', text, re.I | re.S)
    if not m_table:
        # Fallback: small window around 'PL'
        m_table = re.search(r'PL[^\n\r]{0,300}', text, re.I | re.S)
    if not m_table:
        return None

    block = m_table.group(1)
    # 2) Find the first price number after 'PL'
    m_price = re.search(r'\bPL\b[^0-9]{0,40}?(\d{1,4}(?:[.,]\d{2}))', block, re.I)
    if m_price:
        return m_price.group(1).replace(',', '.')
    return None

# ==================== Core PDF Extractor ====================
def extract_data_from_pdf(file):
    """
    Extracts all required data from PEPCO OrderSupp PDF.
    Handles all regex safely and prevents 'no such group' errors.
    """
    try:
        import fitz
        import re
        from datetime import datetime, timedelta

        # --- helper: safe group extraction ---
        def safe_get(match, group=1, default="UNKNOWN"):
            try:
                if match:
                    return match.group(group).strip()
                return default
            except Exception:
                return default

        # --- open PDF ---
        doc = fitz.open(stream=file.read(), filetype="pdf")
        if len(doc) < 2:
            st.error("PDF must have at least 2 pages.")
            return None

        # --- PAGE 1 text ---
        page1 = doc[0].get_text()

        order_id = re.search(r"Order\s*-\s*ID\s*\.{2,}\s*([A-Z0-9_+-]+)", page1)
        season = re.search(r"Season\s*\.{2,}\s*(\w+)?\s*(\d{2})", page1)
        style = re.search(r"\b\d{6}\b", page1)
        item_class = re.search(r"Item classification\s*\.{2,}\s*(.+)", page1)
        supplier_code = re.search(r"Supplier product code\s*\.{2,}\s*(.+)", page1)
        supplier_name = re.search(r"Supplier name\s*\.{2,}\s*(.+)", page1)
        collection = re.search(r"Collection\s*\.{2,}\s*(.+)", page1)

        # --- Season safe extraction ---
        try:
            if season:
                part1 = season.group(1) if season.lastindex and season.lastindex >= 1 else ""
                part2 = season.group(2) if season.lastindex and season.lastindex >= 2 else ""
                season_value = f"{(part1 or '')}{(part2 or '')}".strip() or "UNKNOWN"
            else:
                season_value = "UNKNOWN"
        except Exception:
            season_value = "UNKNOWN"

        # --- Date → Batch (optional) ---
        date_m = re.search(r"Handover\s*date\s*\.{2,}\s*(\d{2}/\d{2}/\d{4})", page1)
        batch = "UNKNOWN"
        if date_m:
            try:
                batch = (datetime.strptime(date_m.group(1), "%d/%m/%Y") - timedelta(days=20)).strftime("%m%Y")
            except Exception:
                pass

        # --- PAGE 2 Colour extraction ---
        page2_text = doc[1].get_text()
        colour = extract_colour_from_page2(page2_text, page_number=2)

        # --- PAGE 3 & 4 for PLN price ---
        page3 = doc[2].get_text() if len(doc) > 2 else ""
        page4 = doc[3].get_text() if len(doc) > 3 else ""

        # --- Auto PLN price detection ---
        auto_pln_price = _extract_pl_price(page3) or _extract_pl_price(page4)

        # --- Extract SKUs & Barcodes ---
        skus = re.findall(r"\b\d{8}\b", page3 + page4)
        barcodes = re.findall(r"\b\d{13}\b", page3 + page4)

        # --- safe field extraction ---
        order_id_value = safe_get(order_id)
        style_value = safe_get(style, 0)
        item_class_value = safe_get(item_class)
        supplier_code_value = safe_get(supplier_code)
        supplier_name_value = safe_get(supplier_name)
        collection_value = safe_get(collection)

        # --- Final structured result ---
        result = [{
            "Order_ID": order_id_value,
            "Style": style_value,
            "Colour": colour,
            "Supplier_product_code": supplier_code_value,
            "Item_classification": item_class_value,
            "Supplier_name": supplier_name_value,
            "today_date": datetime.today().strftime('%d-%m-%Y'),
            "Collection": collection_value,
            "Batch": batch,
            "Season": season_value,
            "SKU": skus[0] if skus else "",
            "barcode": barcodes[0] if barcodes else ""
        }]

        return {"data": result, "pln_price": auto_pln_price}

    except Exception as e:
        st.error(f"PDF error: {e}")
        return None



# ==================== Product name formatter ====================
def format_product_translations(product_name, translation_row,
                                selected_materials=None, material_translations=None,
                                material_compositions=None):
    formatted = []
    country_suffixes = {'BiH':" Sastav materijala na ušivenoj etiketi.", 'RS':" Sastav materijala nalazi se na ušivenoj etiketi."}
    en_text = str(translation_row.get('EN')) if pd.notna(translation_row.get('EN')) else product_name
    formatted.append(f"|EN| {en_text}")

    combined = {'ES': f"{translation_row.get('ES')} / {translation_row.get('ES_CA')}" if pd.notna(translation_row.get('ES_CA')) else translation_row.get('ES')}
    order = ['AL','BG','BiH','CZ','DE','EE','ES','GR','HR','HU','IT','LT','LV','MK','PL','PT','RO','RS','SI','SK']

    for lang in order:
        if lang in combined and combined[lang] is not None:
            text = combined[lang]
        elif pd.notna(translation_row.get(lang)):
            text = translation_row.get(lang)
        else:
            text = product_name

        if selected_materials and material_translations and lang in ['AL','MK']:
            comp = (material_compositions or {}).get(lang, "")
            names = material_translations.get(lang, "")
            if comp: text = f"{text}: {comp}"
            elif names: text = f"{text}: {names}"

        if lang in country_suffixes:
            if not text.endswith('.'): text += "."
            text += country_suffixes[lang]

        formatted.append(f"|{lang}| {text}")

    return " ".join(s for s in formatted if s)

# ==================== Main workflow (FULL) ====================
def process_pepco_pdf(uploaded_pdf, extra_order_ids: str | None = None):
    translations_df = load_product_translations()
    material_translations_df = load_material_translations()
    if not (uploaded_pdf and not translations_df.empty):
        return

    data_obj = extract_data_from_pdf(uploaded_pdf)
    if not data_obj: return

    result_data = data_obj["data"]
    auto_pln = data_obj.get("pln_price")  # <-- AUTO PLN from PL row

    df = pd.DataFrame(result_data)
    first_row = result_data[0] if result_data else {}
    pdf_item_class = first_row.get("Item_classification", "")
    pdf_item_name_en = (first_row.get("Item_name_EN") or "").strip()

    if extra_order_ids:
        try: df['Order_ID'] = df['Order_ID'].astype(str) + "+" + extra_order_ids
        except Exception: pass

    c1,c2,c3,c4 = st.columns(4)
    depts = translations_df['DEPARTMENT'].dropna().unique().tolist()

    default_dept_label = map_item_class_to_dept_label(pdf_item_class)
    default_dept_index = next((i for i,d in enumerate(depts) if str(d).strip().lower()==str(default_dept_label or "").strip().lower()), 0)

    with c1:
        selected_dept = st.selectbox("Select Department", depts, index=default_dept_index, key="ui_dept")

    filtered = translations_df[translations_df['DEPARTMENT']==selected_dept]
    products = filtered['PRODUCT_NAME'].dropna().unique().tolist()
    default_product_index = next((i for i,p in enumerate(products) if str(p).strip().lower()==pdf_item_name_en.lower()), 0)

    with c2:
        product_type = st.selectbox("Select Product Type", products, index=default_product_index, key="ui_product")

    washing_options = list(WASHING_CODES.keys())
    with c3:
        washing_code_key = st.selectbox("Select Washing Code", washing_options, index=washing_options.index('9') if '9' in washing_options else 0, key="ui_wash")

    # ✅ Auto-fill PLN price
    with c4:
        pln_price_raw = st.text_input("Enter PLN Price", value=(auto_pln or ""), key="ui_pln_price")

    # ----- Parse PLN Price & Currency ladder -----
    pln_price = None
    if pln_price_raw.strip():
        try:
            pln_price = float(pln_price_raw.replace(",", "."))
            if pln_price < 0: st.error("❌ Price can't be negative."); pln_price=None
        except ValueError:
            st.error("❌ Please enter a valid number like 12.50 or 12,50")

    # ----- Materials UI -----
    st.markdown("### Material Composition (%)")
    if "mat_rows" not in st.session_state: st.session_state.mat_rows = 1
    if "mat_data" not in st.session_state: st.session_state.mat_data = [{"mat":"Cotton","pct":100}]

    materials_list = material_translations_df['material'].dropna().unique().tolist() if not material_translations_df.empty else ["Cotton"]
    if "Cotton" not in materials_list: materials_list = ["Cotton"] + materials_list

    def _ensure_row(i):
        while i >= len(st.session_state.mat_data):
            st.session_state.mat_data.append({"mat":None,"pct":0})

    for i in range(st.session_state.mat_rows):
        _ensure_row(i)
        prev_total = sum(r["pct"] for r in st.session_state.mat_data[:i] if r["pct"])
        remain = max(0, 100 - prev_total)
        a,b = st.columns([3,1.3])
        with a:
            cur = st.session_state.mat_data[i]["mat"]
            opts = ["—"] + materials_list
            idx = opts.index(cur) if cur in opts else 0
            st.session_state.mat_data[i]["mat"] = st.selectbox("Select Material(s)" if i==0 else f"Select Material(s) #{i+1}", opts, index=idx, key=f"mat_sel_{i}")
        with b:
            cur_pct = st.session_state.mat_data[i]["pct"]
            default_pct = 100 if (i==0 and (cur_pct in (None,0)) and st.session_state.mat_data[i]["mat"]=="Cotton") else min(cur_pct or 0, remain)
            if i==0 and st.session_state.mat_data[i]["mat"]=="Cotton" and (cur_pct in (None,0)):
                default_pct = 100; st.session_state.mat_data[i]["pct"]=100
            st.session_state.mat_data[i]["pct"] = st.number_input("Composition (%)" if i==0 else f"Composition (%) #{i+1}", min_value=0, max_value=remain, step=1, value=default_pct, key=f"mat_pct_{i}")

    valid = [r for r in st.session_state.mat_data[:st.session_state.mat_rows] if r["mat"] not in (None,"—") and r["pct"]>0]
    total_pct = sum(r["pct"] for r in valid)
    st.write(f"**Total: {total_pct}%**")
    if total_pct < 100 and st.session_state.mat_rows < 5:
        last = st.session_state.mat_data[st.session_state.mat_rows-1]
        if last["mat"] not in (None,"—") and last["pct"]>0:
            st.session_state.mat_rows += 1
            st.rerun()
    if total_pct >= 100 and st.session_state.mat_rows > len(valid):
        st.session_state.mat_rows = len(valid)

    selected_materials = [r["mat"] for r in valid]
    cotton_value = "Y" if len(valid)==1 and (valid[0]["mat"] or "").lower()=="cotton" and int(valid[0]["pct"])==100 else ""

    # ----- Material translations -----
    material_trans_dict, material_compositions = {}, {}
    if selected_materials and not material_translations_df.empty:
        for lang in ['AL','MK']:
            names, comp = [], []
            for r in valid:
                t = material_translations_df[(material_translations_df['material']==r['mat']) & (material_translations_df['language']==lang)]
                if not t.empty:
                    tr = t['translation'].iloc[0]
                    names.append(tr); comp.append(f"{r['pct']}% {tr}")
            if names: material_trans_dict[lang] = ", ".join(names)
            if comp:  material_compositions[lang] = ", ".join(comp)

    # ----- Build final DF columns -----
    df['Dept'] = df['Item_classification'].apply(get_dept_value)
    if cotton_value=="Y": df['Cotton'] = "Y"
    else:
        if 'Cotton' in df.columns: df = df.drop(columns=['Cotton'])

    df['Collection'] = df.apply(lambda r: modify_collection(r['Collection'], r['Item_classification']), axis=1)

    product_row = filtered[filtered['PRODUCT_NAME']==product_type]
    if not product_row.empty:
        df['product_name'] = format_product_translations(product_type, product_row.iloc[0], selected_materials, material_trans_dict, material_compositions)
    else:
        df['product_name'] = ""

    df['washing_code'] = WASHING_CODES[washing_code_key]

    # ----- Price ladder + CSV Export -----
    if pln_price is not None:
        currency_values = find_closest_price(pln_price)
        if currency_values:
            for cur in ['EUR','BGN','BAM','RON','CZK','MKD','RSD','HUF']:
                df[cur] = currency_values.get(cur, "")
            df['PLN'] = format_number(pln_price, 'PLN')

            final_cols = [
                "Order_ID","Style","Colour","Supplier_product_code","Item_classification",
                "Supplier_name","today_date","Collection","Colour_SKU","Style_Merch_Season",
                "Batch","barcode","washing_code","EUR","BGN","BAM","PLN","RON","CZK","MKD",
                "RSD","HUF","product_name","Dept","Season"
            ]
            if 'Cotton' in df.columns: final_cols.append("Cotton")
            for c in final_cols:
                if c not in df.columns: df[c] = ""

            st.success("✅ Data ready. Edit if needed, then download CSV.")
            edited_df = st.data_editor(df[final_cols], use_container_width=True)

            csv_buf = StringIO()
            w = pycsv.writer(csv_buf, delimiter=';', quoting=pycsv.QUOTE_ALL)
            w.writerow(final_cols)
            for row in edited_df.itertuples(index=False):
                w.writerow(row)

            first = df.iloc[0]
            season_val = (first.get("Season","UNKNOWN") or "UNKNOWN").upper()
            sku_val = "_".join(df['Colour_SKU'].apply(lambda x: re.sub(r".*SKU\s*","",str(x))).tolist()) or "UNKNOWN"
            supplier_code = first.get("Supplier_product_code","UNKNOWN")
            style_val = first.get("Style","UNKNOWN")
            file_name = f"PEPCO_{season_val}_{sku_val}_DATAFILE_{supplier_code}_00_{style_val}.csv"

            st.download_button("📥 Download CSV", csv_buf.getvalue().encode('utf-8-sig'), file_name=file_name, mime="text/csv")
        else:
            st.warning("⚠️ Valid PLN price not found in the price sheet. Please adjust.")
    else:
        st.info("ℹ️ Enter a PLN price to compute currency ladder & export.")

# ==================== Section (Uploader + Reset) ====================
def pepco_section():
    st.subheader("PEPCO Data Processing")

    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0

    col = st.columns([1,6])[0]
    with col:
        def _reset():
            for k in list(st.session_state.keys()):
                if k.startswith(("ui_","mat_","pepco_","colour_")):
                    st.session_state.pop(k, None)
            st.session_state.uploader_key += 1
            st.rerun()
        st.button("🔄 New upload", on_click=_reset)

    uploaded = st.file_uploader("Upload PEPCO Data file", type=["pdf"], key=f"pepco_uploader_{st.session_state.uploader_key}", accept_multiple_files=True)
    if uploaded:
        files = uploaded if isinstance(uploaded, list) else [uploaded]
        primary = files[0]
        others = files[1:]

        # collect extra order-ids from other PDFs
        other_ids = []
        for f in others:
            try:
                f.seek(0)
                with fitz.open(stream=f.read(), filetype="pdf") as d:
                    if len(d)>0:
                        t = d[0].get_text()
                        m = re.search(r"Order\s*-\s*ID\s*\.{2,}\s*([A-Z0-9_+-]+)", t)
                        if m: other_ids.append(m.group(1).strip())
            except Exception:
                pass
        concatenated_ids = "+".join(other_ids) if other_ids else ""
        process_pepco_pdf(primary, extra_order_ids=concatenated_ids)

# ==================== MAIN ====================
def main():
    st.markdown(THEME_CSS, unsafe_allow_html=True)

    # ✅ Safe logo load for Streamlit Cloud (using GitHub raw URL)
    try:
        logo_url = "https://raw.githubusercontent.com/ovi-ab888/PEPCO_SS26_updated/main/logo.svg"
        st.image(logo_url, width=280)
    except Exception as e:
        st.write("🧾 PEPCO Automation App")

    st.title("🧾 PEPCO Automation App")
    if not check_password():
        st.stop()
    pepco_section()
    st.markdown("---")
    st.caption("Built with ❤️ by Ovi")

if __name__ == "__main__":
    main()







