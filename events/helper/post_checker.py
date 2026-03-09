import re

# Regex to match markdown links [text](url) and raw URLs
_LINK_RE = re.compile(r'\[([^\]]*)\]\([^)]*\)')
_URL_RE = re.compile(r'https?://\S+')
# Escaped markdown characters like \* or \_
_ESCAPED_RE = re.compile(r'\\[*_`]')

CRITICAL_ICON = '<span style="color:red" title="{title}">{symbol}</span>'
WARNING_ICON = '<span style="color:orange" title="{title}">{symbol}</span>'


def _strip_non_markdown(text):
    """Remove URLs, markdown links, and escaped chars so only real formatting remains."""
    text = _LINK_RE.sub(r'\1', text)  # [text](url) -> text
    text = _URL_RE.sub('', text)
    text = _ESCAPED_RE.sub('', text)  # \* \_ \` -> gone
    return text


class PostChecker:
    """Checks Events2Post for data quality issues.

    Usage:
        checker = PostChecker(event)  # pass Events2Post instance
        checker.errors   -> list of (symbol, message, is_critical)
        checker.icons_html() -> HTML string for admin list_display
    """

    def __init__(self, event):
        self.event = event
        self.post = event.post or ''
        self.clean_post = _strip_non_markdown(self.post)
        self.errors = []
        self._run_checks()

    def _add(self, symbol, message, critical=True):
        self.errors.append((symbol, message, critical))

    def _run_checks(self):
        self._check_asterisks()
        self._check_underscores()
        self._check_all_bold()
        self._check_length()
        self._check_full_text_empty()
        self._check_price()
        self._check_place()
        self._check_category()

    # --- Critical checks ---

    def _check_asterisks(self):
        count = self.clean_post.count('*')
        if count % 2 != 0:
            self._add('*', f"Odd number of * ({count})")

    def _check_underscores(self):
        count = self.clean_post.count('_')
        if count % 2 != 0:
            self._add('_', f"Odd number of _ ({count})")

    def _check_all_bold(self):
        lines = self.clean_post.strip().split('\n')
        if not lines:
            return
        first_line = lines[0]
        ast_count = first_line.count('*')
        if ast_count >= 3 and ast_count % 2 != 0:
            self._add('T', f"Title has odd * ({ast_count})")
            return
        stripped = self.clean_post.strip()
        if len(stripped) > 50 and stripped.startswith('*') and stripped.endswith('*'):
            inner = stripped[1:-1]
            if '*' not in inner:
                self._add('B', "Entire post is bold")

    def _check_length(self):
        length = len(self.post)
        if length > 1000:
            self._add('L', f"Post too long ({length} chars)")

    def _check_full_text_empty(self):
        full_text = self.event.full_text
        if not full_text or not full_text.strip():
            self._add('F', "full_text is empty")

    def _check_price(self):
        price_int = self.event.price_int
        price = (self.event.price or '').strip().lower()
        if price_int == -1:
            has_digits = any(c.isdigit() for c in price)
            is_free = 'бесплатно' in price or 'free' in price
            if not has_digits and not is_free:
                self._add('$', f"Unclear price: '{self.event.price}'")

    # --- Warning checks (minor) ---

    def _check_place(self):
        if self.event.place_id is None:
            self._add('P', "No place linked", critical=False)

    def _check_category(self):
        if self.event.main_category_id == 2:
            self._add('C', "Category is 'Other'", critical=False)

    # --- Output ---

    @property
    def has_critical(self):
        return any(critical for _, _, critical in self.errors)

    @property
    def has_warnings(self):
        return any(not critical for _, _, critical in self.errors)

    def icons_html(self):
        if not self.errors:
            return ''
        parts = []
        for symbol, message, critical in self.errors:
            template = CRITICAL_ICON if critical else WARNING_ICON
            parts.append(template.format(title=message, symbol=symbol))
        return ' '.join(parts)

    def summary(self):
        return '; '.join(msg for _, msg, _ in self.errors)
