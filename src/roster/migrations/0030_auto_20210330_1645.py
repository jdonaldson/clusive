# Generated by Django 2.2.13 on 2021-03-30 16:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roster', '0029_userstats_active_duration'),
    ]

    operations = [
        migrations.AlterField(
            model_name='clusiveuser',
            name='permission',
            field=models.CharField(choices=[('PE', 'Permissioned'), ('PD', 'Pending'), ('DC', 'Declined'), ('WD', 'Withdrew'), ('SC', 'Self-created account'), ('PC', 'Parent-created account'), ('TC', 'Teacher-created account'), ('TA', 'Test account'), ('GU', 'Guest account')], default='TA', max_length=2),
        ),
    ]
