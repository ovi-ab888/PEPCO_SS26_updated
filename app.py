# ==================== PAGE CONFIG (MUST BE FIRST) ====================
import streamlit as st
st.set_page_config(page_title="PEPCO Data Processor", page_icon="🧾", layout="wide")

# ==================== Imports ====================
# ---- Robust PDF backends ----
PDF_BACKEND = None

try:
    import fitz  # PyMuPDF import name
    PDF_BACKEND = "pymupdf"
except Exception:
    fitz = None
    try:
        import pdfplumber  # pure-Python, uses pdfminer.six
        PDF_BACKEND = "pdfplumber"
    except Exception:
        pdfplumber = None
        try:
            from pypdf import PdfReader  # pure-Python
            PDF_BACKEND = "pypdf"
        except Exception:
            PdfReader = None
            import streamlit as st
            st.error("No PDF backend available. Install one of: pymupdf, pdfplumber, pypdf.")
            st.stop()

import pandas as pd
import re
from io import StringIO
import csv as pycsv
from datetime import datetime, timedelta
import os
import requests

# Local modules
from auth import check_password                 # 🔐 access control (from auth.py)
from theme import apply_theme, render_header    # 🎨 global CSS + header (from theme.py)


# ========== FALLBACK MAPPINGS (used if config.py not provided) ==========
WASHING_CODES =  {
    '1': '১২৩৪৫', '2': '১৪৭৮৫', '3': 'djnst', '4': 'djnpt', '5': 'djnqt',
    '6': 'djnqt', '7': 'gjnpt', '8': 'gjnpu', '9': 'gjnqt', '10': 'gjnqu',
    '11': 'ijnst', '12': 'ijnsu', '13': 'ijnpu', '14': 'ijnsv', '15': 'djnsw'
}

COLLECTION_MAPPING =  {
    'b': {
        'CROCO CLUB': 'MODERN 1',
        'LITTLE SAILOR': 'MODERN 2',
        'EXPLORE THE WORLD': 'MODERN 3',
        'JURASIC ADVENTURE': 'MODERN 4',
        'WESTERN SPIRIT': 'CLASSIC 1',
        'SUMMER FUN': 'CLASSIC 2'
    },
    'a': {
        'Rainbow Girl': 'MODERN 1',
        'NEONS PICNIC': 'MODERN 2',
        'COUNTRY SIDE': 'ROMANTIC 2',
        'ESTER GARDENG': 'ROMANTIC 3'
    },
    'd': {
        'LITTLE TREASURE': 'MODERN 1',
        'DINO FRIENDS': 'CLASSIC 1',
        'EXOTIC ANIMALS': 'CLASSIC 2'
    },
    'd_girls': {
        'SWEEET PASTELS': 'MODERN 1',
        'PORCELAIN': 'ROMANTIC 2',
        'SUMMER VIBE': 'ROMANTIC 3'
    },
    'yg': {
        'CUTE_JUMP': 'COLLECTION_1',
        'SWEET_HEART': 'COLLECTION_2',
        'DAISY': 'COLLECTION_3',
        'SPECIAL OCC': 'COLLECTION_4',
        'LILALOV': 'COLLECTION_5',
        'COOL GIRL': 'COLLECTION_6',
        'DEL MAR': 'COLLECTION_7'
    }
}

# ==================== DATA LOADERS ====================
@st.cache_data(ttl=600)
def load_price_data():
    try:
        url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRdAQmBHwDEWCgmLdEdJc0HsFYpPSyERPHLwmr2tnTYU1BDWdBD6I0ZYfEDzataX0wTNhfLfnm-Te6w/pub?gid=583402611&single=true&output=csv"
        df = pd.read_csv(url)
        if df.empty:
            st.error("Price data sheet is empty")
            return None
        price_data = {}
        for currency in df.columns:
            price_data[currency] = df[currency].dropna().tolist()
        return price_data
    except Exception as e:
        st.error(f"Failed to load price data: {str(e)}")
        return None

@st.cache_data(ttl=600)
def load_product_translations():
    try:
        sheet_id = "1ue68TSJQQedKa7sVBB4syOc0OXJNaLS7p9vSnV52mKA"
        sheet_name = "SS26 Product_Name"
        encoded_sheet_name = requests.utils.quote(sheet_name)
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={encoded_sheet_name}"
        df = pd.read_csv(url)
        if df.empty:
            st.error("Loaded translations but sheet appears empty")
        return df
    except Exception as e:
        st.error(f"❌ Failed to load translations: {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=600)
def load_material_translations():
    try:
        url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRdAQmBHwDEWCgmLdEdJc0HsFYpPSyERPHLwmr2tnTYU1BDWdBD6I0ZYfEDzataX0wTNhfLfnm-Te6w/pub?gid=1096440227&single=true&output=csv"
        df = pd.read_csv(url)
        if df.empty:
            st.error("Material translations sheet is empty")
            return pd.DataFrame()
        material_translations = []
        for _, row in df.iterrows():
            for lang in ['AL', 'BG', 'MK', 'RS']:
                material_translations.append({
                    'material': row['Name'],
                    'language': lang,
                    'translation': row[lang]
                })
        return pd.DataFrame(material_translations)
    except Exception as e:
        st.error(f"Failed to load material translations: {str(e)}")
        return pd.DataFrame()

# ==================== HELPERS ====================
def format_number(value, currency):
    try:
        if isinstance(value, str):
            value = float(value.replace(',', '.'))
        if currency in ['EUR', 'BGN', 'BAM', 'RON', 'PLN']:
            formatted = f"{float(value):,.2f}".replace(".", ",")
            if ',' in formatted:
                parts = formatted.split(',')
                parts[0] = parts[0].replace('.', '')
                formatted = ','.join(parts)
            return formatted
        return str(int(float(value)))
    except (ValueError, TypeError):
        return str(value)

def find_closest_price(pln_value):
    try:
        price_data = load_price_data()
        if not price_data or 'PLN' not in price_data:
            st.error("❌ Price data not available")
            return None
        pln_value = float(pln_value)
        available_pln_values = price_data['PLN']
        if pln_value not in available_pln_values:
            st.error(f"❌ PLN {pln_value} not found in price sheet. Available PLN values: {sorted(available_pln_values)}")
            return None
        idx = available_pln_values.index(pln_value)
        return {
            currency: format_number(values[idx], currency)
            for currency, values in price_data.items()
            if currency != 'PLN'
        }
    except (ValueError, TypeError) as e:
        st.error(f"Invalid price value: {str(e)}")
        return None

def get_classification_type(item_class):
    if not item_class: return None
    ic = item_class.lower()
    if 'younger girls outerwear' in ic: return 'yg'
    if 'baby boys outerwear' in ic: return 'b'
    if 'baby girls outerwear' in ic: return 'a'
    if 'baby boys essentials' in ic: return 'd'
    if 'baby girls essentials' in ic: return 'd_girls'
    if 'younger boys outerwear' in ic: return 'yg'
    if 'older girls outerwear' in ic: return 'yg'
    if 'older boys outerwear' in ic: return 'yg'
    if 'ladies outerwear' in ic: return 'a'
    if 'mens outerwear' in ic: return 'b'
    return None

def get_dept_value(item_class):
    if not item_class: return ""
    ic = item_class.lower()
    if any(x in ic for x in ['baby boys outerwear','baby girls outerwear','baby boys essentials','baby girls essentials']): return "BABY"
    if any(x in ic for x in ['younger boys outerwear','younger girls outerwear']): return "KIDS"
    if any(x in ic for x in ['older girls outerwear','older boys outerwear']): return "TEENS"
    if 'ladies outerwear' in ic: return "WOMEN"
    if 'mens outerwear' in ic: return "MEN"
    return ""

def modify_collection(collection, item_class):
    if not item_class: return collection
    ic = item_class.lower()
    if any(x in ic for x in ['younger boys outerwear','older boys outerwear']): return f"{collection} B"
    if any(x in ic for x in ['older girls outerwear','younger girls outerwear']): return f"{collection} G"
    return collection

def extract_colour_from_page2(text, page_number=1):
    try:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        skip_keywords = [
            "PURCHASE", "COLOUR", "TOTAL", 'PANTONE', 'SUPPLIER', 'PRICE',
            'ORDERED', 'SIZES', 'TPG', 'TPX', 'USD', 'NIP', 'PEPCO',
            'Poland', 'ul. Strzeszyńska 73A, 60-479 Poznań', 'NIP 782-21-31-157'
        ]
        filtered = [
            line for line in lines
            if all(k.lower() not in line.lower() for k in skip_keywords)
            and not re.match(r"^[\d\s,./-]+$", line)
        ]
        colour = "UNKNOWN"
        if filtered:
            colour = filtered[0]
            colour = re.sub(r'[\d\.\)\(]+', '', colour).strip().upper()
            if "MANUAL" in colour:
                st.warning(f"⚠️ Page {page_number}: 'MANUAL' detected in colour field")
                manual = st.text_input(f"Enter Colour (Page {page_number}):", key=f"colour_manual_{page_number}")
                return manual.upper() if manual else "UNKNOWN"
            return colour if colour else "UNKNOWN"
        st.warning(f"⚠️ Page {page_number}: Colour information not found in PDF")
        manual = st.text_input(f"Enter Colour (Page {page_number}):", key=f"colour_missing_{page_number}")
        return manual.upper() if manual else "UNKNOWN"
    except Exception as e:
        st.error(f"Error extracting colour: {str(e)}")
        return "UNKNOWN"

def extract_order_id_only(file):
    pos = None
    try: pos = file.tell()
    except Exception: pass
    try: file.seek(0)
    except Exception: pass
    try:
        with fitz.open(stream=file.read(), filetype="pdf") as doc:
            if len(doc) < 1:
                try: file.seek(0 if pos is None else pos)
                except Exception: pass
                return None
            page1_text = doc[0].get_text()
    except Exception:
        try: file.seek(0 if pos is None else pos)
        except Exception: pass
        return None
    try: file.seek(0 if pos is None else pos)
    except Exception: pass
    m = re.search(r"Order\s*-\s*ID\s*\.{2,}\s*([A-Z0-9_+-]+)", page1_text, re.IGNORECASE)
    return m.group(1).strip() if m else None

def extract_data_from_pdf(file):
    try:
        doc = fitz.open(stream=file.read(), filetype="pdf")
        if len(doc) < 3:
            st.error("PDF must have at least 3 pages.")
            return None
        page1 = doc[0].get_text()

        merch_code = re.search(r"Merch\s*code\s*\.{2,}\s*([\w/]+)", page1)
        season = re.search(r"Season\s*\.{2,}\s*(\w+)?\s*(\d{2})", page1)
        style_code = re.search(r"\b\d{6}\b", page1)
        style_suffix = ""
        if merch_code and season:
            merch_value = merch_code.group(1).strip()
            season_digits = season.group(2)
            style_suffix = f"{merch_value}{season_digits}"
        elif merch_code:
            style_suffix = merch_code.group(1).strip()

        collection = re.search(r"Collection\s*\.{2,}\s*(.+)", page1)
        date_match = re.search(r"Handover\s*date\s*\.{2,}\s*(\d{2}/\d{2}/\d{4})", page1)
        batch = "UNKNOWN"
        if date_match:
            try:
                batch = (datetime.strptime(date_match.group(1), "%d/%m/%Y") - timedelta(days=20)).strftime("%m%Y")
            except Exception:
                pass

        order_id = re.search(r"Order\s*-\s*ID\s*\.{2,}\s*(.+)", page1)
        item_class = re.search(r"Item classification\s*\.{2,}\s*(.+)", page1)
        supplier_code = re.search(r"Supplier product code\s*\.{2,}\s*(.+)", page1)
        supplier_name = re.search(r"Supplier name\s*\.{2,}\s*(.+)", page1)

        item_class_value = item_class.group(1).strip() if item_class else "UNKNOWN"
        class_type = get_classification_type(item_class_value)
        collection_value = collection.group(1).split("-")[0].strip() if collection else "UNKNOWN"
        if class_type and class_type in COLLECTION_MAPPING:
            for orig_collection, new_collection in COLLECTION_MAPPING[class_type].items():
                if orig_collection.upper() in collection_value.upper():
                    collection_value = new_collection
                    break

        colour = extract_colour_from_page2(doc[1].get_text())
        page3 = doc[2].get_text()
        skus = re.findall(r"\b\d{8}\b", page3)
        all_barcodes = re.findall(r"\b\d{13}\b", page3)
        excluded = set(re.findall(r"barcode:\s*(\d{13});", page3))
        valid_barcodes = [b for b in all_barcodes if b not in excluded]

        result = [{
            "Order_ID": order_id.group(1).strip() if order_id else "UNKNOWN",
            "Style": style_code.group() if style_code else "UNKNOWN",
            "Colour": colour,
            "Supplier_product_code": supplier_code.group(1).strip() if supplier_code else "UNKNOWN",
            "Item_classification": item_class_value,
            "Supplier_name": supplier_name.group(1).strip() if supplier_name else "UNKNOWN",
            "today_date": datetime.today().strftime('%d-%m-%Y'),
            "Collection": collection_value,
            "Colour_SKU": f"{colour} • SKU {sku}",
            "Style_Merch_Season": f"STYLE {style_code.group()} • {style_suffix} • Batch No./" if style_code else "STYLE UNKNOWN",
            "Batch": f"Data e prodhimit: {batch}",
            "barcode": barcode
        } for sku, barcode in zip(skus, valid_barcodes)]

        return result
    except Exception as e:
        st.error(f"PDF error: {str(e)}")
        return None

def format_product_translations(product_name, translation_row,
                                selected_materials=None, material_translations=None,
                                material_compositions=None):
    formatted = []
    country_suffixes = {
        'BiH': " Sastav materijala na ušivenoj etiketi.",
        'RS': " Sastav materijala nalazi se na ušivenoj etiketi.",
    }
    en_text = str(translation_row['EN']) if pd.notna(translation_row.get('EN')) else product_name
    formatted.append(f"|EN| {en_text}")
    combined_languages = {
        'ES': f"{translation_row['ES']} / {translation_row['ES_CA']}"
              if pd.notna(translation_row.get('ES_CA'))
              else translation_row.get('ES')
    }
    language_order = [
        'AL', 'BG', 'BiH', 'CZ', 'DE', 'EE', 'ES',
        'GR', 'HR', 'HU', 'IT', 'LT', 'LV', 'MK',
        'PL', 'PT', 'RO', 'RS', 'SI', 'SK'
    ]
    for lang in language_order:
        if lang in combined_languages and combined_languages[lang] is not None:
            text = combined_languages[lang]
        elif pd.notna(translation_row.get(lang)):
            text = translation_row[lang]
        else:
            text = product_name

        if selected_materials and material_translations and lang in ['AL', 'BG', 'MK', 'RS']:
            material_text = material_translations.get(lang, "")
            if material_text:
                if material_compositions:
                    composition_text = material_compositions.get(lang, "")
                    if composition_text:
                        text = f"{text}: {composition_text}"
                else:
                    text = f"{text}: {material_text}"

        if lang in country_suffixes:
            if not text.endswith('.'):
                text += "."
            text += country_suffixes[lang]
        formatted.append(f"|{lang}| {text}")
    return " ".join([s for s in formatted if s])

# ==================== MAIN WORKFLOW ====================
def process_pepco_pdf(uploaded_pdf, extra_order_ids: str | None = None):
    # ---------- Load reference sheets ----------
    translations_df = load_product_translations()
    material_translations_df = load_material_translations()
    if not (uploaded_pdf and not translations_df.empty):
        return

    # ---------- Parse PDF ----------
    result_data = extract_data_from_pdf(uploaded_pdf)
    if not result_data:
        return
    df = pd.DataFrame(result_data)

    if extra_order_ids:
        try:
            df['Order_ID'] = df['Order_ID'].astype(str) + "+" + extra_order_ids
        except Exception:
            pass

    # ---------- Dept | Product | Washing | PLN ----------
    c1, c2, c3, c4 = st.columns(4)
    depts = translations_df['DEPARTMENT'].dropna().unique().tolist()
    with c1: selected_dept = st.selectbox("Select Department", options=depts, key="ui_dept")
    filtered = translations_df[translations_df['DEPARTMENT'] == selected_dept]
    products = filtered['PRODUCT_NAME'].dropna().unique().tolist()
    with c2: product_type = st.selectbox("Select Product Type", options=products, key="ui_product")
    with c3: washing_code_key = st.selectbox("Select Washing Code", options=list(WASHING_CODES.keys()), key="ui_wash")
    with c4: pln_price_raw = st.text_input("Enter PLN Price", key="ui_pln_price")

    pln_price = None
    if pln_price_raw.strip():
        try:
            pln_price = float(pln_price_raw.replace(",", "."))
            if pln_price < 0: st.error("❌ Price can't be negative."); pln_price = None
        except ValueError:
            st.error("❌ Please enter a valid number like 12.50 or 12,50"); pln_price = None

    # ---------- Material Composition (auto rows, no Add) ----------
    st.markdown("### Material Composition (%)")
    if "mat_rows" not in st.session_state: st.session_state.mat_rows = 1
    if "mat_data" not in st.session_state: st.session_state.mat_data = [{"mat": None, "pct": 0}]
    materials_list = material_translations_df['material'].dropna().unique().tolist() if not material_translations_df.empty else []

    def _ensure_row(i):
        while i >= len(st.session_state.mat_data):
            st.session_state.mat_data.append({"mat": None, "pct": 0})

    for i in range(st.session_state.mat_rows):
        _ensure_row(i)
        prev_total = sum(r["pct"] for r in st.session_state.mat_data[:i] if r["pct"])
        remain = max(0, 100 - prev_total)
        cA, cB = st.columns([3, 1.3])
        with cA:
            cur_mat = st.session_state.mat_data[i]["mat"]
            idx = (["—"] + materials_list).index(cur_mat) if (cur_mat in materials_list) else 0
            st.session_state.mat_data[i]["mat"] = st.selectbox(
                "Select Material(s)" if i == 0 else f"Select Material(s) #{i+1}",
                ["—"] + materials_list, index=idx, key=f"mat_sel_{i}"
            )
        with cB:
            cur_pct = st.session_state.mat_data[i]["pct"]
            default_pct = 100 if (i == 0 and not cur_pct) else min(cur_pct, remain)
            st.session_state.mat_data[i]["pct"] = st.number_input(
                "Composition (%)" if i == 0 else f"Composition (%) #{i+1}",
                min_value=0, max_value=remain, step=1, value=default_pct, key=f"mat_pct_{i}"
            )

    valid_rows = [r for r in st.session_state.mat_data[:st.session_state.mat_rows]
                  if r["mat"] not in (None, "—") and r["pct"] > 0]
    running_total = sum(r["pct"] for r in valid_rows)

    if running_total < 100 and st.session_state.mat_rows < 5:  # max 5 rows
        last = st.session_state.mat_data[st.session_state.mat_rows - 1]
        if last["mat"] not in (None, "—") and last["pct"] > 0:
            st.session_state.mat_rows += 1
            _ensure_row(st.session_state.mat_rows - 1)
            st.rerun()

    if running_total >= 100 and st.session_state.mat_rows > len(valid_rows):
        st.session_state.mat_rows = len(valid_rows)

    if st.session_state.mat_rows == 1 and valid_rows and valid_rows[0]["pct"] == 100:
        st.info("✅ 100% selected — আর নতুন material প্রয়োজন নেই.")
    elif running_total > 100:
        st.error("⚠️ Total exceeds 100%")
    st.write(f"**Total: {running_total}%**")

    # build outputs
    selected_materials = [r["mat"] for r in valid_rows]
    cotton_value = "Y" if (len(valid_rows) == 1 and valid_rows[0]["mat"] and valid_rows[0]["mat"].lower() == "cotton" and valid_rows[0]["pct"] == 100) else ""
    material_trans_dict, material_compositions = {}, {}
    if selected_materials and not material_translations_df.empty:
        for lang in ['AL','BG','MK','RS']:
            names, comp = [], []
            for r in valid_rows:
                t = material_translations_df[
                    (material_translations_df['material'] == r['mat']) &
                    (material_translations_df['language'] == lang)
                ]
                if not t.empty:
                    tr = t['translation'].iloc[0]
                    names.append(tr); comp.append(f"{r['pct']}% {tr}")
            if names: material_trans_dict[lang] = ", ".join(names)
            if comp: material_compositions[lang] = ", ".join(comp)

    # ---------- DataFrame enrich ----------
    df['Dept'] = df['Item_classification'].apply(get_dept_value)
    df['Cotton'] = cotton_value
    df['Collection'] = df.apply(lambda r: modify_collection(r['Collection'], r['Item_classification']), axis=1)
    product_row = filtered[filtered['PRODUCT_NAME'] == product_type]
    if not product_row.empty:
        df['product_name'] = format_product_translations(product_type, product_row.iloc[0], selected_materials, material_trans_dict, material_compositions)
    else:
        df['product_name'] = ""
    df['washing_code'] = WASHING_CODES[washing_code_key]

    # ---------- Price ladder + export ----------
    if pln_price is not None:
        currency_values = find_closest_price(pln_price)
        if currency_values:
            for cur in ['EUR','BGN','BAM','RON','CZK','MKD','RSD','HUF']:
                df[cur] = currency_values.get(cur, "")
            df['PLN'] = format_number(pln_price, 'PLN')

            final_cols = ["Order_ID","Style","Colour","Supplier_product_code","Item_classification",
                          "Supplier_name","today_date","Collection","Colour_SKU","Style_Merch_Season",
                          "Batch","barcode","washing_code","EUR","BGN","BAM","PLN","RON","CZK","MKD",
                          "RSD","HUF","product_name","Dept","Cotton"]

            st.success("✅ Done!")
            st.subheader("Edit Before Download")
            edited_df = st.data_editor(df[final_cols])

            csv_buffer = StringIO()
            writer = pycsv.writer(csv_buffer, delimiter=';', quoting=pycsv.QUOTE_ALL)
            writer.writerow(final_cols)
            for row in edited_df.itertuples(index=False): writer.writerow(row)

            st.download_button("📥 Download CSV", csv_buffer.getvalue().encode('utf-8-sig'),
                               file_name=f"{os.path.splitext(uploaded_pdf.name)[0]}.csv", mime="text/csv")
        else:
            st.warning("Processing stopped - valid PLN price not found")



# ==================== SECTION (with New upload/Reset) ====================
def pepco_section():
    st.subheader("PEPCO Data Processing")

    # one-time init for uploader key
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0

    # Reset/New upload button
    cols = st.columns([1, 6])
    with cols[0]:
        def _reset_all():
            # clear app state keys only
            for k in list(st.session_state.keys()):
                if k.startswith(("ui_", "mat_", "mix_", "pepco_", "colour_", "colour_manual_", "colour_missing_")):
                    st.session_state.pop(k, None)
            st.session_state.uploader_key += 1
            st.rerun()
        st.button("🔄 New upload", on_click=_reset_all)

    uploaded_pdfs = st.file_uploader(
        "Upload PEPCO Data file",
        type=["pdf"],
        key=f"pepco_uploader_{st.session_state.uploader_key}",
        accept_multiple_files=True
    )

    if uploaded_pdfs:
        if not isinstance(uploaded_pdfs, list):
            uploaded_pdfs = [uploaded_pdfs]
        primary_pdf = uploaded_pdfs[0]
        others = uploaded_pdfs[1:]

        # collect Order_ID from additional PDFs
        other_ids = []
        for f in others:
            try: f.seek(0)
            except Exception: pass
            oid = extract_order_id_only(f)
            if oid: other_ids.append(oid)
            try: f.seek(0)
            except Exception: pass

        concatenated_ids = "+".join(other_ids) if other_ids else ""
        process_pepco_pdf(primary_pdf, extra_order_ids=concatenated_ids)

# ==================== MAIN ====================
def main():
    apply_theme()
    render_header()
    st.title("PEPCO Automation App")

    if not check_password():
        st.stop()

    pepco_section()

    st.markdown("---")
    st.caption("This app developed by Ovi")

if __name__ == "__main__":
    main()




