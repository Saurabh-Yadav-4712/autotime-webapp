from functools import wraps
from flask import session, redirect, url_for, flash


def login_required_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "admin_id" not in session:
            flash("Please login to access this page.", "warning")
            return redirect(url_for("main.login_page"))
        return f(*args, **kwargs)

    return decorated_function


def login_required_teacher(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "teacher_id" not in session:
            flash("Please login as a teacher to access this page.", "warning")
            return redirect(url_for("main.login_page"))
        return f(*args, **kwargs)

    return decorated_function


def login_required_student(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "student_id" not in session:
            flash("Please login as a student to access this page.", "warning")
            return redirect(url_for("main.login_page"))
        return f(*args, **kwargs)

    return decorated_function
