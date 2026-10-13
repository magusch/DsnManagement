from django.core.cache import cache


class EmojiManager:
    """Cached mapping of unicode emoji -> custom_emoji_id for Telegram."""
    CACHE_KEY = 'emoji_mapping'
    CACHE_TIMEOUT = 43200  # 12 hours

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_from_cache()
        return cls._instance

    def _load_from_cache(self):
        self._mapping = cache.get(self.CACHE_KEY)
        if self._mapping is None:
            self._load_from_db()

    def _load_from_db(self):
        from .models import EmojiMapping
        self._mapping = dict(
            EmojiMapping.objects.filter(custom_emoji_id__isnull=False)
            .exclude(custom_emoji_id='')
            .values_list('emoji', 'custom_emoji_id')
        )
        cache.set(self.CACHE_KEY, self._mapping, timeout=self.CACHE_TIMEOUT)

    def refresh(self):
        self._load_from_db()

    def get_custom_id(self, emoji):
        """Return custom_emoji_id for a unicode emoji, or None."""
        self._load_from_cache()
        return self._mapping.get(emoji)

    def replace_emojis(self, text):
        """Replace unicode emojis with Telegram custom emoji syntax where mapping exists."""
        self._load_from_cache()
        if not self._mapping:
            return text
        for emoji, custom_id in self._mapping.items():
            if emoji in text:
                text = text.replace(emoji, f'![{emoji}](tg://emoji?id={custom_id})')
        return text
