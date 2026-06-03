"""Service CRUD — matières, UEs, chapitres."""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from models import Matiere, UE, Chapitre, HistoriqueQuiz
import config


# ══════════════════════════════════════════════════════════
# Matières
# ══════════════════════════════════════════════════════════

def lister_matieres(db: Session) -> list[Matiere]:
    return db.query(Matiere).order_by(Matiere.nom).all()


def creer_matiere(db: Session, nom: str, ue_nom: Optional[str] = None) -> Matiere:
    """Crée une matière, optionnellement assignée à une UE."""
    # Vérifier doublons
    existant = db.query(Matiere).filter(Matiere.nom == nom).first()
    if existant:
        raise ValueError(f"La matière « {nom} » existe déjà.")

    matiere = Matiere(nom=nom)
    db.add(matiere)
    db.flush()

    if ue_nom:
        ue = db.query(UE).filter(UE.nom == ue_nom).first()
        if not ue:
            ue = UE(nom=ue_nom)
            db.add(ue)
            db.flush()
        matiere.ues.append(ue)

    db.commit()
    db.refresh(matiere)
    return matiere


def obtenir_matiere(db: Session, matiere_id: int) -> Matiere | None:
    return db.query(Matiere).filter(Matiere.id == matiere_id).first()


def renommer_matiere(db: Session, matiere_id: int, nouveau_nom: str) -> Matiere:
    matiere = db.query(Matiere).filter(Matiere.id == matiere_id).first()
    if not matiere:
        raise ValueError("Matière introuvable.")
    existant = db.query(Matiere).filter(Matiere.nom == nouveau_nom).first()
    if existant and existant.id != matiere_id:
        raise ValueError(f"« {nouveau_nom} » existe déjà.")
    matiere.nom = nouveau_nom
    db.commit()
    db.refresh(matiere)
    return matiere


def supprimer_matiere(db: Session, matiere_id: int) -> bool:
    matiere = db.query(Matiere).filter(Matiere.id == matiere_id).first()
    if not matiere:
        return False
    db.delete(matiere)
    db.commit()
    return True


# ══════════════════════════════════════════════════════════
# UEs
# ══════════════════════════════════════════════════════════

def lister_ues(db: Session) -> list[UE]:
    return db.query(UE).order_by(UE.nom).all()


def creer_ue(db: Session, nom: str) -> UE:
    existant = db.query(UE).filter(UE.nom == nom).first()
    if existant:
        raise ValueError(f"L'UE « {nom} » existe déjà.")
    ue = UE(nom=nom)
    db.add(ue)
    db.commit()
    db.refresh(ue)
    return ue


def renommer_ue(db: Session, ue_id: int, nouveau_nom: str) -> UE:
    ue = db.query(UE).filter(UE.id == ue_id).first()
    if not ue:
        raise ValueError("UE introuvable.")
    ue.nom = nouveau_nom
    db.commit()
    db.refresh(ue)
    return ue


def supprimer_ue(db: Session, ue_id: int) -> bool:
    ue = db.query(UE).filter(UE.id == ue_id).first()
    if not ue:
        return False
    db.delete(ue)
    db.commit()
    return True


def assigner_matiere_a_ue(db: Session, matiere_id: int, ue_nom: Optional[str]) -> Matiere:
    matiere = db.query(Matiere).filter(Matiere.id == matiere_id).first()
    if not matiere:
        raise ValueError("Matière introuvable.")

    # Retirer de toutes les UEs actuelles
    matiere.ues.clear()

    if ue_nom:
        ue = db.query(UE).filter(UE.nom == ue_nom).first()
        if not ue:
            ue = UE(nom=ue_nom)
            db.add(ue)
            db.flush()
        matiere.ues.append(ue)

    db.commit()
    db.refresh(matiere)
    return matiere


# ══════════════════════════════════════════════════════════
# Chapitres
# ══════════════════════════════════════════════════════════

def lister_chapitres(
    db: Session,
    matiere_id: int,
    filtre_statut: str = "tous",
    sort_mode: str = "date_asc",
    filtre_texte: str = "",
) -> list[Chapitre]:
    """Liste les chapitres d'une matière avec tri et filtres."""
    chapitres = (
        db.query(Chapitre)
        .filter(Chapitre.matiere_id == matiere_id)
        .order_by(Chapitre.ordre, Chapitre.nom)
        .all()
    )

    # Filtre par statut
    if filtre_statut == "urgent":
        chapitres = [c for c in chapitres if config.diff_jours(c.date_prochaine) <= 0]
    elif filtre_statut == "bientot":
        chapitres = [c for c in chapitres if 0 < config.diff_jours(c.date_prochaine) <= 3]
    elif filtre_statut == "ok":
        chapitres = [c for c in chapitres if config.diff_jours(c.date_prochaine) > 3]
    elif filtre_statut == "maitrise":
        chapitres = [c for c in chapitres if c.niveau_actuel >= len(config.INTERVALLES_J) - 1]

    # Filtre texte
    if filtre_texte:
        ft = filtre_texte.lower()
        chapitres = [c for c in chapitres if ft in c.nom.lower() or ft in (c.notes or "").lower()]

    # Tri
    reverse = sort_mode.endswith("_desc")
    if sort_mode.startswith("date"):
        chapitres.sort(key=lambda c: c.date_prochaine, reverse=reverse)
    elif sort_mode.startswith("level"):
        chapitres.sort(key=lambda c: c.niveau_actuel, reverse=reverse)
    elif sort_mode.startswith("name"):
        chapitres.sort(key=lambda c: c.nom.lower(), reverse=reverse)

    return chapitres


def creer_chapitre(
    db: Session,
    matiere_id: int,
    nom: str,
    mega_chapitre: Optional[str] = None,
    fichier_attache: Optional[str] = None,
    video_youtube: Optional[str] = None,
    notes: str = "",
) -> Chapitre:
    """Crée un chapitre. Le chapitre démarre à la date du jour (niveau 0)."""
    matiere = db.query(Matiere).filter(Matiere.id == matiere_id).first()
    if not matiere:
        raise ValueError("Matière introuvable.")

    existant = db.query(Chapitre).filter(
        Chapitre.matiere_id == matiere_id, Chapitre.nom == nom
    ).first()
    if existant:
        raise ValueError(f"Le chapitre « {nom} » existe déjà dans cette matière.")

    # Déterminer l'ordre
    max_ordre = db.query(func.max(Chapitre.ordre)).filter(
        Chapitre.matiere_id == matiere_id
    ).scalar() or 0

    chap = Chapitre(
        matiere_id=matiere_id,
        nom=nom,
        ordre=max_ordre + 1,
        niveau_actuel=0,
        date_prochaine=datetime.now().strftime("%Y-%m-%d"),
        mega_chapitre=mega_chapitre,
        fichier_attache=fichier_attache,
        video_youtube=video_youtube,
        notes=notes,
    )
    db.add(chap)
    db.commit()
    db.refresh(chap)
    return chap


def creer_chapitres_batch(db: Session, matiere_id: int, noms: list[str]) -> list[Chapitre]:
    """Crée plusieurs chapitres en lot."""
    chapitres = []
    for nom in noms:
        try:
            chap = creer_chapitre(db, matiere_id, nom.strip())
            chapitres.append(chap)
        except ValueError:
            pass  # Ignore les doublons
    return chapitres


def obtenir_chapitre(db: Session, matiere_id: int, chap_uid: str) -> Chapitre | None:
    return db.query(Chapitre).filter(
        Chapitre.matiere_id == matiere_id, Chapitre.uid == chap_uid
    ).first()


def renommer_chapitre(db: Session, matiere_id: int, chap_uid: str, nouveau_nom: str) -> Chapitre:
    chap = obtenir_chapitre(db, matiere_id, chap_uid)
    if not chap:
        raise ValueError("Chapitre introuvable.")
    existant = db.query(Chapitre).filter(
        Chapitre.matiere_id == matiere_id,
        Chapitre.nom == nouveau_nom,
        Chapitre.uid != chap_uid,
    ).first()
    if existant:
        raise ValueError(f"Le chapitre « {nouveau_nom} » existe déjà.")
    chap.nom = nouveau_nom
    db.commit()
    db.refresh(chap)
    return chap


def supprimer_chapitre(db: Session, matiere_id: int, chap_uid: str) -> bool:
    chap = obtenir_chapitre(db, matiere_id, chap_uid)
    if not chap:
        return False
    db.delete(chap)
    db.commit()
    return True


def deplacer_chapitre(db: Session, matiere_id: int, chap_uid: str, matiere_dst_id: int) -> Chapitre:
    chap = obtenir_chapitre(db, matiere_id, chap_uid)
    if not chap:
        raise ValueError("Chapitre introuvable.")
    matiere_dst = db.query(Matiere).filter(Matiere.id == matiere_dst_id).first()
    if not matiere_dst:
        raise ValueError("Matière de destination introuvable.")
    chap.matiere_id = matiere_dst_id
    # Recalculer l'ordre dans la matière de destination
    max_ordre = db.query(func.max(Chapitre.ordre)).filter(
        Chapitre.matiere_id == matiere_dst_id
    ).scalar() or 0
    chap.ordre = max_ordre + 1
    db.commit()
    db.refresh(chap)
    return chap


def dupliquer_chapitre(db: Session, matiere_id: int, chap_uid: str) -> Chapitre:
    chap = obtenir_chapitre(db, matiere_id, chap_uid)
    if not chap:
        raise ValueError("Chapitre introuvable.")
    nouveau = Chapitre(
        matiere_id=matiere_id,
        nom=f"{chap.nom} (copie)",
        ordre=chap.ordre + 1,
        niveau_actuel=0,
        date_prochaine=datetime.now().strftime("%Y-%m-%d"),
        mega_chapitre=chap.mega_chapitre,
        fichier_attache=chap.fichier_attache,
        video_youtube=chap.video_youtube,
        notes=chap.notes,
    )
    db.add(nouveau)
    db.commit()
    db.refresh(nouveau)
    return nouveau


def assigner_mega(db: Session, matiere_id: int, chap_uid: str, mega_nom: Optional[str]) -> Chapitre:
    chap = obtenir_chapitre(db, matiere_id, chap_uid)
    if not chap:
        raise ValueError("Chapitre introuvable.")
    chap.mega_chapitre = mega_nom
    db.commit()
    db.refresh(chap)
    return chap


def monter_chapitre(db: Session, matiere_id: int, chap_uid: str) -> bool:
    """Monte le chapitre (décrémente l'ordre)."""
    chap = obtenir_chapitre(db, matiere_id, chap_uid)
    if not chap:
        return False
    prev = (
        db.query(Chapitre)
        .filter(Chapitre.matiere_id == matiere_id, Chapitre.ordre < chap.ordre)
        .order_by(Chapitre.ordre.desc())
        .first()
    )
    if prev:
        chap.ordre, prev.ordre = prev.ordre, chap.ordre
        db.commit()
        return True
    return False


def descendre_chapitre(db: Session, matiere_id: int, chap_uid: str) -> bool:
    """Descend le chapitre (incrémente l'ordre)."""
    chap = obtenir_chapitre(db, matiere_id, chap_uid)
    if not chap:
        return False
    next_c = (
        db.query(Chapitre)
        .filter(Chapitre.matiere_id == matiere_id, Chapitre.ordre > chap.ordre)
        .order_by(Chapitre.ordre.asc())
        .first()
    )
    if next_c:
        chap.ordre, next_c.ordre = next_c.ordre, chap.ordre
        db.commit()
        return True
    return False


def editer_notes(db: Session, matiere_id: int, chap_uid: str, notes: str) -> Chapitre:
    chap = obtenir_chapitre(db, matiere_id, chap_uid)
    if not chap:
        raise ValueError("Chapitre introuvable.")
    chap.notes = notes
    db.commit()
    db.refresh(chap)
    return chap
