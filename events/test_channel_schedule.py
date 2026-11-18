from unittest.mock import Mock, patch
from django.test import SimpleTestCase
from events import utils


class SharedSchedulerTests(SimpleTestCase):
    def test_refresh_delegates_city_and_reads_assigned_rows(self):
        response = Mock()
        response.json.return_value = {'assignments': [{'id': 7}], 'changes': []}
        with patch.object(utils, 'channel_api_request', return_value=(response, None)) as api, \
             patch.object(utils.Events2Post.objects, 'filter') as rows:
            rows.return_value.order_by.return_value = ['assigned row']
            self.assertEqual(utils.refresh_posting_time(None, None, None, city='kzn'), ['assigned row'])
            api.assert_called_once_with({'api_url': 'api/events/schedule/channel/', 'method': 'POST',
                                         'params': {'city': 'kzn', 'dry_run': 'false', 'reselect': 'false'}})
            rows.assert_called_once_with(id__in=[7], city_id='kzn')

    def test_api_failure_never_falls_back_to_local_dates(self):
        with patch.object(utils, 'channel_api_request', return_value=(None, 'unavailable')), \
             patch.object(utils, 'good_post_time') as local:
            with self.assertRaisesRegex(RuntimeError, 'unavailable'):
                utils.refresh_posting_time(None, None, None)
            local.assert_not_called()

    def test_guarded_plan_is_not_reported_as_success(self):
        response = Mock()
        response.json.return_value = {'assignments': [], 'skipped': 'change_limit'}
        with patch.object(utils, 'channel_api_request', return_value=(response, None)):
            with self.assertRaisesRegex(RuntimeError, 'change_limit'):
                utils.refresh_posting_time(None, None, None)

    def test_manual_date_order_uses_queue_without_reselection(self):
        from datetime import datetime, timezone, timedelta
        from types import SimpleNamespace
        now = datetime.now(timezone.utc)
        rows = [SimpleNamespace(queue=10, post_date=now+timedelta(days=2), score_breakdown={},
                                from_date=now-timedelta(days=5), to_date=now+timedelta(days=30)),
                SimpleNamespace(queue=20, post_date=now+timedelta(days=1), score_breakdown={},
                                from_date=now-timedelta(days=5), to_date=now+timedelta(days=30))]
        with patch('django.db.transaction.atomic'), \
             patch.object(utils.Events2Post.objects, 'filter') as query, \
             patch.object(utils.Events2Post.objects, 'bulk_update') as save, \
             patch.object(utils, 'channel_api_request') as api:
            query.return_value.select_for_update.return_value.order_by.return_value = rows
            utils.post_date_order_by_queue('spb')
            self.assertLess(rows[0].post_date, rows[1].post_date)
            self.assertIn('manual_schedule', rows[0].score_breakdown)
            save.assert_called_once()
            api.assert_not_called()

    def test_change_event_place_swaps_queue_and_date_without_api(self):
        from datetime import datetime, timezone, timedelta
        from django.contrib.admin import site
        from events.admin import Events2PostAdmin
        from events.models import Events2Post
        now = datetime.now(timezone.utc)
        rows = [Events2Post(id=i, queue=q, status='ReadyToPost', city_id='spb', score=70,
                           post_date=now+timedelta(days=d), score_breakdown={},
                           from_date=now-timedelta(days=5), to_date=now+timedelta(days=30))
                for i, q, d in [(18276, 28932, 1), (18619, 28934, 2)]]
        before = [(e.queue, e.post_date) for e in rows]
        queryset = Mock(model=Events2Post)
        queryset.filter.return_value.select_related.return_value.select_for_update.return_value.order_by.return_value = rows
        admin = Events2PostAdmin(Events2Post, site)
        with patch('django.db.transaction.atomic'), \
             patch.object(admin, 'collection_city', return_value='spb'), \
             patch.object(admin, 'message_user'), \
             patch.object(Events2Post.objects, 'bulk_update'), \
             patch.object(utils, 'channel_api_request') as api:
            admin.change_queue(Mock(), queryset)
        self.assertEqual([(e.queue, e.post_date) for e in rows], before[::-1])
        self.assertIn('manual_schedule', rows[0].score_breakdown)
        self.assertEqual([e.score for e in rows], [70, 70])
        api.assert_not_called()
