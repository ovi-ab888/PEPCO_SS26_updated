# ==================== PAGE CONFIG (MUST BE FIRST) ====================
import streamlit as st
st.set_page_config(page_title="PEPCO Data Processor", page_icon="🧾", layout="wide")

# ==================== Imports ====================
import pandas as pd
import re
from io import StringIO
import csv as pycsv
from datetime import datetime, timedelta
import os
import requests

# Try to use pdfplumber, fallback to pypdf
try:
    import pdfplumber
    PDF_BACKEND = "pdfplumber"
except ImportError:
    try:
        from pypdf import PdfReader
        PDF_BACKEND = "pypdf"
    except ImportError:
        st.error("❌ Please install pdfplumber or pypdf")
        st.stop()

# Local modules
try:
    from auth import check_password
    from theme import apply_theme, render_header
except ImportError:
    # Fallback if auth.py or theme.py are missing
    def check_password():
        return True
    
    def apply_theme():
        st.markdown("""
        <style>
        .main { padding: 2rem; }
        </style>
        """, unsafe_allow_html=True)
    
    def render_header():
        st.markdown("<h1 style='text-align: center;'>PEPCO Data Processor</h1>", unsafe_allow_html=True)

# ========== FALLBACK MAPPINGS ==========
WASHING_CODES = {
    '1': '১২৩৪৫', '2': '১৪৭৮৫', '3': 'djnst', '4': 'djnpt', '5': 'djnqt',
    '6': 'djnqt', '7': 'gjnpt', '8': 'gjnpu', '9': 'gjnqt', '10': 'gjnqu',
    '11': 'ijnst', '12': 'ijnsu', '13': 'ijnpu', '14': 'ijnsv', '15': 'djnsw'
}

COLLECTION_MAPPING = {
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

def read_pdf_text(uploaded_file):
    """Read PDF text using available backend"""
    pos = uploaded_file.tell()
    uploaded_file.seek(0)
    
    try:
        if PDF_BACKEND == "pdfplumber":
            with pdfplumber.open(uploaded_file) as pdf:
                text = "\n".join([p.extract_text() or "" for p in pdf.pages])
        else:
            from pypdf import PdfReader
            reader = PdfReader(uploaded_file)
            text = "\n".join([page.extract_text() or "" for page in reader.pages])
    except Exception as e:
        st.error(f"Error reading PDF: {str(e)}")
        text = ""
    
    uploaded_file.seek(pos)
    return text

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
    pos = file.tell()
    file.seek(0)
    try:
        if PDF_BACKEND == "pdfplumber":
            with pdfplumber.open(file) as pdf:
                if len(pdf.pages) < 1:
                    file.seek(pos)
                    return None
                page1_text = pdf.pages[0].extract_text() or ""
        else:
            from pypdf import PdfReader
            reader = PdfReader(file)
            if len(reader.pages) < 1:
                file.seek(pos)
                return None
            page1_text = reader.pages[0].extract_text() or ""
        
        m = re.search(r"Order\s*-\s*ID\s*\.{2,}\s*([A-Z0-9_+-]+)", page1_text, re.IGNORECASE)
        return m.group(1).strip() if m else None
    except Exception:
        return None
    finally:
        file.seek(pos)

def extract_data_from_pdf(file):
    try:
        # Read PDF text
        pdf_text = read_pdf_text(file)
        if not pdf_text:
            st.error("Could not read PDF content")
            return None
        
        # Extract data from text using regex
        order_id = re.search(r"Order\s*-\s*ID\s*\.{2,}\s*(.+)", pdf_text)
        merch_code = re.search(r"Merch\s*code\s*\.{2,}\s*([\w/]+)", pdf_text)
        season = re.search(r"Season\s*\.{2,}\s*(\w+)?\s*(\d{2})", pdf_text)
        style_code = re.search(r"\b\d{6}\b", pdf_text)
        collection = re.search(r"Collection\s*\.{2,}\s*(.+)", pdf_text)
        date_match = re.search(r"Handover\s*date\s*\.{2,}\s*(\d{2}/\d{2}/\d{4})", pdf_text)
        item_class = re.search(r"Item classification\s*\.{2,}\s*(.+)", pdf_text)
        supplier_code = re.search(r"Supplier product code\s*\.{2,}\s*(.+)", pdf_text)
        supplier_name = re.search(r"Supplier name\s*\.{2,}\s*(.+)", pdf_text)

        # Process extracted data
        style_suffix = ""
        if merch_code and season:
            style_suffix = f"{merch_code.group(1).strip()}{season.group(2)}"
        elif merch_code:
            style_suffix = merch_code.group(1).strip()

        batch = "UNKNOWN"
        if date_match:
            try:
                batch = (datetime.strptime(date_match.group(1), "%d/%m/%Y") - timedelta(days=20)).strftime("%m%Y")
            except Exception:
                pass

        item_class_value = item_class.group(1).strip() if item_class else "UNKNOWN"
        class_type = get_classification_type(item_class_value)
        collection_value = collection.group(1).split("-")[0].strip() if collection else "UNKNOWN"
        
        if class_type and class_type in COLLECTION_MAPPING:
            for orig_collection, new_collection in COLLECTION_MAPPING[class_type].items():
                if orig_collection.upper() in collection_value.upper():
                    collection_value = new_collection
                    break

        colour = extract_colour_from_page2(pdf_text)
        
        # Extract SKUs and barcodes
        skus = re.findall(r"\b\d{8}\b", pdf_text)
        all_barcodes = re.findall(r"\b\d{13}\b", pdf_text)
        excluded = set(re.findall(r"barcode:\s*(\d{13});", pdf_text))
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

# ==================== MAIN WORKFLOW ====================
def process_pepco_pdf(uploaded_pdf, extra_order_ids=None):
    st.info("PDF processing functionality would go here")
    st.write(f"File: {uploaded_pdf.name}")
    if extra_order_ids:
        st.write(f"Extra order IDs: {extra_order_ids}")

# ==================== MAIN ====================
def main():
    apply_theme()
    render_header()
    st.title("PEPCO Automation App")

    if not check_password():
        st.stop()

    st.subheader("PEPCO Data Processing")
    st.info("📁 Please upload PDF files to begin processing")

    uploaded_files = st.file_uploader("Upload PEPCO PDF files", type=["pdf"], accept_multiple_files=True)
    
    if uploaded_files:
        st.success(f"✅ Loaded {len(uploaded_files)} PDF file(s)")
        for file in uploaded_files:
            text = read_pdf_text(file)
            st.write(f"📄 {file.name} - {len(text)} characters read")
            
            # Simple display of PDF content
            with st.expander(f"View PDF content: {file.name}"):
                st.text_area("PDF Text", text[:1000] + "..." if len(text) > 1000 else text, height=200)

if __name__ == "__main__":
    main()
