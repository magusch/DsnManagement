from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("place", "0009_city_check_db_only"),
    ]

    operations = [
        migrations.AddField(
            model_name="place",
            name="latitude",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="place",
            name="longitude",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="place",
            name="geocoding_status",
            field=models.CharField(blank=True, max_length=30, null=True),
        ),
        migrations.AddField(
            model_name="place",
            name="geocoded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="place",
            name="geocoding_metadata",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
