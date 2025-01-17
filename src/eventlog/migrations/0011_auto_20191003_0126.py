# Generated by Django 2.2.4 on 2019-10-03 01:26

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('eventlog', '0010_auto_20190903_1614'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='type',
            field=models.CharField(choices=[('ANNOTATION_EVENT', 'AnnotationEvent'), ('ASSESSMENT_EVENT', 'AssessmentEvent'), ('ASSESSMENT_ITEM_EVENT', 'AssessmentItemEvent'), ('ASSIGNABLE_EVENT', 'AssignableEvent'), ('EVENT', 'Event'), ('FORUM_EVENT', 'ForumEvent'), ('MEDIA_EVENT', 'MediaEvent'), ('MESSAGE_EVENT', 'MessageEvent'), ('NAVIGATION_EVENT', 'NavigationEvent'), ('GRADE_EVENT', 'GradeEvent'), ('SESSION_EVENT', 'SessionEvent'), ('THREAD_EVENT', 'ThreadEvent'), ('TOOL_USE_EVENT', 'ToolUseEvent'), ('VIEW_EVENT', 'ViewEvent')], max_length=32),
        ),
        migrations.AlterField(
            model_name='loginsession',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='roster.ClusiveUser'),
        ),
    ]
