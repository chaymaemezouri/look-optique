import re
import json
import os
from pathlib import Path
from PyPDF2 import PdfReader

import pytesseract
from pdf2image import convert_from_path
from dotenv import load_dotenv


# 1) Charger les variables du fichier .env
load_dotenv()

# Chemin Poppler (nécessaire pour convertir PDF -> images)
POPPLER_PATH = os.getenv("POPPLER_PATH")

# Chemin vers tesseract.exe (OCR)
TESSERACT_PATH = os.getenv("TESSERACT_PATH")

# Chemin vers le dossier tessdata (langues OCR comme fra.traineddata)
TESSDATA_PREFIX = os.getenv("TESSDATA_PREFIX")

# Si le chemin de tesseract existe, on le configure dans pytesseract
if TESSERACT_PATH:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# Si le chemin tessdata existe, on le met dans les variables système
if TESSDATA_PREFIX:
    os.environ["TESSDATA_PREFIX"] = TESSDATA_PREFIX


# 2) Fonction : extraire le texte d'un PDF
def extract_text_pdf(pdf_path: str) -> str:
   

    # --- 2.1 Essayer extraction texte normale (PDF texte)
    try:
        reader = PdfReader(pdf_path)
        text_parts = []

        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

        text = "\n".join(text_parts).strip()

        # Si on a trouvé du texte => return
        if len(text) > 30:
            return text

    except Exception:
        # Si erreur, on ignore et on passe à l'OCR
        pass

    # --- 2.2 Si PDF scanné => OCR
    if not POPPLER_PATH:
        raise RuntimeError("POPPLER_PATH is not set in .env")

    # Convertir PDF en images (une image par page)
    images = convert_from_path(pdf_path, dpi=400, poppler_path=POPPLER_PATH)

    ocr_text_parts = []

    # OCR sur chaque image
    for img in images:
        page_txt = pytesseract.image_to_string(
            img,
            lang="eng",  # "eng" marche bien pour chiffres, sinon tu peux mettre "fra"
            config="--oem 3 --psm 6"
        )
        ocr_text_parts.append(page_txt)

    # Retourner tout le texte OCR combiné
    return "\n".join(ocr_text_parts)


# 3) Fonction : reformater le numéro (groupe par 2 chiffres)
def format_number_2digit_groups(digits: str) -> str:
    

    first = digits[0]  # premier chiffre seul
    groups = [digits[i:i+2] for i in range(1, len(digits), 2)]  # groupes de 2
    return " ".join([first] + groups)


# 4) Fonction : extraire le nom + numéro depuis le texte
def extract_client_info(text: str):
    

    # Nettoyage du texte OCR (espaces bizarres)
    t = text.replace("\xa0", " ")
    t = re.sub(r"[ \t]+", " ", t)

    # --- 4.1 Extraction du numéro
    # On cherche "Mon numéro : 2 74 01 ...."
    num_match = re.search(
        r"Mon\s+num[eé]ro\s*[:\-]?\s*([0-9][0-9 \-]{10,})",
        t,
        flags=re.IGNORECASE
    )

    client_number = num_match.group(1).strip() if num_match else None

    # Nettoyer le numéro (garder uniquement chiffres)
    if client_number:
        digits = re.sub(r"\D", "", client_number)

        # Souvent numéro = 15 chiffres (exemple NIR)
        if len(digits) >= 15:
            digits = digits[:15]  # prendre les 15 premiers chiffres
            client_number = format_number_2digit_groups(digits)
        else:
            client_number = re.sub(r"[^0-9 ]", "", client_number).strip()

    # --- 4.2 Extraction du nom
    name_match = re.search(
        r"Mon\s+nom\s+ou\s+celui\s+de\s+mon\s+ayant\s+droit\s*[:\-]?\s*([^\n]+)",
        text,
        flags=re.IGNORECASE
    )

    client_name = name_match.group(1).strip() if name_match else None

    return client_name, client_number


# 5) Fonction : traiter un PDF complet
def process_pdf(pdf_path: str):
    """
    - Extraire texte du PDF
    - Extraire nom + numéro
    - Retourner un dictionnaire (JSON)
    """

    text = extract_text_pdf(pdf_path)
    name, number = extract_client_info(text)

    return {
        "file": os.path.basename(pdf_path),
        "client_name": name,
        "client_number": number
    }


# 6) Fonction : sauvegarder tous les clients dans un fichier JSON
def save_all_to_json(data, output_file="clients.json"):
    """
    Sauvegarde la liste de clients dans un fichier JSON
    """
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# 7) MAIN : programme principal
if __name__ == "__main__":

    # Trouver le dossier du script code.py
    base_dir = Path(__file__).resolve().parent

    # Le dossier qui contient les PDF
    contracts_dir = base_dir / "contracts"

    # Vérifier que le dossier existe
    if not contracts_dir.exists():
        raise FileNotFoundError(f"Dossier introuvable: {contracts_dir}")

    # Trouver automatiquement tous les fichiers .pdf dans contracts/
    pdf_files = sorted(contracts_dir.glob("*.pdf"))

    # Si aucun pdf trouvé => erreur
    if not pdf_files:
        raise FileNotFoundError(f" Aucun PDF trouvé dans: {contracts_dir}")

    # Liste où on va stocker tous les résultats
    all_clients = []

    # Parcourir chaque pdf trouvé
    for pdf in pdf_files:
        result = process_pdf(str(pdf))
        all_clients.append(result)

        # Afficher résultat dans terminal
        print("Fichier:", result["file"])
        print("Nom:", result["client_name"])
        print("Numéro:", result["client_number"])

    # Sauvegarder tous les résultats dans clients.json
    save_all_to_json(all_clients)
