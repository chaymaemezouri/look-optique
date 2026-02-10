import re
import json
import os
from pathlib import Path
from PyPDF2 import PdfReader

import pytesseract
from pdf2image import convert_from_path
from dotenv import load_dotenv


# ============================
# Load .env configuration
# ============================
load_dotenv()

POPPLER_PATH = os.getenv("POPPLER_PATH")
TESSERACT_PATH = os.getenv("TESSERACT_PATH")
TESSDATA_PREFIX = os.getenv("TESSDATA_PREFIX")

if TESSERACT_PATH:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

if TESSDATA_PREFIX:
    os.environ["TESSDATA_PREFIX"] = TESSDATA_PREFIX


# ============================
# Extract text from PDF (text or OCR)
# ============================
def extract_text_pdf(pdf_path: str) -> str:
    # 1) Try text-based extraction first
    try:
        reader = PdfReader(pdf_path)
        parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
        text = "\n".join(parts).strip()
        if len(text) > 30:
            return text
    except Exception:
        pass

    # 2) OCR fallback
    if not POPPLER_PATH:
        raise RuntimeError("POPPLER_PATH is not set in .env")

    images = convert_from_path(pdf_path, dpi=400, poppler_path=POPPLER_PATH)

    ocr_parts = []
    for img in images:
        ocr_parts.append(
            pytesseract.image_to_string(
                img,
                lang="eng",  # good for digits; switch to "fra" if installed
                config="--oem 3 --psm 6"
            )
        )
    return "\n".join(ocr_parts)


# ============================
# Parse needed fields
# ============================
def parse_ordonnance(text: str) -> dict:
    t = text.replace("\xa0", " ")
    t = re.sub(r"[ \t]+", " ", t)

    # Person line: Monsieur/Madame/Mlle/M./Enfant + (dd/mm/yyyy)
    person_match = re.search(
        r"\b(Monsieur|Madame|Mlle|M\.|Enfant)\s+([A-Za-zÀ-ÿ' \-]+?)\s*\((\d{2}/\d{2}/\d{4})\)",
        t,
        flags=re.IGNORECASE
    )
    title = person_match.group(1).strip() if person_match else None
    full_name = person_match.group(2).strip() if person_match else None
    birthdate = person_match.group(3).strip() if person_match else None

    # Eye values
    od_match = re.search(
        r"(?:Oeil|Œil)\s*Droit\s*[:\-]?\s*([+\-]?\d+(?:[.,]\d+)?)",
        t,
        flags=re.IGNORECASE
    )
    og_match = re.search(
        r"(?:Oeil|Œil)\s*Gauche\s*[:\-]?\s*([+\-]?\d+(?:[.,]\d+)?)",
        t,
        flags=re.IGNORECASE
    )

    eye_right = od_match.group(1).replace(",", ".") if od_match else None
    eye_left = og_match.group(1).replace(",", ".") if og_match else None

    return {
        "title": title,
        "full_name": full_name,
        "birthdate": birthdate,
        "eye_right": eye_right,
        "eye_left": eye_left
    }


def process_pdf(pdf_path: str) -> dict:
    text = extract_text_pdf(pdf_path)
    data = parse_ordonnance(text)
    data["file"] = os.path.basename(pdf_path)
    return data


def save_all_to_json(data, output_file="ordonnances.json"):
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"Données enregistrées dans : {output_file}")


# ============================
# Main: process ALL PDFs in ordonnances/
# ============================
if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent
    ord_dir = base_dir / "ordonnances"

    if not ord_dir.exists():
        raise FileNotFoundError(f" Dossier introuvable: {ord_dir}")

    # Tous les PDFs (même dans sous-dossiers)
    pdf_files = sorted(ord_dir.rglob("*.pdf"))

    if not pdf_files:
        raise FileNotFoundError(f" Aucun PDF trouvé dans: {ord_dir}")

    results = []

    for pdf in pdf_files:
        result = process_pdf(str(pdf))
        results.append(result)

        print("Fichier:", result["file"])
        print("Nom:", (f"{result['title']} {result['full_name']}" if result["full_name"] else None))
        print("Naissance:", result["birthdate"])
        print("Oeil Droit:", result["eye_right"])
        print("Oeil Gauche:", result["eye_left"])

    save_all_to_json(results)
