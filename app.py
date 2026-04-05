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

def clean_text(text):
    if pd.isna(text):
        return ""
    text = unicodedata.normalize('NFKD', str(text))
    text = text.encode('ascii', 'ignore').decode('ascii')
    return text.strip()

def clean_filename(first, last):
    name = f"{first}_{last}".lower()
    name = re.sub(r'[^a-z0-9]+', '_', name)
    return name.strip('_')

if uploaded_file:
    df = pd.read_csv(uploaded_file)

    memory_zip = BytesIO()
    used_names = {}
    generated = 0
    skipped = 0

    with zipfile.ZipFile(memory_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for _, row in df.iterrows():
            first = clean_text(row.get("First Name", ""))
            last = clean_text(row.get("Last Name", ""))
            url = str(row.get("QR codes", "")).strip()

            if not url or url.upper() == "N/A":
                skipped += 1
                continue
            if not first or not last:
                skipped += 1
                continue

            base_name = clean_filename(first, last)

            if base_name in used_names:
                used_names[base_name] += 1
                filename = f"{base_name}_{used_names[base_name]}.svg"
            else:
                used_names[base_name] = 1
                filename = f"{base_name}.svg"

            factory = svg.SvgImage
            img = qrcode.make(url, image_factory=factory, box_size=10)

            img_bytes = BytesIO()
            img.save(img_bytes)
            img_bytes.seek(0)

            zf.writestr(filename, img_bytes.read())
            generated += 1

    memory_zip.seek(0)

    st.success(f"✅ {generated} QR codes generated | ⏭️ {skipped} skipped")

    st.download_button(
        label="⬇️ Download ZIP",
        data=memory_zip,
        file_name="qr_codes.zip",
        mime="application/zip"
    )