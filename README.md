# AutoTime

Smart Timetable Generator and Management System

AutoTime is a Flask-based web application designed to help colleges automatically create and manage timetables while avoiding teacher and class conflicts.

Live Application: [AutoTime on Vercel](https://autotime-webapp.vercel.app/)
![CI Status](https://github.com/Saurabh-Yadav-4712/autotime-webapp/actions/workflows/ci.yml/badge.svg)

## About the Project

Manual timetable creation takes significant time and often results in clashes, uneven schedules, teacher availability problems, and difficulties handling unexpected leave. AutoTime helps automate these scheduling tasks while allowing administrators to fully manage and edit the timetable.

## Main Features

### Admin
- Manage institute settings
- Manage courses, classes, subjects, and teachers
- Generate timetable
- Edit and view timetable
- Approve teacher leave
- Automatic proxy assignment
- Timetable history
- Excel/PDF export

### Teacher
- Account activation and login
- Personal timetable
- Live Current Week timetable
- Leave request and cancellation
- View proxy lectures
- Notifications

### Student
- Registration and login
- Class timetable
- Current-week timetable
- Updated proxy teacher information

## Timetable Generation

The automated scheduling engine constructs the timetable by matching available teachers and subjects to class time slots without overlaps. It handles practical blocks, consecutive lectures, and shared subjects. The system checks teacher availability, workload limits, and required course hours while generating the timetable. It performs validation before saving and attempts to optimize the timetable to reduce unnecessary timetable gaps and improve schedule quality.

## Leave and Proxy Management

When a teacher requests leave, the system manages the absence as follows:
Teacher requests leave -> Admin approves -> System finds an available eligible proxy teacher -> Current timetable displays proxy -> Master weekly timetable remains unchanged -> Cancelling or revoking the leave automatically restores the normal teacher.

## Technology Used

| Component | Technology |
|---|---|
| **Backend** | Python, Flask |
| **Database** | PostgreSQL / Supabase, SQLAlchemy |
| **Frontend** | HTML, CSS, Bootstrap, JavaScript, Jinja2 |
| **Email** | SMTP |
| **Excel** | openpyxl |
| **Testing** | Pytest |
| **Deployment** | Vercel |
| **Version Control** | Git and GitHub |

## Project Structure

- `routes/` - Handles web traffic, URLs, and page requests
- `utils/` - Core logic, scheduling adapter, and helpers
- `utils/scheduler/` - The scheduling engine algorithm
- `templates/` - HTML layout and Jinja2 frontend components
- `static/` - CSS styles and JavaScript files
- `models.py` - Database tables and SQLAlchemy setup
- `migrations/` - Database schema change history
- `tests/` - Automated unit and integration tests
- `app.py` - The main application entry point
- `requirements.txt` - Required Python packages
- `vercel.json` - Deployment configuration for Vercel

## How to Run Locally

```bash
git clone https://github.com/Saurabh-Yadav-4712/autotime-webapp.git
cd autotime-webapp
python -m venv .venv
```

Windows:
```powershell
.venv\Scripts\Activate.ps1
```

macOS/Linux:
```bash
source .venv/bin/activate
```

Then:
```bash
pip install -r requirements.txt
```

Copy/use `.env.example` as a reference and configure the required environment variables. Never place real credentials in the repository.

Then run:
```bash
python app.py
```

## Testing

Automated tests cover important scheduler logic, proxy allocation, security, Live Week behavior, and UI rendering.

For developers who want to run the tests locally:
```bash
pip install -r requirements-dev.txt
python -m pytest
```
GitHub Actions also runs these tests automatically on every push.

## Deployment

The application is deployed on Vercel and uses a cloud PostgreSQL database.
Live Link: [https://autotime-webapp.vercel.app/](https://autotime-webapp.vercel.app/)

## Security

AutoTime includes standard web security controls such as hashed passwords, OTP expiry, CSRF protection, secure sessions, and institute-scoped authorization. Sensitive configuration such as secret keys and credentials is loaded through environment variables. For more details, see [SECURITY.md](SECURITY.md).

## Author

Saurabh Yadav
B.Sc. Computer Science
