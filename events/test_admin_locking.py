import io
import logging
from unittest.mock import patch

from django.db import connection
from django.test import SimpleTestCase
from events.admin import _locked_event_rows
from events.models import Events2Post


class AdminActionLockingTests(SimpleTestCase):
    def test_inherited_nullable_joins_are_removed_before_locking(self):
        queryset = Events2Post.objects.select_related('place', 'main_category')
        locked = _locked_event_rows(queryset)
        self.assertFalse(locked.query.select_related)
        self.assertEqual(locked.query.select_for_update_of, ('self',))
        with patch.object(connection, 'get_autocommit', return_value=False):
            sql, _ = locked.query.sql_with_params()
        self.assertNotIn('LEFT OUTER JOIN', sql)
        self.assertIn('FOR UPDATE OF', sql)

    def test_status_action_can_defer_unrelated_fields_without_field_error(self):
        queryset = Events2Post.objects.select_related('place', 'main_category')
        locked = _locked_event_rows(queryset).only('id', 'score', 'score_breakdown')
        with patch.object(connection, 'get_autocommit', return_value=False):
            sql, _ = locked.query.sql_with_params()
        self.assertIn('FOR UPDATE OF', sql)
        self.assertNotIn('JOIN', sql)

    def test_request_traceback_is_visible_with_debug_disabled(self):
        logger = logging.getLogger('django.request')
        handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
        self.assertTrue(handlers)
        buffer = io.StringIO()
        streams = [h.stream for h in handlers]
        try:
            for handler in handlers:
                handler.setStream(buffer)
            try:
                raise ValueError('test action exception')
            except ValueError:
                logger.error('Test request failure', exc_info=True)
            self.assertIn('ValueError: test action exception', buffer.getvalue())
            self.assertIn('Traceback', buffer.getvalue())
        finally:
            for handler, stream in zip(handlers, streams):
                handler.setStream(stream)
