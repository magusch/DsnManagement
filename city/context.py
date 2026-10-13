"""Which city a request or a background job works for."""
import logging
import zoneinfo
from contextlib import contextmanager

from django.core.exceptions import BadRequest
from django.utils import timezone

from .models import City, get_cities

log = logging.getLogger(__name__)

SESSION_KEY = 'city'


@contextmanager
def city_context(city_code):
    """Run code in the city's local time (`localtime`, `localdate`, `__date`, slots).

    No-op for 'all' and unknown codes: the default TIME_ZONE applies.
    """
    city = get_cities().get(city_code)
    if city is None or city.code == City.ALL:
        yield
        return
    with timezone.override(zoneinfo.ZoneInfo(city.timezone)):
        yield


def admin_city(request):
    """City picked in the admin switcher: a city code or City.ALL. Defaults to SPb."""
    code = request.session.get(SESSION_KEY, City.SPB) if hasattr(request, 'session') else City.SPB
    return code if code in get_cities() else City.SPB


def city_from_request(request):
    """City for a collection-scoped endpoint (queue, slots, parameters, place lookup).

    `?city=<code>` wins (ChannelBot), then the admin switcher. Without either — SPb,
    which is what every caller meant before multicity; logged so the remaining
    callers can be found and fixed.
    """
    code = request.GET.get('city')
    if code:
        if code == City.ALL or code not in get_cities():
            raise BadRequest(f'Unknown city: {code}')
        return code

    code = admin_city(request)
    if code != City.ALL and SESSION_KEY in getattr(request, 'session', {}):
        return code

    log.warning('multicity: missing city on %s, using %s', request.path, City.SPB)
    return City.SPB
