import json
from django.test import SimpleTestCase
from events.models import Events2Post
from events.helper.open_ai_helper import OpenAIHelper, apply_manual_transfer, merge_editorial_result


class EditorialTests(SimpleTestCase):
    def test_local_ai_returns_complete_json_without_replacing_manual_choice(self):
        helper = OpenAIHelper.__new__(OpenAIHelper)
        helper.answer = json.dumps({'title': 'Title', 'text': 'Description', 'editorial': {'score': 95, 'reason': 'Facts'}})
        event = {'score_breakdown': json.dumps({'total': 70, 'manual_transfer': {'target': 'OnlyApi'}, 'manual': {'score': 100}})}
        result = helper.new_event_data(event)
        self.assertEqual(result['score_breakdown']['manual_transfer']['target'], 'OnlyApi')
        self.assertEqual(result['score_breakdown']['editorial']['score'], 95)
        self.assertIsInstance(result['score_breakdown'], dict)
        self.assertEqual(result['score'], 75)

    def test_repeated_transfer_does_not_accumulate_bonus(self):
        event = Events2Post(queue=1, score=80, score_breakdown={'total': 80})
        apply_manual_transfer(event, 'ReadyToPost')
        apply_manual_transfer(event, 'ReadyToPost')
        self.assertEqual(event.score, 85)
        apply_manual_transfer(event, 'OnlyApi')
        self.assertEqual(event.score, 75)
        self.assertEqual(event.score_breakdown['manual_transfer']['target'], 'OnlyApi')

    def test_optional_user_rating_and_saturation(self):
        event = Events2Post(queue=1, score=98, score_breakdown={'total': 98, 'manual': {'score': 100}})
        apply_manual_transfer(event, 'ReadyToPost')
        self.assertEqual(event.score, 100)
        event.score_breakdown['manual']['score'] = 0
        apply_manual_transfer(event, 'OnlyApi')
        self.assertEqual(event.score, 93)

    def test_null_or_invalid_ai_rating_keeps_previous_rating(self):
        event = {'score_breakdown': {'total': 75, 'editorial': {'score': 80}, 'rating_adjustment': 3}}
        result = merge_editorial_result(event, {}, {'score': True})
        self.assertEqual(result['score_breakdown']['editorial']['score'], 80)
        self.assertEqual(result['score'], 75)

    def test_admin_form_status_change_sets_transfer_marker(self):
        from unittest.mock import Mock, patch
        from django.contrib.admin import site, ModelAdmin
        from events.admin import Events2PostAdmin
        event = Events2Post(queue=1, score=80, status='OnlyApi', score_breakdown={'total': 80})
        admin = Events2PostAdmin(Events2Post, site)
        with patch.object(ModelAdmin, 'save_model'):
            admin.save_model(Mock(), event, Mock(changed_data=['status']), True)
        self.assertEqual(event.score, 75)
        self.assertEqual(event.score_breakdown['manual_transfer']['target'], 'OnlyApi')

    def test_admin_bulk_transfer_sets_marker_without_model_save(self):
        from unittest.mock import Mock, patch
        from django.contrib.admin import site
        from events.admin import Events2PostAdmin
        event = Events2Post(queue=1, score=80, score_breakdown={'total': 80})
        queryset = Mock(model=Events2Post)
        queryset.select_related.return_value.select_for_update.return_value.only.return_value = [event]
        admin = Events2PostAdmin(Events2Post, site)
        with patch('django.db.transaction.atomic'), patch.object(Events2Post.objects, 'bulk_update') as save:
            self.assertEqual(admin._manual_transfer(queryset, 'ReadyToPost'), 1)
            save.assert_called_once()
        self.assertEqual(event.score, 85)
        self.assertIn('manual_transfer', event.score_breakdown)
