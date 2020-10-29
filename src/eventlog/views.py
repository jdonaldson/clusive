import csv
import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.http import StreamingHttpResponse
from django.views.generic.base import ContextMixin

from eventlog.models import Event
from roster.models import ResearchPermissions

logger = logging.getLogger(__name__)

class EventMixin(ContextMixin):
    """
    Creates a VIEW_EVENT for this view, and includes the event ID in the context for client-side use.
    Views that use this mixin must define a configure_event method to add appropriate data fields to the event.
    """
    
    def get(self, request, *args, **kwargs):
        event = Event.build(type='VIEW_EVENT',
                            action='VIEWED',
                            session=request.session)
        self.configure_event(event)
        if event:
            logger.info('event logged: %s', event)
            event.save()
            self.event_id = event.id
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['event_id'] = self.event_id
        return context

    def configure_event(self, event: Event):
        raise NotImplementedError('View must define the contribute_event_data method')


@staff_member_required
def event_log_report(request):
    # TODO: get actor in same query
    events = Event.objects \
        .filter(actor__permission=ResearchPermissions.PERMISSIONED) \
        .select_related('actor', 'session', 'group')

    response = StreamingHttpResponse(row_generator(events), content_type="text/csv")
    response['Content-Disposition'] = 'attachment; filename="event-log.csv"'
    return response


def row_generator(events):
    pseudo_buffer = Echo()
    writer = csv.writer(pseudo_buffer)
    yield writer.writerow(['Timestamp', 'User', 'Role', 'Period', 'Site',
                           'Type', 'Action', 'Document', 'Page', 'Control', 'Value',
                           'Event ID', 'Session Id'])
    period_site = {}
    for e in events:
        yield writer.writerow(row_for_event(e, period_site))


def row_for_event(e, period_site):
    period = e.group.anon_id if e.group else None
    # period_site map caches lookups of the site anon_id for each period.
    if period:
        site = period_site.get(period)
        if not site:
            site = e.group.site.anon_id
            period_site[period] = site
    else:
        site = None
    return [e.eventTime, e.actor.anon_id, e.membership, period, site,
            e.type, e.action, e.document, e.page, e.control, e.value,
            e.id, e.session.id]


class Echo:
    """An object that implements just the write method of the file-like
    interface.
    """

    def write(self, value):
        """Write the value by returning it, instead of storing in a buffer."""
        return value
