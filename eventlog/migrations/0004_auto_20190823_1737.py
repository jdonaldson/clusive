# Generated by Django 2.2.4 on 2019-08-23 17:37

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('eventlog', '0003_auto_20190823_1532'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='session',
            field=models.ForeignKey(default=False, on_delete=django.db.models.deletion.CASCADE, to='eventlog.Session'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='event',
            name='eventTime',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name='event',
            name='id',
            field=models.CharField(default=uuid.uuid4, max_length=36, primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name='session',
            name='id',
            field=models.CharField(default=uuid.uuid4, max_length=36, primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name='session',
            name='startedAtTime',
            field=models.DateTimeField(auto_now_add=True),
        ),
    ]