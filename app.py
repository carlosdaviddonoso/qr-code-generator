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

uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])


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


# === MAIN PROCESS ===
if uploaded_file:
    try:
        df = load_csv(uploaded_file)
    except Exception as e:
        st.error(str(e))
        st.stop()

    # Debug: show detected columns
    st.write("📋 Detected columns:", list(df.columns))

    memory_zip = BytesIO()
    used_names = {}
    generated = 0
    skipped = 0

    with zipfile.ZipFile(memory_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for _, row in df.iterrows():
            first = clean_text(row.get("First Name", ""))
            last = clean_text(row.get("Last Name", ""))
            url = str(row.get("QR codes", "")).strip()

            # Skip invalid rows
            if not url or url.upper() == "N/A":
                skipped += 1
                continue

            if not first or not last:
                skipped += 1
                continue

            base_name = clean_filename(first, last)

            # Handle duplicates
            if base_name in used_names:
                used_names[base_name] += 1
                filename = f"{base_name}_{used_names[base_name]}.svg"
            else:
                used_names[base_name] = 1
                filename = f"{base_name}.svg"

            try:
                factory = svg.SvgImage
                img = qrcode.make(url, image_factory=factory, box_size=10)

                img_bytes = BytesIO()
                img.save(img_bytes)
                img_bytes.seek(0)

                zf.writestr(filename, img_bytes.read())
                generated += 1

            except Exception:
                skipped += 1
                continue

    memory_zip.seek(0)

    st.success(f"✅ {generated} QR codes generated | ⏭️ {skipped} skipped")

    st.download_button(
        label="⬇️ Download ZIP",
        data=memory_zip,
        file_name="qr_codes.zip",
        mime="application/zip"
    )
