"""Central configuration. All secrets come from environment variables."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///midya.db")
BUFFER_ACCESS_TOKEN = os.getenv("BUFFER_ACCESS_TOKEN", "")
BUFFER_PROFILE_IDS = [p for p in os.getenv("BUFFER_PROFILE_IDS", "").split(",") if p]
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

GENERATOR_PROVIDER = os.getenv("GENERATOR_PROVIDER", "openai")
JUDGE_PROVIDER = os.getenv("JUDGE_PROVIDER", "anthropic")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")

AUTO_PUBLISH = os.getenv("AUTO_PUBLISH", "false").lower() == "true"
PROMPT_VERSION = "v2.1-arabic-pipeline"
