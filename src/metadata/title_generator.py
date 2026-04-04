"""
Génération automatique de titres et hashtags pour TikTok.
Utilise Groq API (gratuit) avec fallback sur des templates.
"""

import os
import json
import random
from loguru import logger

from src.utils.helpers import load_config


class TitleGenerator:
    """
    Génère des titres accrocheurs et des hashtags pertinents
    pour les vidéos TikTok à partir des métadonnées du clip Twitch.
    """
    
    def __init__(self):
        self.config = load_config()
        meta_cfg = self.config.get("metadata", {})
        
        self.provider = meta_cfg.get("provider", "template")
        self.language = meta_cfg.get("language", "fr")
        self.hashtag_count = meta_cfg.get("hashtag_count", 5)
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        
    def generate(self, clip: dict) -> dict:
        """
        Génère titre et hashtags pour un clip.
        
        Args:
            clip: Données du clip Twitch (title, broadcaster_name, game_name, etc.)
            
        Returns:
            Dict avec 'title' et 'hashtags'
        """
        streamer = clip.get("streamer_display", clip.get("broadcaster_name", ""))
        clip_title = clip.get("title", "")
        game = clip.get("game_name", "")
        views = clip.get("view_count", 0)
        
        logger.debug(
            f"📝 Génération metadata pour: '{clip_title}' by {streamer}"
        )
        
        # Tentative avec le provider principal
        if self.provider == "groq" and self.groq_api_key:
            result = self._generate_with_groq(clip_title, streamer, game, views)
            if result:
                return result
        
        # Fallback sur les templates
        logger.debug("Fallback sur les templates de titres")
        return self._generate_from_template(clip_title, streamer, game)
    
    def _generate_with_groq(
        self,
        clip_title: str,
        streamer: str,
        game: str,
        views: int
    ) -> dict | None:
        """Génère via l'API Groq (modèle Llama 3 gratuit)."""
        try:
            from groq import Groq
            
            client = Groq(api_key=self.groq_api_key)
            
            prompt = self._build_prompt(clip_title, streamer, game, views)
            
            response = client.chat.completions.create(
                model="llama3-8b-8192",  # Gratuit et rapide
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Tu es un expert en création de contenu TikTok gaming. "
                            "Tu génères des titres courts, accrocheurs et des hashtags "
                            "pertinents pour maximiser les vues. "
                            "Réponds UNIQUEMENT en JSON valide, sans texte additionnel."
                        )
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=200,
            )
            
            raw = response.choices[0].message.content.strip()
            
            # Nettoyage du JSON (parfois le LLM ajoute du texte)
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            
            data = json.loads(raw)
            
            # Validation
            if "title" not in data or "hashtags" not in data:
                raise ValueError("JSON incomplet")
            
            logger.debug(f"✓ Titre généré par Groq: {data['title']}")
            return {
                "title": str(data["title"])[:150],  # Limite TikTok
                "hashtags": data["hashtags"][:self.hashtag_count],
            }
            
        except json.JSONDecodeError as e:
            logger.warning(f"JSON invalide retourné par Groq: {e}")
            return None
        except Exception as e:
            logger.warning(f"Erreur Groq API: {e}")
            return None
    
    def _build_prompt(
        self,
        clip_title: str,
        streamer: str,
        game: str,
        views: int
    ) -> str:
        """Construit le prompt pour la génération."""
        lang_instruction = (
            "en français" if self.language == "fr" else "in English"
        )
        
        return f"""
Génère un titre TikTok et des hashtags {lang_instruction} pour ce clip Twitch :

- Streamer : {streamer}
- Titre original : {clip_title}
- Jeu : {game or "Variety"}
- Vues Twitch : {views:,}

Contraintes :
- Titre : max 80 caractères, accrocheur, émojis autorisés
- Hashtags : exactement {self.hashtag_count}, sans le #, en minuscules
- Mix de hashtags populaires (#fyp, #gaming) et spécifiques

Réponds UNIQUEMENT avec ce JSON :
{{
  "title": "Titre ici",
  "hashtags": ["hashtag1", "hashtag2", "hashtag3", "hashtag4", "hashtag5"]
}}
"""
    
    def _generate_from_template(
        self,
        clip_title: str,
        streamer: str,
        game: str
    ) -> dict:
        """Génère titre et hashtags depuis des templates prédéfinis."""
        
        # Templates de titres
        title_templates = [
            f"😱 {streamer} en mode BEAST ! {clip_title[:40]}",
            f"🔥 Moment INCROYABLE de {streamer}",
            f"⚡ {streamer} a tout déchiré ! #{game or 'Twitch'}",
            f"😂 {streamer} : quand ça part en live...",
            f"🎮 Le clip que tu dois voir de {streamer}",
            f"💥 CLIP DU JOUR : {streamer}",
        ]
        
        title = random.choice(title_templates)
        
        # Hashtags par catégorie
        base_hashtags = ["fyp", "foryou", "gaming", "twitch", "twitchclips"]
        
        game_hashtags = {
            "Fortnite": ["fortnite", "fortniteclips", "fortnitefr"],
            "League of Legends": ["lol", "leagueoflegends", "league"],
            "Valorant": ["valorant", "valorantclips", "valorantfr"],
            "Just Chatting": ["justchatting", "stream", "drole"],
            "Minecraft": ["minecraft", "minecraftfr", "minecraftclips"],
            "GTA V": ["gta5", "gtav", "gta"],
        }
        
        streamer_hashtags = [
            streamer.lower().replace(" ", ""),
            "streamer",
            "clip",
            "viral",
            "highlight",
        ]
        
        # Construction du pool de hashtags
        hashtag_pool = base_hashtags.copy()
        
        if game and game in game_hashtags:
            hashtag_pool.extend(game_hashtags[game])
        
        hashtag_pool.extend(streamer_hashtags)
        
        # Dédoublonnage et sélection aléatoire
        unique_hashtags = list(dict.fromkeys(hashtag_pool))
        selected = unique_hashtags[:self.hashtag_count]
        
        return {
            "title": title[:150],
            "hashtags": selected,
        }
