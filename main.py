"""
Point d'entrée principal du pipeline.
Permet le lancement manuel d'une exécution.

Usage :
    python main.py              # Lance une exécution immédiate
    python main.py --dry-run    # Simule sans télécharger
    python main.py --stats      # Affiche les statistiques
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

# Chargement des variables d'environnement
load_dotenv()


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline automatique Twitch Clips → TikTok"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simule l'exécution sans télécharger ni traiter"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Affiche les statistiques de la base de données"
    )
    parser.add_argument(
        "--clip",
        type=str,
        metavar="URL",
        help="Traite un clip spécifique par son URL Twitch"
    )
    
    args = parser.parse_args()
    
    if args.stats:
        _show_stats()
        return
    
    if args.dry_run:
        logger.info("🔍 Mode dry-run activé (aucun fichier ne sera créé)")
        _dry_run()
        return
    
    if args.clip:
        _process_single_clip(args.clip)
        return
    
    # Exécution normale du pipeline
    _run_pipeline()


def _run_pipeline():
    """Lance le pipeline complet."""
    from src.pipeline import Pipeline
    
    try:
        pipeline = Pipeline()
        pipeline.run()
    except EnvironmentError as e:
        logger.error(f"Configuration manquante:\n{e}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Erreur fatale: {e}")
        sys.exit(1)


def _dry_run():
    """Simule le pipeline sans traitement réel."""
    from src.fetcher.twitch_client import TwitchClient
    from src.fetcher.clip_fetcher import ClipFetcher
    import os
    
    client = TwitchClient(
        client_id=os.getenv("TWITCH_CLIENT_ID", ""),
        client_secret=os.getenv("TWITCH_CLIENT_SECRET", ""),
    )
    fetcher = ClipFetcher(client)
    clips = fetcher.fetch_all_streamers()
    
    logger.info(f"\n📋 {len(clips)} clips seraient traités :")
    for i, clip in enumerate(clips, 1):
        logger.info(
            f"  {i:2}. [{clip.get('view_count', 0):>6} vues] "
            f"{clip.get('broadcaster_name', '?'):15} | "
            f"{clip.get('title', '')[:50]}"
        )


def _show_stats():
    """Affiche les statistiques de la base de données."""
    from src.storage.database import Database
    
    db = Database()
    stats = db.get_stats()
    
    print("\n📊 Statistiques du Pipeline")
    print("─" * 40)
    print(f"  Total clips     : {stats.get('total', 0)}")
    print(f"  Complétés       : {stats.get('completed', 0)} ✅")
    print(f"  Échoués         : {stats.get('failed', 0)} ❌")
    print(f"  En attente      : {stats.get('pending', 0)} ⏳")
    print("─" * 40 + "\n")


def _process_single_clip(url: str):
    """Traite un clip unique depuis son URL."""
    logger.info(f"Traitement du clip: {url}")
    # TODO: Implémenter le traitement d'un clip unique
    logger.warning("Fonctionnalité en cours d'implémentation")


if __name__ == "__main__":
    main()

