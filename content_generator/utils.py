from collections import defaultdict

from django.utils import timezone as django_tz

from events.helper.datetime_helper import weekday_name, month_name
from events.utils import channel_api_request


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
