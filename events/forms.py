from django import forms
from .models import EventsNotApprovedProposed

class EventAddForm(forms.ModelForm):
    class Meta:
        model = EventsNotApprovedProposed
        fields = [
            'title', 'full_text', 'address',
            'image_upload', 'from_date', 'to_date',
            'place', 'price']
        widgets = {
            'title':     forms.TextInput(attrs={'class': 'form-control'}),
            'full_text': forms.Textarea(attrs={'class': 'form-control'}),
            'address':   forms.TextInput(attrs={'class': 'form-control'}),
            'place':     forms.Select(attrs={'class': 'form-control'}),
            'price':     forms.TextInput(attrs={'class': 'form-control'}),
            'from_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'to_date':   forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        }

        def clean_image_upload(self):
            image = self.cleaned_data.get('image_upload', False)
            if image:
                if image.size > 2 * 1024 * 1024:
                    raise forms.ValidationError("Image file too large ( > 2MB )")
                return image
            else:
                raise forms.ValidationError("Couldn't read uploaded image")