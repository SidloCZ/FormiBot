import os
from pathlib import Path
from dotenv import load_dotenv

# Cesty projektu
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Načtení proměnných z .env
load_dotenv(BASE_DIR / ".env")

# Token bota – priorita: proměnná prostředí, token.txt v rootu, token.txt ve Work
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    for token_candidate in [BASE_DIR / "token.txt", BASE_DIR / "Work" / "token.txt"]:
        if token_candidate.exists():
            try:
                with open(token_candidate, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        DISCORD_TOKEN = content
                        break
            except IOError:
                pass

BOT_PREFIX = os.getenv("BOT_PREFIX", "!")
_guild_id_env = os.getenv("DEFAULT_GUILD_ID")
DEFAULT_GUILD_ID = int(_guild_id_env) if _guild_id_env and _guild_id_env.strip() else None

# Discord ID rolí a kanálů
RESTART_ROLE_ID = 661971700556234753
STARTUP_CHANNEL_ID = 662424508266840080
BRAINROT_CHANNEL_ID = 662424508266840080
AD_CHANNEL_ID = 721732364664963103
AD_NOTIFICATION_CHANNEL_ID = 662424508266840080
AD_ROLE_ID = 803657064600567838
MOD_ROLE_IDS = [
    661971700556234753,  # Samec - mod na zkoušku
    661971822006239242,  # Královna - moderátor
    661971417746898971,  # Antkeeper - ADMIN
]
EVENTS_NOTIFICATION_CHANNEL_ID = 661958543548612660
EVENTS_ALLOWED_ROLE_IDS = [
    661971700556234753,
    661971822006239242,
    661971417746898971,
    913531312797798420,  # Informátor událostí
]
MOD_LOG_CHANNEL_ID = 707574708551548973
QUIZ_ROLE_ID = 1064127470615408792
QUIZ_SUGGESTION_CHANNEL_ID = 1402286144519143554

def get_data_path(filename: str) -> Path:
    """Vrátí absolutní cestu k datovému souboru ve složce data."""
    return DATA_DIR / filename

QUIZ_QUESTIONS_FILE = get_data_path("quiz_questions.json")
QUIZ_SUGGESTIONS_FILE = get_data_path("quiz_suggestions.json")
SCORES_FILE = get_data_path("scores.json")
HISTORICAL_ANTS_FILE = get_data_path("historical_ants_data.json")
