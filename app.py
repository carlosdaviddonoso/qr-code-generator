import math
import re
import unicodedata
import zipfile
from io import BytesIO
from urllib.parse import urlparse

import pandas as pd
import qrcode
import streamlit as st
from PIL import Image, ImageDraw

st.set_page_config(page_title="LinkedIn QR Code Generator", layout="centered")
st.title("LinkedIn QR Code Generator")

# Fixed high-resolution print-ready settings
DEFAULT_DPI = 600
DEFAULT_PRINT_SIZE_IN = 1.25


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
def clean_filename(*parts):
    name = "_".join([str(part).strip() for part in parts if str(part).strip()])
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", "_", name)
    return name.strip("_")


# === BASIC LINKEDIN URL CHECK ===
def is_valid_linkedin_url(url):
    if not url:
        return False
    parsed = urlparse(url.strip())
    hostname = parsed.netloc.lower()
    return "linkedin.com" in hostname


# === EXTRACT LINKEDIN HANDLE FROM URL ===
def extract_linkedin_handle(url):
    try:
        parsed = urlparse(url.strip())
        path = parsed.path.strip("/")

        if not path:
            return ""

        parts = [part for part in path.split("/") if part]
        if not parts:
            return ""

        # Typical LinkedIn profile formats:
        # /in/handle
        # /pub/handle/xx/yy/zz
        if parts[0].lower() == "in" and len(parts) >= 2:
            handle = parts[1]
        elif parts[0].lower() == "pub" and len(parts) >= 2:
            handle = parts[1]
        else:
            handle = parts[-1]

        handle = handle.strip()
        handle = re.sub(r"[?#].*$", "", handle)
        handle = re.sub(r"\s+", "_", handle)
        handle = re.sub(r'[\\/*?:"<>|]', "", handle)

        return handle
    except Exception:
        return ""


# === CHOOSE SINGLE FILE NAME ===
def build_single_filename(url, first_name="", last_name=""):
    first_name = clean_text(first_name)
    last_name = clean_text(last_name)

    if first_name and last_name:
        filename_base = clean_filename(first_name, last_name)
        if filename_base:
            return f"{filename_base}.png"

    handle = extract_linkedin_handle(url)
    if handle:
        filename_base = clean_filename(handle)
        if filename_base:
            return f"{filename_base}.png"

    return "linkedin_qr.png"


# === CROP AWAY OUTER TRANSPARENT MARGINS FROM LOGO ===
def trim_logo(img):
    rgba = img.convert("RGBA")
    bbox = rgba.getbbox()
    if bbox:
        rgba = rgba.crop(bbox)
    return rgba


# === CREATE ROUNDED WHITE BADGE ===
def create_rounded_badge(size, radius):
    badge = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    mask = Image.new("L", (size, size), 0)

    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle(
        [(0, 0), (size - 1, size - 1)],
        radius=radius,
        fill=255
    )

    white_fill = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    badge = Image.composite(white_fill, badge, mask)
    return badge


# === GENERATE PRINT-READY QR WITH CENTERED LINKEDIN LOGO ===
def generate_qr_with_logo(
    url,
    logo_path="linkedin_logo.png",
    dpi=DEFAULT_DPI,
    print_size_in=DEFAULT_PRINT_SIZE_IN
):
    target_px = int(round(dpi * print_size_in))

    qr_probe = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr_probe.add_data(url)
    qr_probe.make(fit=True)

    total_modules = qr_probe.modules_count + (qr_probe.border * 2)
    box_size = max(1, math.ceil(target_px / total_modules))

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=box_size,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")

    logo = Image.open(logo_path).convert("RGBA")
    logo = trim_logo(logo)

    qr_width, qr_height = qr_img.size

    logo_size = int(qr_width * 0.18)
    logo = logo.resize((logo_size, logo_size), Image.LANCZOS)

    padding = int(logo_size * 0.16)
    badge_size = logo_size + (2 * padding)
    badge_radius = int(badge_size * 0.22)

    badge = create_rounded_badge(badge_size, badge_radius)

    badge_x = (qr_width - badge_size) // 2
    badge_y = (qr_height - badge_size) // 2
    logo_x = (badge_size - logo_size) // 2
    logo_y = (badge_size - logo_size) // 2

    badge.paste(logo, (logo_x, logo_y), logo)
    qr_img.paste(badge, (badge_x, badge_y), badge)

    return qr_img, dpi


# === SINGLE QR DOWNLOAD ===
def build_single_qr_file(url):
    img, img_dpi = generate_qr_with_logo(url)

    img_bytes = BytesIO()
    img.save(img_bytes, format="PNG", dpi=(img_dpi, img_dpi))
    img_bytes.seek(0)
    return img_bytes


# === BATCH QR ZIP DOWNLOAD ===
def build_batch_zip(df, first_col, last_col, url_col):
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
            elif not is_valid_linkedin_url(url):
                reason = "Invalid LinkedIn URL"

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
                img, img_dpi = generate_qr_with_logo(url)

                img_bytes = BytesIO()
                img.save(img_bytes, format="PNG", dpi=(img_dpi, img_dpi))
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
    return memory_zip, generated, skipped


# === UI ===
tab_single, tab_batch = st.tabs(["Single QR Code", "Batch from CSV"])

with tab_single:
    st.subheader("Generate one QR code")
    single_url = st.text_input("Paste a LinkedIn profile URL")
    single_first_name = st.text_input("First Name (optional)")
    single_last_name = st.text_input("Last Name (optional)")

    if single_url:
        if not is_valid_linkedin_url(single_url):
            st.error("Please enter a valid LinkedIn profile URL.")
        else:
            try:
                single_file = build_single_qr_file(single_url)
                output_filename = build_single_filename(
                    single_url,
                    first_name=single_first_name,
                    last_name=single_last_name
                )

                st.success(f"QR code generated: {output_filename}")

                st.download_button(
                    label="Download PNG",
                    data=single_file,
                    file_name=output_filename,
                    mime="image/png"
                )
            except Exception as e:
                st.error(f"Could not generate QR code: {e}")

with tab_batch:
    st.subheader("Generate multiple QR codes from a CSV")
    uploaded_file = st.file_uploader("Upload a CSV file", type=["csv"], key="batch_csv")

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

        try:
            zip_file, generated, skipped = build_batch_zip(df, first_col, last_col, url_col)

            st.success(f"{generated} QR codes generated | {skipped} skipped")

            st.download_button(
                label="Download ZIP",
                data=zip_file,
                file_name="qr_codes.zip",
                mime="application/zip"
            )
        except Exception as e:
            st.error(f"Could not generate batch QR codes: {e}")
