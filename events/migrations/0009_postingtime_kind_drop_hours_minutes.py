import datetime

from django.db import migrations, models


def fill_empty_posting_time(apps, schema_editor):
    """posting_time becomes NOT NULL: fill the gaps from the legacy hours/minutes."""
    PostingTime = apps.get_model("events", "PostingTime")
    for slot in PostingTime.objects.filter(posting_time__isnull=True):
        slot.posting_time = datetime.time(slot.posting_time_hours % 24, slot.posting_time_minutes % 60)
        slot.save(update_fields=["posting_time"])


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0008_alter_events2post_status_and_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="postingtime",
            name="kind",
            field=models.CharField(
                choices=[("event", "Мероприятие"), ("digest", "Дайджест"), ("inactive", "Выключен")],
                default="event",
                max_length=16,
            ),
        ),
        migrations.RunPython(fill_empty_posting_time, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="postingtime",
            name="posting_time",
            field=models.TimeField(),
        ),
        migrations.RemoveField(
            model_name="postingtime",
            name="posting_time_hours",
        ),
        migrations.RemoveField(
            model_name="postingtime",
            name="posting_time_minutes",
        ),
    ]
