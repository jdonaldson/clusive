import logging
from datetime import timedelta

from django.db import models
from django.utils import timezone

from roster.models import ClusiveUser, UserStats, Roles

logger = logging.getLogger(__name__)


class TipType(models.Model):
    """
    A tip is a short message that is displayed to introduce or remind users of a feature.
    They are shown with a certain frequency (eg, once a week), no more than one at a time,
    with certain visibility restrictions. Showing of tips can be pre-empted by related user actions:
    we don't need to remind users of features they have recently used.
    """
    name = models.CharField(max_length=20, unique=True)
    priority = models.PositiveSmallIntegerField(unique=True)
    max = models.PositiveSmallIntegerField(verbose_name='Maximum times to show')
    interval = models.DurationField(verbose_name='Interval between shows')

    def can_show(self, page: str, version_count: int):
        """Test whether this tip can be shown on a particular page"""
        if self.name == 'switch':
            return page == 'Reading' and version_count > 1
        if self.name in ['context', 'settings', 'readaloud', 'wordbank']:
            return page == 'Reading'
        return False

    def __str__(self):
        return '<TipType %s>' % self.name


class TipHistory(models.Model):
    type = models.ForeignKey(to=TipType, on_delete=models.CASCADE)
    user = models.ForeignKey(to=ClusiveUser, on_delete=models.CASCADE, db_index=True)
    show_count = models.PositiveSmallIntegerField(default=0)
    last_show = models.DateTimeField(null=True)
    last_action = models.DateTimeField(null=True)

    class Meta:
        unique_together = ('type', 'user')
        verbose_name = 'tip history'
        verbose_name_plural = "tip histories"

    def __str__(self):
        return '<TipHistory %s:%s>' % (self.type.name, self.user.user.username)

    def ready_to_show(self):
        # Already shown the maximum number of times?
        if self.show_count >= self.type.max:
            return False
        now = timezone.now()
        # Shown too recently?
        if self.last_show and (self.last_show + self.type.interval) > now:
            return False
        # Related action too recently?
        if self.last_action and (self.last_action + self.type.interval) > now:
            return False
        return True

    def show(self):
        self.show_count += 1
        self.last_show = timezone.now()
        self.save()

    @classmethod
    def initialize_histories(cls, user: ClusiveUser):
        """Make sure given user has appropriate TipHistory objects"""
        types = TipType.objects.all()
        histories = TipHistory.objects.filter(user=user)
        have_history = [h.type for h in histories]
        for type in types:
            if not type in have_history:
                TipHistory(user=user, type=type).save()

    @classmethod
    def register_action(cls, user: ClusiveUser, action: str, timestamp):
        try:
            type = TipType.objects.get(name=action)
            history = TipHistory.objects.get(user=user, type=type)
            if not history.last_action or timestamp > history.last_action:
                history.last_action = timestamp
                history.save()
        except TipType.DoesNotExist:
            logger.error('Tip-related action received with non-existent TipType: %s', action)
        except TipHistory.DoesNotExist:
            logger.error('Could not find TipHistory object for user %s, type %s', user, action)

    @classmethod
    def available_tips(cls, user: ClusiveUser, page: str, version_count: int):
        """Return all tips that are currently available to show this user."""

        # All tips are currently disallowed on the user's FIRST reading page view
        if page == 'Reading':
            stats: UserStats
            stats = UserStats.for_clusive_user(user)
            if stats.reading_views < 1:
                logger.debug('First reading page view. No tips')
                return []

        # Check tip history to see which are ready to be shown
        histories = TipHistory.objects.filter(user=user).order_by('type__priority')
        return [h for h in histories
                if h.type.can_show(page, version_count)
                and h.ready_to_show()]


class CallToAction(models.Model):
    """
    A Call To Action is a message that is displayed to prompt a certain action.
    Unlike a Tip, a CTA does not have an interval between showings.
    It will continue to be displayed until the action is taken, up to a max number of times, and then never again.
    The "enabled" field can be used to remove old calls to action without deleting their data,
    or put in a placeholder to begin at a later date.
    """
    name = models.CharField(max_length=20, unique=True)
    priority = models.PositiveSmallIntegerField(unique=True)
    enabled = models.BooleanField(default=False)
    max = models.PositiveSmallIntegerField(verbose_name='Maximum times to show', null=True)

    def can_show(self, page: str):
        """
        Test whether this CTA is enabled and can be shown on a particular page.
        Currently, they are all enabled only on the dashboard so this is trivial.
        """
        return self.enabled and page == 'Dashboard'

    def __str__(self):
        return '<CTA %s>' % self.name


class CompletionType:
    """Why this CTA is listed as completed. Was the action taken or not?"""
    TAKEN    = 'T'
    DECLINED = 'D'
    MAX      = 'M'

    CHOICES = (
        (TAKEN, 'Action Taken'),
        (DECLINED, 'Declined'),
        (MAX, 'Max shows'),
    )


class CTAHistory(models.Model):
    type = models.ForeignKey(to=CallToAction, on_delete=models.CASCADE)
    user = models.ForeignKey(to=ClusiveUser, on_delete=models.CASCADE, db_index=True)
    show_count = models.PositiveSmallIntegerField(default=0)
    first_show = models.DateTimeField(null=True, blank=True)
    last_show = models.DateTimeField(null=True, blank=True)
    completed = models.DateTimeField(null=True, blank=True)
    completion_type = models.CharField(max_length=8, null=True, blank=True, choices=CompletionType.CHOICES)

    class Meta:
        unique_together = ('type', 'user')
        verbose_name = 'CTA history'
        verbose_name_plural = "CTA histories"

    def __str__(self):
        return '<CTAHistory %s:%s>' % (self.type.name, self.user.anon_id)

    def ready_to_show(self, user_stats: UserStats):
        if self.completed:
            return False
        # Welcome panel. Generally the first thing shown.
        if self.type.name == 'welcome':
            return True
        # Summer Reading Challenge "congrats" panel: Students only. Requires >100 minutes active reading time.
        if self.type.name == 'summer_reading_st':
            if self.user.role != Roles.STUDENT:
                return False
            return user_stats.active_duration and user_stats.active_duration > timedelta(minutes=100)
            return True
        # Summer reading promo for Guest users - shown to all guests
        if self.type.name == 'summer_reading_gu':
            return self.user.role == Roles.GUEST
        # Demographics, shown right away, for parent & teacher.
        if self.type.name == 'demographics':
            return self.user.role == Roles.PARENT or self.user.role == Roles.TEACHER
        # Star Rating: any registered user, > 60 minutes active or > 3 logins.
        if self.type.name == 'star_rating':
            if self.user.role == Roles.GUEST:
                return False
            if user_stats.logins > 3:
                return True
            return user_stats.active_duration and user_stats.active_duration > timedelta(minutes=60)
        # Unknown type
        logger.warning('Unimplemented CTA type: %s', self)
        return False

    def show(self):
        """Update stats when this CTA is displayed to this user"""
        self.show_count += 1
        now = timezone.now()
        if not self.first_show:
            self.first_show = now
        self.last_show = now
        if self.type.max and self.show_count >= self.type.max:
            self.completed = now
            self.completion_type = CompletionType.MAX
        self.save()

    @classmethod
    def initialize_histories(cls, user: ClusiveUser):
        """Make sure given user has appropriate CTAHistory objects"""
        types = CallToAction.objects.all()
        histories = cls.objects.filter(user=user)
        have_history = [h.type for h in histories]
        for type in types:
            if not type in have_history:
                cls(user=user, type=type).save()

    @classmethod
    def register_action(cls, user: ClusiveUser, cta_name: str, completion_type: CompletionType,
                        timestamp=timezone.now()):
        try:
            type = CallToAction.objects.get(name=cta_name)
            history = cls.objects.get(user=user, type=type)
            if not history.completed:
                history.completed = timestamp
                history.completion_type = completion_type
                history.save()
        except CallToAction.DoesNotExist:
            logger.error('CTA-related action received with non-existent CTA: %s', cta_name)
        except cls.DoesNotExist:
            logger.error('Could not find CTAHistory object for user %s, type %s', user, cta_name)

    @classmethod
    def available_ctas(cls, user: ClusiveUser, page: str):
        """Return all Calls To Action that are currently available to show this user."""

        # Check history to see which are ready to be shown
        histories = cls.objects.filter(user=user).order_by('type__priority')
        user_stats = UserStats.objects.get(user=user)

        return [h for h in histories
                if h.type.can_show(page)
                and h.ready_to_show(user_stats)]
