"""
Récupération et filtrage des clips Twitch selon les critères configurés.
"""

from __future__ import annotations
from typing import List
from datetime import datetime, timezone, timedelta
from loguru import logger

from src.fetcher.twitch_client import TwitchClient
from src.storage.database import Database, ClipStatus
from src.utils.helpers import load_config, load_streamers


class ClipFetcher:
    
    def __init__(self, twitch_client: TwitchClient, database: Database):
        self.client = twitch_client
        self.db = database
        self.config = load_config()
        self.filters = self.config["twitch"]["filters"]
        
    def fetch_all_streamers(self) -> List[dict]:
        streamers = load_streamers()
        all_clips = []
        
        for streamer in streamers:
            if not streamer.get("enabled", True):
                logger.debug(f"Streamer '{streamer['username']}' désactivé, skip")
                continue
                
            try:
                clips = self.fetch_streamer_clips(streamer)
                all_clips.extend(clips)
                logger.info(f"✓ {streamer['username']}: {len(clips)} clips valides trouvés")
            except Exception as e:
                logger.error(f"✗ Erreur pour '{streamer['username']}': {e}")
                continue
        
        all_clips.sort(key=lambda x: x["view_count"], reverse=True)
        max_clips = self.filters.get("max_clips_per_run", 10)
        selected = all_clips[:max_clips]
        
        logger.info(f"📋 {len(selected)} clips sélectionnés sur {len(all_clips)} éligibles")
        return selected
    
    def fetch_streamer_clips(self, streamer: dict) -> List[dict]:
        username = streamer["username"]
        
        broadcaster_id = self.db.get_cached_user_id(username)
        if not broadcaster_id:
            broadcaster_id = self.client.get_user_id(username)
            if not broadcaster_id:
                return []
            self.db.cache_user_id(username, broadcaster_id)
        
        max_age_hours = self.filters.get("max_age_hours", 48)
        started_at = (
            datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        raw_clips = self.client.get_clips(
            broadcaster_id=broadcaster_id,
            first=50,
            started_at=started_at,
        )
        
        filtered = []
        for clip in raw_clips:
            result = self._filter_clip(clip, username)
            if result["valid"]:
                clip["streamer_username"] = username
                clip["streamer_display"] = streamer.get("display_name", username)
                filtered.append(clip)
            else:
                logger.debug(f"  Skip '{clip.get('id')}': {result['reason']}")
        
        return filtered
    
    def _filter_clip(self, clip: dict, username: str) -> dict:
        clip_id = clip.get("id", "unknown")
        
        if self.db.is_clip_processed(clip_id):
            return {"valid": False, "reason": "déjà traité"}
        
        view_count = clip.get("view_count", 0)
        min_views = self.filters.get("min_views", 500)
        if view_count < min_views:
            return {"valid": False, "reason": f"vues insuffisantes ({view_count} < {min_views})"}
        
        duration = clip.get("duration", 0)
        max_duration = self.filters.get("max_duration_seconds", 60)
        if duration > max_duration:
            return {"valid": False, "reason": f"trop long ({duration}s > {max_duration}s)"}
        
        min_duration = self.filters.get("min_duration_seconds", 10)
        if duration < min_duration:
            return {"valid": False, "reason": f"trop court ({duration}s < {min_duration}s)"}
        
        if not clip.get("thumbnail_url"):
            return {"valid": False, "reason": "pas d'URL de téléchargement"}
        
        return {"valid": True, "reason": None}
