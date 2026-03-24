"""
Récupération et filtrage des clips Twitch selon les critères configurés.
"""

from datetime import datetime, timezone, timedelta
from loguru import logger

from src.fetcher.twitch_client import TwitchClient
from src.storage.database import ClipDatabase
from src.utils.helpers import load_config, load_streamers


class ClipFetcher:
    """
    Récupère les clips populaires des streamers configurés
    et applique les filtres définis dans la configuration.
    """
    
    def __init__(self, twitch_client: TwitchClient, database: ClipDatabase):
        self.client = twitch_client
        self.db = database
        self.config = load_config()
        self.filters = self.config["twitch"]["filters"]
        
    def fetch_all_streamers(self) -> list[dict]:
        """
        Récupère les clips valides pour tous les streamers activés.
        
        Returns:
            Liste de clips filtrés et enrichis, triés par pertinence
        """
        streamers = load_streamers()
        all_clips = []
        
        for streamer in streamers:
            if not streamer.get("enabled", True):
                logger.debug(f"Streamer '{streamer['username']}' désactivé, skip")
                continue
                
            try:
                clips = self.fetch_streamer_clips(streamer)
                all_clips.extend(clips)
                logger.info(
                    f"✓ {streamer['username']}: {len(clips)} clips valides trouvés"
                )
            except Exception as e:
                logger.error(
                    f"✗ Erreur pour '{streamer['username']}': {e}"
                )
                continue
        
        # Tri global par vues décroissantes
        all_clips.sort(key=lambda x: x["view_count"], reverse=True)
        
        # Limite globale
        max_clips = self.filters.get("max_clips_per_run", 10)
        selected = all_clips[:max_clips]
        
        logger.info(
            f"📋 {len(selected)} clips sélectionnés sur {len(all_clips)} éligibles"
        )
        return selected
    
    def fetch_streamer_clips(self, streamer: dict) -> list[dict]:
        """
        Récupère et filtre les clips d'un streamer spécifique.
        
        Args:
            streamer: Configuration du streamer depuis streamers.yaml
            
        Returns:
            Liste de clips filtrés pour ce streamer
        """
        username = streamer["username"]
        
        # Résolution de l'ID utilisateur
        broadcaster_id = self.db.get_cached_user_id(username)
        if not broadcaster_id:
            broadcaster_id = self.client.get_user_id(username)
            if not broadcaster_id:
                return []
            self.db.cache_user_id(username, broadcaster_id)
        
        # Calcul de la fenêtre temporelle
        max_age_hours = self.filters.get("max_age_hours", 48)
        started_at = (
            datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Récupération des clips
        raw_clips = self.client.get_clips(
            broadcaster_id=broadcaster_id,
            first=50,
            started_at=started_at,
        )
        
        # Application des filtres
        filtered = []
        for clip in raw_clips:
            result = self._filter_clip(clip, username)
            if result["valid"]:
                # Enrichissement avec les infos du streamer
                clip["streamer_username"] = username
                clip["streamer_display"] = streamer.get("display_name", username)
                filtered.append(clip)
            else:
                logger.debug(
                    f"  Skip '{clip.get('id')}': {result['reason']}"
                )
        
        return filtered
    
    def _filter_clip(self, clip: dict, username: str) -> dict:
        """
        Applique tous les filtres à un clip.
        
        Returns:
            Dict avec 'valid' (bool) et 'reason' (str si invalide)
        """
        clip_id = clip.get("id", "unknown")
        
        # Filtre 1 : Déjà traité
        if self.db.is_clip_processed(clip_id):
            return {"valid": False, "reason": "déjà traité"}
        
        # Filtre 2 : Vues minimum
        view_count = clip.get("view_count", 0)
        min_views = self.filters.get("min_views", 500)
        if view_count < min_views:
            return {
                "valid": False,
                "reason": f"vues insuffisantes ({view_count} < {min_views})"
            }
        
        # Filtre 3 : Durée maximum
        duration = clip.get("duration", 0)
        max_duration = self.filters.get("max_duration_seconds", 60)
        if duration > max_duration:
            return {
                "valid": False,
                "reason": f"trop long ({duration}s > {max_duration}s)"
            }
        
        # Filtre 4 : Durée minimum
        min_duration = self.filters.get("min_duration_seconds", 10)
        if duration < min_duration:
            return {
                "valid": False,
                "reason": f"trop court ({duration}s < {min_duration}s)"
            }
        
        # Filtre 5 : URL de téléchargement disponible
        if not clip.get("thumbnail_url"):
            return {"valid": False, "reason": "pas d'URL de téléchargement"}
        
        return {"valid": True, "reason": None}
