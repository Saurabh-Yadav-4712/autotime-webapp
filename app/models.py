from app.extensions import db
from datetime import datetime

# ==========================================
# DATABASE MODELS
# ==========================================
class Institute(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    institute_code = db.Column(db.String(20), unique=True, nullable=False)
    admin_username = db.Column(db.String(50), unique=True, nullable=False)
    admin_email = db.Column(db.String(100), unique=True, nullable=False)
    admin_password = db.Column(db.String(255), nullable=False)

class Teacher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
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
    institute_code = db.Column(db.String(20), nullable=False)
    class_id = db.Column(db.String(50), nullable=False)
    department = db.Column(db.String(50), nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    division = db.Column(db.String(10), nullable=False)

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institute_code = db.Column(db.String(20), nullable=False)
    subject_code = db.Column(db.String(20), nullable=False)
    subject_name = db.Column(db.String(100), nullable=False)
    class_id = db.Column(db.String(100), nullable=False)
    teacher_id = db.Column(db.String(20), nullable=False)
    total_course_hours = db.Column(db.Integer, nullable=False, default=50)
    required_hours = db.Column(db.Integer, nullable=False)
    subject_type = db.Column(db.String(50), default='Theory')
    session_length = db.Column(db.Integer, default=1)
    preferred_days = db.Column(db.String(100), default="")

class Timetable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institute_code = db.Column(db.String(20), nullable=False)
    class_id = db.Column(db.String(50), nullable=False)
    day_name = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.String(20), nullable=False)
    end_time = db.Column(db.String(20), nullable=False)
    subject_name = db.Column(db.String(100), nullable=False)
    teacher_name = db.Column(db.String(100), nullable=False)
    is_proxy = db.Column(db.Boolean, default=False)
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

