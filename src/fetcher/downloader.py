"""
Téléchargement des clips Twitch via yt-dlp.
"""

from __future__ import annotations
from typing import Optional
import os
import subprocess
from pathlib import Path
from loguru import logger

from src.utils.helpers import load_config


class ClipDownloader:
    
    def __init__(self):
        self.config = load_config()
        self.tmp_dir = Path(self.config["storage"]["tmp_dir"])
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        
    def download(self, clip: dict) -> Optional[Path]:
        clip_id = clip["id"]
        clip_url = clip["url"]
        output_path = self.tmp_dir / f"{clip_id}.mp4"
        
        if output_path.exists():
            logger.debug(f"Clip {clip_id} déjà dans le cache tmp")
            return output_path
        
        logger.info(f"⬇️  Téléchargement du clip {clip_id}...")
        
        command = [
            "yt-dlp",
            "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--output", str(output_path),
            "--no-playlist",
            "--quiet",
            "--no-warnings",
            "--retries", "3",
            "--fragment-retries", "3",
            clip_url,
        ]
        
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode != 0:
                logger.error(f"yt-dlp a échoué pour {clip_id}: {result.stderr}")
                return None
            
            if not output_path.exists():
                logger.error(f"Fichier non créé après téléchargement: {output_path}")
                return None
                
            file_size_mb = output_path.stat().st_size / (1024 * 1024)
            logger.success(f"✓ Clip {clip_id} téléchargé ({file_size_mb:.1f} MB)")
            return output_path
            
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout lors du téléchargement de {clip_id}")
            if output_path.exists():
                output_path.unlink()
            return None
            
        except Exception as e:
            logger.error(f"Erreur inattendue lors du téléchargement de {clip_id}: {e}")
            return None
    
    def cleanup(self, file_path: Path) -> None:
        try:
            if file_path.exists():
                file_path.unlink()
                logger.debug(f"Fichier temporaire supprimé: {file_path}")
        except Exception as e:
            logger.warning(f"Impossible de supprimer {file_path}: {e}")
