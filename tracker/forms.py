from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Q
from .models import Category, Profile, Sprint, Team, Ticket, TicketComment, team_of

User = get_user_model()


class UserChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj): return obj.get_full_name() or obj.username


def active_users(): return User.objects.filter(is_active=True).order_by('first_name', 'username')


def open_sprints(): return Sprint.objects.exclude(state=Sprint.State.CLOSED).order_by('start_date')


class TicketForm(forms.ModelForm):
    assigned_to = UserChoiceField(queryset=User.objects.none(), required=False, empty_label='Unassigned')
    class Meta:
        model = Ticket
        fields = ['title','description','priority','team','category','sprint','assigned_to','due_date']
        labels = {'team': 'Role / team'}
        widgets = {
            'title': forms.TextInput(attrs={'autofocus': True, 'placeholder': 'Short summary of the work'}),
            'description': forms.Textarea(attrs={'rows':6, 'placeholder': 'Details, references, acceptance criteria...'}),
            'due_date': forms.DateInput(attrs={'type':'date'}, format='%Y-%m-%d'),
        }
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance
        # Keep the current values selectable even if they were deactivated later.
        self.fields['assigned_to'].queryset = User.objects.filter(Q(is_active=True) | Q(pk=inst.assigned_to_id)).order_by('first_name', 'username')
        self.fields['team'].queryset = Team.objects.filter(Q(is_active=True) | Q(pk=inst.team_id))
        self.fields['team'].empty_label = 'No team'
        self.fields['category'].queryset = Category.objects.select_related('team').filter(Q(is_active=True) | Q(pk=inst.category_id)).order_by('team__name', 'name')
        self.fields['category'].empty_label = 'Uncategorized'
        self.fields['category'].help_text = 'Shared categories, or ones belonging to the chosen team.'
        self.fields['sprint'].queryset = Sprint.objects.filter(Q(pk=inst.sprint_id) | ~Q(state=Sprint.State.CLOSED)).order_by('start_date')
        self.fields['sprint'].empty_label = 'No sprint'
        if not inst.pk and user is not None and 'team' not in self.initial:
            self.initial['team'] = getattr(team_of(user), 'pk', None)
        if not inst.pk and 'sprint' not in self.initial:
            active = Sprint.objects.filter(state=Sprint.State.ACTIVE).order_by('start_date').first()
            if active: self.initial['sprint'] = active.pk
    def clean(self):
        data = super().clean()
        team, category = data.get('team'), data.get('category')
        if category and category.team_id:
            if team is None: data['team'] = category.team
            elif category.team_id != team.pk: self.add_error('category', f'"{category.name}" belongs to the {category.team} team.')
        return data


class TicketEditForm(TicketForm):
    class Meta(TicketForm.Meta):
        fields = ['title','description','status','priority','team','category','sprint','assigned_to','due_date']


class CommentForm(forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ['text']
        widgets = {'text': forms.Textarea(attrs={'rows':3, 'placeholder':'Notes, results, links, or questions...'})}


class BulkUpdateForm(forms.Form):
    tickets = forms.ModelMultipleChoiceField(queryset=Ticket.objects.all())
    status = forms.ChoiceField(choices=[('', 'Keep status')] + Ticket.Status.choices, required=False)
    priority = forms.ChoiceField(choices=[('', 'Keep priority')] + Ticket.Priority.choices, required=False)
    category = forms.ModelChoiceField(queryset=Category.objects.filter(is_active=True), required=False)
    assigned_to = forms.CharField(required=False)
    sprint = forms.CharField(required=False)
    def clean_assigned_to(self):
        value = self.cleaned_data['assigned_to']
        if value in ('', 'none'): return value
        try: return active_users().get(pk=value)
        except (User.DoesNotExist, ValueError): raise forms.ValidationError('Unknown user.')
    def clean_sprint(self):
        value = self.cleaned_data['sprint']
        if value in ('', 'none'): return value
        try: return open_sprints().get(pk=value)
        except (Sprint.DoesNotExist, ValueError): raise forms.ValidationError('Unknown sprint.')


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'team', 'is_active']
        labels = {'team': 'Role / team', 'is_active': 'Active'}
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['team'].queryset = Team.objects.filter(is_active=True)
        self.fields['team'].empty_label = 'Shared with everyone'
        if user and not user.is_staff:
            # Members manage categories for their own team only.
            own = team_of(user)
            self.fields['team'].queryset = Team.objects.filter(pk=getattr(own, 'pk', None))
            self.fields['team'].required = own is not None
            self.fields['team'].disabled = True
            self.initial['team'] = getattr(own, 'pk', None)
        elif user and not self.instance.pk:
            self.initial.setdefault('team', getattr(team_of(user), 'pk', None))
    def clean(self):
        data = super().clean()
        name, team = (data.get('name') or '').strip(), data.get('team')
        clash = Category.objects.filter(name__iexact=name, team=team).exclude(pk=self.instance.pk)
        if name and clash.exists(): self.add_error('name', 'That category already exists for this team.')
        data['name'] = name
        return data


class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ['name', 'description', 'color', 'is_active']
        labels = {'is_active': 'Active'}
        widgets = {'color': forms.TextInput(attrs={'type': 'color'})}


class SprintForm(forms.ModelForm):
    class Meta:
        model = Sprint
        fields = ['name', 'goal', 'start_date', 'end_date', 'state']
        widgets = {
            'goal': forms.TextInput(attrs={'placeholder': 'What the team wants to achieve'}),
            'start_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'end_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }
    def clean(self):
        data = super().clean()
        if data.get('start_date') and data.get('end_date') and data['end_date'] < data['start_date']:
            self.add_error('end_date', 'The sprint must end on or after its start date.')
        return data


ROLE_CHOICES = [('Member','Member'),('Admin','Admin')]


class AdminUserCreationForm(UserCreationForm):
    display_name = forms.CharField(max_length=150)
    team = forms.ModelChoiceField(queryset=Team.objects.filter(is_active=True), required=False, empty_label='No team', label='Role / team')
    role = forms.ChoiceField(choices=ROLE_CHOICES, label='Access level')
    class Meta(UserCreationForm.Meta): fields = ('username','display_name','team','role','password1','password2')
    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data['display_name']
        user.is_staff = self.cleaned_data['role'] == 'Admin'
        if commit:
            user.save()
            Profile.objects.update_or_create(user=user, defaults={'team': self.cleaned_data['team']})
        return user


class UserEditForm(forms.Form):
    display_name = forms.CharField(max_length=150)
    team = forms.ModelChoiceField(queryset=Team.objects.filter(is_active=True), required=False, empty_label='No team', label='Role / team')
    role = forms.ChoiceField(choices=ROLE_CHOICES, label='Access level', help_text='Admins manage users, roles, sprints, and all categories.')
    is_active = forms.BooleanField(required=False, label='Account can sign in')


class AdminPasswordResetForm(forms.Form):
    password1 = forms.CharField(widget=forms.PasswordInput, min_length=10, label='New password')
    password2 = forms.CharField(widget=forms.PasswordInput, min_length=10, label='Confirm password')
    def clean(self):
        data = super().clean()
        if data.get('password1') != data.get('password2'): raise forms.ValidationError('Passwords do not match.')
        return data
