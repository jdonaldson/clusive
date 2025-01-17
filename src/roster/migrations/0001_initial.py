# Generated by Django 2.2.3 on 2019-07-26 20:23

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ClusiveUser',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('subject_id', models.CharField(default=uuid.uuid4, max_length=32, unique=True)),
                ('permission', models.BooleanField(default=False)),
                ('role', models.CharField(choices=[('GU', 'Guest'), ('ST', 'Student'), ('TE', 'Teacher'), ('RE', 'Researcher'), ('AD', 'Admin')], default='GU', max_length=2)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
