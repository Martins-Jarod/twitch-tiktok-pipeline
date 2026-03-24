#!/bin/bash
# ============================================================
# Script d'installation automatique du pipeline
# Compatible: Ubuntu 20.04+, Debian 11+, macOS
# ============================================================

set -e  # Arrêt immédiat en cas d'erreur

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  Installation Pipeline Twitch → TikTok  ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Vérification Python ──────────────────────────────────────
echo "▶ Vérification de Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 non trouvé. Installation requise."
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  ✓ Python $PYTHON_VERSION trouvé"

# ── Installation FFmpeg ──────────────────────────────────────
echo ""
echo "▶ Vérification de FFmpeg..."
if ! command -v ffmpeg &> /dev/null; then
    echo "  Installation de FFmpeg..."
    
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo apt-get update -qq
        sudo apt-get install -y ffmpeg
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &> /dev/null; then
            brew install ffmpeg
        else
            echo "❌ Homebrew requis sur macOS. Installez-le depuis https://brew.sh"
            exit 1
        fi
    else
        echo "❌ OS non supporté. Installez FFmpeg manuellement."
        exit 1
    fi
fi
echo "  ✓ FFmpeg $(ffmpeg -version 2>&1 | head -1 | cut -d' ' -f3) trouvé"

# ── Environnement virtuel Python ─────────────────────────────
echo ""
echo "▶ Création de l'environnement virtuel..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "  ✓ Environnement virtuel créé"
else
    echo "  ✓ Environnement virtuel existant"
fi

source venv/bin/activate

# ── Installation des dépendances Python ──────────────────────
echo ""
echo "▶ Installation des dépendances Python..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  ✓ Dépendances installées"

# ── Création des dossiers nécessaires ────────────────────────
echo ""
echo "▶ Création de la structure de dossiers..."
mkdir -p output tmp logs data
echo "  ✓ Dossiers créés"

# ── Configuration .env ───────────────────────────────────────
echo ""
echo "▶ Configuration..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  ⚠️  Fichier .env créé depuis .env.example"
    echo "  ⚠️  IMPORTANT: Remplissez vos clés API dans .env"
else
    echo "  ✓ Fichier .env existant"
fi

# ── Test de l'installation ───────────────────────────────────
echo ""
echo "▶ Test de l'installation..."
python3 -c "
import sys
modules = ['requests', 'yt_dlp', 'faster_whisper', 'apscheduler', 'yaml', 'loguru']
failed = []
for mod in modules:
    try:
        __import__(mod)
    except ImportError:
        failed.append(mod)

if failed:
    print(f'  ❌ Modules manquants: {failed}')
    sys.exit(1)
else:
    print('  ✓ Tous les modules Python sont disponibles')
"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║            Installation terminée !       ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Prochaines étapes :"
echo "  1. Remplissez le fichier .env avec vos clés API"
echo "  2. Configurez config/streamers.yaml avec vos streamers"
echo "  3. Testez avec : python main.py --dry-run"
echo "  4. Lancez     : python main.py"
echo "  5. Scheduler  : python scheduler.py --run-now"
echo ""
