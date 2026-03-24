"""
Gestion de la base de données SQLite pour le tracking des clips traités.
Évite les doublons et conserve l'historique du pipeline.
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from enum import Enum
from loguru import logger

from src.utils.helpers import load_config


class ClipStatus(Enum):
    """États possibles d'un clip dans le pipeline."""
    PENDING     = "pending"      # En attente de traitement
    DOWNLOADING = "downloading"  # Téléchargement en cours
    PROCESSING  = "processing"   # Traitement vidéo en cours
    COMPLETED   = "completed"    # Traitement terminé avec succès
    FAILED      = "failed"       # Échec du traitement
    SKIPPED     = "skipped"      # Ignoré (critères non remplis)


class Database:
    """
    Interface SQLite pour persister l'état du pipeline.
    
    Tables :
    - clips        : Historique de tous les clips rencontrés
    - pipeline_runs: Historique des exécutions du pipeline
    """
    
    def __init__(self):
        self.config = load_config()
        db_path = Path(self.config["storage"]["db_path"])
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.db_path = db_path
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Crée une connexion SQLite avec les paramètres optimaux."""
        conn = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        conn.row_factory = sqlite3.Row  # Accès par nom de colonne
        conn.execute("PRAGMA journal_mode=WAL")  # Meilleure concurrence
        conn.execute("PRAGMA foreign_keys=ON")
        return conn
    
    def _init_db(self):
        """Initialise le schéma de la base de données."""
        with self._get_connection() as conn:
            conn.executescript("""
                -- Table principale des clips
                CREATE TABLE IF NOT EXISTS clips (
                    id              TEXT PRIMARY KEY,
                    twitch_id       TEXT UNIQUE NOT NULL,
                    broadcaster     TEXT NOT NULL,
                    title           TEXT,
                    game            TEXT,
                    view_count      INTEGER DEFAULT 0,
                    duration        REAL DEFAULT 0,
                    created_at      TEXT,
                    
                    status          TEXT DEFAULT 'pending',
                    error_message   TEXT,
                    retry_count     INTEGER DEFAULT 0,
                    
                    clip_url        TEXT,
                    output_path     TEXT,
                    
                    fetched_at      TEXT DEFAULT (datetime('now')),
                    processed_at    TEXT,
                    
                    tiktok_title    TEXT,
                    tiktok_hashtags TEXT
                );
                
                -- Index pour les requêtes fréquentes
                CREATE INDEX IF NOT EXISTS idx_clips_status
                    ON clips(status);
                CREATE INDEX IF NOT EXISTS idx_clips_broadcaster
                    ON clips(broadcaster);
                CREATE INDEX IF NOT EXISTS idx_clips_fetched_at
                    ON clips(fetched_at);
                
                -- Historique des exécutions du pipeline
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at      TEXT DEFAULT (datetime('now')),
                    finished_at     TEXT,
                    status          TEXT DEFAULT 'running',
                    clips_fetched   INTEGER DEFAULT 0,
                    clips_processed INTEGER DEFAULT 0,
                    clips_failed    INTEGER DEFAULT 0,
                    error_message   TEXT
                );
            """)
        
        logger.debug(f"Base de données initialisée: {self.db_path}")
    
    # ─────────────────────────────────────────────
    # Gestion des clips
    # ─────────────────────────────────────────────
    
    def clip_exists(self, twitch_id: str) -> bool:
        """Vérifie si un clip a déjà été traité ou est en cours."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT status FROM clips WHERE twitch_id = ?",
                (twitch_id,)
            ).fetchone()
            
            if not row:
                return False
            
            # On retraite les clips en échec (max 3 tentatives)
            if row["status"] == ClipStatus.FAILED.value:
                retry = conn.execute(
                    "SELECT retry_count FROM clips WHERE twitch_id = ?",
                    (twitch_id,)
                ).fetchone()
                return retry["retry_count"] >= 3
            
            return True
    
    def save_clip(self, clip: dict):
        """Enregistre un nouveau clip dans la base."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO clips
                    (twitch_id, broadcaster, title, game, view_count,
                     duration, created_at, clip_url, status)
                VALUES
                    (:id, :broadcaster_name, :title, :game_name, :view_count,
                     :duration, :created_at, :url, 'pending')
            """, clip)
    
    def update_clip_status(
        self,
        twitch_id: str,
        status: ClipStatus,
        error: str | None = None,
        output_path: str | None = None,
        tiktok_title: str | None = None,
        tiktok_hashtags: str | None = None,
    ):
        """Met à jour le statut d'un clip."""
        with self._get_connection() as conn:
            # Incrémente retry_count si c'est un échec
            if status == ClipStatus.FAILED:
                conn.execute("""
                    UPDATE clips
                    SET status        = ?,
                        error_message = ?,
                        retry_count   = retry_count + 1,
                        processed_at  = datetime('now')
                    WHERE twitch_id = ?
                """, (status.value, error, twitch_id))
            else:
                conn.execute("""
                    UPDATE clips
                    SET status          = ?,
                        error_message   = ?,
                        output_path     = ?,
                        tiktok_title    = ?,
                        tiktok_hashtags = ?,
                        processed_at    = datetime('now')
                    WHERE twitch_id = ?
                """, (
                    status.value, error, output_path,
                    tiktok_title, tiktok_hashtags,
                    twitch_id
                ))
    
    def get_stats(self) -> dict:
        """Retourne des statistiques globales du pipeline."""
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'failed'    THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN status = 'pending'   THEN 1 ELSE 0 END) as pending
                FROM clips
            """).fetchone()
            
            return dict(row)
    
    # ─────────────────────────────────────────────
    # Gestion des runs
    # ─────────────────────────────────────────────
    
    def start_run(self) -> int:
        """Démarre un nouveau run et retourne son ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO pipeline_runs DEFAULT VALUES"
            )
            run_id = cursor.lastrowid
            logger.debug(f"Run #{run_id} démarré")
            return run_id
    
    def finish_run(
        self,
        run_id: int,
        fetched: int,
        processed: int,
        failed: int,
        error: str | None = None,
    ):
        """Finalise un run avec ses statistiques."""
        status = "success" if not error else "error"
        
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE pipeline_runs
                SET finished_at     = datetime('now'),
                    status          = ?,
                    clips_fetched   = ?,
                    clips_processed = ?,
                    clips_failed    = ?,
                    error_message   = ?
                WHERE id = ?
            """, (status, fetched, processed, failed, error, run_id))
        
        logger.debug(f"Run #{run_id} terminé: {processed} traités, {failed} échoués")
