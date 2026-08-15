from flask import current_app
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from models import db
from models import *
from utils.helpers import *
import json
import random
import os
import io
import csv
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from io import BytesIO
from datetime import datetime, timedelta
import string

from routes.blueprint import main_bp
from utils.helpers import get_dynamic_time_slots, trim_time_slots, get_val

@main_bp.route('/student_portal')
def student_portal():
    inst_code = request.args.get('inst_code')
    class_id = request.args.get('class_id')
    
    schedule = {}
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    time_slots = []
    lunch_after = 2
    
    if inst_code and class_id:
        # Check if institute exists
        institute = Institute.query.filter_by(institute_code=inst_code).first()
        if not institute:
            flash('Invalid Institute Code!', 'danger')
            return redirect(url_for('main.student_portal'))
            
        time_slots = get_dynamic_time_slots(inst_code)
        settings = Settings.query.filter_by(institute_code=inst_code).all()
        s = {st.key: st.value for st in settings}
        lunch_after = int(s.get('lunch_after_lecture', 2))
        
        entries = Timetable.query.filter_by(institute_code=inst_code, class_id=class_id).all()
        for day in days:
            schedule[day] = {}
            for entry in entries:
                if entry.day_name == day:
                    schedule[day][entry.start_time] = entry
                    
        time_slots = trim_time_slots(schedule, time_slots, lunch_after)

    return render_template('student/student_portal.html', schedule=schedule, days=days, time_slots=time_slots, lunch_after=lunch_after, inst_code=inst_code, class_id=class_id)

@main_bp.route('/register_student', methods=['GET', 'POST'])
def register_student():
    if request.method == 'POST':
        inst_code = request.form['inst_code'].strip()
        name = request.form['name'].strip()
        email = request.form['email'].strip()
        password = request.form['password'].strip()
        class_id = request.form.get('class_id', '').strip()

        # Institute check
        institute = Institute.query.filter_by(institute_code=inst_code).first()
        if not institute:
            flash('Invalid Institute Code!', 'danger')
            return redirect(url_for('main.register_student'))
            
        # Class check
        course = Course.query.filter_by(institute_code=inst_code, class_id=class_id).first()
        if not course:
            flash(f'Invalid Class ID for Institute {inst_code}!', 'danger')
            return redirect(url_for('main.register_student'))

        # Email check
        if Student.query.filter_by(email=email).first():
            flash('Email already registered! Please login.', 'warning')
            return redirect(url_for('main.login_page'))

        # Generate OTP and store in session
        otp = generate_and_store_otp('reg')
        session['reg_data'] = {
            'type': 'student',
            'inst_code': inst_code,
            'name': name,
            'email': email,
            'class_id': class_id,
            'password': password
        }
        session['reg_otp'] = otp
        
        email_sent = send_otp_email(email, otp, context="Student Registration")
        if not email_sent:
            flash('Failed to send OTP email. Please try again later or contact support.', 'warning')
        else:
            flash('An OTP has been sent to your email for verification.', 'info')
        return redirect(url_for('main.verify_reg_otp'))

    return render_template('auth/register_student.html')

@main_bp.route('/login_student', methods=['GET', 'POST'])
def login_student():
    if request.method == 'GET':
        return redirect(url_for('main.login_page'))
        
    student = Student.query.filter_by(email=request.form['email']).first()
    if student and check_password_hash(student.password, request.form['password']):
        session['student_id'] = student.id
        session['institute_code'] = student.institute_code
        session['student_name'] = student.name
        session['student_class'] = student.class_id
        flash(f'Welcome to your Live Timetable, {student.name}!', 'success')
        return redirect(url_for('main.student_dash'))
    
    flash('Invalid Email or Password!', 'danger')
    return redirect(url_for('main.login_page'))

@main_bp.route('/student_dash')
def student_dash():
    if 'student_id' not in session: return redirect(url_for('main.login_page'))
    inst_code = session['institute_code']
    class_id = session['student_class']
    s_name = session['student_name']
    
    time_slots = get_dynamic_time_slots(inst_code)
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    settings = Settings.query.filter_by(institute_code=inst_code).all()
    s = {st.key: st.value for st in settings}
    lunch_after = int(s.get('lunch_after_lecture', 2))
    
    schedule = {day: {} for day in days}
    entries = Timetable.query.filter_by(institute_code=inst_code, class_id=class_id).all()
    
    for entry in entries:
        schedule[entry.day_name][entry.start_time] = entry

    inst = Institute.query.filter_by(institute_code=inst_code).first()
    
    flash('Password successfully reset! Please login.', 'success')
    return redirect(url_for('main.login_page'))