# Generated by Django 2.2.13 on 2020-09-04 12:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('library', '0019_auto_20200805_2159'),
    ]

    operations = [
        migrations.AlterField(
            model_name='bookassignment',
            name='dateAssigned',
            field=models.DateTimeField(auto_now_add=True),
        ),
    ]