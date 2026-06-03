"""Service IA DeepSeek — fiches, quiz, QCM, évaluation + extraction PDF."""

import json
import re
import threading
import io as _io
import os

from sqlalchemy.orm import Session
from models import Chapitre
import config


class ServiceIA:
    """Service d'intelligence artificielle pour StudyTracker."""

    def __init__(self, cle_api: str | None = None):
        self._client_cache = None
        self._cle_cache = None
        self._cle_api = cle_api or os.getenv("DEEPSEEK_API_KEY", "")

    @property
    def cle_api(self) -> str:
        return self._cle_api

    @cle_api.setter
    def cle_api(self, value: str):
        self._cle_api = value
        self._client_cache = None

    @property
    def disponible(self) -> bool:
        return config.HAS_AI and bool(self.cle_api)

    def _client(self):
        cle = self.cle_api
        if self._client_cache is None or self._cle_cache != cle:
            try:
                from openai import OpenAI
            except ImportError:
                raise RuntimeError("Le module 'openai' n'est pas installé. pip install openai")
            self._client_cache = OpenAI(api_key=cle, base_url=config.DEEPSEEK_BASE_URL)
            self._cle_cache = cle
        return self._client_cache

    def _appel_ia_avec_timeout(self, fn):
        resultat = [None]
        erreur = [None]

        def _worker():
            try:
                resultat[0] = fn()
            except Exception as e:
                erreur[0] = e

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        thread.join(timeout=config.TIMEOUT_IA_SECONDES)
        if thread.is_alive():
            raise TimeoutError(f"L'appel IA n'a pas répondu en {config.TIMEOUT_IA_SECONDES}s.")
        if erreur[0]:
            raise erreur[0]
        return resultat[0]

    # ── Génération IA ──

    def generer_fiche(self, nom_chap: str, matiere: str, texte_pdf: str) -> str:
        systeme = f"""Tu es un professeur d'élite — pédagogue exigeant, expert en mémorisation.

Ta mission : produire une FICHE DE RÉVISION CHIRURGICALE pour le sous-chapitre « {nom_chap} » dans la matière « {matiere} ».

═══ RÈGLE ABSOLUE ═══
Le document peut contenir plusieurs chapitres.
Concentre-toi EXCLUSIVEMENT sur la partie « {nom_chap} ».

═══ STRUCTURE ═══

╔══════════════════════════════════════╗
║  📌 TITRE DU CHAPITRE                ║
╚══════════════════════════════════════╝

🎯 IDÉE CENTRALE

─────────────────────────────────────────
🧠 NOTIONS FONDAMENTALES
─────────────────────────────────────────

─────────────────────────────────────────
📐 FORMULES / SCHÉMAS / DATES CLÉS
─────────────────────────────────────────

─────────────────────────────────────────
⚠️ PIÈGES & ERREURS CLASSIQUES
─────────────────────────────────────────

─────────────────────────────────────────
🔗 CONNEXIONS & CONTEXTE
─────────────────────────────────────────

─────────────────────────────────────────
❓ MINI-QUIZ (5 questions progressives)
─────────────────────────────────────────
Q1-Q5 puis ▼ RÉPONSES R1-R5

─────────────────────────────────────────
💡 MOYEN MNÉMOTECHNIQUE
─────────────────────────────────────────

═══ STYLE ═══
- **Gras** pour termes clés (syntaxe markdown **mot**)
- Unicode : ² ³ ⁴ ⁿ ˣ ₀ ₁ ₂ ₃ × ÷ ± √ ∫ ∑ ∏ ∞ ≠ ≤ ≥ ≈ ∝ → ⇒ ∈ ∉ ⊂ ∪ ∩ Δ θ π α β γ λ μ σ Ω ½ ⅓ ¼
- Dense, précis, sans remplissage
- Français, direct
- NE GÉNÈRE QUE LA FICHE."""
        msg = f"Localise « {nom_chap} » et génère la fiche.\n\nDOCUMENT :\n{texte_pdf}"

        def _appel():
            resp = self._client().chat.completions.create(
                model=config.DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": systeme},
                    {"role": "user", "content": msg},
                ],
            )
            return resp.choices[0].message.content

        return self._appel_ia_avec_timeout(_appel)

    def generer_questions(self, nom_chap, matiere, contexte, nb=5):
        ctx = f"\nContenu :\n{contexte[:60000]}" if contexte.strip() else "\nPas de texte."
        prompt = f"""Génère EXACTEMENT {nb} questions pour « {nom_chap} » ({matiere}).
Varie : définition, mécanisme, application, comparaison, cause/effet.
2 rappel + 2 compréhension + 1 synthèse.
Unicode pour formules.
{ctx}

Liste numérotée UNIQUEMENT :
1. [question]
..."""

        def _appel():
            resp = self._client().chat.completions.create(
                model=config.DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": "Professeur exigeant. Liste numérotée uniquement."},
                    {"role": "user", "content": prompt},
                ],
            )
            return [
                re.sub(r"^\d+[\.\)]\s*", "", l.strip()).strip()
                for l in resp.choices[0].message.content.strip().splitlines()
                if l.strip()
            ][:nb]

        return self._appel_ia_avec_timeout(_appel)

    def _extraire_json(self, texte: str) -> str:
        """Extrait le bloc JSON d'une chaîne (gère les backticks et le texte autour)."""
        match = re.search(r"(\{.*\}|\[.*\])", texte, re.DOTALL)
        if match:
            return match.group(0)
        return texte

    def generer_qcm(self, nom_chap, matiere, contexte, nb=5):
        ctx = f"\nContenu :\n{contexte[:40000]}" if contexte.strip() else ""
        prompt = f"""Génère {nb} QCM sur « {nom_chap} » ({matiere}).
{ctx}

Format STRICT JSON (sans backticks) :
[{{"question":"...","options":["A) ...","B) ...","C) ...","D) ..."],"correct":"A","explication":"..."}}]"""

        def _appel():
            resp = self._client().chat.completions.create(
                model=config.DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": "JSON valide uniquement."},
                    {"role": "user", "content": prompt},
                ],
            )
            brut = self._extraire_json(resp.choices[0].message.content.strip())
            try:
                return json.loads(brut)
            except json.JSONDecodeError as e:
                raise ValueError(f"Réponse IA invalide (JSON malformé): {e}\nBrut: {brut[:200]}")

        return self._appel_ia_avec_timeout(_appel)

    def evaluer_reponses(self, nom_chap, matiere, questions, reponses, contexte):
        ctx = f"\nRéférence :\n{contexte[:30000]}" if contexte.strip() else ""
        paires = "\n".join(
            [f"Q{i + 1}: {q}\nRéponse: {r}" for i, (q, r) in enumerate(zip(questions, reponses))]
        )
        prompt = f"""Évalue les réponses sur « {nom_chap} » ({matiere}).
{ctx}

{paires}

Pour chaque question : score "correct"/"partiel"/"incorrect" + feedback 1-2 phrases.
Verdict global : "réussi" ou "à retravailler".

JSON UNIQUEMENT :
{{"resultats":[{{"score":"...","feedback":"..."}}],"verdict":"réussi"|"à retravailler","message":"..."}}"""

        def _appel():
            resp = self._client().chat.completions.create(
                model=config.DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": "Correcteur. JSON valide uniquement."},
                    {"role": "user", "content": prompt},
                ],
            )
            brut = self._extraire_json(resp.choices[0].message.content.strip())
            try:
                data = json.loads(brut)
            except json.JSONDecodeError as e:
                raise ValueError(f"Évaluation IA invalide (JSON malformé): {e}\nBrut: {brut[:200]}")
            corrects = sum(1 for r in data["resultats"] if r["score"] == "correct")
            partiels = sum(1 for r in data["resultats"] if r["score"] == "partiel")
            data["score_num"] = (corrects + 0.5 * partiels) / max(len(data["resultats"]), 1)
            return data

        return self._appel_ia_avec_timeout(_appel)

    # ── Extraction PDF / OCR ──

    def extraire_texte_pdf(self, chemin, callback_progression=None, max_pages=None):
        if callback_progression:
            callback_progression("Extraction du texte (PyPDF2)...")
        texte = self._extraire_pypdf2(chemin)
        nb_pages = self._compter_pages(chemin)
        if len(texte.strip()) / max(nb_pages, 1) >= config.MIN_CHARS_PER_PAGE:
            return texte, "pypdf2"
        if config._check_fitz():
            if callback_progression:
                callback_progression("Essai PyMuPDF...")
            texte_fitz = self._extraire_fitz(chemin)
            if len(texte_fitz.strip()) / max(nb_pages, 1) >= config.MIN_CHARS_PER_PAGE:
                return texte_fitz, "fitz"
        limite = max_pages or config.MAX_OCR_PAGES
        if config._check_fitz() and config._check_tesseract():
            if callback_progression:
                callback_progression("OCR Tesseract...")
            texte_ocr = self._ocr_tesseract(chemin, callback_progression, max_pages=limite)
            if texte_ocr and len(texte_ocr.strip()) / max(min(nb_pages, limite), 1) >= config.MIN_CHARS_PER_PAGE:
                return texte_ocr, "tesseract"
        meilleur = texte
        if config._check_fitz():
            tf = self._extraire_fitz(chemin)
            if len(tf) > len(meilleur):
                meilleur = tf
        return meilleur, "fallback"

    def _compter_pages(self, chemin):
        try:
            if config._check_fitz():
                import fitz
                doc = fitz.open(chemin)
                n = len(doc)
                doc.close()
                return n
            import PyPDF2
            with open(chemin, "rb") as f:
                return len(PyPDF2.PdfReader(f).pages)
        except Exception:
            return 1

    def _extraire_pypdf2(self, chemin):
        import PyPDF2
        texte = ""
        try:
            with open(chemin, "rb") as f:
                for page in PyPDF2.PdfReader(f).pages:
                    t = page.extract_text()
                    if t:
                        texte += t + "\n"
        except Exception:
            pass
        return texte

    def _extraire_fitz(self, chemin):
        import fitz
        texte = ""
        try:
            doc = fitz.open(chemin)
            for page in doc:
                t = page.get_text("text")
                if t:
                    texte += t + "\n"
            doc.close()
        except Exception:
            pass
        return texte

    def _ocr_tesseract(self, chemin, callback_progression=None, max_pages=None):
        import fitz
        from PIL import Image
        import pytesseract
        texte = ""
        try:
            doc = fitz.open(chemin)
            limite = min(len(doc), max_pages) if max_pages else len(doc)
            for i in range(limite):
                if callback_progression and i % 3 == 0:
                    callback_progression(f"OCR page {i + 1}/{limite}...")
                pix = doc[i].get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72))
                img = Image.open(_io.BytesIO(pix.tobytes("png")))
                try:
                    t = pytesseract.image_to_string(img, lang="fra+eng")
                except Exception:
                    try:
                        t = pytesseract.image_to_string(img, lang="eng")
                    except Exception:
                        t = pytesseract.image_to_string(img)
                if t:
                    texte += t + "\n"
            doc.close()
        except Exception as e:
            print(f"[OCR Tesseract] {e}")
        return texte

    def obtenir_statut_ocr(self):
        caps = ["PyPDF2 (texte natif)"]
        if config._check_fitz():
            caps.append("PyMuPDF (avancé)")
        if config._check_fitz() and config._check_tesseract():
            caps.append("Tesseract OCR (local)")
        if self.disponible:
            caps.append("DeepSeek IA (cloud)")
        manquantes = []
        if not config._check_fitz():
            manquantes.append("pymupdf (pip install pymupdf)")
        if not config._check_tesseract():
            manquantes.append("pytesseract + Tesseract")
        if not config.HAS_AI:
            manquantes.append("openai (pip install openai)")
        return caps, manquantes
