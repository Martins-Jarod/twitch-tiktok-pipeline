"""
Orchestrateur principal du pipeline Twitch → TikTok.
Coordonne tous les modules dans le bon ordre avec gestion d'erreurs.
"""

import shutil
from pathlib import Path
from datetime import datetime, timezone
from loguru import logger

from src.fetcher.twitch_client import TwitchClient
from src.fetcher.clip_fetcher import ClipFetcher
from src.fetcher.downloader import Downloader
from src.processor.video_converter import VideoConverter
from src.processor.subtitle_engine import SubtitleEngine
from src.processor.subtitle_burner import SubtitleBurner
from src.metadata.title_generator import TitleGenerator
from src.storage.database import Database, ClipStatus
from src.storage.output_manager import OutputManager
from src.utils.helpers import load_config
from src.utils.logger import setup_logger


class Pipeline:
    """
    Pipeline complet de transformation Twitch → TikTok.
    
    Workflow pour chaque clip :
    1. Fetch  → Récupérer les clips populaires depuis Twitch API
    2. Filter → Appliquer les critères de filtrage
    3. Download → Télécharger le fichier MP4 brut
    4. Convert  → Transformer en format vertical 9:16
    5. Subtitle → Transcrire et incruster les sous-titres
    6. Metadata → Générer titre et hashtags TikTok
    7. Export   → Organiser dans le dossier output final
    8. Cleanup  → Supprimer les fichiers temporaires
    """
    
    def __init__(self):
        self.config = load_config()
        setup_logger(self.config)
        
        # Initialisation des modules
        self.db             = Database()
        self.twitch_client  = TwitchClient(
            client_id     = self._get_env("TWITCH_CLIENT_ID"),
            client_secret = self._get_env("TWITCH_CLIENT_SECRET"),
        )
        self.clip_fetcher   = ClipFetcher(self.twitch_client)
        self.downloader     = Downloader()
        self.converter      = VideoConverter()
        self.subtitle_engine = SubtitleEngine()
        self.subtitle_burner = SubtitleBurner()
        self.title_generator = TitleGenerator()
        self.output_manager  = OutputManager()
        
        # Répertoires de travail
        self.tmp_dir = Path(self.config["storage"]["tmp_dir"])
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("Pipeline initialisé ✓")
    
    # ─────────────────────────────────────────────────────────
    # Point d'entrée principal
    # ─────────────────────────────────────────────────────────
    
    def run(self):
        """
        Lance une exécution complète du pipeline.
        Traite tous les streamers configurés.
        """
        run_id = self.db.start_run()
        
        stats = {
            "fetched"  : 0,
            "processed": 0,
            "failed"   : 0,
        }
        
        logger.info("=" * 60)
        logger.info("🚀 Démarrage du pipeline Twitch → TikTok")
        logger.info("=" * 60)
        
        try:
            # Récupération de tous les clips filtrés
            clips = self.clip_fetcher.fetch_all_streamers()
            stats["fetched"] = len(clips)
            
            if not clips:
                logger.info("Aucun nouveau clip à traiter")
                self.db.finish_run(run_id, **stats)
                return
            
            logger.info(f"📦 {len(clips)} clips à traiter")
            
            # Traitement clip par clip
            max_clips = self.config["twitch"]["filters"]["max_clips_per_run"]
            
            for i, clip in enumerate(clips[:max_clips], start=1):
                clip_id = clip.get("id", "unknown")
                streamer = clip.get("broadcaster_name", "unknown")
                
                logger.info(f"\n[{i}/{min(len(clips), max_clips)}] "
                           f"Traitement: {clip.get('title', '')[:50]} "
                           f"(@{streamer})")
                
                success = self._process_clip(clip)
                
                if success:
                    stats["processed"] += 1
                else:
                    stats["failed"] += 1
            
            # Affichage du bilan final
            self._log_summary(stats)
            self.db.finish_run(run_id, **stats)
            
        except KeyboardInterrupt:
            logger.warning("Pipeline interrompu par l'utilisateur")
            self.db.finish_run(run_id, **stats, error="Interrupted by user")
            
        except Exception as e:
            logger.critical(f"Erreur critique du pipeline: {e}", exc_info=True)
            self.db.finish_run(run_id, **stats, error=str(e))
            raise
    
    # ─────────────────────────────────────────────────────────
    # Traitement d'un clip individuel
    # ─────────────────────────────────────────────────────────
    
    def _process_clip(self, clip: dict) -> bool:
        """
        Traite un clip de A à Z.
        
        Args:
            clip: Métadonnées du clip Twitch
            
        Returns:
            True si le clip a été traité avec succès
        """
        clip_id   = clip["id"]
        streamer  = clip.get("broadcaster_name", "unknown")
        
        # Vérification doublon
        if self.db.clip_exists(clip_id):
            logger.debug(f"⏭ Clip déjà traité, skip: {clip_id}")
            return True
        
        # Enregistrement en base
        self.db.save_clip(clip)
        
        # Dossier de travail temporaire pour ce clip
        work_dir = self.tmp_dir / clip_id
        work_dir.mkdir(exist_ok=True)
        
        try:
            # ── Étape 1 : Téléchargement ──────────────────────────
            self.db.update_clip_status(clip_id, ClipStatus.DOWNLOADING)
            
            raw_video = work_dir / "raw.mp4"
            success = self.downloader.download(
                url=clip["url"],
                output_path=raw_video,
            )
            
            if not success or not raw_video.exists():
                raise RuntimeError("Échec du téléchargement")
            
            logger.debug(f"✓ Téléchargé: {raw_video.stat().st_size / 1024 / 1024:.1f} MB")
            
            # ── Étape 2 : Conversion vidéo ────────────────────────
            self.db.update_clip_status(clip_id, ClipStatus.PROCESSING)
            
            converted_video = work_dir / "converted.mp4"
            success = self.converter.convert(
                input_path=raw_video,
                output_path=converted_video,
            )
            
            if not success:
                raise RuntimeError("Échec de la conversion vidéo")
            
            # ── Étape 3 : Sous-titres ─────────────────────────────
            final_video = converted_video  # Par défaut, sans sous-titres
            
            if self.config["subtitles"]["enabled"]:
                srt_path = self.subtitle_engine.transcribe(converted_video)
                
                if srt_path and srt_path.exists():
                    subtitled_video = work_dir / "subtitled.mp4"
                    success = self.subtitle_burner.burn_subtitles(
                        video_path=converted_video,
                        srt_path=srt_path,
                        output_path=subtitled_video,
                    )
                    
                    if success:
                        final_video = subtitled_video
                    else:
                        logger.warning(
                            "Échec de l'incrustation des sous-titres, "
                            "utilisation de la vidéo sans sous-titres"
                        )
                else:
                    logger.warning("Transcription échouée ou vide, skip sous-titres")
            
            # ── Étape 4 : Génération des métadonnées ──────────────
            metadata = self.title_generator.generate(clip)
            
            # ── Étape 5 : Export final ────────────────────────────
            output_path = self.output_manager.save(
                video_path=final_video,
                clip=clip,
                metadata=metadata,
            )
            
            # ── Mise à jour base de données ───────────────────────
            self.db.update_clip_status(
                twitch_id     = clip_id,
                status        = ClipStatus.COMPLETED,
                output_path   = str(output_path),
                tiktok_title  = metadata.get("title"),
                tiktok_hashtags = ", ".join(metadata.get("hashtags", [])),
            )
            
            logger.success(
                f"✅ Clip terminé: {output_path.parent.name}"
            )
            return True
            
        except Exception as e:
            logger.error(f"❌ Échec du traitement [{clip_id}]: {e}")
            self.db.update_clip_status(
                clip_id,
                ClipStatus.FAILED,
                error=str(e)
            )
            return False
        
        finally:
            # Nettoyage des fichiers temporaires
            if not self.config["storage"].get("keep_tmp_files", False):
                self._cleanup_work_dir(work_dir)
    
    # ─────────────────────────────────────────────────────────
    # Utilitaires
    # ─────────────────────────────────────────────────────────
    
    def _cleanup_work_dir(self, work_dir: Path):
        """Supprime le répertoire de travail temporaire."""
        try:
            if work_dir.exists():
                shutil.rmtree(work_dir)
                logger.debug(f"🗑 Dossier tmp supprimé: {work_dir.name}")
        except Exception as e:
            logger.warning(f"Impossible de supprimer {work_dir}: {e}")
    
    def _log_summary(self, stats: dict):
        """Affiche un résumé de l'exécution."""
        db_stats = self.db.get_stats()
        
        logger.info("\n" + "=" * 60)
        logger.info("📊 RÉSUMÉ DE L'EXÉCUTION")
        logger.info("=" * 60)
        logger.info(f"  Clips récupérés  : {stats['fetched']}")
        logger.info(f"  Clips traités    : {stats['processed']} ✅")
        logger.info(f"  Clips échoués    : {stats['failed']} ❌")
        logger.info("─" * 60)
        logger.info(f"  Total historique : {db_stats.get('total', 0)}")
        logger.info(f"  Complétés (all)  : {db_stats.get('completed', 0)}")
        logger.info("=" * 60 + "\n")
    
    @staticmethod
    def _get_env(key: str) -> str:
        """Récupère une variable d'environnement ou lève une erreur claire."""
        import os
        value = os.getenv(key)
        if not value:
            raise EnvironmentError(
                f"Variable d'environnement manquante: {key}\n"
                f"Copiez .env.example vers .env et remplissez les valeurs."
            )
        return value
