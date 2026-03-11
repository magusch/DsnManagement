"""
Telegram MarkdownV2 utilities: escaping and converting to HTML for admin preview.

MarkdownV2 special characters that MUST be escaped with \\ outside of formatting:
    _ * [ ] ( ) ~ ` > # + - = | { } . !

Formatting syntax:
    *bold*   _italic_   __underline__   ~strikethrough~
    ||spoiler||   `inline code`   ```pre```
    [text](url)   ![emoji](tg://emoji?id=ID)
    > blockquote
"""
import re

# Regex for chars to escape in plain text segments
_V2_ESCAPE_RE = re.compile(r'([_*\[\]()~`>#+\-=|{}.!])')

# Custom emoji: ![alt](tg://emoji?id=123)
_CUSTOM_EMOJI_RE = re.compile(r'!\[([^\]]*)\]\(tg://emoji\?id=\d+\)')

# Markdown links: [text](url)
_LINK_RE = re.compile(r'\[([^\]]*)\]\(([^)]*)\)')


def escape_v2(text):
    """Escape all MarkdownV2 special characters in plain text.

    Preserves custom emoji ![alt](tg://emoji?id=ID)
    and markdown links [text](url) from being escaped.
    """
    protected = []

    def _save(m):
        protected.append(m.group(0))
        return f'\x00PROT{len(protected) - 1}\x00'

    text = _CUSTOM_EMOJI_RE.sub(_save, text)
    text = _LINK_RE.sub(_save, text)

    text = _V2_ESCAPE_RE.sub(r'\\\1', text)

    for i, original in enumerate(protected):
        text = text.replace(f'\x00PROT{i}\x00', original)

    return text


def escape_v2_url(url):
    """Escape only ) and \\ inside markdown link URLs."""
    return url.replace('\\', '\\\\').replace(')', '\\)')


# --- MarkdownV2 to HTML conversion for admin preview ---

def v2_to_html(text):
    """Convert Telegram MarkdownV2 text to HTML for Django admin preview."""
    # 1. Protect custom emoji: ![alt](tg://emoji?id=ID)
    emojis = []

    def _save_emoji(m):
        emojis.append(m.group(1))
        return f'\x00EMOJI{len(emojis) - 1}\x00'

    text = _CUSTOM_EMOJI_RE.sub(_save_emoji, text)

    # 2. Protect markdown links [text](url)
    links = []

    def _save_link(m):
        links.append((m.group(1), m.group(2)))
        return f'\x00LINK{len(links) - 1}\x00'

    text = _LINK_RE.sub(_save_link, text)

    # 3. Save all escaped characters: \X -> placeholder
    escapes = []

    def _save_escape(m):
        escapes.append(m.group(1))
        return f'\x00ESC{len(escapes) - 1}\x00'

    text = re.sub(r'\\(.)', _save_escape, text)

    # 4. Convert formatting (order matters: longer markers first)
    text = re.sub(r'__([^_]+)__', r'<u>\1</u>', text)           # underline
    text = re.sub(r'~([^~]+)~', r'<s>\1</s>', text)             # strikethrough
    text = re.sub(r'\|\|([^|]+)\|\|',                            # spoiler
                  r'<span class="tg-spoiler" style="background:#ccc;color:#ccc">\1</span>', text)
    text = re.sub(r'\*([^*]+)\*', r'<b>\1</b>', text)           # bold
    text = re.sub(r'_([^_]+)_', r'<i>\1</i>', text)             # italic
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)       # inline code

    # 5. Restore escaped characters as literal
    for i, ch in enumerate(escapes):
        text = text.replace(f'\x00ESC{i}\x00', ch)

    # 6. Restore custom emoji (show alt text)
    for i, alt in enumerate(emojis):
        text = text.replace(f'\x00EMOJI{i}\x00', alt)

    # 7. Restore links
    for i, (link_text, url) in enumerate(links):
        clean_url = re.sub(r'\\(.)', r'\1', url)
        text = text.replace(
            f'\x00LINK{i}\x00',
            f'<a href="{clean_url}" target="_blank">{link_text}</a>'
        )

    # 8. Newlines to <br>
    text = text.replace('\n', '<br>')
    return text
