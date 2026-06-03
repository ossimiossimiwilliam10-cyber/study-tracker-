"""Modèles SQLAlchemy — StudyTracker V2."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    Text,
    ForeignKey,
    DateTime,
    Date,
    Table,
    JSON,
)
from sqlalchemy.orm import relationship

from database import Base

# ══════════════════════════════════════════════════════════
# Table d'association Matière <-> UE
# ══════════════════════════════════════════════════════════

matiere_ue = Table(
    "matiere_ue",
    Base.metadata,
    Column("matiere_id", Integer, ForeignKey("matieres.id", ondelete="CASCADE"), primary_key=True),
    Column("ue_id", Integer, ForeignKey("ues.id", ondelete="CASCADE"), primary_key=True),
)


# ══════════════════════════════════════════════════════════
# Modèles
# ══════════════════════════════════════════════════════════

class Matiere(Base):
    """Une matière (ex: Maths, Physique, Histoire...)."""

    __tablename__ = "matieres"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nom = Column(String(200), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now)

    # Relations
    chapitres: list["Chapitre"] = relationship(
        "Chapitre", back_populates="matiere", cascade="all, delete-orphan",
        order_by="Chapitre.ordre",
    )
    ues: list["UE"] = relationship(
        "UE", secondary=matiere_ue, back_populates="matieres",
    )


class UE(Base):
    """Une Unité d'Enseignement regroupant plusieurs matières."""

    __tablename__ = "ues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nom = Column(String(200), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now)

    # Relations
    matieres: list["Matiere"] = relationship(
        "Matiere", secondary=matiere_ue, back_populates="ues",
    )


class Chapitre(Base):
    """Un chapitre à réviser au sein d'une matière."""

    __tablename__ = "chapitres"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uid = Column(String(8), unique=True, default=lambda: str(uuid.uuid4())[:8], index=True)
    matiere_id = Column(Integer, ForeignKey("matieres.id", ondelete="CASCADE"), nullable=False, index=True)
    nom = Column(String(200), nullable=False)
    ordre = Column(Integer, default=0)
    trashed = Column(Boolean, default=False)  # Corbeille

    # Répétition espacée
    niveau_actuel = Column(Integer, default=0)
    date_prochaine = Column(String(10), default=lambda: datetime.now().strftime("%Y-%m-%d"))

    # Fichiers & liens
    fichiers_attaches = Column(JSON, default=list)  # [{"nom": "...", "chemin": "..."}, ...]
    video_youtube = Column(String(500), nullable=True)

    # Regroupement
    mega_chapitre = Column(String(200), nullable=True)

    # Contenu
    notes = Column(Text, default="")

    # IA (cachés pour plus tard)
    fiche_ia = Column(Text, nullable=True)
    texte_cache = Column(Text, nullable=True)
    quiz_cache = Column(JSON, nullable=True)
    qcm_cache = Column(JSON, nullable=True)

    # Relations
    matiere: Matiere = relationship("Matiere", back_populates="chapitres")
    historique_quiz: list["HistoriqueQuiz"] = relationship(
        "HistoriqueQuiz", back_populates="chapitre", cascade="all, delete-orphan",
        order_by="HistoriqueQuiz.date.desc()",
    )

    def to_dict(self) -> dict:
        """Sérialise le chapitre en dict (compatible V1)."""
        return {
            "id": self.uid,
            "nom": self.nom,
            "niveau_actuel": self.niveau_actuel,
            "date_prochaine": self.date_prochaine,
            "fichiers_attaches": self.fichiers_attaches or [],
            "mega_chapitre": self.mega_chapitre,
            "historique_quiz": [h.to_dict() for h in self.historique_quiz],
            "quiz_cache": self.quiz_cache,
            "qcm_cache": self.qcm_cache,
            "fiche_ia": self.fiche_ia,
            "notes": self.notes or "",
            "texte_cache": self.texte_cache,
            "video_youtube": self.video_youtube,
        }


class HistoriqueQuiz(Base):
    """Historique d'un quiz passé sur un chapitre."""

    __tablename__ = "historique_quiz"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chapitre_id = Column(Integer, ForeignKey("chapitres.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(String(16), nullable=False)  # "YYYY-MM-DD HH:MM"
    score = Column(Float, default=0.0)  # 0.0 à 1.0
    type = Column(String(10), default="qcm")  # "qcm" | "ouvert"
    reussi = Column(Boolean, default=False)

    # Relations
    chapitre: Chapitre = relationship("Chapitre", back_populates="historique_quiz")

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "score": self.score,
            "type": self.type,
            "reussi": self.reussi,
        }


class Activite(Base):
    """Activité quotidienne (révisions, quiz)."""

    __tablename__ = "activites"

    date = Column(String(10), primary_key=True)  # "YYYY-MM-DD"
    revisions = Column(Integer, default=0)
    quiz_reussis = Column(Integer, default=0)
    quiz_echoues = Column(Integer, default=0)

    def to_dict(self) -> dict:
        return {
            "revisions": self.revisions,
            "quiz_reussis": self.quiz_reussis,
            "quiz_echoues": self.quiz_echoues,
        }


class Parametre(Base):
    """Préférences utilisateur (clé/valeur)."""

    __tablename__ = "parametres"

    cle = Column(String(100), primary_key=True)
    valeur = Column(String(500), nullable=True)

    @staticmethod
    def creer_defauts(db):
        """Insère les paramètres par défaut s'ils n'existent pas."""
        defauts = {
            "theme": "dark",
            "notifications_enabled": "true",
            "quiz_timer_enabled": "true",
            "quiz_timer_seconds": "120",
            "auto_fiche_threshold": "7",
            "sort_mode": "date_asc",
            "filtre_statut": "tous",
            "pomodoro_work": str(25 * 60),
            "pomodoro_break": str(5 * 60),
        }
        for cle, valeur in defauts.items():
            if not db.query(Parametre).filter(Parametre.cle == cle).first():
                db.add(Parametre(cle=cle, valeur=valeur))
        db.commit()
