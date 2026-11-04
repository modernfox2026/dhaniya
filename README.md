# Team Work Tracker - Django MVC

A local Django application backed by Microsoft SQL Server where every role on the team (Developer, Toxicologist, Technical, Administration, or any role you add) tracks its work, plans sprints, and sees how long tasks take.

## Roles, categories, sprints, and time

- **Roles**: admins create roles (Users > Roles) and give each person a role and an access level (Member or Admin) when creating their login or later from Users.
- **Categories**: each role has its own categories of work (for example Developers: Bug fix, Code review; Toxicologists: Study review, Risk assessment). Any member can add or edit categories for their own role; admins manage all of them, including shared categories everyone can use.
- **Sprints**: admins create sprints with dates and a goal, then start them. The active sprint is shown on the **Team board** (home page) for the whole team, with progress, time worked, and days left. Closing a sprint moves unfinished tasks to the next sprint or back to the backlog. Plan tasks into a sprint from All tasks using the bulk bar.
- **Time tracking**: the clock starts automatically when a task moves to **In Progress** and stops when it is **Completed**. Time in Ready to Test still counts; moving a task back to Backlog pauses the clock, and reopening a completed task resumes it. Running clocks update live on the board and appear on My work.


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
- **Drag and drop** on the Team board (or use the swap icon on each card); cards sort by priority then due date, and Completed shows the latest 25
- **Filters**: role chips on the board, plus Mine, My team, Unassigned, Overdue, Due in 7 days, Critical, Hide completed, category, sprint, and assignee
- **Search by task number** (`ACMI-000012`, `#12`, or `12`). Set `TICKET_PREFIX` in `.env` to change the prefix.
- **All tasks**: sortable columns, pagination, and bulk updates of status, priority, assignee, category, or sprint (Shift+Click selects a range)
- **CSV export** of the current filtered list
- **Insights**: overall completion, weekly throughput, progress and average time per role and per category, workload per person
- Ticket page: one click status changes, **Assign to me**, **Duplicate**, copy ticket number, field by field change history
- **Save and add another** when entering several tickets in a row
- User administration: enable or disable accounts, promote or demote admins, see each person's open ticket count
- **Keyboard shortcuts** (press `?`): `/` search, `n` new ticket, `g m`/`g b`/`g l`/`g i` navigate, `e` edit, `a` assign to me, `Ctrl+Enter` submit

## Quick demo without SQL Server

Set `DB_ENGINE=sqlite` in `.env` to use a local `db.sqlite3` file instead of SQL Server. This is handy for trying the app or running the tests:

```powershell
$env:DB_ENGINE="sqlite"; python manage.py test tracker
```

## Upgrading from the modernization tracker

Run `python manage.py migrate` and then `python manage.py seed_tracker`. Existing areas become shared categories, existing users get an empty role (assign one in Users), and tasks already In Progress or Ready to Test start their clock at upgrade time.

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

8. Create the default roles, their starter categories, and the initial administrator (safe to run again; it never resets an existing admin password):

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
