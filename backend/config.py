"""Constantes, configuration et algorithme de répétition espacée."""

import os
from datetime import datetime, timedelta
from collections import defaultdict

# ── Base directory ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Intervalles de répétition espacée (14 niveaux, J+1 à J+2190 / 6 ans) ──
INTERVALLES_J: list[int] = [
    1, 3, 7, 14, 30, 60, 90, 180, 365, 730, 1095, 1460, 1825, 2190,
]

# ── Fichiers / dossiers ──
DOSSIER_DATA = os.path.join(BASE_DIR, "data")
DOSSIER_BACKUPS = os.path.join(BASE_DIR, "backups")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(DOSSIER_DATA, 'studytracker.db')}",
)

# ── Répétition espacée intelligente ──
MAX_REVISIONS_PAR_JOUR: int = 5
ETALEMENT_INITIAL: int = 3

# ── Polices (pour les exports / futurs rendus) ──
FONT_FAMILY: str = "Segoe UI"
FONT_MONO: str = "Consolas"

# ── Pomodoro (valeurs par défaut) ──
POMODORO_WORK: int = 25 * 60
POMODORO_BREAK: int = 5 * 60

# ── Niveaux : couleurs pour représentation visuelle ──
LEVEL_COLORS: list[str] = [
    "#f87171", "#fb923c", "#fbbf24", "#facc15", "#a3e635",
    "#34d399", "#2dd4bf", "#22d3ee", "#60a5fa", "#818cf8",
    "#a78bfa", "#c084fc", "#f472b6", "#fb7185",
]

os.makedirs(DOSSIER_DATA, exist_ok=True)
os.makedirs(DOSSIER_BACKUPS, exist_ok=True)


# ══════════════════════════════════════════════════════════
# FONCTIONS UTILITAIRES (stdlib uniquement)
# ══════════════════════════════════════════════════════════

def couleur_niveau(actuel: int, max_niv: int = 13) -> str:
    """Retourne une couleur hex représentant le niveau actuel."""
    idx = min(int(actuel / max(max_niv, 1) * (len(LEVEL_COLORS) - 1)), len(LEVEL_COLORS) - 1)
    return LEVEL_COLORS[idx]


def diff_jours(date_str: str) -> int:
    """Jours entre une date et aujourd'hui (négatif = passé)."""
    try:
        return (datetime.strptime(date_str, "%Y-%m-%d").date() - datetime.now().date()).days
    except (ValueError, TypeError) as e:
        raise ValueError(f"Format de date invalide '{date_str}': {e}")


def parser_date(date_str: str, fmt: str = "%Y-%m-%d") -> datetime | None:
    """Parse une date, retourne None si invalide."""
    try:
        return datetime.strptime(date_str, fmt).date()
    except (ValueError, TypeError):
        return None


def date_aujourdhui() -> str:
    """Retourne la date du jour au format YYYY-MM-DD."""
    return datetime.now().strftime("%Y-%m-%d")


# ══════════════════════════════════════════════════════════
# PLANIFICATION INTELLIGENTE
# ══════════════════════════════════════════════════════════

def compter_revisions_par_jour(
    compteur_existant: dict[str, int] | None = None,
) -> dict[str, int]:
    """
    Compte les révisions par date.
    `compteur_existant` est un dict {date_str: nb_revisions} déjà calculé.
    """
    return compteur_existant or {}


def trouver_meilleur_jour(
    date_ideale: str,
    compteur_par_jour: dict[str, int],
    max_par_jour: int | None = None,
) -> str:
    """
    Trouve le meilleur jour autour de date_ideale avec le moins de révisions.
    Cherche dans une fenêtre de ±3 jours.
    """
    if max_par_jour is None:
        max_par_jour = MAX_REVISIONS_PAR_JOUR

    base = datetime.strptime(date_ideale, "%Y-%m-%d").date()

    for offset in range(0, 4):
        for direction in (1, -1) if offset > 0 else (1,):
            candidat = base + timedelta(days=offset * direction)
            ds = candidat.strftime("%Y-%m-%d")
            if compteur_par_jour.get(ds, 0) < max_par_jour:
                return ds

    # Si tout est plein, prendre le jour le moins chargé
    return min(
        (
            compteur_par_jour.get((base + timedelta(days=i)).strftime("%Y-%m-%d"), 0),
            (base + timedelta(days=i)).strftime("%Y-%m-%d"),
        )
        for i in range(-3, 4)
    )[1]
