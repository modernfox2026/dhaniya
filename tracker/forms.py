from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Q
from .models import ProjectArea, Ticket, TicketComment

User = get_user_model()


class UserChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj): return obj.get_full_name() or obj.username


def active_users(): return User.objects.filter(is_active=True).order_by('first_name', 'username')


class TicketForm(forms.ModelForm):
    assigned_to = UserChoiceField(queryset=User.objects.none(), required=False, empty_label='Unassigned')
    class Meta:
        model = Ticket
        fields = ['title','description','priority','area','assigned_to','due_date']
        widgets = {
            'title': forms.TextInput(attrs={'autofocus': True, 'placeholder': 'Short summary of the work'}),
            'description': forms.Textarea(attrs={'rows':6, 'placeholder': 'Legacy FoxPro forms, programs, tables, acceptance criteria...'}),
            'due_date': forms.DateInput(attrs={'type':'date'}, format='%Y-%m-%d'),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep the current assignee/area selectable even if they were deactivated later.
        self.fields['assigned_to'].queryset = User.objects.filter(Q(is_active=True) | Q(pk=self.instance.assigned_to_id)).order_by('first_name', 'username')
        self.fields['area'].queryset = ProjectArea.objects.filter(Q(is_active=True) | Q(pk=self.instance.area_id))
        self.fields['area'].empty_label = 'Other'


class TicketEditForm(TicketForm):
    class Meta(TicketForm.Meta):
        fields = ['title','description','status','priority','area','assigned_to','due_date']


class CommentForm(forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ['text']
        widgets = {'text': forms.Textarea(attrs={'rows':3, 'placeholder':'Implementation notes, test results, or legacy references...'})}


class BulkUpdateForm(forms.Form):
    tickets = forms.ModelMultipleChoiceField(queryset=Ticket.objects.all())
    status = forms.ChoiceField(choices=[('', 'Keep status')] + Ticket.Status.choices, required=False)
    priority = forms.ChoiceField(choices=[('', 'Keep priority')] + Ticket.Priority.choices, required=False)
    area = forms.ModelChoiceField(queryset=ProjectArea.objects.filter(is_active=True), required=False)
    assigned_to = forms.CharField(required=False)
    def clean_assigned_to(self):
        value = self.cleaned_data['assigned_to']
        if value in ('', 'none'): return value
        try: return active_users().get(pk=value)
        except (User.DoesNotExist, ValueError): raise forms.ValidationError('Unknown user.')


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
