import streamlit as st
import pandas as pd
import qrcode
import qrcode.image.svg as svg
import re
import unicodedata
import zipfile
from io import BytesIO

st.set_page_config(page_title="QR Code Generator", layout="centered")

st.title("📦 CSV → QR Codes (SVG) → ZIP")


# === ROBUST CSV LOADER ===
def load_csv(file):
    encodings = ["utf-8", "latin1", "cp1252"]
    separators = [",", ";"]

    for enc in encodings:
        for sep in separators:
            try:
                file.seek(0)
                df = pd.read_csv(file, encoding=enc, sep=sep)
                if len(df.columns) > 1:
                    return df
            except:
                continue

    raise ValueError("❌ Unable to read CSV. Please check file format.")


# === NORMALIZE COLUMN NAMES ===
def normalize_column(col):
    col = unicodedata.normalize('NFKD', str(col))
    col = col.encode('ascii', 'ignore').decode('ascii')
    col = col.lower()
    col = re.sub(r'[^a-z0-9]', '', col)
    return col


# === AUTO-DETECT COLUMNS ===
def detect_columns(df):
    normalized = {normalize_column(c): c for c in df.columns}

    first_col = None
    last_col = None
    url_col = None

    for key, original in normalized.items():
        if not first_col and ("firstname" in key or "prenom" in key):
            first_col = original
        elif not last_col and ("lastname" in key or "nom" in key):
            last_col = original
        elif not url_col and ("qr" in key or "link" in key or "url" in key):
            url_col = original

    return first_col, last_col, url_col


# === CLEAN TEXT ===
def clean_text(text):
    if pd.isna(text):
        return ""
    text = unicodedata.normalize('NFKD', str(text))
    text = text.encode('ascii', 'ignore').decode('ascii')
    return text.strip()


# === CLEAN FILENAME ===
def clean_filename(first, last):
    name = f"{first}_{last}".lower()
    name = re.sub(r'[^a-z0-9]+', '_', name)
    return name.strip('_')


uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])

if uploaded_file:
    try:
        df = load_csv(uploaded_file)
    except Exception as e:
        st.error(str(e))
        st.stop()

    st.write("📋 Detected columns:", list(df.columns))

    first_col, last_col, url_col = detect_columns(df)

    if not all([first_col, last_col, url_col]):
        st.error("❌ Could not automatically detect required columns.")
        st.stop()

    st.success(f"✅ Columns detected → First: {first_col}, Last: {last_col}, URL: {url_col}")

    memory_zip = BytesIO()
    used_names = {}
    error_rows = []

    generated = 0
    skipped = 0

    with zipfile.ZipFile(memory_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for idx, row in df.iterrows():
            first = clean_text(row.get(first_col, ""))
            last = clean_text(row.get(last_col, ""))
            url = str(row.get(url_col, "")).strip()

            reason = None

            if not url or url.upper() == "N/A":
                reason = "Missing or N/A URL"
            elif not first or not last:
                reason = "Missing name"

            if reason:
                skipped += 1
                error_rows.append({
                    "row": idx,
                    "first": first,
                    "last": last,
                    "url": url,
                    "error": reason
                })
                continue

            base_name = clean_filename(first, last)

            if base_name in used_names:
                used_names[base_name] += 1
                filename = f"{base_name}_{used_names[base_name]}.svg"
            else:
                used_names[base_name] = 1
                filename = f"{base_name}.svg"

            try:
                factory = svg.SvgImage
                img = qrcode.make(
                    url,
                    image_factory=factory,
                    box_size=10,
                    border=4  # ✅ quiet zone restored
                )

                img_bytes = BytesIO()
                img.save(img_bytes)
                img_bytes.seek(0)

                zf.writestr(filename, img_bytes.read())
                generated += 1

            except Exception as e:
                skipped += 1
                error_rows.append({
                    "row": idx,
                    "first": first,
                    "last": last,
                    "url": url,
                    "error": str(e)
                })

        # Add error report inside ZIP
        if error_rows:
            error_df = pd.DataFrame(error_rows)
            zf.writestr("error_report.csv", error_df.to_csv(index=False))

    memory_zip.seek(0)

    st.success(f"✅ {generated} QR codes generated | ⏭️ {skipped} skipped")

    st.download_button(
        label="⬇️ Download ZIP",
        data=memory_zip,
        file_name="qr_codes.zip",
        mime="application/zip"
    )
