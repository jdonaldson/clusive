# Generated by Django 2.2.13 on 2020-11-16 16:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('eventlog', '0017_auto_20201116_1030'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='book_version',
            field=models.BigIntegerField(null=True),
        ),
    ]
