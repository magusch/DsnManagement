from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0005_events2post_score_events2post_score_breakdown_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS vector",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
