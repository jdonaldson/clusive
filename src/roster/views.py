import csv
import json
import logging
from datetime import timedelta
from urllib.parse import urlencode

import requests
from allauth.socialaccount.models import SocialToken, SocialApp, SocialAccount
from allauth.socialaccount.providers.oauth2.client import OAuth2Error
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login, get_user_model, logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import PermissionDenied
from django.core.mail import EmailMultiAlternatives
from django.dispatch import receiver
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404
from django.template import loader
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.views import View
from django.views.generic import TemplateView, UpdateView, CreateView, FormView, RedirectView
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from eventlog.models import Event
from eventlog.signals import preference_changed
from eventlog.views import EventMixin
from messagequeue.models import Message, client_side_prefs_change
from pages.views import ThemedPageMixin, SettingsPageMixin
from roster import csvparser
from roster.csvparser import parse_file
from roster.forms import SimpleUserCreateForm, UserEditForm, UserRegistrationForm, \
    AccountRoleForm, AgeCheckForm, ClusiveLoginForm, GoogleCoursesForm, PeriodCreateForm, PeriodNameForm
from roster.models import ClusiveUser, Period, PreferenceSet, Roles, ResearchPermissions, MailingListMember, \
    RosterDataSource
from roster.signals import user_registered

logger = logging.getLogger(__name__)

def guest_login(request):
    clusive_user = ClusiveUser.make_guest()
    login(request, clusive_user.user, 'django.contrib.auth.backends.ModelBackend')
    return redirect('dashboard')


class LoginView(auth_views.LoginView):
    template_name='roster/login.html'
    form_class = ClusiveLoginForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context.get('form')
        if form.errors:
            for err in form.errors.as_data().get('__all__'):
                if err.code == 'email_validate':
                    context['email_validate'] = True
                    username = form.cleaned_data['username']
                    try:
                        user = User.objects.get_by_natural_key(username=username)
                        context['user_id'] = user.id
                    except User.DoesNotExist:
                        logger.error('Email not validated error signalled when account does not exist')
        return context


class SignUpView(EventMixin, ThemedPageMixin, CreateView):
    template_name='roster/sign_up.html'
    model = User
    form_class = UserRegistrationForm

    def get_initial(self, *args, **kwargs):
        initial = super(SignUpView, self).get_initial(**kwargs)
        # If registration during SSO, use info from the SSO user
        if self.request.session.get('sso', False):
            initial['user'] = self.request.user
        return initial

    def dispatch(self, request, *args, **kwargs):
        self.role = kwargs['role']
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.current_clusive_user = request.clusive_user
        self.current_site = get_current_site(request)
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['role'] = self.role
        context['isSSO'] = self.request.session.get('sso', False)
        return context

    def form_valid(self, form):
        # Don't call super since that would save the target model, which we might not want.
        target : User
        target = form.instance
        if not self.role in ['TE', 'PA', 'ST']:
            raise PermissionError('Invalid role')
        user: User
        if self.current_clusive_user:
            # There is a logged-in user, either a Guest or an SSO user.
            # Update the ClusiveUser and User objects based on the form target.
            clusive_user: ClusiveUser
            clusive_user = self.current_clusive_user
            isSSO = self.request.session.get('sso', False)
            update_clusive_user(clusive_user,
                                self.role,
                                ResearchPermissions.SELF_CREATED,
                                isSSO,
                                form.cleaned_data['education_levels'])
            user = clusive_user.user
            user.first_name = target.first_name
            # If the user is already logged in via SSO, these fields are already
            # set by the SSO process.  If not an SSO user, get the values from
            # the form.
            if not isSSO:
                user.username = target.username
                user.set_password(form.cleaned_data["password1"])
                user.email = target.email
            user.save()

            # Either log in the SSO user and redirect to the dashboard, or, for
            # Guests signing up, send the confirmation email to the new user and
            # log them in.
            if isSSO:
                login(self.request, user, 'allauth.account.auth_backends.AuthenticationBackend')
                logger.debug('sending signal for new google user who has completed registration')
                user_registered.send(self.__class__, clusive_user=clusive_user)
                return HttpResponseRedirect(reverse('dashboard'))
            else:
                send_validation_email(self.current_site, clusive_user)
                login(self.request, user, 'django.contrib.auth.backends.ModelBackend')
        else:
            # This is a new user.  Save the form target User object, and create a ClusiveUser.
            user = target
            user.set_password(form.cleaned_data["password1"])
            user.save()
            clusive_user = ClusiveUser.objects.create(user=user,
                                                      role=self.role,
                                                      permission=ResearchPermissions.SELF_CREATED,
                                                      anon_id=ClusiveUser.next_anon_id(),
                                                      education_levels = form.cleaned_data['education_levels'],
                                                      )
            send_validation_email(self.current_site, clusive_user)
        return HttpResponseRedirect(reverse('validate_sent', kwargs={'user_id' : user.id}))

    def configure_event(self, event: Event):
        event.page = 'Register'


class ValidateSentView(ThemedPageMixin, TemplateView):
    template_name = 'roster/validate_sent.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = User.objects.get(pk=kwargs.get('user_id'))
        context['user_id'] = user.id
        context['email'] = user.email
        context['status'] = 'sent'
        return context


class ValidateResendView(ThemedPageMixin, TemplateView):
    template_name = 'roster/validate_sent.html'

    def get(self, request, *args, **kwargs):
        self.user = User.objects.get(pk=kwargs.get('user_id'))
        clusive_user = ClusiveUser.objects.get(user=self.user)
        if clusive_user.unconfirmed_email:
            send_validation_email(get_current_site(request), clusive_user)
            self.status = 'resent'
        else:
            logger.warning('Skipping email sending; already activated user %s', clusive_user)
            self.status = 'unneeded'
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user_id'] = self.user.id
        context['email'] = self.user.email
        context['status'] = self.status
        return context


class ValidateEmailView(View):
    template = 'roster/validate.html'

    def get(self, request, *args, **kwargs):
        uid = kwargs.get('user_id')
        token = kwargs.get('token')
        user_model = get_user_model()
        try:
            user = user_model.objects.get(pk=uid)
            clusive_user = ClusiveUser.objects.get(user=user)
            if clusive_user.unconfirmed_email:
                check_token = default_token_generator.check_token(user, token)
                if check_token:
                    logger.info('Activating user %s', user)
                    clusive_user.unconfirmed_email = False
                    clusive_user.save()
                    result = 'activated'
                    logger.debug('sending signal for new user who has completed email validation')
                    user_registered.send(self.__class__, clusive_user=clusive_user)
                else:
                    logger.warning('Email validation check failed. User=%s; token=%s; result=%s',
                                user, token, check_token)
                    result = 'error'
            else:
                logger.warning('Skipping activation of already activated user %s', user)
                result = 'unneeded'
        except:
            result = 'error'
        context = {
            'status': result,
            'user_id': uid
        }
        return render(request, self.template, context)


class SignUpRoleView(EventMixin, ThemedPageMixin, FormView):
    form_class = AccountRoleForm
    template_name = 'roster/sign_up_role.html'

    def form_valid(self, form):
        clusive_user = self.request.clusive_user
        role = form.cleaned_data['role']
        if role == Roles.STUDENT:
            self.success_url = reverse('sign_up_age_check')
        else:
            # Logging in via SSO for the first time entails that there is a
            # clusive_user and its role is UNKNOWN
            isSSO = True if (clusive_user and clusive_user.role == Roles.UNKNOWN) else False
            if isSSO:
                update_clusive_user(clusive_user,
                                    role,
                                    ResearchPermissions.SELF_CREATED,
                                    isSSO)
            self.success_url = reverse('sign_up', kwargs={'role': role, 'isSSO': isSSO})
        return super().form_valid(form)

    def configure_event(self, event: Event):
        event.page = 'RegisterRole'


class SignUpAgeCheckView(EventMixin, ThemedPageMixin, FormView):
    form_class = AgeCheckForm
    template_name = 'roster/sign_up_age_check.html'

    def form_valid(self, form):
        clusive_user = self.request.clusive_user
        logger.debug("of age: %s", repr(form.cleaned_data['of_age']))
        if form.cleaned_data['of_age'] == 'True':
            # Logging in via SSO for the first time entails that there is a
            # clusive_user and its role is UNKNOWN
            isSSO = True if (clusive_user and clusive_user.role == Roles.UNKNOWN) else False
            if clusive_user and clusive_user.role == Roles.UNKNOWN:
                update_clusive_user(self.request.clusive_user,
                                    Roles.STUDENT,
                                    ResearchPermissions.SELF_CREATED,
                                    isSSO)
            self.success_url = reverse('sign_up', kwargs={'role': Roles.STUDENT, 'isSSO': isSSO})
        else:
            self.success_url = reverse('sign_up_ask_parent')
        return super().form_valid(form)

    def configure_event(self, event: Event):
        event.page = 'RegisterAge'


class SignUpAskParentView(EventMixin, ThemedPageMixin, TemplateView):
    template_name = 'roster/sign_up_ask_parent.html'

    def get(self, request, *args, **kwargs):
        # Create and log the event as usual, but then delete any SSO underage
        # student records.
        result = super().get(request, *args, **kwargs)
        logout_sso(request, 'student')
        return result

    def configure_event(self, event: Event):
        event.page = 'RegisterAskParent'

class PreferenceView(View):

    def get(self, request):
        user = ClusiveUser.from_request(request)
        return JsonResponse(user.get_preferences_dict())

    def post(self, request):
        try:
            request_prefs = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': 0, 'message': 'Invalid JSON in request'})

        user = ClusiveUser.from_request(request)
        set_user_preferences(user, request_prefs, None, None, request)

        return JsonResponse({'success': 1})


# TODO: should we specially log an event that adopts a full new preference set?
class PreferenceSetView(View):

    def post(self, request):
        user = ClusiveUser.from_request(request)
        try:
            request_json = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': 0, 'message': 'Invalid JSON in request'})

        desired_prefs_name = request_json["adopt"]
        event_id = request_json["eventId"]
        timestamp = timezone.now()

        try:
            desired_prefs = PreferenceSet.get_json(desired_prefs_name)
        except PreferenceSet.DoesNotExist:
            return JsonResponse(status=404, data={'message': 'Preference set named %s does not exist' % desired_prefs_name})

        set_user_preferences(user, desired_prefs, event_id, timestamp, request)

        # Return the preferences set
        return JsonResponse(desired_prefs)


# Set user preferences from a dictionary
def set_user_preferences(user, new_prefs, event_id, timestamp, request, reader_info=None):
    """Sets User's preferences to match the given dictionary of preference values."""
    old_prefs = user.get_preferences_dict()
    prefs_to_use = new_prefs
    for pref_key in prefs_to_use:
        old_val = old_prefs.get(pref_key)
        if old_val != prefs_to_use[pref_key]:
            # Preference changes associated with a page event (user action)
            if(event_id):
                set_user_preference_and_log_event(user, pref_key, prefs_to_use[pref_key], event_id, timestamp, request, reader_info=reader_info)
            # Preference changes not associated with a page event - not logged
            else:
                user.set_preference(pref_key, prefs_to_use[pref_key])

            # logger.debug("Pref %s changed %s (%s) -> %s (%s)", pref_key,
            #              old_val, type(old_val),
            #              pref.typed_value, type(pref.typed_value))

def set_user_preference_and_log_event(user, pref_key, pref_value, event_id, timestamp, request, reader_info=None):
    pref = user.set_preference(pref_key, pref_value)
    preference_changed.send(sender=ClusiveUser.__class__, request=request, event_id=event_id, preference=pref, timestamp=timestamp, reader_info=reader_info)

@receiver(client_side_prefs_change, sender=Message)
def set_preferences_from_message(sender, content, timestamp, request, **kwargs):
    logger.debug("client_side_prefs_change message received")
    reader_info = content.get("readerInfo")
    user = request.clusive_user
    set_user_preferences(user, content["preferences"], content["eventId"], timestamp, request, reader_info=reader_info)


@staff_member_required
def upload_csv(request):
    template = 'roster/upload_csv.html'
    context = {'fields': csvparser.FIELDS, 'title': 'Bulk add users'}

    if request.method == "GET":
        # First render; just show the form.
        return render(request, template, context)

    # POST means a file was uploaded.
    dry_run = request.POST.get('test')
    if dry_run:
        messages.warning(request, 'Testing CSV file only - database will not be changed')

    if not request.FILES:
        messages.error(request, 'No file uploaded')
    else:
        csv_file = request.FILES['file']
        try:
            csvreader = csv.DictReader(chunk.decode() for chunk in csv_file)
            result = parse_file(csvreader)
            context = result
            context['dry_run'] = dry_run

            if not context['errors'] and not dry_run:
                try:
                    for u in result['users']:
                        ClusiveUser.create_from_properties(u)
                    messages.info(request, 'Users created')
                except Exception as e:
                    context['errors'].append('Database error: %s' % e)
                    messages.error(request, 'Error during creation of users - some may have been created')

        except csv.Error as e:
            context['errors'] = ["CSV formatting error: %s" % e]
            context['sites'] = {}
            context['users'] = {}

        if context['errors']:
            messages.error(request, 'Problems found')
        else:
            messages.info(request, 'File looks good')

    return render(request, template, context)


class ManageView(LoginRequiredMixin, EventMixin, ThemedPageMixin, SettingsPageMixin, TemplateView):
    template_name = 'roster/manage.html'
    periods = None
    current_period = None

    def get(self, request, *args, **kwargs):
        user = request.clusive_user
        if not user.can_manage_periods:
            self.handle_no_permission()
        if self.periods is None:
            self.periods = user.periods.all()
        if kwargs.get('period_id'):
            self.current_period = get_object_or_404(Period, pk=kwargs.get('period_id'))
            # Make sure you can only edit a Period you are in.
            if self.current_period not in self.periods:
                self.handle_no_permission()
        if self.current_period is None:
            if user.current_period:
                self.current_period = user.current_period
            elif self.periods:
                self.current_period = self.periods[0]
            # else:
            #     # No periods.  If this case actually happens, should have a better error message.
            #     self.handle_no_permission()
        if self.current_period != user.current_period and self.current_period is not None:
            user.current_period = self.current_period
            user.save()
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['periods'] = self.periods
        context['current_period'] = self.current_period
        if self.current_period is not None:
            context['students'] = self.make_student_info_list()
            context['period_name_form'] = PeriodNameForm(instance=self.current_period)
            context['allow_add_student'] = (self.current_period.data_source == RosterDataSource.CLUSIVE)
        return context

    def make_student_info_list(self):
        students = self.current_period.users.filter(role=Roles.STUDENT).order_by('user__first_name')
        return [{
            'info': s.user,
        } for s in students]

    def configure_event(self, event: Event):
        event.page = 'Manage'


class ManageCreateUserView(LoginRequiredMixin, EventMixin, ThemedPageMixin, SettingsPageMixin, CreateView):
    model = User
    form_class = SimpleUserCreateForm
    template_name = 'roster/manage_create_user.html'
    period = None

    def dispatch(self, request, *args, **kwargs):
        self.period = get_object_or_404(Period, id=kwargs['period_id'])
        # Sanity check requested period
        cu = request.clusive_user
        if not cu.can_manage_periods or not self.period.users.filter(id=cu.id).exists():
            self.handle_no_permission()
        self.creating_user_role = cu.role
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse('manage', kwargs={'period_id': self.period.id})

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data['period_id'] = self.period.id
        return data

    def form_valid(self, form):
        # Create User
        form.save()
        target : User
        target = form.instance
        # Set password
        new_pw = form.cleaned_data['password']
        if new_pw:
            target.set_password(new_pw)
            target.save()
        # Create ClusiveUser
        if self.creating_user_role == Roles.TEACHER:
            perm = ResearchPermissions.TEACHER_CREATED
        elif self.creating_user_role == Roles.PARENT:
            perm = ResearchPermissions.PARENT_CREATED
        else:
            self.handle_no_permission()
        cu = ClusiveUser.objects.create(user=target,
                                        role=Roles.STUDENT,
                                        anon_id=ClusiveUser.next_anon_id(),
                                        permission=perm)

        # Add user to the Period
        self.period.users.add(cu)
        return super().form_valid(form)

    def configure_event(self, event: Event):
        event.page = 'ManageCreateStudent'

class ManageEditUserView(LoginRequiredMixin, EventMixin, ThemedPageMixin, SettingsPageMixin, UpdateView):
    model = User
    form_class = UserEditForm
    template_name = 'roster/manage_edit_user.html'
    period = None

    def dispatch(self, request, *args, **kwargs):
        self.period = get_object_or_404(Period, id=kwargs['period_id'])
        # Sanity check requested period
        cu = request.clusive_user
        if not cu.can_manage_periods or not self.period.users.filter(id=cu.id).exists():
            self.handle_no_permission()
        # Sanity check requested User. Associated ClusiveUser should be a member of that Period.
        target = get_object_or_404(User, id=kwargs['pk'])
        if not self.period.users.filter(user__id=target.id).exists():
            self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse('manage', kwargs={'period_id': self.period.id})

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data['period_id'] = self.period.id
        return data

    def form_valid(self, form):
        form.save()
        target : User
        target = form.instance
        new_pw = form.cleaned_data['password']
        if new_pw:
            target.set_password(new_pw)
            target.save()
        return super().form_valid(form)

    def configure_event(self, event: Event):
        event.page = 'ManageEditStudent'


class ManageEditPeriodView(LoginRequiredMixin, EventMixin, ThemedPageMixin, SettingsPageMixin, UpdateView):
    model = Period
    form_class = PeriodNameForm
    template_name = 'roster/manage_edit_period.html'

    def dispatch(self, request, *args, **kwargs):
        cu = request.clusive_user
        if not cu.can_manage_periods or not self.get_object().users.filter(id=cu.id).exists():
            self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse('manage', kwargs={'period_id': self.object.id})

    def configure_event(self, event: Event):
        event.page = 'ManageEditPeriod'


class ManageCreatePeriodView(LoginRequiredMixin, EventMixin, ThemedPageMixin, SettingsPageMixin, CreateView):
    """
    Displays a choice for the user between the various supported methods for creating a new Period.
    Options are manual (always available) and importing from Google Classroom (if user has a connected Google acct).
    Redirects to manage page for manual creation, or to GetGoogleCourses.
    """
    model = Period
    form_class = PeriodCreateForm
    template_name = 'roster/manage_create_period.html'

    def get_form(self, form_class=None):
        instance=Period(site=self.clusive_user.get_site())
        kwargs = self.get_form_kwargs()
        kwargs['instance'] = instance
        kwargs['allow_google'] = (self.clusive_user.data_source == RosterDataSource.GOOGLE)
        logger.debug('kwargs %s', kwargs)
        return PeriodCreateForm(**kwargs)

    def dispatch(self, request, *args, **kwargs):
        cu = request.clusive_user
        if not cu.can_manage_periods:
            self.handle_no_permission()
        self.clusive_user = cu
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse('manage', kwargs={'period_id': self.object.id})

    def form_valid(self, form):
        if form.cleaned_data.get('create_or_import') == 'google':
            # Do not save the period, just redirect.
            return HttpResponseRedirect(reverse('get_google_courses'))
        else:
            # Save Period and add current user
            result = super().form_valid(form)
            self.object.users.add(self.clusive_user)
            return result

    def configure_event(self, event: Event):
        event.page = 'ManageCreatePeriod'


def finish_login(request):
    """
    Called as the redirect after Google Oauth SSO login.
    Checks if we need to ask user for their role and privacy policy agreement, or if that's already done.
    """
    if request.user.is_staff:
        return HttpResponseRedirect('/admin')
    clusive_user = ClusiveUser.from_request(request)
    # If you're logging in via Google, then you are marked as a Google user from now on.
    if clusive_user.data_source != RosterDataSource.GOOGLE:
        clusive_user.data_source = RosterDataSource.GOOGLE
        clusive_user.save()
    # If you haven't logged in before, your role will be UNKNOWN and we need to ask you for it.
    if clusive_user.role == Roles.UNKNOWN:
        request.session['sso'] = True
        return HttpResponseRedirect(reverse('sign_up_role'))
    else:
        return HttpResponseRedirect(reverse('dashboard'))


def update_clusive_user(current_clusive_user, role, permissions, isSSO, edu_levels=None):
    clusive_user: ClusiveUser
    clusive_user = current_clusive_user
    logger.debug('Updating %s from %s to %s', clusive_user, clusive_user.role, role)
    clusive_user.role = role
    clusive_user.permission = permissions
    if isSSO:
        clusive_user.unconfirmed_email = False
    if edu_levels:
        clusive_user.education_levels = edu_levels
    clusive_user.save()


def send_validation_email(site, clusive_user : ClusiveUser):
    clusive_user.unconfirmed_email = True
    clusive_user.save()
    user = clusive_user.user
    token = default_token_generator.make_token(user)
    logger.info('Generated validation token for user: %s %s', user, token)
    context = {
        'site_name': site.name,
        'domain': site.domain,
        'protocol': 'https', # Note, this will send incorrect URLs in local development without https.
        'email': user.email,
        'uid': user.pk,
        'user': user,
        'token': token,
    }
    subject = loader.render_to_string('roster/validate_subject.txt', context)
    # Email subject *must not* contain newlines
    subject = ''.join(subject.splitlines())
    body = loader.render_to_string('roster/validate_email.txt', context)
    from_email = None  # Uses default specified in settings
    email_message = EmailMultiAlternatives(subject, body, from_email, [user.email])
    # TODO add if we create HTML email
    # if html_email_template_name is not None:
    #     html_email = loader.render_to_string(html_email_template_name, context)
    #     email_message.attach_alternative(html_email, 'text/html')
    email_message.send()

def cancel_registration(request):
    logger.debug("Cancelling registration")
    logout_sso(request)
    return HttpResponseRedirect('/')

def logout_sso(request, student=''):
    """This is used in the cases where (1) an SSO user has cancelled the
    registration process or (2) a student signed up using SSO, but is not of
    age.  Remove associated User, ClusiveUser, SocialAccount, and AccessToken
    records, effectively logging out.  If not an SSO situation, this does
    nothing."""
    clusive_user = request.clusive_user
    if (clusive_user and clusive_user.role == Roles.UNKNOWN) or request.session.get('sso', False):
        logger.debug("SSO logout, and removing records for %s %s", student, clusive_user)
        django_user = request.user
        logout(request)
        django_user.delete()
    else:
        logger.debug("Unregistered user, nothing to delete")


class SyncMailingListView(View):
    """
    Called by script to periodically send new member info to the mailing list software.
    """

    def get(self, request):
        logger.debug('Sync mailing list request received')
        MailingListMember.synchronize_user_emails()
        return JsonResponse({'success': 1})


class GoogleCoursesView(LoginRequiredMixin, EventMixin, ThemedPageMixin, TemplateView, FormView):
    """
    Displays the list of Google Classroom courses and allows user to choose one to import.
    Expects to receive a 'google_courses' parameter in the session, which is a list of dicts
    each of which has at least 'name', 'id', and 'imported' (aka already exists in Clusive).
    See GetGoogleCourses, which sets this.
    After choice is made, redirects to GetGoogleRoster.
    """
    form_class = GoogleCoursesForm
    courses = []
    template_name = 'roster/manage_show_google_courses.html'

    def get_form(self, form_class=None):
        kwargs = self.get_form_kwargs()
        return GoogleCoursesForm(**kwargs, courses = self.request.session.get('google_courses', []))

    def dispatch(self, request, *args, **kwargs):
        cu = request.clusive_user
        if not cu.can_manage_periods:
            self.handle_no_permission()
        self.clusive_user = cu
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        selected_course_id = self.request.POST.get('course_select')
        return reverse('get_google_roster', kwargs={'course_id': selected_course_id})

    def configure_event(self, event: Event):
        event.page = 'ManageImportPeriodChoice'


class GoogleRosterView(LoginRequiredMixin, ThemedPageMixin, EventMixin, TemplateView):
    """
    Display the roster of a google class, allow user to confirm whether it should be imported.
    Expects google_courses and google_roster parameters in the session: see GetGoogleRoster method.
    The roster is saved in the session for use if the user confirms creation.
    """
    template_name = 'roster/manage_show_google_roster.html'
    role_info = {
        'students': { 'role': Roles.STUDENT, 'display_name': 'Student' },
        'teachers': { 'role': Roles.TEACHER, 'display_name': 'Teacher' }
    }

    def make_roster_tuples(self, google_roster):
        tuples = []
        for group in google_roster:
            for person in google_roster[group]:
                email = person['profile']['emailAddress']
                users = User.objects.filter(email=email)
                if users.exists():
                    user_with_that_email = users.first()
                    # Exclude the current user from the roster.
                    if self.request.user == user_with_that_email:
                        continue
                    clusive_user = ClusiveUser.objects.get(user=user_with_that_email)
                    a_person = {
                        'name': user_with_that_email.first_name,
                        'email': email,
                        'role': clusive_user.role,
                        'role_display': Roles.display_name(clusive_user.role),
                        'exists': True
                    }
                else:
                    a_person = {
                        'name': person['profile']['name']['givenName'],
                        'email': email,
                        'role': self.role_info[group]['role'],
                        'role_display': self.role_info[group]['display_name'],
                        'exists': False
                    }
                tuples.append(a_person)
        return tuples

    def dispatch(self, request, *args, **kwargs):
        cu = request.clusive_user
        if not cu.can_manage_periods:
            self.handle_no_permission()
        self.clusive_user = cu

        # API returns all courses, we need to search for the one we're importing.
        google_courses = self.request.session.get('google_courses', [])
        self.course = None
        for course in google_courses:
            if course['id'] == kwargs['course_id']:
                self.course = course
                break
        if not self.course:
            raise PermissionDenied('Course not found')

        # Period name for Clusive is a composite of Google's "name" and (optional) "section"
        self.period_name = self.course['name']
        if 'section' in self.course:
            self.period_name += ' ' + self.course['section']

        # Extract interesting data from the Google roster.
        google_roster = self.request.session.get('google_roster', {})
        self.people = self.make_roster_tuples(google_roster)
        # Data stored in session until user confirms addition (or cancels).
        # Consider also keeping:  course descriptionHeading, updateTime, courseState
        course_data = {
            'id': self.course['id'],
            'name': self.period_name,
            'people': self.people,
        }
        request.session['google_period_import'] = course_data
        logger.debug('Session data stored: %s', course_data)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'course_id': self.course['id'],
            'period_name': self.period_name,
            'people': self.people,
        })
        return context

    def configure_event(self, event: Event):
        event.page = 'ManageImportPeriodConfirm'


class GooglePeriodImport(LoginRequiredMixin, RedirectView):
    """
    Import new Period data that was just confirmed, then redirect to manage page.
    """

    def get(self, request, *args, **kwargs):
        course_id = kwargs['course_id']
        session_data = request.session.get('google_period_import', None)
        if not session_data or session_data['id'] != course_id:
            raise PermissionDenied('Import data is out of date')
        creator = request.clusive_user

        # Find or create user accounts
        user_list = [creator]
        creating_permission = ResearchPermissions.TEACHER_CREATED if creator.role == Roles.TEACHER \
            else ResearchPermissions.PARENT_CREATED
        for person in session_data['people']:
            if person['exists']:
                user_list.append(ClusiveUser.objects.get(user__email=person['email']))
            else:
                properties = {
                    'username': person['email'],
                    'email': person['email'],
                    'first_name': person['name'],
                    'role': person['role'],
                    'permission': creating_permission,
                    'anon_id': ClusiveUser.next_anon_id(),
                    'data_source': RosterDataSource.GOOGLE,
                }
                user_list.append(ClusiveUser.create_from_properties(properties))

        # Create Period
        period = Period.objects.create(name=session_data['name'],
                                       site=creator.get_site(),
                                       data_source=RosterDataSource.GOOGLE,
                                       external_id=session_data['id'])
        period.users.set(user_list)
        period.save()
        self.period = period

        return super().get(request, *args, **kwargs)

    def get_redirect_url(self, *args, **kwargs):
        # Redirect to newly created period
        return reverse('manage', kwargs={'period_id': self.period.id})


class GetGoogleCourses(LoginRequiredMixin, View):
    """
    Calls the Google Classroom API to get a list of courses for this user, then redirects to GoogleCoursesView.
    Requests additional Google permissions if necessary.
    """
    provider = 'google'
    classroom_scopes = 'https://www.googleapis.com/auth/classroom.courses.readonly https://www.googleapis.com/auth/classroom.rosters.readonly https://www.googleapis.com/auth/classroom.profile.emails'
    auth_parameters = urlencode({
        'provider': provider,
        'scopes': classroom_scopes,
        'authorization': 'http://accounts.google.com/o/oauth2/v2/auth?'
    })

    def get(self, request, *args, **kwargs):
        logger.debug("GetGoogleCourses")
        teacher_id = self.google_teacher_id(request.user)
        if teacher_id:
            db_access = OAuth2Database()
            user_credentials = self.make_credentials(request.user, self.classroom_scopes, db_access)
            service = build('classroom', 'v1', credentials=user_credentials)
            try:
                results = service.courses().list(teacherId=teacher_id, pageSize=30).execute()
            except HttpError as e:
                if e.status_code == 403:
                    request.session['add_scopes_return_uri'] = 'get_google_courses'
                    request.session['add_scopes_course_id'] = None
                    return HttpResponseRedirect(reverse('add_scope_access') + '?' + self.auth_parameters)
                else:
                    raise
            courses = results.get('courses', [])
        else:
            courses = []
        logger.debug('There are (%s) Google courses', len(courses))
        for course in courses:
            course['imported'] = Period.objects.filter(data_source=RosterDataSource.GOOGLE, external_id=course['id']).exists()
            logger.debug('- %s, id = %s. Imported=%s', course['name'], course['id'], course['imported'])
        request.session['google_courses'] = courses
        return HttpResponseRedirect(reverse('manage_google_courses'))

    def make_credentials(self, user, scopes, db_access):
        client_info = db_access.retrieve_client_info(self.provider)
        access_token = db_access.retrieve_access_token(user, self.provider)
        return Credentials(access_token.token,
                            refresh_token=access_token.token_secret,
                            client_id=client_info.client_id,
                            client_secret=client_info.secret,
                            token_uri='https://accounts.google.com/o/oauth2/token')

    def google_teacher_id(self, user):
        # Rationale: Google teacher identifer can be the special key 'me', the
        # user's Google account email address, or their Google identifier.  Only
        # the latter is guaranteed to match a Google course's teacher
        # identifier.
        # https://developers.google.com/classroom/reference/rest/v1/courses/list
        try:
            google_user = SocialAccount.objects.get(user=user, provider='google')
            return google_user.uid
        except SocialAccount.DoesNotExist:
            logger.debug('User %s is not an SSO user', user.username)
            return None

class GetGoogleRoster(GetGoogleCourses):
    """
    Calls Google Classroom API to get the roster of a given course, then redirects to GoogleRosterView.
    """

    def get(self, request, *args, **kwargs):
        course_id = kwargs.get('course_id')
        db_access = OAuth2Database()
        user_credentials = self.make_credentials(request.user, self.classroom_scopes, db_access)
        service = build('classroom', 'v1', credentials=user_credentials)

        # TODO:  could get a permission error, not because of lack of scope, but
        # because the access_token has expired, and need a new one.  Should use
        # the `refresh` workflow instead of the `code` workflow -- the latter
        # will always work, however.  Question is, can you tell from the
        # authorization error (HttpError) if it's lack of scope or expired
        # token?
        # Note: documentation for `pageSize` query parameter (defaults to 30):
        # https://developers.google.com/classroom/reference/rest/v1/courses.students/list
        # https://developers.google.com/classroom/reference/rest/v1/courses.teachers/list
        try:
            studentResponse = service.courses().students().list(courseId=course_id, pageSize=100).execute()
            teacherResponse = service.courses().teachers().list(courseId=course_id).execute()
        except HttpError as e:
            if e.status_code == 403:
                request.session['add_scopes_return_uri'] = 'get_google_roster'
                request.session['add_scopes_course_id'] = course_id
                return HttpResponseRedirect(reverse('add_scope_access') + '?' + self.auth_parameters)
            else:
                raise
        students = studentResponse.get('students', [])
        teachers = teacherResponse.get('teachers', [])
        self.log_results(students, 'students')
        self.log_results(teachers, 'teachers')

        request.session['google_roster'] = { 'students': students, 'teachers': teachers }
        return HttpResponseRedirect(reverse('manage_google_roster', kwargs={'course_id': course_id}));

    def log_results(self, group, role):
        logger.debug('Get Google roster: there are (%s) %s', len(group), role)
        for person in group:
            logger.debug('- %s, %s', person['profile']['name']['givenName'], person['profile']['emailAddress'])

########################################
#
# Functions for adding scope(s) workflow

class OAuth2Database(object):

    def retrieve_client_info(self, provider):
        client_info = SocialApp.objects.filter(provider=provider).first()
        return client_info

    def retrieve_access_token(self, user, provider):
        access_token = SocialToken.objects.filter(
            account__user=user, account__provider=provider
        ).first()
        return access_token

    def update_access_token(self, access_token_json, user, provider):
        db_token = self.retrieve_access_token(user, provider)
        db_token.token = access_token_json.get('access_token')
        db_token.expires_at = timezone.now() + timedelta(seconds=int(access_token_json.get('expires_in')))

        # Update the refresh token only if a new one was provided.  OAuth2
        # providers don't always send a refresh token.
        if access_token_json.get('refresh_token') != None:
            db_token.token_secret = access_token_json['refresh_token']
        db_token.save()

def add_scope_access(request):
    """First step for the request-additional-scope-access workflow.  Sets a new
    `state` query parameter (the anti-forgery token) for the workflow, and
    stores it in the session as `oauth2_state`.  Redirects to provider's
    authorization end point."""
    provider = request.GET.get('provider')
    new_scopes = request.GET.get('scopes')
    authorization_uri = request.GET.get('authorization')
    oauth2_state = get_random_string(12)
    request.session['oauth2_state'] = oauth2_state

    client_info = OAuth2Database().retrieve_client_info(provider)
    parameters = urlencode({
        'client_id': client_info.client_id,
        'response_type': 'code',
        'scope': new_scopes,
        'include_granted_scopes': 'true',
        'state': oauth2_state,
        'redirect_uri': get_add_scope_redirect_uri(request),
    })
    logger.debug('Authorization request to provider for larger scope access')
    return HttpResponseRedirect(authorization_uri + parameters)

def add_scope_callback(request):
    """Handles callback from OAuth2 provider where access tokens are given for
    the requested scopes."""
    request_state = request.GET.get('state')
    session_state = request.session.get('oauth2_state')
    if request_state != session_state:
        raise OAuth2Error("Mismatched state in request: %s" % request_state)

    code = request.GET.get('code')
    dbAccess = OAuth2Database()
    # TODO: the provider is hard coded here -- how to parameterize?  Note that
    # this function is specific to google, so perhaps okay.
    # Note: for production, replace the `redirect_uri` with the official uri
    client_info = dbAccess.retrieve_client_info('google')
    logger.debug('Token request to provider for larger scope access')
    resp = requests.request(
        'POST',
        'https://accounts.google.com/o/oauth2/token',
        data={
            'redirect_uri': get_add_scope_redirect_uri(request),
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': client_info.client_id,
            'client_secret': client_info.secret,
            'state': request_state
        }
    )
    access_token = None
    if resp.status_code == 200 or resp.status_code == 201:
        access_token = resp.json()
    if not access_token or access_token.get('access_token') == None:
        raise OAuth2Error("Error retrieving access token: none given, status: %d" % resp.status_code)
    dbAccess.update_access_token(access_token, request.user, 'google')

    # TODO:  There has to be a better way.
    return_uri = request.session['add_scopes_return_uri']
    course_id = request.session['add_scopes_course_id']
    logger.debug('Larger scope access request complete, returning to %s, with course id %s', return_uri, course_id)
    if course_id:
        return HttpResponseRedirect(reverse(return_uri, kwargs={'course_id': course_id}))
    else:
        return HttpResponseRedirect(reverse(return_uri))


def get_add_scope_redirect_uri(request):
    # Determine if we are using HTTPS - outside any reverse proxy.
    # Would be better to do this by setting SECURE_PROXY_SSL_HEADER but I am not 100% sure that will not cause other
    # problems, so trying this first and will attempt to set that as a smaller update later.
    # See: https://ubuntu.com/blog/django-behind-a-proxy-fixing-absolute-urls
    scheme = request.scheme
    if scheme == 'http' and request.META.get('HTTP_X_FORWARDED_PROTO') == 'https':
        scheme = 'https'
    return scheme + '://' + get_current_site(request).domain + '/account/add_scope_callback/'
