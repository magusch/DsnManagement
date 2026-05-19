from django.db import migrations, models
from django.db.models import Q

import pgvector.django


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0006_enable_pgvector"),
    ]

    operations = [
        migrations.AddField(
            model_name="events2post",
            name="embedding",
            field=pgvector.django.VectorField(blank=True, dimensions=1536, null=True),
        ),
        migrations.AddField(
            model_name="events2post",
            name="embedding_model",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="events2post",
            name="embedding_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="eventsnotapprovednew",
            name="embedding",
            field=pgvector.django.VectorField(blank=True, dimensions=1536, null=True),
        ),
        migrations.AddField(
            model_name="eventsnotapprovednew",
            name="embedding_model",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="eventsnotapprovednew",
            name="embedding_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="eventsnotapprovedproposed",
            name="embedding",
            field=pgvector.django.VectorField(blank=True, dimensions=1536, null=True),
        ),
        migrations.AddField(
            model_name="eventsnotapprovedproposed",
            name="embedding_model",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="eventsnotapprovedproposed",
            name="embedding_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="events2post",
            index=pgvector.django.HnswIndex(
                condition=Q(embedding__isnull=False),
                ef_construction=64,
                fields=["embedding"],
                m=16,
                name="events2post_emb_hnsw",
                opclasses=["vector_cosine_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="eventsnotapprovednew",
            index=pgvector.django.HnswIndex(
                condition=Q(embedding__isnull=False),
                ef_construction=64,
                fields=["embedding"],
                m=16,
                name="enapproved_new_emb_hnsw",
                opclasses=["vector_cosine_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="eventsnotapprovedproposed",
            index=pgvector.django.HnswIndex(
                condition=Q(embedding__isnull=False),
                ef_construction=64,
                fields=["embedding"],
                m=16,
                name="enapproved_prop_emb_hnsw",
                opclasses=["vector_cosine_ops"],
            ),
        ),
    ]
