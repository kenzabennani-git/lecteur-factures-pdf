import pdfplumber
import re
import mysql.connector

# ----------------------------------------------------
# 1. CONNEXION À LA BASE DE DONNÉES
# ----------------------------------------------------
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="root",
    database="projet_stage"
)
cursor = conn.cursor()
print("Connexion à la base réussie !")

# Variables pour le fournisseur
fournisseur_id_to_insert = None
fournisseur = None 

# ----------------------------------------------------
# 2. EXTRACTION DU TEXTE DU PDF
# ----------------------------------------------------
pdf_path = "test2_facture.pdf.pdf"
try:
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(page.extract_text() for page in pdf.pages)
except FileNotFoundError:
    print(f"Erreur: Le fichier {pdf_path} n'a pas été trouvé.")
    exit()

clean_text = text.replace("\xa0", " ").replace("\u202f", " ").replace("\u200b", "")
lines = clean_text.split("\n")
MONTANT_REGEX = r"([0-9\s]*[,\.][0-9]{2}\s*€?)"

# ----------------------------------------------------
# 3. EXTRACTION DES INFORMATIONS
# ----------------------------------------------------

# FOURNISSEUR 
for line in lines[:15]:
    clean_line = line.strip()
    if clean_line == "":
        continue
    if any(keyword in clean_line.lower() for keyword in [
        "facture", "numéro", "date", "émission", "réf", "invoice", "émetteur", "émettrice"
    ]):
        continue
    fournisseur = clean_line
    break

# NUMERO FACTURE
num_keywords = [r"Num[eé]ro de facture", r"Facture N[°o]", r"Réf\.?", r"Invoice", r"Numéro"]
num_facture = None
for kw in num_keywords:
    match = re.search(rf"{kw}\s*[:\s]*([A-Z0-9\-\/]+)", clean_text, re.IGNORECASE)
    if match:
        num_facture = match.group(1).strip()
        break

# DATE FACTURE
mois = r"(?:janv\.?|févr\.?|mars|avr\.?|mai|juin|juil\.?|août|sept\.?|oct\.?|nov\.?|déc\.?)"
date_keywords = [r"Date d['’`´]?émission", r"Date de facture", r"Facture émise le", r"Émise le", r"Date", r"Emission"]
date_facture = None
for kw in date_keywords:
    match = re.search(rf"{kw}.*?([0-9]{{1,2}}\s+{mois}\s+[0-9]{{4}})", clean_text, re.IGNORECASE)
    if match:
        date_facture = match.group(1).strip()
        break
if date_facture is None:
    for kw in date_keywords:
        match = re.search(rf"{kw}.*?([0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}})", clean_text, re.IGNORECASE)
        if match:
            date_facture = match.group(1).strip()
            break

# HT 5,5%
ht5 = None
match = re.search(r"5[,\.]5\s*%\s*" + MONTANT_REGEX, clean_text)
if match:
    ht5 = match.group(1).strip()

# HT 20%
ht20 = None
match = re.search(r"20[,\.]?0?\s*%\s*" + MONTANT_REGEX, clean_text)
if match:
    ht20 = match.group(1).strip()

# TOTAL TVA
tva = None
tva_keywords = r"(Montant total de la TVA|Total TVA|TVA totale|Montant total TVA|TVA)"
match = re.search(rf"{tva_keywords}\s*[:\s]*{MONTANT_REGEX}", clean_text, re.IGNORECASE)
if match:
    tva = match.group(2).strip()
else:
    tva_only_match = re.search(r"\bTVA\b\s*:\s*" + MONTANT_REGEX, clean_text, re.IGNORECASE)
    if tva_only_match:
        tva = tva_only_match.group(1).strip()

# TOTAL TTC
ttc = None
ttc_keywords = r"(Total TTC|Montant TTC|Total à payer|Net à payer|Montant à régler)"
match = re.search(rf"{ttc_keywords}\s*[:\s]*{MONTANT_REGEX}", clean_text, re.IGNORECASE)
if match:
    ttc = match.group(2).strip()

# ----------------------------------------------------
# 4. AFFICHAGE DES DONNÉES
# ----------------------------------------------------
print("\n----- DONNÉES EXTRAITES -----")
print("Fournisseur (Nom) :", fournisseur)
print("Numéro de facture :", num_facture)
print("Date de facture :", date_facture)
print("HT (5,5%) :", ht5 if ht5 else "None")
print("HT (20%) :", ht20 if ht20 else "None")
print("Total TVA :", tva if tva else "None")
print("Total TTC :", ttc if ttc else "None")

# ----------------------------------------------------
# 4.5. GESTION DU FOURNISSEUR
# ----------------------------------------------------
if fournisseur:
    
    sql_check = "SELECT id FROM fournisseurs WHERE nom_fournisseur = %s"
    cursor.execute(sql_check, (fournisseur,))
    result = cursor.fetchone()

    if result is None:
        
        sql_insert_f = "INSERT INTO fournisseurs (nom_fournisseur) VALUES (%s)"
        try:
            cursor.execute(sql_insert_f, (fournisseur,))
            conn.commit()
            
            fournisseur_id_to_insert = cursor.lastrowid
            print(f"\nFournisseur '{fournisseur}' inséré. ID récupéré: {fournisseur_id_to_insert}")
        except mysql.connector.Error as err:
            print(f"Erreur lors de l'insertion du fournisseur : {err}")
            conn.rollback()
    else:
        
        fournisseur_id_to_insert = result[0]
        print(f"\nFournisseur '{fournisseur}' déjà existant. ID récupéré: {fournisseur_id_to_insert}")
else:
    print("\nFournisseur non trouvé dans le PDF. fournisseur_id_to_insert = NULL.")

# ----------------------------------------------------
# 5. INSERTION EN BASE DE DONNÉES
# ----------------------------------------------------
sql = """
INSERT INTO factures
(fournisseur_id, numero_facture, date_facture, ht_5_5, ht_20, total_tva, total_ttc)
VALUES (%s, %s, %s, %s, %s, %s, %s)
"""
values = (
    fournisseur_id_to_insert, 
    num_facture,
    date_facture,
    ht5,
    ht20,
    tva,
    ttc
)

try:
    cursor.execute(sql, values)
    conn.commit()
    print("\nDonnées insérées dans la table 'factures' avec succès (avec fournisseur_id) !")
except mysql.connector.Error as err:
    print(f"\nErreur lors de l'insertion en base de données : {err}")
    conn.rollback()
finally:
    if 'conn' in locals() and conn.is_connected():
        cursor.close()
        conn.close()
        print("Connexion à la base de données fermée.")






