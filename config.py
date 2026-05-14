from pathlib import Path

DB_PATH = Path.home() / ".local/share/memevault/vault.db"
INCOMING_DIR = Path.home() / "Pictures" / "memes"
PHASH_THRESHOLD = 10
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# Local vision-language model identifier (HuggingFace repo or local path)
VLM_MODEL = "./models/qwen2.5-vl-3b"

# Multimodal embedding model (vision + text in shared space)
EMBEDDING_MODEL = "jinaai/jina-embeddings-v5-omni-small-retrieval"
