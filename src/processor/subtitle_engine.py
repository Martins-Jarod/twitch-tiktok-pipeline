"""
Génération de sous-titres via faster-whisper (transcription locale).
"""

import os
from pathlib import Path
from loguru import logger

from src.utils.helpers import load_config


class SubtitleEngine:
    """
    Transcrit l'audio d'une vidéo et génère un fichier SRT.
    Utilise faster-whisper pour des performances optimisées sur CPU.
    """
    
    def __init__(self):
        self.config = load_config()
        subtitle_cfg = self.config.get("subtitles", {})
        
        self.enabled = subtitle_cfg.get("enabled", True)
        self.model_size = subtitle_cfg.get("model", "small")
        self.language = subtitle_cfg.get("language", "auto")
        
        self._model = None  # Lazy loading
        
    def _load_model(self):
        """Charge le modèle Whisper (une seule fois)."""
        if self._model is not None:
            return
            
        logger.info(f"🔄 Chargement du modèle Whisper '{self.model_size}'...")
        
        try:
            from faster_whisper import WhisperModel
            
            # Utilise le CPU si pas de GPU disponible
            self._model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8"  # Optimisation mémoire pour CPU
            )
            logger.success(f"✓ Modèle Whisper '{self.model_size}' chargé")
            
        except ImportError:
            logger.error(
                "faster-whisper non installé. "
                "Exécutez: pip install faster-whisper"
            )
            raise
    
    def transcribe(self, video_path: Path) -> Path | None:
        """
        Transcrit l'audio d'une vidéo et génère un fichier SRT.
        
        Args:
            video_path: Chemin vers la vidéo à transcrire
            
        Returns:
            Chemin vers le fichier SRT généré, ou None en cas d'échec
        """
        if not self.enabled:
            logger.debug("Sous-titres désactivés, skip transcription")
            return None
        
        srt_path = video_path.with_suffix(".srt")
        
        # Si SRT déjà généré
        if srt_path.exists():
            logger.debug(f"SRT déjà existant: {srt_path}")
            return srt_path
        
        logger.info(f"🎤 Transcription: {video_path.name}")
        
        try:
            self._load_model()
            
            # Détection automatique de la langue si configuré
            lang = None if self.language == "auto" else self.language
            
            segments, info = self._model.transcribe(
                str(video_path),
                language=lang,
                beam_size=5,
                word_timestamps=False,
                vad_filter=True,           # Filtre les silences
                vad_parameters={
                    "min_silence_duration_ms": 500
                }
            )
            
            logger.debug(
                f"Langue détectée: {info.language} "
                f"(probabilité: {info.language_probability:.2f})"
            )
            
            # Conversion en format SRT
            srt_content = self._segments_to_srt(list(segments))
            
            if not srt_content.strip():
                logger.warning(f"Transcription vide pour {video_path.name}")
                return None
            
            srt_path.write_text(srt_content, encoding="utf-8")
            
            line_count = srt_content.count("\n\n")
            logger.success(f"✓ SRT généré: {line_count} segments")
            
            return srt_path
            
        except Exception as e:
            logger.error(f"Erreur de transcription: {e}")
            return None
    
    def _segments_to_srt(self, segments: list) -> str:
        """
        Convertit les segments Whisper au format SRT standard.
        
        Format SRT :
        1
        00:00:00,000 --> 00:00:02,500
        Texte du sous-titre
        
        """
        srt_lines = []
        
        for i, segment in enumerate(segments, start=1):
            # Formatage des timestamps
            start = self._seconds_to_srt_time(segment.start)
            end = self._seconds_to_srt_time(segment.end)
            text = segment.text.strip()
            
            if not text:
                continue
            
            srt_lines.append(f"{i}")
            srt_lines.append(f"{start} --> {end}")
            srt_lines.append(text)
            srt_lines.append("")  # Ligne vide séparatrice
        
        return "\n".join(srt_lines)
    
    @staticmethod
    def _seconds_to_srt_time(seconds: float) -> str:
        """
        Convertit des secondes en format timestamp SRT.
        
        Args:
            seconds: Temps en secondes (ex: 65.5)
            
        Returns:
            String au format "HH:MM:SS,mmm" (ex: "00:01:05,500")
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
