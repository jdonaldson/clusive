# Generated by Django 2.2.20 on 2021-04-23 17:14

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('roster', '0031_clusiveuser_education_levels'),
        ('library', '0032_auto_20210416_1809'),
        ('assessment', '0006_auto_20210415_2101'),
    ]

    operations = [
        migrations.CreateModel(
            name='AffectiveCheckResponse',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('annoyed_option_response', models.BooleanField(null=True)),
                ('bored_option_response', models.BooleanField(null=True)),
                ('calm_option_response', models.BooleanField(null=True)),
                ('confused_option_response', models.BooleanField(null=True)),
                ('curious_option_response', models.BooleanField(null=True)),
                ('disappointed_option_response', models.BooleanField(null=True)),
                ('frustrated_option_response', models.BooleanField(null=True)),
                ('happy_option_response', models.BooleanField(null=True)),
                ('interested_option_response', models.BooleanField(null=True)),
                ('okay_option_response', models.BooleanField(null=True)),
                ('sad_option_response', models.BooleanField(null=True)),
                ('surprised_option_response', models.BooleanField(null=True)),
                ('book', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='library.Book')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='roster.ClusiveUser')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
