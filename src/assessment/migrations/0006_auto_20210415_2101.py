# Generated by Django 2.2.20 on 2021-04-15 21:01

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('assessment', '0005_auto_20210324_1820'),
    ]

    operations = [
        migrations.AddField(
            model_name='comprehensioncheckresponse',
            name='created',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='comprehensioncheckresponse',
            name='updated',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
