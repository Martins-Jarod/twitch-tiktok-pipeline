"""
Scheduler automatique du pipeline.
Lance le pipeline à intervalles réguliers en arrière-plan.

Usage :
    python scheduler.py          # Démarrage en mode continu
    python scheduler.py --once   # Exécution immédiate puis schedule
"""

import sys
import signal
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
from loguru import logger

load_dotenv()


def run_pipeline_job():
    """Job APScheduler : exécute le pipeline."""
    logger.info(f"⏰ Démarrage automatique: {datetime.now().strftime('%H:%M:%S')}")
    
    try:
        from src.pipeline import Pipeline
        Pipeline().run()
    except Exception as e:
        logger.error(f"Erreur dans le job schedulé: {e}", exc_info=True)


def main():
    from src.utils.helpers import load_config
    
    config = load_config()
    scheduler_cfg = config.get("scheduler", {})
    
    interval_hours = scheduler_cfg.get("interval_hours", 6)
    timezone       = scheduler_cfg.get("timezone", "Europe/Paris")
    
    scheduler = BlockingScheduler(timezone=timezone)
    
    # Ajout du job
    scheduler.add_job(
        func=run_pipeline_job,
        trigger=IntervalTrigger(hours=interval_hours),
        id="pipeline_job",
        name="Pipeline Twitch → TikTok",
        replace_existing=True,
        max_instances=1,        # Évite les exécutions parallèles
        misfire_grace_time=300, # 5 min de tolérance si le job est en retard
    )
    
    # Gestion propre de l'arrêt (Ctrl+C ou signal système)
    def shutdown(signum, frame):
        logger.info("Signal d'arrêt reçu, arrêt du scheduler...")
        scheduler.shutdown(wait=False)
        sys.exit(0)
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    logger.info("=" * 60)
    logger.info("⏰ Scheduler démarré")
    logger.info(f"   Intervalle : toutes les {interval_hours}h")
    logger.info(f"   Timezone   : {timezone}")
    logger.info(f"   Prochain run: {scheduler.get_jobs()[0].next_run_time}")
    logger.info("=" * 60)
    
    # Exécution immédiate au démarrage si --once
    if "--once" in sys.argv or "--run-now" in sys.argv:
        logger.info("Exécution immédiate au démarrage...")
        run_pipeline_job()
    
    try:
        scheduler.start()
    except Exception as e:
        logger.critical(f"Erreur fatale du scheduler: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
