"""
Conversion des clips Twitch (16:9) en format TikTok vertical (9:16).
Deux modes disponibles : crop_center et blur_background.
"""

import subprocess
from pathlib import Path
from loguru import logger

from src.utils.helpers import load_config


class VideoConverter:
    """
    Convertit une vidéo horizontale en format vertical 9:16
    adapté à TikTok (1080x1920).
    """
    
    def __init__(self):
        self.config = load_config()
        video_cfg = self.config["video"]
        
        self.output_width = video_cfg.get("output_width", 1080)
        self.output_height = video_cfg.get("output_height", 1920)
        self.fps = video_cfg.get("fps", 30)
        self.crf = video_cfg.get("crf", 23)
        self.video_codec = video_cfg.get("video_codec", "libx264")
        self.audio_codec = video_cfg.get("audio_codec", "aac")
        self.conversion_mode = video_cfg.get("conversion_mode", "blur_background")
        self.blur_strength = video_cfg.get("blur_strength", 20)
        
    def convert(self, input_path: Path, output_path: Path) -> bool:
        """
        Convertit une vidéo au format vertical TikTok.
        
        Args:
            input_path: Chemin de la vidéo source
            output_path: Chemin de sortie
            
        Returns:
            True si succès, False sinon
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(
            f"🎬 Conversion vidéo [{self.conversion_mode}]: "
            f"{input_path.name} → {output_path.name}"
        )
        
        if self.conversion_mode == "blur_background":
            success = self._convert_blur_background(input_path, output_path)
        elif self.conversion_mode == "crop_center":
            success = self._convert_crop_center(input_path, output_path)
        else:
            logger.error(f"Mode de conversion inconnu: {self.conversion_mode}")
            return False
        
        if success:
            size_mb = output_path.stat().st_size / (1024 * 1024)
            logger.success(f"✓ Vidéo convertie ({size_mb:.1f} MB): {output_path}")
        
        return success
    
    def _build_base_ffmpeg(self, input_path: Path, output_path: Path) -> list[str]:
        """Construit les paramètres FFmpeg communs."""
        return [
            "ffmpeg",
            "-i", str(input_path),
            "-y",               # Écraser sans confirmation
            "-loglevel", "error",
        ]
    
    def _build_output_params(self) -> list[str]:
        """Paramètres de sortie FFmpeg communs."""
        return [
            "-c:v", self.video_codec,
            "-crf", str(self.crf),
            "-preset", "fast",
            "-c:a", self.audio_codec,
            "-b:a", "128k",
            "-r", str(self.fps),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",  # Optimisation streaming
        ]
    
    def _convert_blur_background(
        self,
        input_path: Path,
        output_path: Path
    ) -> bool:
        """
        Mode "blur background" :
        - Fond : vidéo originale floutée et étirée en 9:16
        - Premier plan : vidéo originale centrée, redimensionnée pour tenir
        
        Résultat visuel :
        ┌──────────────┐
        │ ░░░░░░░░░░░░ │  ← fond flouté
        │ ┌──────────┐ │
        │ │          │ │  ← vidéo originale centrée
        │ │  VIDEO   │ │
        │ │          │ │
        │ └──────────┘ │
        │ ░░░░░░░░░░░░ │
        └──────────────┘
        """
        W = self.output_width    # 1080
        H = self.output_height   # 1920
        blur = self.blur_strength
        
        # Calcul de la taille du premier plan
        # On veut que la vidéo tienne en largeur : largeur = W, hauteur auto
        fg_width = W
        fg_height = -2  # FFmpeg calcule automatiquement en maintenant ratio
        
        filter_complex = (
            # Flux 0 = fond flouté
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},"
            f"boxblur={blur}:1[bg];"
            
            # Flux 1 = premier plan redimensionné
            f"[0:v]scale={fg_width}:{fg_height}[fg];"
            
            # Overlay : fg centré sur bg
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[out]"
        )
        
        command = (
            self._build_base_ffmpeg(input_path, output_path)
            + ["-filter_complex", filter_complex, "-map", "[out]", "-map", "0:a?"]
            + self._build_output_params()
            + [str(output_path)]
        )
        
        return self._run_ffmpeg(command, "blur_background")
    
    def _convert_crop_center(
        self,
        input_path: Path,
        output_path: Path
    ) -> bool:
        """
        Mode "crop center" :
        Découpe la partie centrale de la vidéo pour obtenir un 9:16.
        Simple et rapide, mais perd les côtés de l'image.
        
        ┌──────────────────────────┐
        │░░░│                  │░░░│  ← parties découpées (16:9 original)
        │░░░│    ZONE GARDÉE   │░░░│
        │░░░│    (9:16 crop)   │░░░│
        │░░░│                  │░░░│
        └──────────────────────────┘
        """
        W = self.output_width    # 1080
        H = self.output_height   # 1920
        
        # Calcul du crop : depuis une vidéo 1920x1080, on garde 608x1080 au centre
        # puis on scale à 1080x1920
        # Ratio cible 9:16 → crop_w = input_h * 9/16
        vf = (
            f"crop=ih*9/16:ih,"      # Crop au centre en ratio 9:16
            f"scale={W}:{H},"        # Scale à la taille cible
            f"setsar=1"              # Pixel aspect ratio
        )
        
        command = (
            self._build_base_ffmpeg(input_path, output_path)
            + ["-vf", vf]
            + self._build_output_params()
            + [str(output_path)]
        )
        
        return self._run_ffmpeg(command, "crop_center")
    
    def _run_ffmpeg(self, command: list[str], mode: str) -> bool:
        """Exécute une commande FFmpeg et gère les erreurs."""
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes max
            )
            
            if result.returncode != 0:
                logger.error(
                    f"FFmpeg [{mode}] a échoué:\n{result.stderr}"
                )
                return False
            
            return True
            
        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg [{mode}] timeout après 5 minutes")
            return False
        except Exception as e:
            logger.error(f"Erreur FFmpeg [{mode}]: {e}")
            return False
