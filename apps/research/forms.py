from django import forms
from .models import Research

class ResearchForm(forms.ModelForm):
    class Meta:
        model = Research
        fields = ['query', 'breadth', 'depth']
        widgets = {
            'query': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter your research query...'
            }),
            'breadth': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 2,
                'max': 10
            }),
            'depth': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 5
            })
        } 