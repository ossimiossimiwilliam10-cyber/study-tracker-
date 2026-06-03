"""
StudyTracker V2 — App Streamlit
Déploiement : push sur GitHub → connecter à streamlit.io/cloud
"""

import sys
import os

# Ajouter le dossier backend au path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# ── Imports backend ──
from database import engine, SessionLocal, Base
import models
from services import crud_service, revision_service
from services.ia_service import ServiceIA
import config as cfg

# ══════════════════════════════════════════════════════════
# INIT (une seule fois par session)
# ══════════════════════════════════════════════════════════

st.set_page_config(
    page_title="StudyTracker V2",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ══════════════════════════════════════════════════════════
# THÈME DYNAMIQUE (dark / light)
# ══════════════════════════════════════════════════════════

def _get_theme():
    """Lit le thème depuis la BDD. Défaut: dark."""
    db = get_db()
    param = db.query(models.Parametre).filter(models.Parametre.cle == "theme").first()
    db.close()
    return param.valeur if param and param.valeur else "dark"

def _set_theme(theme: str):
    """Sauvegarde le thème en BDD."""
    db = get_db()
    param = db.query(models.Parametre).filter(models.Parametre.cle == "theme").first()
    if param:
        param.valeur = theme
    else:
        db.add(models.Parametre(cle="theme", valeur=theme))
    db.commit()
    db.close()

# L'initialisation du thème est faite après init_db()

def _theme_css():
    """Génère le CSS selon le thème actuel."""
    if st.session_state.theme == "dark":
        return """
        <style>
            .stApp { background-color: #08090e; }
            .urgent-badge { background: #f87171; color: white; border-radius: 10px; padding: 2px 10px; font-size: 0.7rem; font-weight: bold; }
            .count-badge { color: #64748b; font-size: 0.7rem; }
            h1, h2, h3, p, span { color: #e2e8f0 !important; }
            .stMetric label, .stMetric [data-testid="stMetricLabel"] { color: #64748b !important; }
            .stMetric [data-testid="stMetricValue"] { color: #e2e8f0 !important; }
            .stButton > button { border-radius: 8px !important; }
            section[data-testid="stSidebar"] { background-color: #0c0d14; border-right: 1px solid #1f2335; }
            section[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
        </style>"""
    else:
        return """
        <style>
            .stApp { background-color: #f8fafc; }
            .urgent-badge { background: #ef4444; color: white; border-radius: 10px; padding: 2px 10px; font-size: 0.7rem; font-weight: bold; }
            .count-badge { color: #64748b; font-size: 0.7rem; }
            h1, h2, h3, p, span { color: #0f172a !important; }
            .stMetric label, .stMetric [data-testid="stMetricLabel"] { color: #64748b !important; }
            .stMetric [data-testid="stMetricValue"] { color: #0f172a !important; }
            .stButton > button { border-radius: 8px !important; }
            section[data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e2e8f0; }
            section[data-testid="stSidebar"] * { color: #0f172a !important; }
        </style>"""

# ── CSS bonus (badges, animations, mobile) ──
st.markdown("""
<style>
    .big-badge { background: linear-gradient(135deg, #f87171, #fb923c); color: white; border-radius: 14px; padding: 10px 24px; font-size: 1.2rem; font-weight: bold; animation: pulse 2s infinite; }
    .badge-gold { background: linear-gradient(135deg, #fbbf24, #f59e0b); color: #1a1a1a; border-radius: 10px; padding: 4px 14px; font-size: 0.8rem; font-weight: bold; display: inline-block; margin: 3px; }
    .badge-silver { background: linear-gradient(135deg, #94a3b8, #64748b); color: white; border-radius: 10px; padding: 4px 14px; font-size: 0.8rem; font-weight: bold; display: inline-block; margin: 3px; }
    .badge-bronze { background: linear-gradient(135deg, #fb923c, #d97706); color: white; border-radius: 10px; padding: 4px 14px; font-size: 0.8rem; font-weight: bold; display: inline-block; margin: 3px; }
    @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.7; } }
    @keyframes bounce { 0%,100% { transform:translateY(0); } 50% { transform:translateY(-6px); } }
    @media (max-width: 768px) {
        section[data-testid="stSidebar"] { width: 100% !important; position: relative !important; height: auto !important; }
        .stApp .stMain { margin-left: 0 !important; }
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def init_db():
    """Initialise la base de données (une seule fois)."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    models.Parametre.creer_defauts(db)
    db.close()


def get_db():
    """Retourne une session BDD."""
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise


init_db()

# ── Init thème (après init_db pour avoir get_db défini) ──
if "theme" not in st.session_state:
    st.session_state.theme = _get_theme()
st.markdown(_theme_css(), unsafe_allow_html=True)

# ── Import auto du CSV si BDD vide ──
def _importer_csv_si_vide():
    """Importe le CSV de l'ancienne app si la BDD est vide (premier lancement)."""
    import csv as _csv
    db = get_db()
    nb = db.query(models.Matiere).count()
    if nb > 0:
        db.close()
        return  # Déjà des données, ne rien faire

    csv_path = os.path.join(os.path.dirname(__file__), "Sauvegarde app précédente.csv")
    if not os.path.exists(csv_path):
        db.close()
        return

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = _csv.DictReader(f)
        for row in reader:
            ue_nom = row.get("UE", "").strip()
            mat_nom = row.get("Matière", "").strip()
            chap_nom = row.get("Chapitre", "").strip()
            niveau = int(row.get("Niveau", "0") or "0")
            prochain = row.get("Prochain", "").strip() or cfg.date_aujourdhui()
            mega = row.get("Méga chapitre", "").strip() or None
            notes = row.get("Notes", "").strip() or ""
            video = row.get("Vidéo", "").strip() or None

            if not mat_nom or not chap_nom:
                continue

            # UE
            if ue_nom:
                ue = db.query(models.UE).filter(models.UE.nom == ue_nom).first()
                if not ue:
                    ue = models.UE(nom=ue_nom)
                    db.add(ue)
                    db.flush()
            else:
                ue = None

            # Matière
            matiere = db.query(models.Matiere).filter(models.Matiere.nom == mat_nom).first()
            if not matiere:
                matiere = models.Matiere(nom=mat_nom)
                db.add(matiere)
                db.flush()
            if ue and ue not in matiere.ues:
                matiere.ues.append(ue)
                db.flush()

            # Chapitre (skip si existe déjà)
            existant = db.query(models.Chapitre).filter(
                models.Chapitre.matiere_id == matiere.id,
                models.Chapitre.nom == chap_nom,
            ).first()
            if existant:
                continue

            max_ordre = db.query(models.Chapitre.ordre).filter(
                models.Chapitre.matiere_id == matiere.id
            ).order_by(models.Chapitre.ordre.desc()).first()
            ordre = (max_ordre[0] + 1) if max_ordre and max_ordre[0] is not None else 0

            chap = models.Chapitre(
                matiere_id=matiere.id, nom=chap_nom, ordre=ordre,
                niveau_actuel=niveau, date_prochaine=prochain,
                mega_chapitre=mega, notes=notes, video_youtube=video,
                fichiers_attaches=[],
            )
            db.add(chap)
    db.commit()
    db.close()

_importer_csv_si_vide()

# ── IA (DeepSeek) ──
def get_ia() -> ServiceIA | None:
    """Retourne l'instance IA configurée avec la clé API stockée en session."""
    if "ia_service" not in st.session_state:
        st.session_state.ia_service = ServiceIA()
    # Mettre à jour la clé depuis les paramètres stockés
    db = get_db()
    param = db.query(models.Parametre).filter(models.Parametre.cle == "deepseek_api_key").first()
    db.close()
    if param and param.valeur:
        st.session_state.ia_service.cle_api = param.valeur
    if st.session_state.ia_service.disponible:
        return st.session_state.ia_service
    return None


# ══════════════════════════════════════════════════════════
# ÉTAT DE SESSION
# ══════════════════════════════════════════════════════════

if "page" not in st.session_state:
    st.session_state.page = "dashboard"
if "matiere_id" not in st.session_state:
    st.session_state.matiere_id = None
if "matiere_nom" not in st.session_state:
    st.session_state.matiere_nom = ""


def naviguer(page, matiere_id=None, matiere_nom=""):
    st.session_state.page = page
    st.session_state.matiere_id = matiere_id
    st.session_state.matiere_nom = matiere_nom
    st.rerun()


def rafraichir():
    st.rerun()


# ══════════════════════════════════════════════════════════
# FONCTIONS UI RÉUTILISABLES
# ══════════════════════════════════════════════════════════

def couleur_niveau_hex(niv: int) -> str:
    """Retourne une couleur hex pour un niveau."""
    colors = ["#f87171", "#fb923c", "#fbbf24", "#facc15", "#a3e635",
              "#34d399", "#2dd4bf", "#22d3ee", "#60a5fa", "#818cf8",
              "#a78bfa", "#c084fc", "#f472b6", "#fb7185"]
    return colors[min(niv, 13)]


def render_progress(niv: int, max_niv: int = 13):
    """Barre de progression colorée."""
    pct = niv / max_niv if max_niv > 0 else 0
    col = couleur_niveau_hex(niv)
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:8px;width:100%">
        <div style="flex:1;height:6px;background:#282d42;border-radius:3px;overflow:hidden">
            <div style="width:{pct*100}%;height:100%;background:{col};border-radius:3px"></div>
        </div>
        <span style="color:#64748b;font-size:0.7rem;white-space:nowrap">{niv}/{max_niv}</span>
    </div>
    """, unsafe_allow_html=True)


def status_badge(retard: int, date_str: str):
    """Badge de statut (urgent, aujourd'hui, bientôt, ok)."""
    if retard < 0:
        return f"🔴 En retard - {abs(retard)}j", "#f87171"
    elif retard == 0:
        return "🟠 Aujourd'hui", "#fbbf24"
    elif retard <= 3:
        return f"🟡 Dans {retard}j", "#facc15"
    else:
        return f"{date_str} ({retard}j)", "#64748b"


# ══════════════════════════════════════════════════════════
# FONCTION : RENDU D'UN CHAPITRE
# ══════════════════════════════════════════════════════════

def _render_chapitre(chap, matiere_id):
    """Affiche une carte chapitre avec toutes les actions."""
    retard = cfg.diff_jours(chap.date_prochaine)
    badge_text, badge_color = status_badge(retard, chap.date_prochaine)
    niv_j = cfg.INTERVALLES_J[min(chap.niveau_actuel, 13)]

    with st.container(border=True):
        col1, col2, col3 = st.columns([5, 3, 1.5])

        with col1:
            tags = ""
            if chap.mega_chapitre:
                tags += " \U0001f4c2"
            if chap.historique_quiz:
                tags += f" \U0001f3af{len(chap.historique_quiz)}"
            if chap.notes:
                tags += " \U0001f4ac"
            st.markdown(f"**{chap.nom}**{tags}")

            st.caption(f"J+{niv_j}")
            render_progress(chap.niveau_actuel)

        with col2:
            st.markdown(f'<span style="color:{badge_color};font-size:0.85rem"> {badge_text}</span>',
                        unsafe_allow_html=True)

        with col3:
            if st.button("\u2705 Valider", key=f"val_{chap.uid}", use_container_width=True):
                db = get_db()
                c = crud_service.obtenir_chapitre(db, matiere_id, chap.uid)
                if c:
                    revision_service.valider_chapitre(db, c)
                db.close()
                st.rerun()

        # ── Fichiers attachés ──
        fichiers = chap.fichiers_attaches or []
        if fichiers:
            st.caption(f"\U0001f4ce {len(fichiers)} fichier(s) attach\u00e9(s)")
            for i, f in enumerate(fichiers):
                col_f1, col_f2 = st.columns([8, 1])
                with col_f1:
                    st.caption(f"  \U0001f4c4 {f.get('nom', 'PDF')}")
                with col_f2:
                    if st.button("\u274c", key=f"del_file_{chap.uid}_{i}", help="Retirer ce fichier"):
                        db = get_db()
                        crud_service.retirer_fichier(db, matiere_id, chap.uid, i)
                        db.close()
                        st.rerun()

        # ── Upload PDF ──
        uploaded = st.file_uploader("Ajouter un PDF", type=["pdf"], key=f"pdf_{chap.uid}",
                                     label_visibility="collapsed")
        if uploaded:
            # Sauvegarder le fichier
            import time
            nom_fichier = f"{int(time.time())}_{uploaded.name}"
            chemin = os.path.join(cfg.DOSSIER_FICHIERS, nom_fichier)
            with open(chemin, "wb") as f_out:
                f_out.write(uploaded.getbuffer())
            db = get_db()
            crud_service.ajouter_fichier(db, matiere_id, chap.uid, uploaded.name, chemin)
            db.close()
            st.success(f"\U0001f4c4 {uploaded.name} attach\u00e9 !")
            st.rerun()

        # ── IA : Générer / Voir ──
        ia = get_ia()
        if ia and fichiers:
            # Extraire le texte des PDFs (cache)
            texte_concat = chap.texte_cache
            if not texte_concat:
                if st.button("\u2728 G\u00e9n\u00e9rer la fiche IA", key=f"gen_fiche_{chap.uid}"):
                    with st.spinner("\u2728 Analyse des PDFs..."):
                        all_text = ""
                        for f in fichiers:
                            chemin_f = f.get("chemin", "")
                            if chemin_f and os.path.exists(chemin_f):
                                texte, methode = ia.extraire_texte_pdf(chemin_f)
                                all_text += texte + "\n\n"
                        if all_text.strip():
                            texte_concat = all_text
                            db = get_db()
                            c = crud_service.obtenir_chapitre(db, matiere_id, chap.uid)
                            if c:
                                c.texte_cache = texte_concat
                                db.commit()
                            db.close()
                            st.success("PDF analys\u00e9s ! Reclique pour g\u00e9n\u00e9rer la fiche.")
                            st.rerun()
                        else:
                            st.error("Impossible d'extraire le texte des PDFs.")

            if texte_concat and not chap.fiche_ia:
                if st.button("\U0001f9e0 Cr\u00e9er la fiche de r\u00e9vision", key=f"create_fiche_{chap.uid}"):
                    with st.spinner("\U0001f9e0 DeepSeek g\u00e9n\u00e8re la fiche..."):
                        try:
                            fiche = ia.generer_fiche(chap.nom, chap.matiere.nom if chap.matiere else "?", texte_concat)
                            db = get_db()
                            c = crud_service.obtenir_chapitre(db, matiere_id, chap.uid)
                            if c:
                                c.fiche_ia = fiche
                                db.commit()
                            db.close()
                            st.success("Fiche g\u00e9n\u00e9r\u00e9e !")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur IA : {e}")

            if texte_concat and not chap.quiz_cache:
                if st.button("\U0001f3af G\u00e9n\u00e9rer un quiz", key=f"gen_quiz_{chap.uid}"):
                    with st.spinner("\U0001f3af DeepSeek cr\u00e9e le quiz..."):
                        try:
                            questions = ia.generer_questions(chap.nom, chap.matiere.nom if chap.matiere else "?", texte_concat, nb=5)
                            db = get_db()
                            c = crud_service.obtenir_chapitre(db, matiere_id, chap.uid)
                            if c:
                                c.quiz_cache = questions
                                db.commit()
                            db.close()
                            st.success(f"{len(questions)} questions g\u00e9n\u00e9r\u00e9es !")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur IA : {e}")

            if texte_concat and not chap.qcm_cache:
                if st.button("\U0001f4cb G\u00e9n\u00e9rer un QCM", key=f"gen_qcm_{chap.uid}"):
                    with st.spinner("\U0001f4cb DeepSeek cr\u00e9e le QCM..."):
                        try:
                            qcm = ia.generer_qcm(chap.nom, chap.matiere.nom if chap.matiere else "?", texte_concat, nb=5)
                            db = get_db()
                            c = crud_service.obtenir_chapitre(db, matiere_id, chap.uid)
                            if c:
                                c.qcm_cache = qcm
                                db.commit()
                            db.close()
                            st.success("QCM g\u00e9n\u00e9r\u00e9 !")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur IA : {e}")

        # ── Afficher fiche IA ──
        if chap.fiche_ia:
            with st.expander("\U0001f9e0 Voir la fiche de r\u00e9vision"):
                st.markdown(chap.fiche_ia)

        # ── Quiz interactif ──
        if chap.quiz_cache:
            with st.expander(f"\U0001f3af Quiz ({len(chap.quiz_cache)} questions)"):
                reponses = []
                for i, q in enumerate(chap.quiz_cache):
                    rep = st.text_area(f"Q{i+1}. {q}", key=f"quiz_{chap.uid}_{i}", height=68,
                                       placeholder="Ta r\u00e9ponse...")
                    reponses.append(rep)
                if st.button("\U0001f4dd \u00c9valuer mes r\u00e9ponses", key=f"eval_quiz_{chap.uid}"):
                    texte_concat = chap.texte_cache or ""
                    with st.spinner("\U0001f9e0 \u00c9valuation par DeepSeek..."):
                        try:
                            eval_result = ia.evaluer_reponses(chap.nom, chap.matiere.nom if chap.matiere else "?",
                                                              chap.quiz_cache, reponses, texte_concat)
                            score = eval_result.get("score_num", 0)
                            reussi = eval_result.get("verdict") == "r\u00e9ussi"
                            db = get_db()
                            c = crud_service.obtenir_chapitre(db, matiere_id, chap.uid)
                            if c:
                                revision_service.callback_quiz(db, c, score, reussi, "ouvert")
                            db.close()
                            st.markdown(f"### Verdict : {'\u2705 R\u00e9ussi' if reussi else '\U0001f4da \u00c0 retravailler'}")
                            st.markdown(f"**Score :** {int(score * 100)}%")
                            st.markdown(eval_result.get("message", ""))
                            for j, r in enumerate(eval_result.get("resultats", [])):
                                emoji = {"correct": "\u2705", "partiel": "\u26a0\ufe0f", "incorrect": "\u274c"}.get(r.get("score"), "")
                                st.markdown(f"{emoji} **Q{j+1}** : {r.get('feedback', '')}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur IA : {e}")

        # ── QCM interactif ──
        if chap.qcm_cache:
            with st.expander(f"\U0001f4cb QCM ({len(chap.qcm_cache)} questions)"):
                reponses_qcm = {}
                for i, q_data in enumerate(chap.qcm_cache):
                    choix = st.radio(f"**Q{i+1}.** {q_data['question']}",
                                     q_data["options"], key=f"qcm_{chap.uid}_{i}", index=None)
                    reponses_qcm[i] = choix
                if st.button("\U0001f4dd Valider le QCM", key=f"eval_qcm_{chap.uid}"):
                    corrects = 0
                    for i, q_data in enumerate(chap.qcm_cache):
                        if reponses_qcm.get(i) == q_data["correct"]:
                            corrects += 1
                    score = corrects / len(chap.qcm_cache)
                    reussi = score >= 0.7
                    db = get_db()
                    c = crud_service.obtenir_chapitre(db, matiere_id, chap.uid)
                    if c:
                        revision_service.callback_quiz(db, c, score, reussi, "qcm")
                    db.close()
                    st.markdown(f"### Score : {corrects}/{len(chap.qcm_cache)} ({int(score * 100)}%) — {'\u2705 R\u00e9ussi' if reussi else '\U0001f4da \u00c0 retravailler'}")
                    for i, q_data in enumerate(chap.qcm_cache):
                        user = reponses_qcm.get(i)
                        correct = q_data["correct"]
                        emoji = "\u2705" if user == correct else "\u274c"
                        st.markdown(f"{emoji} **Q{i+1}** : {correct} — {q_data.get('explication', '')}")
                    st.rerun()

        # ── Flashcards IA ──
        if ia and fichiers:
            if not chap.quiz_cache and not chap.qcm_cache:
                if st.button("\U0001f4c7 G\u00e9n\u00e9rer des flashcards", key=f"gen_flash_{chap.uid}"):
                    with st.spinner("\U0001f9e0 DeepSeek cr\u00e9e les flashcards..."):
                        try:
                            texte_concat = chap.texte_cache or ""
                            if not texte_concat:
                                all_text = ""
                                for f in fichiers:
                                    chemin_f = f.get("chemin", "")
                                    if chemin_f and os.path.exists(chemin_f):
                                        texte, _ = ia.extraire_texte_pdf(chemin_f)
                                        all_text += texte + "\n\n"
                                texte_concat = all_text
                            flashcards_prompt = f"G\u00e9n\u00e8re 8 flashcards recto/verso pour \u00ab {chap.nom} \u00bb.\nJSON UNIQUEMENT : [{{\"recto\":\"question ou concept\",\"verso\":\"r\u00e9ponse ou d\u00e9finition\"}}]\n\nDOCUMENT :\n{texte_concat[:50000]}"
                            resp = ia._client().chat.completions.create(
                                model=cfg.DEEPSEEK_MODEL,
                                messages=[{"role":"system","content":"JSON valide uniquement."},
                                          {"role":"user","content":flashcards_prompt}],
                            )
                            import re as _re, json as _json
                            brut = _re.sub(r"^```[a-z]*\n?","",resp.choices[0].message.content.strip())
                            brut = _re.sub(r"\n?```$","",brut)
                            cards = _json.loads(brut)
                            st.session_state[f"flashcards_{chap.uid}"] = cards
                            st.success(f"{len(cards)} flashcards g\u00e9n\u00e9r\u00e9es !")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur IA : {e}")

        if f"flashcards_{chap.uid}" in st.session_state:
            cards = st.session_state[f"flashcards_{chap.uid}"]
            if f"flash_idx_{chap.uid}" not in st.session_state:
                st.session_state[f"flash_idx_{chap.uid}"] = 0
            idx = st.session_state[f"flash_idx_{chap.uid}"]
            if 0 <= idx < len(cards):
                with st.expander(f"\U0001f4c7 Flashcards ({idx+1}/{len(cards)})"):
                    card = cards[idx]
                    st.markdown(f"### \U0001f4d6 {card.get('recto','')}")
                    with st.expander("Voir la r\u00e9ponse"):
                        st.success(card.get('verso',''))
                    col_f1, col_f2, col_f3 = st.columns([1,1,1])
                    with col_f1:
                        if idx > 0 and st.button("\u25c0 Pr\u00e9c\u00e9dent", key=f"flash_prev_{chap.uid}"):
                            st.session_state[f"flash_idx_{chap.uid}"] -= 1
                            st.rerun()
                    with col_f2:
                        st.caption(f"{idx+1}/{len(cards)}")
                    with col_f3:
                        if idx < len(cards)-1 and st.button("Suivant \u25b6", key=f"flash_next_{chap.uid}"):
                            st.session_state[f"flash_idx_{chap.uid}"] += 1
                            st.rerun()
                    if st.button("\U0001f504 Recommencer", key=f"flash_reset_{chap.uid}"):
                        st.session_state[f"flash_idx_{chap.uid}"] = 0
                        st.rerun()

        with st.expander("\u2699\ufe0f Actions"):
            ac1, ac2, ac3, ac4, ac5, ac6, ac7, ac8 = st.columns(8)
            with ac1:
                if st.button("\u270f\ufe0f", key=f"rename_{chap.uid}", help="Renommer"):
                    st.session_state[f"rename_chap_{chap.uid}"] = True
            with ac2:
                if st.button("\u25b2", key=f"up_{chap.uid}", help="Monter"):
                    db = get_db()
                    crud_service.monter_chapitre(db, matiere_id, chap.uid)
                    db.close()
                    st.rerun()
            with ac3:
                if st.button("\u25bc", key=f"down_{chap.uid}", help="Descendre"):
                    db = get_db()
                    crud_service.descendre_chapitre(db, matiere_id, chap.uid)
                    db.close()
                    st.rerun()
            with ac4:
                if st.button("\U0001f4c1", key=f"mega_{chap.uid}", help="Grouper"):
                    st.session_state[f"mega_chap_{chap.uid}"] = True
            with ac5:
                if st.button("\U0001f4cb", key=f"dup_{chap.uid}", help="Dupliquer"):
                    db = get_db()
                    crud_service.dupliquer_chapitre(db, matiere_id, chap.uid)
                    db.close()
                    st.success("Duplique !")
                    st.rerun()
            with ac6:
                if st.button("\u2197\ufe0f", key=f"move_{chap.uid}", help="Deplacer"):
                    st.session_state[f"move_chap_{chap.uid}"] = True
            with ac7:
                if st.button("\U0001f504", key=f"reset_{chap.uid}", help="Reset"):
                    db = get_db()
                    c = crud_service.obtenir_chapitre(db, matiere_id, chap.uid)
                    if c:
                        revision_service.reinitialiser_chapitre(db, c)
                    db.close()
                    st.success("Reinitialise")
                    st.rerun()
            with ac8:
                if st.button("\U0001f5d1\ufe0f", key=f"del_{chap.uid}", help="Supprimer"):
                    db = get_db()
                    crud_service.supprimer_chapitre(db, matiere_id, chap.uid)
                    db.close()
                    st.success("Supprime")
                    st.rerun()

        # Sous-actions inline
        if st.session_state.get(f"rename_chap_{chap.uid}"):
            new_n = st.text_input("Nouveau nom", value=chap.nom, key=f"rn_input_{chap.uid}")
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Renommer", key=f"rn_btn_{chap.uid}"):
                    db = get_db()
                    try:
                        crud_service.renommer_chapitre(db, matiere_id, chap.uid, new_n.strip())
                        db.close()
                        st.session_state[f"rename_chap_{chap.uid}"] = False
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
                        db.close()
            with col_b:
                if st.button("Annuler", key=f"rn_cancel_{chap.uid}"):
                    st.session_state[f"rename_chap_{chap.uid}"] = False
                    st.rerun()

        if st.session_state.get(f"mega_chap_{chap.uid}"):
            mega_name = st.text_input("Nom du groupe (vide = degrouper)", key=f"mega_input_{chap.uid}")
            if st.button("Appliquer", key=f"mega_btn_{chap.uid}"):
                db = get_db()
                crud_service.assigner_mega(db, matiere_id, chap.uid, mega_name.strip() or None)
                db.close()
                st.session_state[f"mega_chap_{chap.uid}"] = False
                st.rerun()

        if st.session_state.get(f"move_chap_{chap.uid}"):
            db = get_db()
            autres = [m.nom for m in crud_service.lister_matieres(db) if m.id != matiere_id]
            db.close()
            if autres:
                dst = st.selectbox("Matiere de destination", autres, key=f"move_dst_{chap.uid}")
                if st.button("Deplacer", key=f"move_btn_{chap.uid}"):
                    db = get_db()
                    mat_dst = db.query(models.Matiere).filter(models.Matiere.nom == dst).first()
                    if mat_dst:
                        crud_service.deplacer_chapitre(db, matiere_id, chap.uid, mat_dst.id)
                    db.close()
                    st.session_state[f"move_chap_{chap.uid}"] = False
                    st.success("Deplace !")
                    st.rerun()
            else:
                st.warning("Creez d'abord une autre matiere.")

        # Notes rapides
        if st.button("\U0001f4ac Notes", key=f"notes_btn_{chap.uid}"):
            st.session_state[f"notes_chap_{chap.uid}"] = not st.session_state.get(f"notes_chap_{chap.uid}", False)
        if st.session_state.get(f"notes_chap_{chap.uid}"):
            notes_val = st.text_area("Notes", value=chap.notes or "", key=f"notes_input_{chap.uid}", height=80)
            if st.button("Sauvegarder les notes", key=f"notes_save_{chap.uid}"):
                db = get_db()
                crud_service.editer_notes(db, matiere_id, chap.uid, notes_val)
                db.close()
                st.success("Notes sauvegardees !")
                st.session_state[f"notes_chap_{chap.uid}"] = False
                st.rerun()


# ══════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## 📚 StudyTracker V2")

    # Navigation
    st.markdown("---")
    if st.button("🏠 Accueil", use_container_width=True,
                 type="primary" if st.session_state.page == "dashboard" else "secondary"):
        naviguer("dashboard")
    if st.button("📊 Stats", use_container_width=True,
                 type="primary" if st.session_state.page == "stats" else "secondary"):
        naviguer("stats")
    if st.button("📅 Calendrier", use_container_width=True,
                 type="primary" if st.session_state.page == "calendar" else "secondary"):
        naviguer("calendar")
    if st.button("\U0001f393 Examen blanc", use_container_width=True,
                 type="primary" if st.session_state.page == "examen" else "secondary"):
        naviguer("examen")

    st.markdown("---")

    # Recherche rapide
    q = st.text_input("🔍 Rechercher", placeholder="Matière ou chapitre...", label_visibility="collapsed")
    if q:
        db = get_db()
        results = db.query(models.Chapitre).filter(
            models.Chapitre.nom.ilike(f"%{q}%") | models.Chapitre.notes.ilike(f"%{q}%")
        ).limit(10).all()
        matieres = db.query(models.Matiere).filter(models.Matiere.nom.ilike(f"%{q}%")).all()
        db.close()

        for m in matieres:
            if st.button(f"📖 {m.nom}", use_container_width=True):
                naviguer("matiere", m.id, m.nom)
        for c in results[:5]:
            if st.button(f"📝 {c.nom} ({c.matiere.nom})", use_container_width=True):
                naviguer("matiere", c.matiere_id, c.matiere.nom)

    st.markdown("---")

    # Liste des matières (groupées par UE)
    st.markdown("**Matières**")
    db = get_db()
    matieres = crud_service.lister_matieres(db)
    ues = crud_service.lister_ues(db)

    # Matières avec UE
    assignees = set()
    for ue in ues:
        ue_matieres = [m for m in ue.matieres if m.nom in [x.nom for x in matieres]]
        if not ue_matieres:
            continue
        with st.container():
            st.markdown(f"📁 **{ue.nom}**")
            for m in ue_matieres:
                assignees.add(m.id)
                urg = sum(1 for c in m.chapitres if cfg.diff_jours(c.date_prochaine) <= 0)
                col1, col2 = st.columns([5, 1])
                with col1:
                    if st.button(f"   📖 {m.nom[:22]}", key=f"side_{m.id}", use_container_width=True,
                                 type="primary" if st.session_state.matiere_id == m.id else "secondary"):
                        naviguer("matiere", m.id, m.nom)
                with col2:
                    if urg > 0:
                        st.markdown(f'<span class="urgent-badge">{urg}</span>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<span class="count-badge">{len(m.chapitres)}</span>', unsafe_allow_html=True)

    # Matières sans UE
    sans_ue = [m for m in matieres if m.id not in assignees]
    if ues and sans_ue:
        st.caption("Autres matières")
    for m in sans_ue:
        urg = sum(1 for c in m.chapitres if cfg.diff_jours(c.date_prochaine) <= 0)
        col1, col2 = st.columns([5, 1])
        with col1:
            if st.button(f"📖 {m.nom[:25]}", key=f"side_noue_{m.id}", use_container_width=True,
                         type="primary" if st.session_state.matiere_id == m.id else "secondary"):
                naviguer("matiere", m.id, m.nom)
        with col2:
            if urg > 0:
                st.markdown(f'<span class="urgent-badge">{urg}</span>', unsafe_allow_html=True)
            else:
                st.markdown(f'<span class="count-badge">{len(m.chapitres)}</span>', unsafe_allow_html=True)

    if not matieres:
        st.caption("Aucune matière")

    if st.button("\uff0b Nouveau (mati\u00e8re ou UE)", use_container_width=True):
        st.session_state.show_new_mat = True

    db.close()

    st.markdown("---")

    # Actions rapides
    col1, col2, col3 = st.columns(3)
    with col1:
        theme_icon = "\u2600\ufe0f" if st.session_state.theme == "dark" else "\U0001f319"
        if st.button(f"{theme_icon} Th\u00e8me", use_container_width=True, help="Basculer dark/light"):
            nouveau = "light" if st.session_state.theme == "dark" else "dark"
            st.session_state.theme = nouveau
            _set_theme(nouveau)
            st.rerun()
    with col2:
        if st.button("\u2699\ufe0f Param\u00e8tres", use_container_width=True):
            st.session_state.show_settings = True
    with col3:
        if st.button("\u21a9\ufe0f Undo", use_container_width=True):
            try:
                db2 = get_db()
                db2.close()
                naviguer(st.session_state.page, st.session_state.matiere_id, st.session_state.matiere_nom)
            except Exception:
                st.warning("Rien \u00e0 annuler")


# ══════════════════════════════════════════════════════════
# MODAL : Paramètres (clé API DeepSeek)
# ══════════════════════════════════════════════════════════

if st.session_state.get("show_settings"):
    with st.expander("\u2699\ufe0f Param\u00e8tres", expanded=True):
        db = get_db()
        param_cle = db.query(models.Parametre).filter(models.Parametre.cle == "deepseek_api_key").first()
        db.close()
        cle_actuelle = param_cle.valeur if param_cle and param_cle.valeur else ""
        ia = get_ia()

        st.markdown("### \U0001f9e0 Intelligence Artificielle (DeepSeek)")
        if ia:
            st.success("\u2705 IA connect\u00e9e et pr\u00eate !")
            st.caption("Fiches de r\u00e9vision, quiz et QCM disponibles pour les chapitres avec PDF.")
        else:
            st.warning("\u26a0\ufe0f Cl\u00e9 API DeepSeek non configur\u00e9e.")

        st.markdown("**Cl\u00e9 API DeepSeek**")
        st.caption("Cr\u00e9e ta cl\u00e9 sur [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys)")

        col_a, col_b = st.columns([3, 1])
        with col_a:
            new_key = st.text_input("Cl\u00e9 API", value=cle_actuelle, type="password",
                                    placeholder="sk-...", key="settings_api_key",
                                    label_visibility="collapsed")
        with col_b:
            if st.button("\U0001f4be Sauvegarder", use_container_width=True):
                db = get_db()
                p = db.query(models.Parametre).filter(models.Parametre.cle == "deepseek_api_key").first()
                if not p:
                    p = models.Parametre(cle="deepseek_api_key", valeur=new_key.strip())
                    db.add(p)
                else:
                    p.valeur = new_key.strip()
                db.commit()
                db.close()
                # Reset le service IA
                if "ia_service" in st.session_state:
                    st.session_state.ia_service.cle_api = new_key.strip()
                st.success("Cl\u00e9 API sauvegard\u00e9e !")
                st.rerun()

        if st.button("Fermer", use_container_width=True):
            st.session_state.show_settings = False
            st.rerun()


# ══════════════════════════════════════════════════════════
# MODAL : Nouvelle matière / UE
# ══════════════════════════════════════════════════════════

if st.session_state.get("show_new_mat"):
    with st.expander("➕ Créer", expanded=True):
        type_creation = st.radio("Type", ["📖 Matière", "📁 UE"], horizontal=True, label_visibility="collapsed")

        if type_creation == "📖 Matière":
            col1, col2 = st.columns(2)
            with col1:
                nom_mat = st.text_input("Nom de la matière", key="new_mat_name")
            with col2:
                ue_mat = st.text_input("UE (optionnel)", key="new_mat_ue")
            if st.button("Créer la matière", use_container_width=True) and nom_mat.strip():
                db = get_db()
                try:
                    crud_service.creer_matiere(db, nom_mat.strip(), ue_mat.strip() if ue_mat.strip() else None)
                    st.success(f"Matière « {nom_mat} » créée !")
                    st.session_state.show_new_mat = False
                    rafraichir()
                except ValueError as e:
                    st.error(str(e))
                finally:
                    db.close()

        else:
            nom_ue = st.text_input("Nom de l'UE", placeholder="ex: UE 2 - Mathématiques", key="new_ue_name")
            if st.button("Créer l'UE", use_container_width=True) and nom_ue.strip():
                db = get_db()
                try:
                    crud_service.creer_ue(db, nom_ue.strip())
                    st.success(f"UE « {nom_ue} » créée !")
                    st.session_state.show_new_mat = False
                    rafraichir()
                except ValueError as e:
                    st.error(str(e))
                finally:
                    db.close()
        if st.button("Annuler", use_container_width=True):
            st.session_state.show_new_mat = False
            rafraichir()


# ══════════════════════════════════════════════════════════
# PAGE : TABLEAU DE BORD
# ══════════════════════════════════════════════════════════

if st.session_state.page == "dashboard":
    db = get_db()
    chapitres_all = db.query(models.Chapitre).all()
    total = len(chapitres_all)
    urgent = sum(1 for c in chapitres_all if cfg.diff_jours(c.date_prochaine) <= 0)
    bientot = sum(1 for c in chapitres_all if 0 < cfg.diff_jours(c.date_prochaine) <= 3)
    maitrise = sum(1 for c in chapitres_all if c.niveau_actuel >= len(cfg.INTERVALLES_J) - 1)
    nb_matieres = db.query(models.Matiere).count()

    # Streak
    from models import Activite
    act_items = sorted(
        [(a.date, a.revisions or 0, a.quiz_reussis or 0, a.quiz_echoues or 0) for a in db.query(Activite).all()],
        key=lambda x: x[0], reverse=True,
    )
    auj = datetime.now().date()
    streak = 0
    for i in range(365):
        d = (auj - timedelta(days=i)).strftime("%Y-%m-%d")
        found = next((a for a in act_items if a[0] == d), None)
        if found and found[1] > 0:
            streak += 1
        else:
            break

    db.close()

    pct_maitrise = int(maitrise / total * 100) if total > 0 else 0

    st.title("Tableau de bord")
    st.caption(datetime.now().strftime("%A %d %B %Y").capitalize())

    # Stats cards
    cols = st.columns(4)
    with cols[0]:
        st.metric("📚 Matières", nb_matieres)
    with cols[1]:
        st.metric("📝 Chapitres", total)
    with cols[2]:
        st.metric("🔥 À réviser", urgent, delta=f"{bientot} bientôt" if bientot > 0 else None,
                  delta_color="inverse")
    with cols[3]:
        st.metric("🏆 Maîtrise", f"{pct_maitrise}%")

    # Streak + Badges
    if streak > 0:
        st.info(f"\U0001f525 **{streak} jours** cons\u00e9cutifs de r\u00e9vision !")

    # Badges de r\u00e9ussite
    badges_html = '<div style="margin:8px 0">'
    if streak >= 7:
        badges_html += '<span class="badge-gold">\U0001f3c5 7 jours de streak</span>'
    if streak >= 30:
        badges_html += '<span class="badge-gold">\U0001f451 30 jours de streak</span>'
    if maitrise >= 10:
        badges_html += '<span class="badge-silver">\U0001f4da 10 chapitres ma\u00eetris\u00e9s</span>'
    if maitrise >= 25:
        badges_html += '<span class="badge-gold">\U0001f4da 25 chapitres ma\u00eetris\u00e9s</span>'
    if total >= 20:
        badges_html += '<span class="badge-silver">\U0001f4dd 20 chapitres cr\u00e9\u00e9s</span>'
    if total >= 5:
        badges_html += '<span class="badge-bronze">\U0001f4dd 5 chapitres cr\u00e9\u00e9s</span>'
    quiz_total = sum(a[2] for a in act_items) + sum(a[3] for a in act_items)
    if quiz_total >= 10:
        badges_html += '<span class="badge-silver">\U0001f3af 10 quiz pass\u00e9s</span>'
    badges_html += '</div>'
    if "badge-gold" in badges_html or "badge-silver" in badges_html or "badge-bronze" in badges_html:
        st.markdown(badges_html, unsafe_allow_html=True)

    # Banni\u00e8re urgente anim\u00e9e
    if urgent > 0:
        st.markdown(f'<div class="big-badge">\U0001f525 {urgent} chapitre(s) \u00e0 r\u00e9viser aujourd\'hui !</div>', unsafe_allow_html=True)

    # Actions urgentes
    if urgent > 0:
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button(f"📖 Lancer la session d'étude ({urgent})", use_container_width=True):
                st.session_state.page = "matiere"
                st.session_state.matiere_id = None
                st.session_state.show_session = True
                st.rerun()
        with col2:
            if st.button(f"⚡ Tout valider ({urgent})", use_container_width=True):
                db = get_db()
                revision_service.valider_chapitres_urgents(db)
                db.close()
                st.success(f"{urgent} chapitres validés !")
                st.rerun()

    st.markdown("---")

    # Pomodoro Timer
    with st.expander("\u23f1\ufe0f Pomodoro (25 min travail / 5 min pause)"):
        if "pomodoro_start" not in st.session_state:
            st.session_state.pomodoro_start = None
            st.session_state.pomodoro_mode = "work"
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            if st.button("\u25b6\ufe0f D\u00e9marrer 25 min", use_container_width=True):
                st.session_state.pomodoro_start = datetime.now()
                st.session_state.pomodoro_mode = "work"
                st.rerun()
        with col_p2:
            if st.button("\u23f8\ufe0f Arr\u00eater", use_container_width=True):
                st.session_state.pomodoro_start = None
                st.rerun()
        if st.session_state.pomodoro_start:
            elapsed = (datetime.now() - st.session_state.pomodoro_start).total_seconds()
            total = 25*60 if st.session_state.pomodoro_mode == "work" else 5*60
            remaining = max(0, total - int(elapsed))
            mins, secs = divmod(remaining, 60)
            pct = min(1.0, elapsed / total)
            st.progress(pct)
            mode_label = "\U0001f4aa Travail" if st.session_state.pomodoro_mode == "work" else "\u2615 Pause"
            st.markdown(f"### {mode_label} — {mins:02d}:{secs:02d}")
            if remaining == 0:
                st.balloons()
                if st.session_state.pomodoro_mode == "work":
                    st.session_state.pomodoro_start = datetime.now()
                    st.session_state.pomodoro_mode = "break"
                else:
                    st.session_state.pomodoro_start = None
                st.rerun()

    st.markdown("---")

    # Chapitres urgents
    st.subheader("📋 À réviser aujourd'hui")
    db = get_db()
    urgents_chaps = [(c, c.matiere) for c in db.query(models.Chapitre).all() if cfg.diff_jours(c.date_prochaine) <= 0]
    urgents_chaps.sort(key=lambda x: cfg.diff_jours(x[0].date_prochaine))

    if not urgents_chaps:
        st.success("🎉 Tout est à jour ! Aucune révision en retard.")
    else:
        for chap, matiere in urgents_chaps:
            retard = cfg.diff_jours(chap.date_prochaine)
            badge_text, badge_color = status_badge(retard, chap.date_prochaine)

            with st.container(border=True):
                col1, col2, col3 = st.columns([4, 2, 1])
                with col1:
                    st.markdown(f"**{chap.nom}**")
                    st.caption(f"📖 {matiere.nom}  ·  J+{cfg.INTERVALLES_J[min(chap.niveau_actuel, 13)]}")
                    render_progress(chap.niveau_actuel)
                with col2:
                    st.markdown(f'<span style="color:{badge_color};font-size:0.9rem"> {badge_text}</span>',
                                unsafe_allow_html=True)
                with col3:
                    if st.button("✅", key=f"val_{chap.uid}", help="Valider ce chapitre"):
                        c = crud_service.obtenir_chapitre(db, matiere.id, chap.uid)
                        if c:
                            revision_service.valider_chapitre(db, c)
                        st.rerun()

    db.close()

    st.markdown("---")

    # Matières overview
    st.subheader("📖 Toutes les matières")
    db = get_db()
    matieres_all = crud_service.lister_matieres(db)

    for m in matieres_all:
        urg = sum(1 for c in m.chapitres if cfg.diff_jours(c.date_prochaine) <= 0)
        with st.container(border=True):
            col1, col2, col3 = st.columns([4, 2, 1])
            with col1:
                ue_tag = f" 📁 {m.ues[0].nom}" if m.ues else ""
                st.markdown(f"📖 **{m.nom}**{ue_tag}")
            with col2:
                st.caption(f"{len(m.chapitres)} ch.  " + (f"🔥 {urg}" if urg > 0 else ""))
            with col3:
                if st.button("Ouvrir", key=f"open_{m.id}"):
                    naviguer("matiere", m.id, m.nom)

    db.close()

    # Session d'étude (popup via expander)
    if st.session_state.get("show_session"):
        st.markdown("---")
        st.header("📖 Session d'étude")
        st.info("Parcourez vos chapitres un par un et validez-les.")
        db2 = get_db()
        urgents = [(c, c.matiere) for c in db2.query(models.Chapitre).all()
                   if cfg.diff_jours(c.date_prochaine) <= 0]
        urgents.sort(key=lambda x: cfg.diff_jours(x[0].date_prochaine))
        db2.close()

        if not urgents:
            st.success("🎉 Plus rien à réviser !")
            st.session_state.show_session = False
        else:
            progress = st.progress(0)
            for i, (chap, matiere) in enumerate(urgents):
                pct = (i + 1) / len(urgents)
                progress.progress(pct)

                with st.container(border=True):
                    st.markdown(f"### {i+1}. {chap.nom}")
                    st.caption(f"📖 {matiere.nom} · Niveau {chap.niveau_actuel} · J+{cfg.INTERVALLES_J[min(chap.niveau_actuel, 13)]}")
                    render_progress(chap.niveau_actuel)

                    if chap.notes:
                        st.info(chap.notes)

                    col1, col2 = st.columns([1, 1])
                    with col1:
                        if st.button(f"✅ Valider — je connais", key=f"session_ok_{chap.uid}", use_container_width=True):
                            db = get_db()
                            c = crud_service.obtenir_chapitre(db, matiere.id, chap.uid)
                            if c: revision_service.valider_chapitre(db, c)
                            db.close()
                            st.rerun()
                    with col2:
                        if st.button(f"📚 Pas encore — je repasse", key=f"session_ko_{chap.uid}", use_container_width=True):
                            pass  # skip, reste dans la liste

            progress.empty()
            if st.button("Terminer la session", use_container_width=True):
                st.session_state.show_session = False
                st.rerun()


# ══════════════════════════════════════════════════════════
# PAGE : MATIÈRE
# ══════════════════════════════════════════════════════════

elif st.session_state.page == "matiere" and st.session_state.matiere_id:
    matiere_id = st.session_state.matiere_id
    matiere_nom = st.session_state.matiere_nom

    db = get_db()
    matiere = crud_service.obtenir_matiere(db, matiere_id)
    if not matiere:
        db.close()
        st.error("Matière introuvable.")
        naviguer("dashboard")
        st.stop()

    chapitres = crud_service.lister_chapitres(db, matiere_id,
                                               st.session_state.get("filtre", "tous"),
                                               st.session_state.get("sort", "date_asc"),
                                               st.session_state.get("q_filtre", ""))

    nb_urg = sum(1 for c in chapitres if cfg.diff_jours(c.date_prochaine) <= 0)
    nb_mait = sum(1 for c in chapitres if c.niveau_actuel >= len(cfg.INTERVALLES_J) - 1)
    niv_moy = sum(c.niveau_actuel for c in chapitres) / max(len(chapitres), 1)

    st.title(matiere_nom)
    st.caption("Matière")

    # Stats bandeau
    cols = st.columns(4)
    with cols[0]:
        st.metric("📝 Chapitres", len(chapitres))
    with cols[1]:
        st.metric("🔥 À réviser", nb_urg)
    with cols[2]:
        st.metric("🏆 Maîtrisés", nb_mait)
    with cols[3]:
        st.metric("📊 Niveau moy.", f"{niv_moy:.1f}")

    st.markdown("---")

    # Filtres et tri
    col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
    with col1:
        filtre = st.selectbox("Filtre", ["tous", "urgent", "bientot", "ok", "maitrise"],
                              format_func=lambda x: {"tous": "Tous", "urgent": "🔥 Urgents",
                                                     "bientot": "⏰ Bientôt", "ok": "✅ À jour",
                                                     "maitrise": "🏆 Maîtrisés"}[x],
                              key="filtre_select")
        if filtre != st.session_state.get("filtre", "tous"):
            st.session_state.filtre = filtre
            st.rerun()
    with col2:
        sort = st.selectbox("Tri", ["date_asc", "date_desc", "level_asc", "level_desc", "name_asc", "name_desc"],
                            format_func=lambda x: {"date_asc": "📅 ↑ Date", "date_desc": "📅 ↓ Date",
                                                   "level_asc": "📊 ↑ Niveau", "level_desc": "📊 ↓ Niveau",
                                                   "name_asc": "🔤 ↑ Nom", "name_desc": "🔤 ↓ Nom"}[x],
                            key="sort_select")
        if sort != st.session_state.get("sort", "date_asc"):
            st.session_state.sort = sort
            st.rerun()
    with col3:
        q_f = st.text_input("🔍 Filtrer", key="q_filter", placeholder="Nom...", label_visibility="collapsed")
        if q_f != st.session_state.get("q_filtre", ""):
            st.session_state.q_filtre = q_f
            st.rerun()
    with col4:
        # Actions matière
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a:
            if st.button("✏️ Renommer", use_container_width=True):
                st.session_state.show_rename_mat = True
        with col_b:
            if st.button("🗑️ Supprimer", use_container_width=True):
                st.session_state.show_delete_mat = True
        with col_c:
            if st.button("📁 Assigner UE", use_container_width=True):
                st.session_state.show_assign_ue = True
        with col_d:
            if st.button("＋ Ajouter", use_container_width=True, type="primary"):
                st.session_state.show_add_chap = True

    # Rename matiere
    if st.session_state.get("show_rename_mat"):
        with st.expander("✏️ Renommer la matière", expanded=True):
            new_name = st.text_input("Nouveau nom", value=matiere_nom, key="rename_mat_input")
            if st.button("Renommer", key="rename_mat_btn") and new_name.strip() != matiere_nom:
                db = get_db()
                try:
                    crud_service.renommer_matiere(db, matiere_id, new_name.strip())
                    st.session_state.matiere_nom = new_name.strip()
                    st.success("Renommé !")
                    st.session_state.show_rename_mat = False
                    db.close()
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
                    db.close()

    # Delete matiere
    if st.session_state.get("show_delete_mat"):
        with st.expander("🗑️ Supprimer la matière", expanded=True):
            st.warning(f"Supprimer **{matiere_nom}** et ses {len(chapitres)} chapitres ? Cette action est IRRÉVERSIBLE.")
            if st.button("🗑️ Confirmer la suppression", key="delete_mat_btn", type="primary"):
                db = get_db()
                crud_service.supprimer_matiere(db, matiere_id)
                db.close()
                st.success(f"Matière « {matiere_nom} » supprimée.")
                naviguer("dashboard")

    # Assigner UE
    if st.session_state.get("show_assign_ue"):
        with st.expander("📁 Assigner à une UE", expanded=True):
            db = get_db()
            ues = crud_service.lister_ues(db)
            db.close()
            ue_options = ["Aucune"] + [ue.nom for ue in ues]
            current_ue = matiere.ues[0].nom if matiere.ues else "Aucune"
            selected_ue = st.selectbox("UE", ue_options,
                                       index=ue_options.index(current_ue) if current_ue in ue_options else 0,
                                       key="assign_ue_select")
            if st.button("Appliquer", key="assign_ue_btn"):
                db = get_db()
                crud_service.assigner_matiere_a_ue(db, matiere_id, selected_ue if selected_ue != "Aucune" else None)
                db.close()
                st.success("UE assignée !")
                st.session_state.show_assign_ue = False
                st.rerun()

    st.markdown("---")

    # Ajouter un chapitre
    if st.session_state.get("show_add_chap"):
        with st.expander("➕ Ajouter des chapitres", expanded=True):
            tab1, tab2 = st.tabs(["Simple", "Par lot"])
            with tab1:
                new_chap = st.text_input("Nom du chapitre", key="new_chap_simple")
                if st.button("Ajouter", key="add_chap_simple") and new_chap.strip():
                    db = get_db()
                    try:
                        crud_service.creer_chapitre(db, matiere_id, new_chap.strip())
                        st.success(f"« {new_chap} » ajouté !")
                        st.session_state.show_add_chap = False
                        db.close()
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
                        db.close()
            with tab2:
                batch_text = st.text_area("Un chapitre par ligne", height=120, key="batch_chaps")
                if st.button(f"Ajouter {len([l for l in batch_text.split(chr(10)) if l.strip()])} chapitres", key="add_chap_batch"):
                    noms = [l.strip() for l in batch_text.split("\n") if l.strip()]
                    if noms:
                        db = get_db()
                        crud_service.creer_chapitres_batch(db, matiere_id, noms)
                        db.close()
                        st.success(f"{len(noms)} chapitres ajoutés !")
                        st.session_state.show_add_chap = False
                        st.rerun()

    # Liste des chapitres
    # Grouper par méga-chapitre
    groupes = {}
    sans_groupe = []
    for c in chapitres:
        if c.mega_chapitre:
            groupes.setdefault(c.mega_chapitre, []).append(c)
        else:
            sans_groupe.append(c)

    # Méga-chapitres
    for mega, chaps in groupes.items():
        urg_mega = sum(1 for c in chaps if cfg.diff_jours(c.date_prochaine) <= 0)
        st.markdown(f"📂 **{mega}**  ({len(chaps)} ch.  {f'🔥 {urg_mega}' if urg_mega else ''})")
        for chap in chaps:
            _render_chapitre(chap, matiere_id)

    if groupes and sans_groupe:
        st.markdown("*Non groupés*")

    for chap in sans_groupe:
        _render_chapitre(chap, matiere_id)

    if not chapitres:
        st.info("📝 Aucun chapitre. Cliquez sur « Ajouter ».")

    db.close()


# ══════════════════════════════════════════════════════════
# PAGE : STATISTIQUES
# ══════════════════════════════════════════════════════════

elif st.session_state.page == "stats":
    st.title("Statistiques")

    db = get_db()
    chapitres_all = db.query(models.Chapitre).all()
    total = len(chapitres_all)
    urgent = sum(1 for c in chapitres_all if cfg.diff_jours(c.date_prochaine) <= 0)
    maitrise = sum(1 for c in chapitres_all if c.niveau_actuel >= len(cfg.INTERVALLES_J) - 1)
    nb_matieres = db.query(models.Matiere).count()
    pct_maitrise = int(maitrise / total * 100) if total > 0 else 0

    from models import Activite
    act_items = sorted(
        [(a.date, a.revisions or 0, a.quiz_reussis or 0, a.quiz_echoues or 0) for a in db.query(Activite).all()],
        key=lambda x: x[0], reverse=True,
    )
    auj = datetime.now().date()
    streak = 0
    for i in range(365):
        d = (auj - timedelta(days=i)).strftime("%Y-%m-%d")
        found = next((a for a in act_items if a[0] == d), None)
        if found and found[1] > 0:
            streak += 1
        else:
            break

    total_rev = sum(a[1] for a in act_items)
    total_quiz_r = sum(a[2] for a in act_items)
    total_quiz_e = sum(a[3] for a in act_items)
    total_quiz = total_quiz_r + total_quiz_e
    taux_quiz = int(total_quiz_r / max(total_quiz, 1) * 100)

    matieres = crud_service.lister_matieres(db)

    # Top stats
    cols = st.columns(3)
    with cols[0]:
        st.metric("🔥 Streak", f"{streak} jours")
    with cols[1]:
        st.metric("🎯 Quiz réussis", f"{taux_quiz}%", delta=f"{total_quiz_r}/{total_quiz}")
    with cols[2]:
        st.metric("✅ Révisions total", total_rev)

    st.markdown("---")

    # Par matière
    st.subheader("📖 Par matière")
    for m in matieres:
        chaps = m.chapitres
        if not chaps:
            continue
        urg = sum(1 for c in chaps if cfg.diff_jours(c.date_prochaine) <= 0)
        mait = sum(1 for c in chaps if c.niveau_actuel >= len(cfg.INTERVALLES_J) - 1)
        niv_moy = sum(c.niveau_actuel for c in chaps) / len(chaps)
        quiz_t = sum(len(c.historique_quiz) for c in chaps)
        quiz_c = sum(1 for c in chaps for h in c.historique_quiz if h.score >= 0.5)

        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                st.markdown(f"📖 **{m.nom}**")
                st.caption(f"{len(chaps)} ch. · 🔥 {urg} · 🏆 {mait} · Quiz {int(quiz_c/max(quiz_t,1)*100)}%")
            with col2:
                niv = int(niv_moy)
                render_progress(niv, 13)
                st.caption(f"Niv. moyen: {niv_moy:.1f}")
            with col3:
                if st.button("Ouvrir", key=f"stats_open_{m.id}"):
                    naviguer("matiere", m.id, m.nom)

    db.close()

    # Distribution des niveaux
    st.markdown("---")
    st.subheader("📊 Distribution des niveaux")
    from collections import Counter
    compteurs = Counter(c.niveau_actuel for c in chapitres_all)
    max_c = max(compteurs.values()) if compteurs else 1

    # Bar chart with Streamlit
    df_dist = pd.DataFrame({
        "Niveau": [f"J+{cfg.INTERVALLES_J[i] if i < 14 else '∞'}" for i in range(14)],
        "Chapitres": [compteurs.get(i, 0) for i in range(14)],
    })
    st.bar_chart(df_dist.set_index("Niveau"), use_container_width=True)

    # Heatmap d'activité (90 jours) — simplifiée
    st.markdown("---")
    st.subheader("📅 Activité — 30 derniers jours")
    heat_data = []
    for i in range(30):
        d = (auj - timedelta(days=29 - i))
        ds = d.strftime("%Y-%m-%d")
        found = next((a for a in act_items if a[0] == ds), None)
        rev = found[1] if found else 0
        heat_data.append({"date": d.strftime("%d/%m"), "révisions": rev})

    df_heat = pd.DataFrame(heat_data)
    st.bar_chart(df_heat.set_index("date"), use_container_width=True)

    # Graphique de progression (niveau moyen sur 30 jours)
    st.markdown("---")
    st.subheader("\U0001f4c8 Progression du niveau moyen")
    progression_data = []
    niv_cumul = 0
    count_cumul = 0
    for i in range(30):
        d = (auj - timedelta(days=29 - i))
        ds = d.strftime("%Y-%m-%d")
        rev_du_jour = next((a[1] for a in act_items if a[0] == ds), 0)
        if rev_du_jour > 0:
            niv_cumul += rev_du_jour
            count_cumul += 1
        progression_data.append({"date": d.strftime("%d/%m"), "niveau_moyen_cumul": niv_cumul / max(count_cumul, 1)})
    df_prog = pd.DataFrame(progression_data)
    st.line_chart(df_prog.set_index("date"), use_container_width=True)

    # Pr\u00e9diction de note IA
    st.markdown("---")
    st.subheader("\U0001f4c8 Pr\u00e9diction de note")
    ia = get_ia()
    if ia and maitrise > 0:
        if st.button("\U0001f9e0 Estimer ma note probable"):
            with st.spinner("\U0001f9e0 DeepSeek analyse..."):
                recap = f"Mati\u00e8res : {nb_matieres}, Chapitres : {total}, Ma\u00eetris\u00e9s : {maitrise} ({pct_maitrise}%), "
                recap += f"Quiz r\u00e9ussis : {taux_quiz}%, Streak : {streak} jours, "
                recap += f"Niveau moyen : {sum(c.niveau_actuel for c in chapitres_all)/max(total,1):.1f}/{len(cfg.INTERVALLES_J)-1}"
                try:
                    resp = ia._client().chat.completions.create(
                        model=cfg.DEEPSEEK_MODEL,
                        messages=[{"role":"system","content":"Expert en p\u00e9dagogie. Estime une note sur 20. R\u00e9ponds en 2 phrases max. Fran\u00e7ais."},
                                  {"role":"user","content":f"Statistiques d'un \u00e9tudiant : {recap}. Estime sa note probable sur 20."}],
                    )
                    st.info(resp.choices[0].message.content)
                except Exception as e:
                    st.error(f"Erreur IA : {e}")
    else:
        st.caption("N\u00e9cessite la cl\u00e9 API DeepSeek et des chapitres ma\u00eetris\u00e9s.")

    # Export Anki CSV
    st.markdown("---")
    st.subheader("\U0001f4cb Export Anki (CSV)")
    anki_data = []
    for c in chapitres_all:
        anki_data.append({"Front": c.nom, "Back": f"Niveau {c.niveau_actuel}/{len(cfg.INTERVALLES_J)-1} - Prochaine r\u00e9vision : {c.date_prochaine}"})
    df_anki = pd.DataFrame(anki_data)
    csv_anki = df_anki.to_csv(index=False)
    st.download_button("\U0001f4e5 T\u00e9l\u00e9charger pour Anki", csv_anki, "studytracker_anki.csv", "text/csv", use_container_width=True)
    st.caption("Importe ce CSV dans Anki : Fichier > Importer > Format CSV")


# ══════════════════════════════════════════════════════════
# PAGE : CALENDRIER
# ══════════════════════════════════════════════════════════

elif st.session_state.page == "calendar":
    st.title("Calendrier des révisions")

    db = get_db()
    chapitres_all = db.query(models.Chapitre).all()

    auj = datetime.now().date()
    from collections import defaultdict

    par_jour = defaultdict(list)
    for c in chapitres_all:
        try:
            d = datetime.strptime(c.date_prochaine, "%Y-%m-%d").date()
        except ValueError:
            continue
        diff = (d - auj).days
        if -7 <= diff <= 30:
            par_jour[c.date_prochaine].append((c, diff, c.matiere.nom if c.matiere else "?"))

    db.close()

    if not par_jour:
        st.info("📅 Aucune révision prévue dans les 30 prochains jours.")
    else:
        for date_str in sorted(par_jour.keys()):
            items = par_jour[date_str]
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            diff = (d - auj).days

            if diff < 0:
                emoji, txt = "⚠️", f"**Retard — {d.strftime('%A %d %B')}** ({abs(diff)}j)"
            elif diff == 0:
                emoji, txt = "🔥", f"**Aujourd'hui — {d.strftime('%A %d %B')}**"
            elif diff == 1:
                emoji, txt = "📅", f"**Demain — {d.strftime('%A %d %B')}**"
            else:
                emoji, txt = "📅", f"{d.strftime('%A %d %B')} — dans {diff}j"

            with st.container(border=True):
                st.markdown(f"{emoji}  {txt}  ({len(items)})")
                st.divider()
                for chap, diff_item, mat_nom in items:
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.markdown(f"📝 **{chap.nom}**")
                        st.caption(f"📖 {mat_nom} · Niv. {chap.niveau_actuel} · J+{cfg.INTERVALLES_J[min(chap.niveau_actuel, 13)]}")
                        render_progress(chap.niveau_actuel)
                    with col2:
                        if st.button("Ouvrir", key=f"cal_{chap.uid}"):
                            db3 = get_db()
                            mat = db3.query(models.Matiere).filter(models.Matiere.nom == mat_nom).first()
                            if mat:
                                db3.close()
                                naviguer("matiere", mat.id, mat.nom)
                            else:
                                db3.close()

# ══════════════════════════════════════════════════════════
# PAGE : EXAMEN BLANC
# ══════════════════════════════════════════════════════════

elif st.session_state.page == "examen":
    st.title("\U0001f393 Examen blanc")
    st.caption("L'IA pioche dans tes cours et crée une épreuve sur mesure.")

    ia = get_ia()
    if not ia:
        st.warning("\u26a0\ufe0f Configure ta cl\u00e9 API DeepSeek dans les \u2699\ufe0f Param\u00e8tres pour utiliser l'examen blanc.")
    else:
        # R\u00e9cup\u00e9rer les chapitres avec texte cache (PDF analys\u00e9s)
        db = get_db()
        chaps_avec_texte = [
            (c, c.matiere.nom) for c in db.query(models.Chapitre).all()
            if c.texte_cache and c.texte_cache.strip()
        ]
        db.close()

        if len(chaps_avec_texte) < 2:
            st.info("\U0001f4c4 Il faut au moins 2 chapitres avec des PDF analys\u00e9s pour g\u00e9n\u00e9rer un examen.\n\n"
                    "Ajoute des PDF \u00e0 tes chapitres, puis clique \u00ab \u2728 Analyser \u00bb avant de g\u00e9n\u00e9rer la fiche.")
        else:
            col1, col2 = st.columns([2, 1])
            with col1:
                nb_questions = st.slider("Nombre de questions", 3, 15, 8)
            with col2:
                if st.button("\U0001f52c G\u00e9n\u00e9rer l'examen", use_container_width=True, type="primary"):
                    st.session_state.exam_generated = False
                    with st.spinner(f"\U0001f9e0 DeepSeek cr\u00e9e un examen de {nb_questions} questions..."):
                        import random
                        # Piocher des chapitres al\u00e9atoires
                        selection = random.sample(chaps_avec_texte, min(len(chaps_avec_texte), max(3, nb_questions // 2)))
                        # Concat\u00e9ner le texte des chapitres s\u00e9lectionn\u00e9s
                        contexte_exam = ""
                        matieres_exam = set()
                        for c, mat_nom in selection:
                            contexte_exam += f"\n\n=== {c.nom} ({mat_nom}) ===\n{c.texte_cache[:4000]}"
                            matieres_exam.add(mat_nom)

                        st.session_state.exam_contexte = contexte_exam

                        try:
                            questions = ia.generer_questions(
                                f"Examen - {', '.join(matieres_exam)}",
                                "Examen blanc",
                                contexte_exam,
                                nb=nb_questions,
                            )
                            st.session_state.exam_questions = questions
                            st.session_state.exam_generated = True
                        except Exception as e:
                            st.error(f"Erreur IA : {e}")

            # Afficher l'examen
            if st.session_state.get("exam_generated") and st.session_state.get("exam_questions"):
                st.markdown("---")
                st.subheader("\U0001f4dd \u00c9preuve")
                questions = st.session_state.exam_questions

                reponses = []
                for i, q in enumerate(questions):
                    rep = st.text_area(f"**Q{i+1}.** {q}", key=f"exam_q_{i}", height=80,
                                       placeholder="Ta r\u00e9ponse...")
                    reponses.append(rep)

                if st.button("\U0001f4ca Corriger l'examen", use_container_width=True, type="primary"):
                    with st.spinner("\U0001f9e0 DeepSeek \u00e9value tes r\u00e9ponses..."):
                        try:
                            eval_result = ia.evaluer_reponses(
                                "Examen blanc", "Toutes mati\u00e8res",
                                questions, reponses,
                                st.session_state.get("exam_contexte", ""),
                            )
                            score = eval_result.get("score_num", 0)
                            verdict = eval_result.get("verdict", "?")

                            st.markdown("---")
                            st.markdown(f"## \U0001f3af R\u00e9sultat : {int(score * 100)}%")
                            if verdict == "r\u00e9ussi":
                                st.success(f"\u2705 **{verdict.upper()}** — Bravo !")
                            else:
                                st.warning(f"\U0001f4da **{verdict.upper()}** — Continue \u00e0 r\u00e9viser.")

                            st.markdown(eval_result.get("message", ""))
                            st.markdown("### D\u00e9tail par question :")
                            for j, r in enumerate(eval_result.get("resultats", [])):
                                emoji = {"correct": "\u2705", "partiel": "\u26a0\ufe0f", "incorrect": "\u274c"}.get(r.get("score"), "")
                                st.markdown(f"{emoji} **Q{j+1}** : {r.get('feedback', '')}")

                            st.balloons() if score >= 0.7 else None
                        except Exception as e:
                            st.error(f"Erreur IA : {e}")
            elif st.session_state.get("exam_generated"):
                st.success(f"\u2705 {len(st.session_state.exam_questions)} questions g\u00e9n\u00e9r\u00e9es ! R\u00e9ponds ci-dessus.")


st.markdown("---")
st.caption("StudyTracker V2 — App de révision espacée  ·  Propulsé par Streamlit")
