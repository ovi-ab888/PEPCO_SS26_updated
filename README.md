# PEPCO SS26 – Data Processor (Streamlit)

A small Streamlit app to parse PEPCO PDFs, enrich with product/material translations,
map business rules (collections, washing codes), and export a ready-to-use CSV.

## ✨ Features
- Password gate via `.streamlit/secrets.toml` or `PEPCO_APP_PASSWORD` env.
- Clean, modular structure — `auth.py` (access), `theme.py` (UI).
- PDF parsing with PyMuPDF: order id, style, colour, barcodes, etc.
- Google Sheets–backed price ladder & translations (cached).
- Multilingual product names with optional material compositions.
- Inline edit and one-click CSV download.

## 📁 Project Structure
