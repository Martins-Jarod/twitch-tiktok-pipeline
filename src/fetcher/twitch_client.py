"""
Client Twitch API avec authentification OAuth2 Client Credentials.
Gère automatiquement le renouvellement des tokens.
"""

import time
import requests
from loguru import logger
from src.utils.helpers import load_config


class TwitchClient:
    """
    Client pour l'API Twitch Helix.
    Utilise le flux OAuth2 Client Credentials (sans compte utilisateur).
    """
    
    BASE_URL = "https://api.twitch.tv/helix"
    AUTH_URL = "https://id.twitch.tv/oauth2/token"
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: str | None = None
        self._token_expires_at: float = 0
        
    def _get_access_token(self) -> str:
        """
        Récupère ou renouvelle le token d'accès.
        Le token est mis en cache jusqu'à expiration.
        """
        # Token encore valide (avec marge de 60 secondes)
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token
            
        logger.debug("Renouvellement du token Twitch...")
        
        response = requests.post(
            self.AUTH_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            timeout=10
        )
        response.raise_for_status()
        
        data = response.json()
        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + data["expires_in"]
        
        logger.debug(f"Token Twitch renouvelé, expire dans {data['expires_in']}s")
        return self._access_token
    
    def _get_headers(self) -> dict:
        """Retourne les headers d'authentification pour l'API."""
        return {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self._get_access_token()}",
        }
    
    def get_user_id(self, username: str) -> str | None:
        """
        Récupère l'ID Twitch d'un utilisateur à partir de son username.
        
        Args:
            username: Login Twitch du streamer
            
        Returns:
            L'ID utilisateur ou None si non trouvé
        """
        response = requests.get(
            f"{self.BASE_URL}/users",
            headers=self._get_headers(),
            params={"login": username},
            timeout=10
        )
        response.raise_for_status()
        
        data = response.json().get("data", [])
        if not data:
            logger.warning(f"Utilisateur Twitch '{username}' introuvable")
            return None
            
        return data[0]["id"]
    
    def get_clips(
        self,
        broadcaster_id: str,
        first: int = 20,
        started_at: str | None = None,
        ended_at: str | None = None,
    ) -> list[dict]:
        """
        Récupère les clips d'un broadcaster.
        
        Args:
            broadcaster_id: ID du streamer
            first: Nombre maximum de clips à récupérer (max 100)
            started_at: Date de début ISO 8601 (ex: "2024-01-01T00:00:00Z")
            ended_at: Date de fin ISO 8601
            
        Returns:
            Liste de clips triés par vues décroissantes
        """
        params = {
            "broadcaster_id": broadcaster_id,
            "first": min(first, 100),  # Limite API = 100
        }
        
        if started_at:
            params["started_at"] = started_at
        if ended_at:
            params["ended_at"] = ended_at
            
        response = requests.get(
            f"{self.BASE_URL}/clips",
            headers=self._get_headers(),
            params=params,
            timeout=10
        )
        response.raise_for_status()
        
        clips = response.json().get("data", [])
        logger.debug(f"Récupéré {len(clips)} clips pour broadcaster {broadcaster_id}")
        
        return clips
