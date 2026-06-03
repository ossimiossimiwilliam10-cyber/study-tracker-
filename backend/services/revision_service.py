"""Service de répétition espacée — logique métier cœur."""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

import config
from models import Chapitre, Activite


def valider_chapitre(db: Session, chap: Chapitre) -> Chapitre:
    """
    Valide la révision d'un chapitre :
    - Monte d'un niveau
    - Recalcule la prochaine date avec planification intelligente
    - Enregistre l'activité
    """
    niv = chap.niveau_actuel
    if niv < len(config.INTERVALLES_J) - 1:
        niv += 1
    chap.niveau_actuel = niv

    # Calculer la date idéale
    j = config.INTERVALLES_J[min(niv, len(config.INTERVALLES_J) - 1)]
    date_ideale = (datetime.now() + timedelta(days=j)).strftime("%Y-%m-%d")

    # Planification intelligente : éviter les jours surchargés
    compteur = _compter_revisions_par_jour(db)
    date_finale = config.trouver_meilleur_jour(date_ideale, compteur)
    chap.date_prochaine = date_finale

    # Enregistrer l'activité
    enregistrer_activite(db, revisions=1)

    db.commit()
    db.refresh(chap)
    return chap


def valider_chapitres_urgents(db: Session) -> int:
    """Valide tous les chapitres urgents. Retourne le nombre validé."""
    from config import diff_jours

    chapitres = db.query(Chapitre).all()
    urgents = [c for c in chapitres if diff_jours(c.date_prochaine) <= 0]
    for chap in urgents:
        valider_chapitre(db, chap)
    return len(urgents)


def reinitialiser_chapitre(db: Session, chap: Chapitre) -> Chapitre:
    """Réinitialise un chapitre au niveau 0."""
    chap.niveau_actuel = 0
    chap.date_prochaine = (
        datetime.now() + timedelta(days=config.INTERVALLES_J[0])
    ).strftime("%Y-%m-%d")
    chap.quiz_cache = None
    chap.qcm_cache = None
    chap.historique_quiz.clear()
    db.commit()
    db.refresh(chap)
    return chap


def callback_quiz(
    db: Session, chap: Chapitre, score: float, reussi: bool, type_quiz: str = "qcm"
) -> Chapitre:
    """
    Enregistre un résultat de quiz :
    - Ajoute à l'historique
    - Si échec : recule d'un niveau (min 0)
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    from models import HistoriqueQuiz

    entry = HistoriqueQuiz(
        chapitre_id=chap.id,
        date=now,
        score=score,
        type=type_quiz,
        reussi=bool(reussi),
    )
    db.add(entry)

    enregistrer_activite(
        db, quiz_reussis=1 if reussi else 0, quiz_echoues=0 if reussi else 1
    )

    # Pénalité : si échec, reculer d'un niveau
    if not reussi and chap.niveau_actuel > 0:
        chap.niveau_actuel -= 1
        j = config.INTERVALLES_J[
            min(chap.niveau_actuel, len(config.INTERVALLES_J) - 1)
        ]
        date_ideale = (datetime.now() + timedelta(days=j)).strftime("%Y-%m-%d")
        compteur = _compter_revisions_par_jour(db)
        chap.date_prochaine = config.trouver_meilleur_jour(date_ideale, compteur)

    db.commit()
    db.refresh(chap)
    return chap


# ══════════════════════════════════════════════════════════
# Activité
# ══════════════════════════════════════════════════════════

def enregistrer_activite(db: Session, revisions: int = 0, quiz_reussis: int = 0, quiz_echoues: int = 0):
    """Enregistre une activité quotidienne."""
    auj = datetime.now().strftime("%Y-%m-%d")
    act = db.query(Activite).filter(Activite.date == auj).first()
    if not act:
        act = Activite(date=auj, revisions=0, quiz_reussis=0, quiz_echoues=0)
        db.add(act)
        db.flush()
    act.revisions = (act.revisions or 0) + revisions
    act.quiz_reussis = (act.quiz_reussis or 0) + quiz_reussis
    act.quiz_echoues = (act.quiz_echoues or 0) + quiz_echoues
    db.commit()


def _compter_revisions_par_jour(db: Session) -> dict[str, int]:
    """Retourne {date_str: nb_revisions} à partir de la BDD."""
    from collections import defaultdict

    compteur = defaultdict(int)
    for chap in db.query(Chapitre).all():
        d = chap.date_prochaine
        if d:
            compteur[d] += 1
    return dict(compteur)
