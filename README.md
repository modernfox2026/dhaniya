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
- Material 3 style interface with an olive green palette, light and dark themes, and a mobile navigation drawer
- Icons bundled locally (no internet needed on the LAN)

## Productivity features

- **My Work** page: your open tickets by status, anything overdue or due within 7 days, the Ready to Test queue, and recent team activity
- **Drag and drop** on the Work Board (or use the swap icon on each card); cards sort by priority then due date, and Completed shows the latest 25
- **Quick filter chips**: Mine, Unassigned, Overdue, Due in 7 days, Critical, Hide completed, plus an assignee filter
- **Search by ticket number** (`ACMI-000012`, `#12`, or `12`)
- **Backlog**: sortable columns, pagination, and bulk updates of status, priority, assignee, or area (Shift+Click selects a range)
- **CSV export** of the current filtered list
- **Insights**: overall completion, weekly throughput for the last 12 weeks, progress by area, workload per person, average days to complete
- Ticket page: one click status changes, **Assign to me**, **Duplicate**, copy ticket number, field by field change history
- **Save and add another** when entering several tickets in a row
- User administration: enable or disable accounts, promote or demote admins, see each person's open ticket count
- **Keyboard shortcuts** (press `?`): `/` search, `n` new ticket, `g m`/`g b`/`g l`/`g i` navigate, `e` edit, `a` assign to me, `Ctrl+Enter` submit

## Quick demo without SQL Server

Set `DB_ENGINE=sqlite` in `.env` to use a local `db.sqlite3` file instead of SQL Server. This is handy for trying the app or running the tests:

```powershell
$env:DB_ENGINE="sqlite"; python manage.py test tracker
```

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
