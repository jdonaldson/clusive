# Generated by Django 2.2.24 on 2021-10-07 18:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roster', '0043_clusiveuser_student_activity_days'),
    ]

    operations = [
        migrations.AddField(
            model_name='clusiveuser',
            name='student_activity_sort',
            field=models.CharField(choices=[('name', 'name'), ('time', 'time'), ('count', 'count')], default='name', max_length=10),
        ),
    ]