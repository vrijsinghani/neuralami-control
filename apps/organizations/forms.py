from django import forms
from .models.base import Organization

class OrganizationForm(forms.ModelForm):
    """
    Form for creating and editing organizations.
    """
    class Meta:
        model = Organization
        fields = ['name', 'description', 'logo', 'billing_email']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Organization Name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Description of your organization',
                'rows': 4
            }),
            'logo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'billing_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'billing@example.com'
            }),
        }

    def clean_name(self):
        """Validate that the organization name is unique."""
        name = self.cleaned_data.get('name')
        instance = getattr(self, 'instance', None)
        
        # If editing an existing organization
        if instance and instance.pk:
            # If the name hasn't been changed, it's valid
            if instance.name == name:
                return name
                
            # If name changed, check it doesn't conflict with other organizations
            if Organization.objects.filter(name=name).exclude(pk=instance.pk).exists():
                raise forms.ValidationError("An organization with this name already exists.")
        # If creating a new organization, check name doesn't exist
        elif name and Organization.objects.filter(name=name).exists():
            raise forms.ValidationError("An organization with this name already exists.")
        
        return name 