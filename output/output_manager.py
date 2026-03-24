"""
Gestion de l'organisation des fichiers de sortie.
Structure les vidéos finales dans des dossiers clairs.
"""

import json
from pathlib import Path
from datetime import datetime
from loguru import logger

from src.utils.helpers import load_config


class OutputManager:
    """
    Organise les vidéos finales dans le dossier output.
    
    Structure de sortie :
    output/
    ├── 2024-01-15/
    │   ├── xqc_clip_abc123/
    │   │   ├── video.mp4          ← Vidéo prête à publier
    │   │   ├── metadata.json      ← Titre, hashtags, infos clip
    │   │   └── thumbnail.jpg      ← Miniature (optionnel)
    │   └── pokimane_clip_def456/
    │       ├── video.mp4
    │       └── metadata.json
    """
    
    def __init__(self):
        self.config   = load_config()
        self.base_dir = Path(self.config["storage"]["output_dir"])
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def save(
        self,
        video_path: Path,
        clip: dict,
        metadata: dict,
    ) -> Path:
        """
        Sauvegarde la vidéo finale et ses métadonnées.
        
        Returns:
            Chemin vers la vidéo finale
        """
        # Création du dossier de sortie
        output_dir = self._create_output_dir(clip)
        
        # Copie de la vidéo finale
        final_video = output_dir / "video.mp4"
        import shutil
        shutil.copy2(video_path, final_video)
        
        # Création du fichier de métadonnées complet
        metadata_path = output_dir / "metadata.json"
        self._write_metadata(metadata_path, clip, metadata)
        
        # Création d'un fichier texte lisible pour copier-coller
        caption_path = output_dir / "caption.txt"
        self._write_caption(caption_path, metadata)
        
        logger.info(f"📁 Output: {output_dir}")
        
        return final_video
    
    def _create_output_dir(self, clip: dict) -> Path:
        """Crée et retourne le dossier de sortie pour un clip."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        streamer  = clip.get("broadcaster_name", "unknown")
        clip_id   = clip.get("id", "unknown")[:8]  # Premiers 8 chars de l'ID
        
        # Format: output/2024-01-15/xqc_abc12345/
        folder_name = f"{streamer}_{clip_id}"
        output_dir  = self.base_dir / date_str / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        return output_dir
    
    def _write_metadata(
        self,
        path: Path,
        clip: dict,
        metadata: dict
    ):
        """Écrit les métadonnées complètes en JSON."""
        full_metadata = {
            "generated_at": datetime.now().isoformat(),
            
            # Métadonnées TikTok
            "tiktok": {
                "title"   : metadata.get("title", ""),
                "hashtags": metadata.get("hashtags", []),
                "caption" : self._build_caption(metadata),
            },
            
            # Métadonnées Twitch originales
            "source": {
                "platform"        : "twitch",
                "clip_id"         : clip.get("id"),
                "clip_url"        : clip.get("url"),
                "clip_title"      : clip.get("title"),
                "broadcaster_name": clip.get("broadcaster_name"),
                "game_name"       : clip.get("game_name"),
                "view_count"      : clip.get("view_count"),
                "duration"        : clip.get("duration"),
                "created_at"      : clip.get("created_at"),
            }
        }
        
        path.write_text(
            json.dumps(full_metadata, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    
    def _write_caption(self, path: Path, metadata: dict):
        """
        Écrit un fichier texte prêt à copier-coller pour TikTok.
        
        Format :
        Titre de la vidéo
        
        #hashtag1 #hashtag2 #hashtag3
        """
        caption = self._build_caption(metadata)
        path.write_text(caption, encoding="utf-8")
    
    def _build_caption(self, metadata: dict) -> str:
        """Construit la légende TikTok finale."""
        title    = metadata.get("title", "")
        hashtags = metadata.get("hashtags", [])
        
        hashtag_str = " ".join(f"#{tag}" for tag in hashtags)
        
        return f"{title}\n\n{hashtag_str}"
