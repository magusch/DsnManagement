from django.core.cache import cache

from city.models import City
from ..models import Parameter


def merge_city_parameters(rows, city):
    """A city's own rows replace the shared ('all') rows with the same (site, name)."""
    overridden = {(r['site'], r['parameter_name']) for r in rows if r['city_id'] == city}
    return [r for r in rows
            if r['city_id'] == city or (r['site'], r['parameter_name']) not in overridden]


class ParametersManager:
    """`dsn_site` parameters (prompts, models) per city: the shared ones plus the city's overrides."""
    CACHE_KEY = 'parameters:{city}'
    LOCK_KEY = 'parameters_lock'

    def __new__(cls):
        if not hasattr(cls, '_instance'):
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load(self, city):
        rows = Parameter.objects.filter(site='dsn_site', city_id__in=[city, City.ALL]).values(
            'site', 'parameter_name', 'value', 'city_id')
        parameters = {r['parameter_name']: r['value'] for r in merge_city_parameters(list(rows), city)}
        cache.set(self.CACHE_KEY.format(city=city), parameters, timeout=43200)
        return parameters

    def get_parameter(self, parameter_name, city=City.SPB):
        parameters = cache.get(self.CACHE_KEY.format(city=city))
        if parameters is None:
            parameters = self._load(city)
        return parameters.get(parameter_name)

    def update_parameters_from_db(self, city=City.SPB):
        self._load(city)

    def periodic_update(self):
        self.update_parameters_from_db()
