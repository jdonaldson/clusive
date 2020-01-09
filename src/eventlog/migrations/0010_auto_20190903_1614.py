# Generated by Django 2.2.4 on 2019-09-03 16:14

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('roster', '0016_auto_20190823_2029'),
        ('eventlog', '0009_event_membership'),
    ]

    operations = [
        migrations.RenameModel('Session', 'LoginSession'),
        migrations.AlterField(
            model_name='event',
            name='actor',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='roster.ClusiveUser'),
        ),
        migrations.AlterField(
            model_name='event',
            name='group',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='roster.Period'),
        ),
        migrations.AlterField(
            model_name='event',
            name='session',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='eventlog.LoginSession'),
        ),
    ]