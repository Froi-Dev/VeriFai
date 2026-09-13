from app.FakeNewsAnalyzer.image_fact_checker import GeminiVisionClient
from app.Global.config import settings

# One process-wide client shares connection pooling, round-robin selection, and
# per-key cooldown state between image detection and OCR fallback.
gemini_vision_client = GeminiVisionClient(settings)
