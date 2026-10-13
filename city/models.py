from django.core.cache import cache
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_delete, post_save


class City(models.Model):
    SPB = 'spb'
    KZN = 'kzn'
    # Pseudo-city for shared rows (prompts, themes). Only tables that mix shared and
    # per-city rows may reference it; per-city tables reject it (see city_field).
    ALL = 'all'

    code = models.CharField(primary_key=True, max_length=8)
    name = models.CharField(max_length=100)
    name_gen = models.CharField(max_length=100, blank=True, help_text='Родительный падеж: «Казани»')
    name_loc = models.CharField(max_length=100, blank=True, help_text='Предложный падеж: «в Казани»')
    timezone = models.CharField(max_length=64, default='Europe/Moscow')
    is_active = models.BooleanField(default=False)
    channel_id = models.BigIntegerField(null=True, blank=True)
    dev_channel_id = models.BigIntegerField(null=True, blank=True)
    channel_link = models.CharField(max_length=200, blank=True)
    vk_group_id = models.BigIntegerField(null=True, blank=True)
    vk_dev_group_id = models.BigIntegerField(null=True, blank=True)
    bot_url = models.CharField(max_length=200, blank=True)
    dgis_slug = models.CharField(max_length=50, blank=True, help_text='Город в ссылках 2GIS: 2gis.ru/<slug>/search/…')
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'code']
        verbose_name = 'Город'
        verbose_name_plural = 'Города'

    def __str__(self):
        return self.name


CITIES_CACHE_KEY = 'city:all'
CITIES_CACHE_TTL = 300


def get_cities():
    """{code: City} for every city including 'all'; cached per worker (LocMem)."""
    return cache.get_or_set(
        CITIES_CACHE_KEY, lambda: {c.code: c for c in City.objects.all()}, CITIES_CACHE_TTL,
    )


def get_city(code):
    return get_cities().get(code)


def _invalidate_cities(**kwargs):
    cache.delete(CITIES_CACHE_KEY)


post_save.connect(_invalidate_cities, sender=City, dispatch_uid='city_cache_save')
post_delete.connect(_invalidate_cities, sender=City, dispatch_uid='city_cache_delete')


def city_field(default=City.SPB):
    """FK to City; `default` is both the Python and the DB default.

    The DB default lets ChannelBot keep inserting rows without knowing the column.
    """
    return models.ForeignKey(
        City,
        on_delete=models.PROTECT,
        default=default,
        db_default=default,
        limit_choices_to=None if default == City.ALL else ~Q(code=City.ALL),
        verbose_name='Город',
    )


def city_not_all_constraint():
    """For per-city tables: a row always belongs to a real city."""
    return models.CheckConstraint(
        condition=~Q(city=City.ALL),
        name='%(app_label)s_%(class)s_city_not_all',
    )
