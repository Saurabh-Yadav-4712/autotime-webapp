from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()
from datetime import datetime

# ==========================================
# DATABASE MODELS
# ==========================================

class SubjectCourse(db.Model):
    __tablename__ = 'subject_courses'
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id', ondelete='CASCADE'), primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id', ondelete='CASCADE'), primary_key=True)
    is_active = db.Column(db.Boolean, default=True)


class Institute(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    institute_code = db.Column(db.String(20), unique=True, nullable=False)
    admin_username = db.Column(db.String(50), unique=True, nullable=False)
    admin_email = db.Column(db.String(100), unique=True, nullable=False)
    admin_password = db.Column(db.String(255), nullable=False)

class Teacher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institute_id = db.Column(db.Integer, db.ForeignKey("institute.id", ondelete="CASCADE"), nullable=True)
    institute_code = db.Column(db.String(20), nullable=False)
    teacher_id = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    departments = db.Column(db.String(100), nullable=False)
    available_days = db.Column(db.String(100), nullable=False)
    max_hours = db.Column(db.Integer, nullable=False)
    password = db.Column(db.String(255), nullable=True)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institute_id = db.Column(db.Integer, db.ForeignKey("institute.id", ondelete="CASCADE"), nullable=True)
    institute_code = db.Column(db.String(20), nullable=False)
    class_id = db.Column(db.String(50), nullable=False)
    department = db.Column(db.String(50), nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    division = db.Column(db.String(10), nullable=False)

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institute_id = db.Column(db.Integer, db.ForeignKey("institute.id", ondelete="CASCADE"), nullable=True)
    teacher_id_fk = db.Column(db.Integer, db.ForeignKey("teacher.id", ondelete="RESTRICT"), nullable=True)
    courses = db.relationship("Course", secondary="subject_courses", backref=db.backref("subjects", lazy="dynamic"))
    institute_code = db.Column(db.String(20), nullable=False)
    subject_code = db.Column(db.String(20), nullable=False)
    subject_name = db.Column(db.String(100), nullable=False)
    class_id = db.Column(db.String(100), nullable=False)
    teacher_id = db.Column(db.String(20), nullable=False)
    total_course_hours = db.Column(db.Integer, nullable=False, default=50)
    required_hours = db.Column(db.Integer, nullable=False) # Weekly
    completed_hours = db.Column(db.Integer, nullable=False, default=0) # Syllabus tracker
    subject_type = db.Column(db.String(50), default='Theory')
    session_length = db.Column(db.Integer, default=1)
    preferred_days = db.Column(db.String(100), default="")

class Timetable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institute_id = db.Column(db.Integer, db.ForeignKey("institute.id", ondelete="CASCADE"), nullable=True)
    course_id_fk = db.Column(db.Integer, db.ForeignKey("course.id", ondelete="CASCADE"), nullable=True)
    teacher_id_fk = db.Column(db.Integer, db.ForeignKey("teacher.id", ondelete="CASCADE"), nullable=True)
    subject_id_fk = db.Column(db.Integer, db.ForeignKey("subject.id", ondelete="CASCADE"), nullable=True)
    session_group_id = db.Column(db.String(50), nullable=True, index=True)
    institute_code = db.Column(db.String(20), nullable=False)
    class_id = db.Column(db.String(50), nullable=False)
    day_name = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.String(20), nullable=False)
    end_time = db.Column(db.String(20), nullable=False)
    subject_name = db.Column(db.String(100), nullable=False)
    teacher_name = db.Column(db.String(100), nullable=False)
    is_proxy = db.Column(db.Boolean, default=False)
    specific_date = db.Column(db.Date, nullable=True) # Used for Make-Up/Proxy classes assigned to a specific date

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institute_code = db.Column(db.String(20), nullable=False)
    key = db.Column(db.String(50), nullable=False)
    value = db.Column(db.String(100), nullable=False)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institute_code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    class_id = db.Column(db.String(50), nullable=False)

class TeacherUpdateRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institute_code = db.Column(db.String(20), nullable=False)
    teacher_id = db.Column(db.String(20), nullable=False)
    new_name = db.Column(db.String(100), nullable=True)
    new_email = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AcademicCalendar(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institute_code = db.Column(db.String(20), nullable=False)
    date = db.Column(db.Date, nullable=False)
    event_name = db.Column(db.String(200), nullable=False)
    department = db.Column(db.String(50), nullable=True) # All, or specific dept
    is_holiday = db.Column(db.Boolean, default=True) # If true, regular lectures are hidden

class TeacherLeave(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institute_code = db.Column(db.String(20), nullable=False)
    teacher_id = db.Column(db.String(20), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='Approved') # Pending, Approved, Rejected

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institute_code = db.Column(db.String(20), nullable=False)
    user_type = db.Column(db.String(20), nullable=False) # 'admin' or 'teacher'
    user_id = db.Column(db.String(50), nullable=True) # teacher_id, or None for admin
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class GenerationHistory(db.Model):
    __tablename__ = 'generation_history'
    id = db.Column(db.Integer, primary_key=True)
    institute_id = db.Column(db.Integer, db.ForeignKey("institute.id", ondelete="CASCADE"), nullable=False)
    institute_code = db.Column(db.String(20), nullable=False) # Kept as legacy/user-facing identifier
    status = db.Column(db.String(20), nullable=False) # SUCCESS, FAILED
    sessions_count = db.Column(db.Integer, nullable=False, default=0)
    generation_time = db.Column(db.Float, nullable=True)
    optimization_time = db.Column(db.Float, nullable=True)
    gap_score = db.Column(db.Integer, nullable=True)
    primary_failure_reason = db.Column(db.String(255), nullable=True)
    diagnostics_json = db.Column(db.Text, nullable=True) # Optional JSON payload for detailed UI if needed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

