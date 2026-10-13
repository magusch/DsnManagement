import re
from collections import defaultdict

from django.utils.html import escape
from django.utils.safestring import mark_safe

from django.utils import timezone as django_tz

from events.helper.datetime_helper import weekday_name, month_name
from events.models import PostingTime
from events.utils import channel_api_request, next_slot


class SafeDict(defaultdict):
    """Dict that returns "" for any missing key — templates never crash."""

    def __init__(self, *args, **kwargs):
        super().__init__(lambda: "", *args, **kwargs)

    def __missing__(self, key):
        return ""


def _safe_attr(obj, path, default=""):
    """Safely resolve dotted attribute path: 'place.place_name' → value or default."""
    try:
        for attr in path.split("."):
            obj = getattr(obj, attr)
        return obj if obj is not None else default
    except (AttributeError, TypeError):
        return default


def _to_local(dt):
    """Convert aware datetime to local timezone."""
    if dt is None:
        return None
    return django_tz.localtime(dt)


def _format_event_date(event):
    """Human-readable date: 'Сб, 16 марта 14:00' or 'Сб, 16 марта — Вск, 17 марта'."""
    date_from = _to_local(event.from_date)
    if not date_from:
        return ""

    wd = weekday_name(date_from)
    day = date_from.day
    month = month_name(date_from)
    hour = date_from.hour
    minute = date_from.minute

    date_to = _to_local(event.to_date)

    if date_to is None or date_from.date() == date_to.date():
        # Same day or no end date
        if hour == 0 and minute == 0:
            return f"{wd}, {day} {month}"
        return f"{wd}, {day} {month} {hour:02}:{minute:02}"

    # Different days
    wd2 = weekday_name(date_to)
    day2 = date_to.day
    month2 = month_name(date_to)

    if date_from.month == date_to.month:
        return f"{wd}–{wd2}, {day}–{day2} {month}"

    return f"{wd}, {day} {month} — {wd2}, {day2} {month2}"


def _build_location(event):
    """Build smart location fields without duplication.

    Returns (location, metro) where:
    - location: "Place Name, улица, д.1" or just "улица, д.1"
    - metro: "м.Невский проспект" or ""
    """
    place_name = _safe_attr(event, "place.place_name")
    place_address = _safe_attr(event, "place.place_address")
    place_metro = _safe_attr(event, "place.place_metro")
    raw_address = event.address or ""

    # Always strip metro from raw address to avoid duplication
    import re
    metro = place_metro
    address_without_metro = raw_address
    if raw_address:
        metro_match = re.search(r',?\s*(м\.\s*\S+(?:\s+\S+)?|метро\s+\S+(?:\s+\S+)?)\s*$', raw_address)
        if metro_match:
            if not metro:
                metro = metro_match.group(1).strip().lstrip(',').strip()
            address_without_metro = raw_address[:metro_match.start()].strip().rstrip(',')

    # Build street address — remove place_name from address to avoid duplication
    street = address_without_metro
    if place_name and street:
        # Remove place name from beginning of address
        if street.lower().startswith(place_name.lower()):
            street = street[len(place_name):].lstrip(',').lstrip().lstrip(',').strip()

    # Combine: "Place Name, street" or just "street" or just "Place Name"
    if place_name and street:
        location = f"{place_name}, {street}"
    elif place_name:
        location = place_name
    else:
        location = street

    return location, metro or ""


def _build_event_context(event):
    """Build context from event. Any new field added to templates on API side
    that isn't here will just become '' — no crash."""
    ctx = SafeDict()

    ctx["title"] = event.title or ""
    ctx["price"] = event.price or "Бесплатно"
    ctx["prepared_text"] = event.prepared_text or ""
    ctx["url"] = event.url or ""
    ctx["category"] = event.category or ""

    # Raw fields (kept for backwards compat)
    ctx["address"] = event.address or ""
    ctx["place_name"] = _safe_attr(event, "place.place_name")
    ctx["place_address"] = _safe_attr(event, "place.place_address")
    ctx["place_metro"] = _safe_attr(event, "place.place_metro")

    # Smart location — no duplication
    location, metro = _build_location(event)
    ctx["location"] = location
    ctx["metro"] = metro

    # Dates — human-readable (in local timezone)
    ctx["event_date"] = _format_event_date(event)
    if event.from_date:
        ctx["from_date"] = _to_local(event.from_date).strftime("%d.%m.%Y %H:%M")
    if event.to_date:
        ctx["to_date"] = _to_local(event.to_date).strftime("%d.%m.%Y %H:%M")

    return ctx


def generate_post(events, template):
    """Generate post from events + template string.

    Any {variable} in template that is not in context → empty string.
    Never raises KeyError — safe for fallback use.
    """
    blocks = []
    for event in events:
        ctx = _build_event_context(event)
        block = template.format_map(ctx)
        blocks.append(block.strip())
    return "\n\n---\n\n".join(blocks)


def event_selection_by_filter_id(filter_id):
    data = {
        "api_url": "api/content_generator_event_selection/",
        "method": "POST",
        "data": {"filter_set_id": filter_id[0]}
    }

    response, error = channel_api_request(data)
    if error or response is None:
        return None
    if response.status_code == 200:
        return True


def generate_post_api(event_selection_id, template_id):
    data = {
        "api_url": "api/content_generator_generate_post/",
        "method": "POST",
        "data": {
            "event_selection_id": event_selection_id,
            "post_template_id": template_id,
        }
    }

    response, error = channel_api_request(data)
    if error or response is None:
        return None
    if response.status_code == 200:
        return True


def theme_post_api(filter_set_id=None, dry_run=False):
    """Ask the channel API to build a themed digest post.

    Without filter_set_id the API picks the least-recently-posted active theme.
    Returns (result_dict, error_message) — result is the raw API JSON
    (usually {'message': ..., 'task_id': ...}).
    """
    payload = {"filter_set_id": filter_set_id, "dry_run": bool(dry_run)}

    response, error = channel_api_request({
        "api_url": "api/content-generator/theme-post/",
        "method": "POST",
        "data": payload,
    })
    if error:
        return None, error

    try:
        return response.json(), None
    except Exception:
        return None, "Невалидный ответ от API"


def refresh_digest_posting_time():
    """Put pending digests into the `digest` PostingTime slots, one per slot.

    Pending = not posted and ReadyToPost (overdue ones included — they need a new
    time anyway). Their current order is kept. Returns the updated schedules;
    empty when there are no active digest slots.
    """
    from .models import PostingSchedule

    pending = PostingSchedule.objects.filter(
        is_posted=False, status="ReadyToPost"
    ).order_by("scheduled_time", "id")

    updated = []
    slot_time = django_tz.now()
    for schedule in pending:
        slot_time = next_slot(slot_time, kind=PostingTime.KIND_DIGEST)
        if slot_time is None:
            break
        schedule.scheduled_time = slot_time
        schedule.save(update_fields=["scheduled_time", "updated_at"])
        updated.append(schedule)
    return updated


# --- Post markdown → HTML (channel preview) ---------------------------------

_MEDIA_RE = re.compile(r'!\[([^\]]*)\]\(tg://photo\?id=([^)]*)\)')
_TG_EMOJI_RE = re.compile(r'!\[([^\]]*)\]\(tg://emoji\?id=\d+\)')
_MD_LINK_RE = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')
_HEADING_RE = re.compile(r'^[ \t]{0,3}#{1,6}[ \t]*(.+?)[ \t]*#*$', re.MULTILINE)
_ESCAPE_RE = re.compile(r'\\([_*\[\]()~`>#+\-=|{}.!\\])')

_SAFE_SCHEMES = ('http://', 'https://', 'tg://', 'mailto:', '/')


def _clean_url(url):
    """Unescape a MarkdownV2 URL and drop anything that isn't a safe scheme."""
    url = url.replace('\\)', ')').replace('\\\\', '\\').strip()
    if url.startswith(_SAFE_SCHEMES):
        return url
    return '#'


def _media_chip(media_id):
    """Placeholder for a photo that Telegram attaches to the post itself."""
    label = f'🖼 фото {media_id}' if media_id else '🖼 фото'
    return f'<span class="tg-post-media">{label}</span>'


def post_markdown_to_html(text):
    """Render post markdown as the channel shows it. Input must be HTML-escaped."""
    protected = []

    def protect(html):
        protected.append(html)
        return f'\x00P{len(protected) - 1}\x00'

    text = text.replace('\r\n', '\n').replace('\r', '\n')

    text = _MEDIA_RE.sub(lambda m: protect(_media_chip(m.group(2))), text)
    text = _TG_EMOJI_RE.sub(lambda m: protect(m.group(1)), text)
    text = _MD_LINK_RE.sub(
        lambda m: protect(
            f'<a href="{_clean_url(m.group(2))}" target="_blank" rel="noopener">{m.group(1)}</a>'
        ),
        text,
    )
    # MarkdownV2 escapes: keep the character, lose the backslash
    text = _ESCAPE_RE.sub(lambda m: protect(m.group(1)), text)

    # Telegram has no headings — the channel shows them as bold
    text = _HEADING_RE.sub(r'<b class="tg-post-heading">\1</b>', text)

    text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)      # classic bold
    text = re.sub(r'__([^_]+)__', r'<b>\1</b>', text)           # classic bold / v2 underline
    text = re.sub(r'\*([^*\n]+)\*', r'<b>\1</b>', text)        # v2 bold
    text = re.sub(r'\|\|([^|]+)\|\|',
                  r'<span class="tg-spoiler">\1</span>', text)   # spoiler
    text = re.sub(r'~([^~\n]+)~', r'<s>\1</s>', text)           # strikethrough
    text = re.sub(r'(?<![\w])_([^_\n]+)_(?![\w])', r'<i>\1</i>', text)  # italic
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)        # inline code
    text = re.sub(r'^&gt;\s?(.*)$', r'<blockquote>\1</blockquote>',
                  text, flags=re.MULTILINE)                     # blockquote

    text = text.replace('\n', '<br>')

    for i, html in enumerate(protected):
        text = text.replace(f'\x00P{i}\x00', html)
    return text


def render_post_html(content, image=None):
    """Render post content as the channel would show it.

    Content is HTML-escaped before conversion, so the result is safe to mark_safe.
    """
    html = post_markdown_to_html(escape(content or ""))
    if not html:
        html = '<span class="tg-post-empty">Пост пустой</span>'
    if image:
        html = f'<img class="tg-post-image" src="{escape(image)}" alt="">' + html
    return mark_safe(f'<div class="tg-post-card">{html}</div>')
