from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from .models import Ticket, TicketComment

User = get_user_model()

class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['title','description','priority','area','assigned_to','due_date']
        widgets = {'description': forms.Textarea(attrs={'rows':5}), 'due_date': forms.DateInput(attrs={'type':'date'})}

class TicketEditForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['title','description','status','priority','area','assigned_to','due_date']
        widgets = {'description': forms.Textarea(attrs={'rows':5}), 'due_date': forms.DateInput(attrs={'type':'date'})}

class CommentForm(forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ['text']
        widgets = {'text': forms.Textarea(attrs={'rows':3, 'placeholder':'Implementation notes, test results, or legacy references...'})}

class AdminUserCreationForm(UserCreationForm):
    display_name = forms.CharField(max_length=150)
    role = forms.ChoiceField(choices=[('Member','Member'),('Admin','Admin')])
    class Meta(UserCreationForm.Meta): fields = ('username','display_name','role','password1','password2')
    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data['display_name']
        user.is_staff = self.cleaned_data['role'] == 'Admin'
        if commit: user.save()
        return user

class AdminPasswordResetForm(forms.Form):
    password1 = forms.CharField(widget=forms.PasswordInput, min_length=10, label='New password')
    password2 = forms.CharField(widget=forms.PasswordInput, min_length=10, label='Confirm password')
    def clean(self):
        data = super().clean()
        if data.get('password1') != data.get('password2'): raise forms.ValidationError('Passwords do not match.')
        return data
