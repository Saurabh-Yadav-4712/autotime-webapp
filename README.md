# AutoTime WebApp 🕒

![AutoTime](https://img.shields.io/badge/AutoTime-Smart_Timetable_System-4f46e5?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)
![Vercel](https://img.shields.io/badge/Vercel-000000?style=for-the-badge&logo=vercel&logoColor=white)

AutoTime is a centralized, cloud-based platform designed for educational institutions to intelligently manage, generate, and distribute academic timetables. Built with modern web technologies, it automates the complex task of scheduling while handling teacher constraints, dynamic time slots, and real-time proxy assignments.

## ✨ Key Features

- **🤖 Automated Timetable Generation**: Algorithmic scheduling that respects teacher availability, prevents double-booking, and adapts to dynamic lecture durations.
- **🛡️ Role-Based Access Control**: Dedicated, secure portals for **Admins** (configuration & generation), **Teachers** (schedule & leave management), and **Students** (read-only schedule view).
- **🔄 Auto-Proxy Management**: When a teacher applies for leave, the system intelligently finds available teachers and auto-assigns proxies to prevent vacant classes.
- **✉️ Secure OTP Authentication**: Passwordless-style email verification and robust secure session states for registration and account recovery.
- **⚡ Lightning Fast UI**: Built with Turbo (Hotwired) for a snappy, Single-Page Application (SPA) feel, complete with modern inline loaders and dynamic Dark/Light mode support.
- **📊 Excel Export**: Download any generated timetable instantly as a beautifully formatted `.xlsx` file.

## 🛠️ Tech Stack

- **Backend**: Python 3, Flask, SQLAlchemy, Werkzeug
- **Database**: PostgreSQL (Supabase recommended)
- **Frontend**: HTML5, CSS3, Vanilla JS, Bootstrap 5, Hotwired Turbo
- **Deployment**: Vercel (Serverless)

## 🚀 Quick Start (Local Development)

### Prerequisites
- Python 3.x installed
- A PostgreSQL database (e.g., local Postgres or a Supabase instance)
- An SMTP email account (e.g., Gmail App Password) for sending OTPs.

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-username/autotime-webapp.git
   cd autotime-webapp
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**
   Set the following environment variables in your terminal before running the app:
   ```env
   DATABASE_URL=postgresql://user:password@localhost:5432/autotime
   SMTP_EMAIL=your-email@gmail.com
   SMTP_PASSWORD=your-app-password
   ```

4. **Run the application**
   ```bash
   python app.py
   ```
   The app will be available at `http://127.0.0.1:5000`.

## 🔒 Security Note (Supabase)
If hosting your database on Supabase, please ensure that **Row Level Security (RLS)** is enabled on all tables (`institute`, `teacher`, `course`, `subject`, `timetable`, `settings`, `student`) via your Supabase SQL Editor. This protects your database against unauthorized access via the public PostgREST API. 

## 📝 License
This project is proprietary and built for internal institute use. All rights reserved.
