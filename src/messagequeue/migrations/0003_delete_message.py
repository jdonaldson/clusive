# Generated by Django 2.2.13 on 2020-07-28 16:33

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('messagequeue', '0002_auto_20200727_1243'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Message',
        ),
    ]