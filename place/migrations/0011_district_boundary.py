from django.contrib.gis.db import models
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("place", "0010_place_geocoding")]

    operations = [
        migrations.RunSQL("CREATE EXTENSION IF NOT EXISTS postgis", migrations.RunSQL.noop),
        migrations.AddField(
            model_name="district",
            name="boundary",
            field=models.MultiPolygonField(
                blank=True, null=True, srid=4326, verbose_name="Граница района",
            ),
        ),
    ]
