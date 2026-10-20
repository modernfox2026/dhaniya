# FoxPro Modernization Tracker - Django MVC

A local Django application backed by Microsoft SQL Server for tracking the Visual FoxPro to .NET modernization project.

## Included

- Django model-view-template/MVC-style structure
- Microsoft SQL Server through `mssql-django`
- Local login with no email verification
- Admin-only account creation
- Admin-only password reset for another user
- All-ticket Backlog with search and filters
- Work Board with Backlog, In Progress, Ready to Test, and Completed stages
- Ticket creation, editing, assignment, comments, and history
- Olive-green responsive interface

## Database

Use a new database in the same SQL Server instance as your other databases. The recommended name is:

```text
FoxProModernizationTracker
```

Create it in SQL Server Management Studio first:

```sql
CREATE DATABASE FoxProModernizationTracker;
```

The Django migration command creates the tables inside that database.

## Windows setup

1. Install Python 3.12 or newer.
2. Install Microsoft ODBC Driver 18 for SQL Server.
3. Extract this ZIP and open PowerShell in the extracted folder.
4. Create and activate a virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

5. Install dependencies:

```powershell
pip install -r requirements.txt
```

6. Copy and edit the environment file:

```powershell
Copy-Item .env.example .env
notepad .env
```

7. Create the database tables:

```powershell
python manage.py migrate
```

8. Create standard areas and the initial administrator:

```powershell
python manage.py seed_tracker
```

9. Start locally:

```powershell
python manage.py runserver
```

10. Open http://127.0.0.1:8000

## Local production-style server

```powershell
python manage.py collectstatic --noinput
waitress-serve --listen=127.0.0.1:8000 modernization_tracker.wsgi:application
```

To permit another computer on the local network, set `DJANGO_ALLOWED_HOSTS` to include the host computer name or IP, then listen on `0.0.0.0:8000`. Coordinate firewall access before doing this.
