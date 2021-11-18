import logging

from django import forms

from library.models import Book
from roster.models import Period, ClusiveUser

import pdb

logger = logging.getLogger(__name__)


class SearchForm(forms.Form):
    query = forms.fields.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'type': 'search',
            'placeholder': 'Search library',
            'aria-label': 'Search library',
            'class': 'form-control library-search-input',
        }))


class UploadForm(forms.Form):
    file = forms.FileField(label='File')


class MetadataForm(forms.ModelForm):
    cover = forms.FileField(required=False, label='Choose new image...')
    cover.widget.attrs.update({'accept': 'image/*'})

    use_orig_cover = forms.BooleanField(label='Use this', required=False, initial=False)
    use_orig_cover.widget.attrs.update({'class': 'usethis-cover'})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ''

    class Meta:
        model = Book
        fields = ['title', 'sort_title', 'author', 'sort_author', 'description', 'subjects']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'Reading title'}),
            'sort_title': forms.TextInput(attrs={'placeholder': 'Version of the title used for sorting'}),
            'author': forms.TextInput(attrs={'placeholder': 'Author of the reading'}),
            'sort_author': forms.TextInput(attrs={'placeholder': 'Version of the author name used for sorting'}),
            'description': forms.Textarea(attrs={'placeholder': 'Brief description to show on the Library page.'}),
            #'subjects': forms.Textarea(attrs={'placeholder': 'Check all that apply.'})
            'subjects': forms.CheckboxSelectMultiple(),
        }



class PeriodModelMultipleChoiceField(forms.ModelMultipleChoiceField):

    def label_from_instance(self, period):
        return period.name


class ShareForm(forms.Form):
    periods = PeriodModelMultipleChoiceField(
        widget=forms.CheckboxSelectMultiple(),
        queryset=Period.objects.all(),
        required=False)

    def __init__(self, *args, **kwargs):
        clusive_user : ClusiveUser
        clusive_user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        periods = clusive_user.periods.all()
        self.fields['periods'].queryset = periods

class BookshareSearchForm(forms.Form):
    keyword = forms.CharField(
        required = False,
        initial = '',
        widget = forms.TextInput(attrs={
            'placeholder': 'Title, Author, or ISBN',
            'aria-label': 'Search by title, author, or ISBN',
            'class': 'form-control',
        })
    )
    
    def clean_keyword(self):
        if self.is_valid():
            data = self.cleaned_data.get('keyword', '')
            return data.strip()
        else:
            raise ValidationError(_('Invalid format for keyword'))

class BookshareListResourcesForm(forms.Form):
    # title, authors, isbn, availability
    label_placeholder = '{}   By {}, ISBN: {} ({})'

    def __init__(self, *args, **kwargs):
        titles = kwargs.pop('titles')
        super().__init__(*args, **kwargs)
        title_choices = []
        for book in titles.get('titles', []):
            title = book['title']
            authors = []
            for contributor in book['contributors']:
                if contributor['type'] == 'author':
                    authors.append(contributor['name']['displayName'])
            by = ', '.join(authors)
            # a None value for isbn13 is possible (!)
            isbn = book.get('isbn13') or '-'
            available = 'available' if book.get('available', False) else 'not available'
            bookshare_id = book['bookshareId']
            label = self.label_placeholder.format(title, by, isbn, available)
            title_choices.append((bookshare_id, label))
            logger.debug('title: %s', label)
        
        self.fields['title_select'] = forms.ChoiceField(
            choices=title_choices,
            required=True,
            widget=forms.RadioSelect
        )

