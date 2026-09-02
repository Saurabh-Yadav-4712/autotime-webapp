from flask import current_app
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import db
from app.models import *
from app.utils import *
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

from app.routes import main_bp
from app.utils import get_dynamic_time_slots, trim_time_slots, get_val

@main_bp.route('/')
def home():
    return render_template('main_site/landing.html')

@main_bp.route('/login')
def login_page():
    return render_template('auth/auth.html')

@main_bp.route('/register_institute', methods=['GET', 'POST'])
def register_institute():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        college_name = request.form['college_name'].strip()
        password = request.form['password']

        if Institute.query.filter_by(admin_username=username).first():
            flash('Username already exists.', 'danger')
            return redirect(url_for('main.register_institute'))
        if Institute.query.filter_by(admin_email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('main.register_institute'))
        
        # Save temp data and send OTP
        otp = generate_and_store_otp('reg')
        session['reg_data'] = {
            'type': 'institute',
            'college_name': college_name,
            'username': username,
            'email': email,
            'password': password
        }
        
        email_sent = send_otp_email(email, otp, context="Institute Registration")
        if not email_sent:
            flash('Failed to send OTP email. Please try again later or contact support.', 'warning')
        else:
            flash('An OTP has been sent to your email for verification.', 'info')
        return redirect(url_for('main.verify_reg_otp'))
    return render_template('auth/register_institute.html')

@main_bp.route('/verify_reg_otp', methods=['GET', 'POST'])
def verify_reg_otp():
    if 'reg_data' not in session or 'reg_otp' not in session:
        flash('Session expired. Please register again.', 'danger')
        return redirect(url_for('main.login_page'))
        
    if request.method == 'POST':
        user_otp = request.form['otp'].strip()
        is_valid, msg = verify_session_otp('reg', user_otp)
        
        if is_valid:
            data = session['reg_data']
            
            if data['type'] == 'institute':
                inst_code = generate_institute_code()
                new_institute = Institute(
                    name=data['college_name'],
                    institute_code=inst_code,
                    admin_username=data['username'],
                    admin_email=data['email'],
                    admin_password=generate_password_hash(data['password'])
                )
                db.session.add(new_institute)
                db.session.commit()
                
                # Clear session
                session.pop('reg_data', None)
                
                flash(f'College Registered Successfully! Your Institute Code is: {inst_code}', 'success')
                return redirect(url_for('main.login_page'))
                
            elif data['type'] == 'student':
                new_student = Student(
                    institute_code=data['inst_code'],
                    name=data['name'],
                    email=data['email'],
                    class_id=data['class_id'],
                    password=generate_password_hash(data['password'])
                )
                db.session.add(new_student)
                db.session.commit()
                
                session.pop('reg_data', None)
                
                flash('Student Registered Successfully! You can now login.', 'success')
                return redirect(url_for('main.login_page'))
                
        else:
            flash(msg, 'danger')
            return redirect(url_for('main.verify_reg_otp'))
            
    return render_template('shared/verify_otp.html', title='Verify Registration', submit_url='/verify_reg_otp')

@main_bp.route('/login_admin', methods=['GET', 'POST'])
def login_admin():
    if request.method == 'GET':
        return redirect(url_for('main.login_page'))
        
    admin = Institute.query.filter_by(admin_username=request.form['username']).first()
    if admin and check_password_hash(admin.admin_password, request.form['password']):
        session['admin_id'] = admin.id
        session['institute_code'] = admin.institute_code
        flash(f'Welcome back, {admin.name}!', 'success')
        return redirect(url_for('main.admin_dash'))
    flash('Invalid Credentials!', 'danger')
    return redirect(url_for('main.login_page'))

@main_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.login_page'))

@main_bp.route('/settings')
def settings():
    if 'admin_id' not in session and 'teacher_id' not in session and 'student_id' not in session:
        flash('Please login to access settings.', 'danger')
        return redirect(url_for('main.login_page'))
        
    user_role = ""
    user_info = {}
    
    if 'admin_id' in session:
        user_role = "admin"
        inst = Institute.query.get(session['admin_id'])
        user_info = {'name': inst.name, 'email': inst.admin_email, 'institute_code': inst.institute_code}
    elif 'teacher_id' in session:
        user_role = "teacher"
        t = Teacher.query.filter_by(teacher_id=session['teacher_id']).first()
        user_info = {'name': t.name, 'email': t.email, 'institute_code': t.institute_code}
    elif 'student_id' in session:
        user_role = "student"
        s = Student.query.get(session['student_id'])
        user_info = {'name': s.name, 'email': s.email, 'institute_code': s.institute_code}

    return render_template('shared/settings.html', user_role=user_role, user_info=user_info)

@main_bp.route('/settings/update_profile', methods=['POST'])
def update_profile():
    if 'admin_id' not in session and 'teacher_id' not in session and 'student_id' not in session:
        return redirect(url_for('main.login_page'))
    
    new_name = request.form.get('name', '').strip()
    new_email = request.form.get('email', '').strip()
    
    if not new_name or not new_email:
        flash('Name and Email cannot be empty.', 'danger')
        return redirect(url_for('main.settings'))

    user = None
    role = None
    current_email = None

    if 'admin_id' in session:
        role = 'admin'
        user = Institute.query.get(session['admin_id'])
        current_email = user.admin_email
        new_code = request.form.get('institute_code', '').strip().upper()
        if new_code and new_code != user.institute_code:
            if Institute.query.filter_by(institute_code=new_code).first():
                flash('Institute Code already taken by another institute.', 'danger')
                return redirect(url_for('main.settings'))
            
            # Cascade update to related tables
            old_code = user.institute_code
            Teacher.query.filter_by(institute_code=old_code).update({"institute_code": new_code})
            Student.query.filter_by(institute_code=old_code).update({"institute_code": new_code})
            Course.query.filter_by(institute_code=old_code).update({"institute_code": new_code})
            Timetable.query.filter_by(institute_code=old_code).update({"institute_code": new_code})
            # Also subjects are tied to course_id, which is fine, but they don't have institute_code directly.
            user.institute_code = new_code
            db.session.commit()
            
    elif 'teacher_id' in session:
        role = 'teacher'
        user = Teacher.query.filter_by(teacher_id=session['teacher_id']).first()
        current_email = user.email
    elif 'student_id' in session:
        role = 'student'
        user = Student.query.get(session['student_id'])
        current_email = user.email

    if user:
        user.name = new_name
        db.session.commit()

    # If email changed, trigger OTP flow
    if new_email != current_email:
        # Check uniqueness across models
        if Institute.query.filter_by(admin_email=new_email).first() or \
           Teacher.query.filter_by(email=new_email).first() or \
           Student.query.filter_by(email=new_email).first():
            flash('This email is already in use.', 'danger')
            return redirect(url_for('main.settings'))
            
        otp = generate_and_store_otp('email_update')
        if send_otp_email(new_email, otp, context="Email Update"):
            session['pending_email'] = new_email
            session['email_update_role'] = role
            return redirect(url_for('main.verify_email_update'))
        else:
            flash('Failed to send verification email. Please try again.', 'danger')
            return redirect(url_for('main.settings'))

    flash('Profile updated successfully!', 'success')
    return redirect(url_for('main.settings'))

@main_bp.route('/verify_email_update', methods=['GET', 'POST'])
def verify_email_update():
    if 'pending_email' not in session or 'email_update_otp' not in session:
        flash('No pending email update found.', 'warning')
        return redirect(url_for('main.settings'))
        
    if request.method == 'POST':
        user_otp = request.form.get('otp', '').strip()
        is_valid, msg = verify_session_otp('email_update', user_otp)
        if is_valid:
            new_email = session['pending_email']
            role = session['email_update_role']
            
            if role == 'admin' and 'admin_id' in session:
                user = Institute.query.get(session['admin_id'])
                user.admin_email = new_email
            elif role == 'teacher' and 'teacher_id' in session:
                user = Teacher.query.filter_by(teacher_id=session['teacher_id']).first()
                user.email = new_email
            elif role == 'student' and 'student_id' in session:
                user = Student.query.get(session['student_id'])
                user.email = new_email
                
            db.session.commit()
            
            session.pop('pending_email', None)
            
            session.pop('email_update_role', None)
            
            flash('Email successfully updated!', 'success')
            return redirect(url_for('main.settings'))
        else:
            flash('Invalid OTP code.', 'danger')
            
    return render_template('shared/verify_otp.html', title='Verify Email Update', submit_url='/verify_email_update')

@main_bp.route('/settings/change_password', methods=['POST'])
def settings_change_password():
    if 'admin_id' not in session and 'teacher_id' not in session and 'student_id' not in session:
        return redirect(url_for('main.login_page'))
    
    old_pass = request.form['current_password']
    new_pass = request.form['new_password']
    
    if 'admin_id' in session:
        user = Institute.query.get(session['admin_id'])
        if check_password_hash(user.admin_password, old_pass):
            user.admin_password = generate_password_hash(new_pass)
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('main.settings'))
    elif 'teacher_id' in session:
        user = Teacher.query.filter_by(teacher_id=session['teacher_id']).first()
        if user and check_password_hash(user.password, old_pass):
            user.password = generate_password_hash(new_pass)
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('main.settings'))
    elif 'student_id' in session:
        user = Student.query.get(session['student_id'])
        if user and check_password_hash(user.password, old_pass):
            user.password = generate_password_hash(new_pass)
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('main.settings'))
            
    flash('Incorrect current password.', 'danger')
    return redirect(url_for('main.settings'))

@main_bp.route('/settings/delete_account')
def delete_account_page():
    if 'admin_id' not in session and 'teacher_id' not in session and 'student_id' not in session:
        return redirect(url_for('main.login_page'))
    return render_template('shared/delete_account.html')

@main_bp.route('/settings/delete_account/send_otp', methods=['POST'])
def delete_account_send_otp():
    if 'admin_id' not in session and 'teacher_id' not in session and 'student_id' not in session:
        return redirect(url_for('main.login_page'))
    
    password = request.form.get('password')
    is_valid = False
    email = None
    
    if 'admin_id' in session:
        user = Institute.query.get(session['admin_id'])
        email = user.admin_email
        is_valid = check_password_hash(user.admin_password, password)
    elif 'teacher_id' in session:
        user = Teacher.query.filter_by(teacher_id=session['teacher_id'], institute_code=session['institute_code']).first()
        email = user.email
        is_valid = check_password_hash(user.password, password) if user.password else False
    elif 'student_id' in session:
        user = Student.query.get(session['student_id'])
        email = user.email
        is_valid = check_password_hash(user.password, password)
        
    if not is_valid:
        flash('Incorrect current password.', 'danger')
        return redirect(url_for('main.delete_account_page'))
        
    otp = generate_and_store_otp('delete_account')
    if send_otp_email(email, otp, context="Account Deletion"):
        return redirect(url_for('main.verify_delete_account_page'))
    else:
        flash('Failed to send verification email. Please try again.', 'danger')
        return redirect(url_for('main.delete_account_page'))

@main_bp.route('/settings/delete_account/verify')
def verify_delete_account_page():
    if 'admin_id' not in session and 'teacher_id' not in session and 'student_id' not in session:
        return redirect(url_for('main.login_page'))
    if 'delete_account_otp' not in session:
        return redirect(url_for('main.delete_account_page'))
    return render_template('shared/verify_otp.html', title='Confirm Deletion', message='Enter the 6-digit OTP sent to your email to confirm deletion. This cannot be undone.', submit_url='/settings/delete_account/confirm', btn_text='Permanently Delete Account')

@main_bp.route('/settings/delete_account/confirm', methods=['POST'])
def delete_account_confirm():
    if 'admin_id' not in session and 'teacher_id' not in session and 'student_id' not in session:
        return redirect(url_for('main.login_page'))
    if 'delete_account_otp' not in session:
        return redirect(url_for('main.delete_account_page'))
        
    user_otp = request.form.get('otp', '').strip()
    is_valid, msg = verify_session_otp('delete_account', user_otp)
    if not is_valid:
        flash(msg, 'danger')
        return redirect(url_for('main.verify_delete_account_page'))
        
    # Process Deletion based on role
    if 'admin_id' in session:
        inst_code = session['institute_code']
        Institute.query.filter_by(institute_code=inst_code).delete()
        Teacher.query.filter_by(institute_code=inst_code).delete()
        Course.query.filter_by(institute_code=inst_code).delete()
        Subject.query.filter_by(institute_code=inst_code).delete()
        Timetable.query.filter_by(institute_code=inst_code).delete()
        Settings.query.filter_by(institute_code=inst_code).delete()
        Student.query.filter_by(institute_code=inst_code).delete()
        db.session.commit()
        flash('Institute and all associated data have been permanently deleted.', 'success')
        
    elif 'teacher_id' in session:
        user = Teacher.query.filter_by(teacher_id=session['teacher_id'], institute_code=session['institute_code']).first()
        if user:
            user.password = None
            db.session.commit()
            flash('Your account login has been deactivated. You can re-activate later.', 'success')
            
    elif 'student_id' in session:
        user = Student.query.get(session['student_id'])
        if user:
            db.session.delete(user)
            db.session.commit()
            flash('Your account has been permanently deleted.', 'success')
            
    session.clear()
    return redirect(url_for('main.landing'))