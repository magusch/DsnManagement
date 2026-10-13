from .context import admin_city, city_context


class CityMiddleware:
    """Sets `request.city` from the admin switcher and runs the request in that city's time."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.city = admin_city(request)
        with city_context(request.city):
            return self.get_response(request)
