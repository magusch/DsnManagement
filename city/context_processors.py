from .models import get_cities


def city(request):
    """City switcher data for the admin header."""
    user = getattr(request, 'user', None)
    if user is None or not user.is_staff:
        return {}
    cities = get_cities()
    return {
        'current_city': cities.get(getattr(request, 'city', None)),
        'city_choices': sorted(cities.values(), key=lambda c: (c.sort_order, c.code)),
    }
