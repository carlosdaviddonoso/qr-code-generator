import streamlit as st
import pandas as pd
import qrcode
import re
import unicodedata
import zipfile
from io import BytesIO
from PIL import Image

st.set_page_config(page_title="QR Code Generator", layout="centered")
st.title("LinkedIn QR Code PNG Generator")


# === ROBUST CSV LOADER ===
def load_csv(file):
    encodings = ["utf-8-sig", "utf-8", "mac_roman", "cp1252", "latin1"]
    separators = [",", ";"]

    for enc in encodings:
        for sep in separators:
            try:
                file.seek(0)
                df = pd.read_csv(file, encoding=enc, sep=sep)

                if len(df.columns) <= 1:
                    continue

                sample_text = " ".join(
                    str(x) for x in df.head(20).fillna("").astype(str).values.flatten()
                )

                suspicious_patterns = ["Ã", "Â", "�", "\x8d", ""]
                if any(p in sample_text for p in suspicious_patterns):
                    continue

                return df

            except Exception:
                continue

    raise ValueError("Unable to read CSV correctly. Please check file encoding/export format.")


# === NORMALIZE COLUMN NAMES FOR DETECTION ONLY ===
def normalize_column(col):
    col = unicodedata.normalize("NFKD", str(col))
    col = col.encode("ascii", "ignore").decode("ascii")
    col = col.lower()
    col = re.sub(r"[^a-z0-9]", "", col)
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
    return str(text).strip()


# === CLEAN FILENAME ===
def clean_filename(first, last):
    name = f"{first}_{last}"
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", "_", name)
    return name.strip("_")


# === GENERATE QR WITH CENTERED LINKEDIN LOGO ===
def generate_qr_with_logo(url, logo_path="linkedin_logo.png"):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")

    logo = Image.open(logo_path).convert("RGBA")

    qr_width, qr_height = qr_img.size

    # Keep logo small enough for reliable scanning
    logo_size = int(qr_width * 0.18)
    logo = logo.resize((logo_size, logo_size), Image.LANCZOS)

    # White badge behind logo
    padding = int(logo_size * 0.16)
    badge_size = logo_size + 2 * padding
    badge = Image.new("RGBA", (badge_size, badge_size), "white")

    badge_x = (qr_width - badge_size) // 2
    badge_y = (qr_height - badge_size) // 2
    logo_x = (badge_size - logo_size) // 2
    logo_y = (badge_size - logo_size) // 2

    badge.paste(logo, (logo_x, logo_y), logo)
    qr_img.paste(badge, (badge_x, badge_y), badge)

    return qr_img


uploaded_file = st.file_uploader("Upload a CSV file", type=["csv"])

if uploaded_file:
    try:
        df = load_csv(uploaded_file)
    except Exception as e:
        st.error(str(e))
        st.stop()

    first_col, last_col, url_col = detect_columns(df)

    if not all([first_col, last_col, url_col]):
        st.error("Could not automatically detect required columns.")
        st.stop()

    st.success(f"Columns detected: First = {first_col}, Last = {last_col}, URL = {url_col}")

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
            name_key = base_name.casefold()

            if name_key in used_names:
                used_names[name_key] += 1
                filename = f"{base_name}_{used_names[name_key]}.png"
            else:
                used_names[name_key] = 1
                filename = f"{base_name}.png"

            try:
                img = generate_qr_with_logo(url, "linkedin_logo.png")

                img_bytes = BytesIO()
                img.save(img_bytes, format="PNG")
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

        if error_rows:
            error_df = pd.DataFrame(error_rows)
            zf.writestr("error_report.csv", error_df.to_csv(index=False))

    memory_zip.seek(0)

    st.success(f"{generated} QR codes generated | {skipped} skipped")

    st.download_button(
        label="Download ZIP",
        data=memory_zip,
        file_name="qr_codes.zip",
        mime="application/zip"
    )
