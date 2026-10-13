from django.test import SimpleTestCase

from city.models import City
from content_generator.models import EventSelection, FilterSet, GeneratedPost, PostingSchedule
from events.models import (
    Events2Post, EventsNotApprovedNew, EventsNotApprovedProposed, Parameter, PostingTime,
)
from place.models import District, Place

PER_CITY_MODELS = [
    Events2Post, EventsNotApprovedNew, EventsNotApprovedProposed, PostingTime,
    Place, District, EventSelection, GeneratedPost, PostingSchedule,
]
SHARED_MODELS = [Parameter, FilterSet]


class CityFieldTests(SimpleTestCase):
    def test_per_city_models_default_to_spb(self):
        for model in PER_CITY_MODELS:
            field = model._meta.get_field('city')
            with self.subTest(model=model.__name__):
                self.assertEqual(field.default, City.SPB)
                self.assertEqual(field.db_default, City.SPB)

    def test_shared_models_default_to_all(self):
        for model in SHARED_MODELS:
            field = model._meta.get_field('city')
            with self.subTest(model=model.__name__):
                self.assertEqual(field.default, City.ALL)
                self.assertEqual(field.db_default, City.ALL)

    def test_per_city_models_reject_all(self):
        for model in PER_CITY_MODELS:
            names = {c.name for c in model._meta.constraints}
            expected = f'{model._meta.app_label}_{model._meta.model_name}_city_not_all'
            with self.subTest(model=model.__name__):
                self.assertIn(expected, names)

    def test_new_instance_gets_default_city_without_db(self):
        self.assertEqual(Events2Post(queue=1).city_id, City.SPB)
        self.assertEqual(Parameter().city_id, City.ALL)


from unittest import mock

from django.contrib import admin
from django.core.exceptions import BadRequest
from django.test import RequestFactory

from city.admin_mixins import CityScopedAdmin
from city.context import city_from_request
from events.utils import bot_handles_city
from events.views import merge_city_parameters

CITIES = dict.fromkeys([City.SPB, City.KZN, City.ALL])


@mock.patch('city.context.get_cities', return_value=CITIES)
class CityFromRequestTests(SimpleTestCase):
    def request(self, query=None, session=None):
        request = RequestFactory().get('/events/fill_empty_post_time/', query or {})
        request.session = session if session is not None else {}
        return request

    def test_query_param_wins(self, _):
        self.assertEqual(city_from_request(self.request({'city': 'kzn'}, {'city': 'spb'})), 'kzn')

    def test_all_and_unknown_codes_are_rejected(self, _):
        for code in ('all', 'msk'):
            with self.subTest(code=code), self.assertRaises(BadRequest):
                city_from_request(self.request({'city': code}))

    def test_admin_switcher_city(self, _):
        self.assertEqual(city_from_request(self.request(session={'city': 'kzn'})), 'kzn')

    def test_missing_city_falls_back_to_spb_with_warning(self, _):
        for session in ({}, {'city': 'all'}):
            with self.subTest(session=session), self.assertLogs('city.context', 'WARNING'):
                self.assertEqual(city_from_request(self.request(session=session)), 'spb')


class MergeCityParametersTests(SimpleTestCase):
    def row(self, name, city, value):
        return {'site': 'dsn_site', 'parameter_name': name, 'city_id': city, 'value': value}

    def test_city_row_overrides_shared(self):
        rows = [self.row('rules', 'all', 'shared'), self.row('rules', 'kzn', 'kazan'),
                self.row('model', 'all', 'gpt')]
        self.assertEqual([r['value'] for r in merge_city_parameters(rows, 'kzn')], ['kazan', 'gpt'])

    def test_multi_value_parameter_is_replaced_as_a_whole(self):
        rows = [self.row('bad_keywords', 'all', 'a'), self.row('bad_keywords', 'all', 'b'),
                self.row('bad_keywords', 'kzn', 'c')]
        self.assertEqual([r['value'] for r in merge_city_parameters(rows, 'kzn')], ['c'])


class ScopedAdminTests(SimpleTestCase):
    def request(self, city):
        request = RequestFactory().get('/')
        request.city = city
        request.resolver_match = None
        return request

    def scope(self, model_admin, city):
        queryset = mock.Mock()
        model_admin.scope_by_city(self.request(city), queryset)
        return queryset.filter.call_args

    def test_per_city_admin_filters_by_city(self):
        self.assertEqual(self.scope(admin.site.get_model_admin(Events2Post), 'kzn'), mock.call(city='kzn'))

    def test_related_city_lookup(self):
        from place.models import PlaceKeyword
        self.assertEqual(self.scope(admin.site.get_model_admin(PlaceKeyword), 'kzn'),
                         mock.call(place__city='kzn'))

    def test_shared_admin_shows_city_and_shared_rows(self):
        self.assertEqual(self.scope(admin.site.get_model_admin(Parameter), 'kzn'),
                         mock.call(city__in=['kzn', 'all']))

    def test_all_mode_does_not_filter(self):
        self.assertIsNone(self.scope(admin.site.get_model_admin(Events2Post), City.ALL))

    def test_city_scoped_admins_registered(self):
        for model in PER_CITY_MODELS + SHARED_MODELS:
            with self.subTest(model=model.__name__):
                self.assertIsInstance(admin.site.get_model_admin(model), CityScopedAdmin)


class BotCityTests(SimpleTestCase):
    def test_only_spb_goes_to_bot(self):
        self.assertTrue(bot_handles_city(City.SPB))
        self.assertFalse(bot_handles_city(City.KZN))
