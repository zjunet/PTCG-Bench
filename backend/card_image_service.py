"""
Card Image Mapping Service
Provides card name to image URL mapping by reading card_data_cache.json
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class CardImageService:
    """Service for managing card image URLs"""

    def __init__(self, cache_path: Optional[str] = None):
        if cache_path is None:
            self.cache_path: Path = Path(__file__).parent.parent / "card_data_cache.json"
        else:
            self.cache_path = Path(cache_path)

        self.card_images: Dict[str, Dict[str, str]] = {}
        self._build_image_map()

    def _build_image_map(self):
        """Build card name to image URL mapping from card_data_cache.json"""
        if not self.cache_path.exists():
            logger.warning(f"Cache file not found: {self.cache_path}")
            return

        logger.info(f"Loading card images from {self.cache_path}")

        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)

            for card_id, card in cache.items():
                card_name = card.get("name")
                image_url = card.get("img")

                if card_name and image_url:
                    self.card_images[card_name] = {
                        "url": image_url,
                        "set": card.get("set_name", ""),
                        "number": card.get("number", ""),
                        "card_type": card.get("card_type", ""),
                    }

            logger.info(f"Loaded {len(self.card_images)} card images from cache")

        except Exception as e:
            logger.error(f"Error loading cache: {e}")
            self.card_images = {}

    def get_card_image_url(self, card_name: str) -> Optional[str]:
        """Get image URL for a card"""
        card_info = self.card_images.get(card_name)
        return card_info["url"] if card_info else None

    def get_all_card_images(self) -> Dict[str, str]:
        """Get all card name to URL mappings"""
        return {name: info["url"] for name, info in self.card_images.items()}

    def get_card_info(self, card_name: str) -> Optional[Dict[str, str]]:
        """Get full card info including URL and metadata"""
        return self.card_images.get(card_name)


# Global instance
card_image_service = CardImageService()
