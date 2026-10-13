import datetime
from unittest import mock

from django.conf import settings
from django.contrib import admin
from django.core.cache import cache
from django.core.files.storage import storages
from django.db.models.signals import post_save
from django.test import RequestFactory, SimpleTestCase
from django.utils import timezone

from city.models import City
from place.models import PlaceSchedule

from .admin import (
    CATEGORY_SUMMARY_CACHE_KEY,
    CATEGORY_SUMMARY_SCOPES,
    SUMMARY_CACHE_KEY,
    invalidate_events2post_summary,
    open_url,
)
from .helper.colors import css_color
from .helper.post_helper import PostHelper
from .models import Events2Post, EventsNotApprovedNew

MSK_OFFSET = datetime.timedelta(hours=3)


class SettingsTests(SimpleTestCase):
    """Django 5.2: media must still go to S3 via the STORAGES setting."""

    def test_default_storage_is_s3(self):
        self.assertEqual(type(storages["default"]).__module__, "storages.backends.s3")

    def test_timezone(self):
        self.assertEqual(settings.TIME_ZONE, "Europe/Moscow")
        self.assertTrue(settings.USE_TZ)


class AdminHtmlTests(SimpleTestCase):
    """Admin columns built with format_html / mark_safe."""

    def event(self, **kwargs):
        data = dict(
            title="t",
            from_date=timezone.now() + datetime.timedelta(days=5),
            to_date=timezone.now() + datetime.timedelta(days=6),
            status="ReadyToPost",
            image="https://example.com/a.jpg",
            post="Текст",
            url="https://example.com/",
            queue=1,  # default queries the DB
        )
        data.update(kwargs)
        return Events2Post(**data)

    def test_markdown_preview_with_curly_braces(self):
        html = self.event(post="Текст с {фигурными} скобками").markdown_post_view_model()
        self.assertIn("{фигурными}", html)
        self.assertIn("src='https://example.com/a.jpg'", html)

    def test_open_url_is_escaped(self):
        html = open_url(self.event(url="https://example.com/?a=1&b=<x>"))
        self.assertIn("&amp;b=&lt;x&gt;", html)
        self.assertNotIn("<x>", html)

    def test_status_color(self):
        html = self.event(status="Posted").status_color()
        # light mode keeps the original color as var() fallback; dark mode overrides --dsn-c-red
        self.assertEqual(html, '<span style="color: var(--dsn-c-red, red);">Posted</span>')

    def test_from_date_color(self):
        future = self.event().from_date_color()
        self.assertIn("color: var(--dsn-c-green, Green);", future)
        past = self.event(from_date=timezone.now() - datetime.timedelta(days=1)).from_date_color()
        self.assertIn("color: var(--dsn-c-red, Red);", past)
        ready = self.event(is_ready=True).from_date_color()
        self.assertIn("✅", ready)

    def test_css_color_keeps_original_as_fallback(self):
        self.assertEqual(css_color("Green"), "var(--dsn-c-green, Green)")
        self.assertEqual(css_color("#b36b00"), "var(--dsn-c-b36b00, #b36b00)")

    def test_every_css_color_has_dark_value(self):
        from django.template.loader import get_template

        palette = get_template("admin/base_site.html").template.source
        used = {"green", "red", "blue", "purple", "orange", "gray", "black",
                "007bff", "17a2b8", "2f7d32", "b36b00", "ba2121", "555", "2c3e50", "666"}
        for name in used:
            self.assertEqual(palette.count(f"--dsn-c-{name}:"), 3, name)  # light + 2 dark blocks

    def test_not_approved_from_date_color(self):
        event = EventsNotApprovedNew(title="t", from_date=timezone.now(), to_date=timezone.now())
        self.assertIn("color: var(--dsn-c-orange, Orange);", event.from_date_color())


@mock.patch("events.helper.load_parameters.ParametersManager")
class PostHelperTimezoneTests(SimpleTestCase):
    """PostHelper must show event time in its city's time (Moscow for SPb), whatever comes in."""

    def setUp(self):
        cities = {"spb": City(code="spb", timezone="Europe/Moscow"),
                  "ekb": City(code="ekb", timezone="Asia/Yekaterinburg")}
        patcher = mock.patch("city.models.get_cities", return_value=cities)
        patcher.start()
        self.addCleanup(patcher.stop)

    def helper(self, from_date, to_date=None, **extra):
        return PostHelper({"from_date": from_date, "to_date": to_date or from_date, **extra})

    def assert_msk(self, value, hour):
        self.assertEqual(value.utcoffset(), MSK_OFFSET)
        self.assertEqual((value.hour, value.minute), (hour, 0))

    def test_aware_utc_datetime_from_db(self, _):
        dt = datetime.datetime(2026, 10, 14, 16, 0, tzinfo=datetime.timezone.utc)
        self.assert_msk(self.helper(dt).event.from_date, 19)

    def test_iso_string_with_offset_from_api(self, _):
        self.assert_msk(self.helper("2026-10-14T16:00:00+00:00").event.from_date, 19)

    def test_naive_string_from_change_form(self, _):
        # change_form.html sends "date time" without timezone; it means Moscow time
        self.assert_msk(self.helper("2026-10-14 19:00").event.from_date, 19)

    def test_summer_date_has_same_offset(self, _):
        # no DST in Russia: +03:00 all year round
        self.assert_msk(self.helper("2026-07-01T16:00:00+00:00").event.from_date, 19)

    def test_event_city_timezone(self, _):
        value = self.helper("2026-10-14T16:00:00+00:00", city_id="ekb").event.from_date
        self.assertEqual((value.utcoffset(), value.hour), (datetime.timedelta(hours=5), 21))


class PlaceScheduleConstraintTests(SimpleTestCase):
    def test_check_constraint_uses_condition(self):
        constraint = next(
            c for c in PlaceSchedule._meta.constraints if c.name == "valid_schedule_type_constraint"
        )
        self.assertIsNotNone(constraint.condition)



class SummaryCacheTests(SimpleTestCase):
    """Sidebar counters are cached and dropped when an Events2Post changes."""

    CITIES = ("spb", "kzn", "all")

    def setUp(self):
        cache.clear()
        patcher = mock.patch("city.models.get_cities", return_value=dict.fromkeys(self.CITIES))
        patcher.start()
        self.addCleanup(patcher.stop)

    def summary_keys(self):
        return ([SUMMARY_CACHE_KEY.format(city=c) for c in self.CITIES]
                + [CATEGORY_SUMMARY_CACHE_KEY.format(scope=s, city=c)
                   for s in CATEGORY_SUMMARY_SCOPES for c in self.CITIES])

    def test_invalidate_drops_all_summary_keys(self):
        for key in self.summary_keys():
            cache.set(key, "x")
        invalidate_events2post_summary()
        self.assertEqual([k for k in self.summary_keys() if cache.get(k) is not None], [])

    def test_save_signal_invalidates(self):
        key = SUMMARY_CACHE_KEY.format(city="kzn")
        cache.set(key, "x")
        post_save.send(sender=Events2Post, instance=Events2Post(queue=1), created=False)
        self.assertIsNone(cache.get(key))

    def test_unknown_show_value_uses_default_scope(self):
        model_admin = admin.site._registry[Events2Post]
        for query, scope in [({"show": "whatever"}, "default"), ({"show": "upcoming"}, "upcoming")]:
            cache.clear()
            request = RequestFactory().get("/events/events2post/", query)
            with mock.patch.object(model_admin, "_base_queryset_for_date_filter") as qs:
                qs.return_value.filter.return_value.values.return_value.annotate.return_value.order_by.return_value = []
                model_admin._get_category_summary(request)
            self.assertEqual(cache.get(CATEGORY_SUMMARY_CACHE_KEY.format(scope=scope, city="spb")), [])


class ChannelApiRequestMethodTests(SimpleTestCase):
    """Each method reaches the channel API as itself (DELETE used to go as GET)."""

    def send(self, payload, status_code=200):
        from . import utils

        response = mock.Mock(status_code=status_code)
        response.json.return_value = {"status": "revoked"}
        senders = {
            name: mock.patch(f"events.utils.requests.{name}", return_value=response)
            for name in ("get", "post", "put", "patch", "delete")
        }
        mocks = {name: patcher.start() for name, patcher in senders.items()}
        self.addCleanup(mock.patch.stopall)
        result = utils.channel_api_request(payload)
        return result, mocks

    def test_delete_goes_out_as_delete(self):
        (_, error), mocks = self.send({"api_url": "api/tasks/abc", "method": "DELETE"})
        self.assertIsNone(error)
        mocks["delete"].assert_called_once()
        mocks["get"].assert_not_called()
        self.assertNotIn("json", mocks["delete"].call_args.kwargs)

    def test_post_sends_json_body(self):
        (_, error), mocks = self.send(
            {"api_url": "api/x", "method": "post", "data": {"ids": [1]}}
        )
        self.assertIsNone(error)
        self.assertEqual(mocks["post"].call_args.kwargs["json"], {"ids": [1]})

    def test_any_2xx_is_success(self):
        (_, error), _ = self.send({"api_url": "api/x", "method": "POST"}, status_code=202)
        self.assertIsNone(error)

    def test_unknown_method_rejected_without_request(self):
        (response, error), mocks = self.send({"api_url": "api/x", "method": "TRACE"})
        self.assertIsNone(response)
        self.assertIn("TRACE", error)
        self.assertFalse(any(m.called for m in mocks.values()))
