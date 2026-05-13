from pathlib import Path

DB_PATH = Path.home() / ".memevault" / "vault.db"
INCOMING_DIR = Path.home() / "Pictures" / "memes" / "incoming"
PHASH_THRESHOLD = 10
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# Local vision-language model identifier (HuggingFace repo or local path)
VLM_MODEL = "Salesforce/blip-image-captioning-base"
