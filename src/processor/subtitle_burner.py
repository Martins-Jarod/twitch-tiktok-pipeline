"""
Incrustation des sous-titres SRT dans la vidéo via FFmpeg.
"""

import subprocess
from pathlib import Path
from loguru import logger

from src.utils.helpers import load_config


class SubtitleBurner:
    """
    Incruste les sous-titres directement dans la vidéo (hardcoded).
    Les sous-titres seront toujours visibles, quel que soit le lecteur.
    """
    
    def __init__(self):
        self.config = load_config()
        style_cfg = self.config.get("subtitles", {}).get("style", {})
        
        self.font = style_cfg.get("font", "Arial")
        self.font_size = style_cfg.get("font_size", 18)
        self.font_color = style_cfg.get("font_color", "white")
        self.outline_color = style_cfg.get("outline_color", "black")
        self.outline_width = style_cfg.get("outline_width", 2)
        self.margin_bottom = style_cfg.get("margin_bottom", 150)
        
    def burn_subtitles(
        self,
        video_path: Path,
        srt_path: Path,
        output_path: Path
    ) -> bool:
        """
        Incruste les sous-titres dans la vidéo.
        
        Args:
            video_path: Vidéo source
            srt_path: Fichier SRT à incruster
            output_path: Vidéo de sortie avec sous-titres
            
        Returns:
            True si succès
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Style ASS des sous-titres pour FFmpeg
        # Force le style directement dans la commande
        style_override = (
            f"FontName={self.font},"
            f"FontSize={self.font_size},"
            f"PrimaryColour=&H00FFFFFF,"  # Blanc opaque
            f"OutlineColour=&H00000000,"  # Noir opaque  
            f"Outline={self.outline_width},"
            f"Shadow=1,"
            f"Alignment=2,"               # Centré en bas
            f"MarginV={self.margin_bottom}"
        )
        
        # Note: Le chemin SRT doit être escapé pour FFmpeg sous Windows
        srt_path_escaped = str(srt_path).replace("\\", "/").replace(":", "\\:")
        
        subtitle_filter = (
            f"subtitles='{srt_path_escaped}'"
            f":force_style='{style_override}'"
        )
        
        command = [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", subtitle_filter,
            "-c:v", "libx264",
            "-crf", str(self.config["video"].get("crf", 23)),
            "-preset", "fast",
            "-c:a", "copy",     # Audio sans ré-encodage (plus rapide)
            "-y",
            "-loglevel", "error",
            str(output_path),
        ]
        
        logger.info(f"📝 Incrustation des sous-titres...")
        
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                logger.error(f"Erreur incrustation sous-titres:\n{result.stderr}")
                return False
            
            logger.success(f"✓ Sous-titres incrustés: {output_path.name}")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("Timeout lors de l'incrustation des sous-titres")
            return False
        except Exception as e:
            logger.error(f"Erreur inattendue: {e}")
            return False
