from django import forms
from django.core.exceptions import ValidationError
from .models import Client, TargetedKeyword, KeywordRankingHistory, SEOProject
import csv
import io
from django.utils import timezone

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'website_url', 'status', 'group', 'target_audience']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter client name'
            }),
            'website_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://example.com'
            }),
            'status': forms.Select(attrs={
                'class': 'form-select'
            }),
            'group': forms.Select(attrs={
                'class': 'form-select'
            }),
            'target_audience': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe the target audience'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add any additional field customization here
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({
                    'class': field.widget.attrs.get('class', '') + ' form-control'
                })

class BusinessObjectiveForm(forms.Form):
    goal = forms.CharField(required=True)
    metric = forms.CharField(required=True)
    target_date = forms.DateField(required=True)
    status = forms.BooleanField(required=False, initial=True)

    def clean_target_date(self):
        target_date = self.cleaned_data.get('target_date')
        if target_date and target_date < timezone.now().date():
            raise ValidationError("Target date cannot be in the past")
        return target_date

class TargetedKeywordForm(forms.ModelForm):
    class Meta:
        model = TargetedKeyword
        fields = ['keyword', 'priority', 'notes']
        widgets = {
            'keyword': forms.TextInput(attrs={'class': 'form-control'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class KeywordBulkUploadForm(forms.Form):
    csv_file = forms.FileField(
        label='CSV File',
        help_text='Upload a CSV file with columns: keyword, priority (1-5), notes (optional)',
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )

    def clean_csv_file(self):
        csv_file = self.cleaned_data['csv_file']
        if not csv_file.name.endswith('.csv'):
            raise ValidationError('File must be a CSV')
        
        # Validate CSV structure
        try:
            decoded_file = csv_file.read().decode('utf-8')
            csv_data = csv.DictReader(io.StringIO(decoded_file))
            required_fields = ['keyword', 'priority']
            
            if not all(field in csv_data.fieldnames for field in required_fields):
                raise ValidationError('CSV must contain keyword and priority columns')
            
            # Reset file pointer
            csv_file.seek(0)
            return csv_file
        except Exception as e:
            raise ValidationError(f'Invalid CSV file: {str(e)}')

class RankingImportForm(forms.Form):
    IMPORT_SOURCE_CHOICES = [
        ('search_console', 'Google Search Console'),
        ('csv', 'CSV Upload'),
        ('manual', 'Manual Entry'),
    ]

    import_source = forms.ChoiceField(
        choices=IMPORT_SOURCE_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )
    
    date_from = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control flatpickr-date',
            'data-toggle': 'flatpickr'
        })
    )
    
    date_to = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control flatpickr-date',
            'data-toggle': 'flatpickr'
        })
    )
    
    csv_file = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )

    def clean(self):
        cleaned_data = super().clean()
        import_source = cleaned_data.get('import_source')
        csv_file = cleaned_data.get('csv_file')

        if import_source == 'csv' and not csv_file:
            raise ValidationError('CSV file is required when importing from CSV')

        return cleaned_data

    def process_import(self, user):
        import_source = self.cleaned_data['import_source']
        
        if import_source == 'search_console':
            return self._process_search_console_import()
        elif import_source == 'csv':
            return self._process_csv_import()
        else:
            return self._process_manual_entry()

    def _process_search_console_import(self):
        # Implementation for Search Console import
        pass

    def _process_csv_import(self):
        # Implementation for CSV import
        pass

    def _process_manual_entry(self):
        # Implementation for manual entry
        pass

class SEOProjectForm(forms.ModelForm):
    class Meta:
        model = SEOProject
        fields = ['title', 'description', 'status', 
                 'implementation_date', 'completion_date', 
                 'targeted_keywords']
        widgets = {
            'implementation_date': forms.DateInput(attrs={
                'class': 'form-control datepicker',
                'type': 'date'
            }),
            'completion_date': forms.DateInput(attrs={
                'class': 'form-control datepicker',
                'type': 'date'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3, 
                'class': 'form-control'
            }),
            'title': forms.TextInput(attrs={
                'class': 'form-control'
            }),
            'status': forms.Select(attrs={
                'class': 'form-control'
            }),
            'targeted_keywords': forms.SelectMultiple(attrs={
                'class': 'form-control'
            }),
        }

    def __init__(self, *args, **kwargs):
        client = kwargs.pop('client', None)
        super().__init__(*args, **kwargs)
        
        if client:
            self.fields['targeted_keywords'].queryset = TargetedKeyword.objects.filter(
                client=client
            ).order_by('keyword')

    def clean(self):
        cleaned_data = super().clean()
        implementation_date = cleaned_data.get('implementation_date')
        completion_date = cleaned_data.get('completion_date')

        if completion_date and implementation_date and completion_date < implementation_date:
            raise ValidationError({
                'completion_date': 'Completion date cannot be earlier than implementation date.'
            })

        return cleaned_data

class ClientProfileForm(forms.Form):
    client_profile = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 10,
            'placeholder': 'Enter a detailed 300-500 word profile of the client\'s business, goals, and SEO strategy'
        }),
        help_text="Provide a comprehensive overview of the client's business, target market, goals, and SEO strategy."
    )
