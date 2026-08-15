import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import secrets
from flask import session
import random
import string
from datetime import datetime, timedelta

def generate_institute_code(prefix="INS"):
    chars = string.ascii_uppercase + string.digits
    return f"{prefix}-{''.join(random.choices(chars, k=5))}"

def generate_and_store_otp(purpose):
    otp = "".join([str(secrets.randbelow(10)) for _ in range(6)])
    session[f'{purpose}_otp'] = otp
    session[f'{purpose}_otp_time'] = datetime.now().timestamp()
    session[f'{purpose}_otp_attempts'] = 0
    return otp

def verify_session_otp(purpose, user_otp):
    otp_key = f'{purpose}_otp'
    time_key = f'{purpose}_otp_time'
    attempts_key = f'{purpose}_otp_attempts'
    
    if otp_key not in session:
        return False, 'No OTP session found. Please request a new OTP.'
        
    session[attempts_key] += 1
    if session[attempts_key] > 3:
        clear_session_otp(purpose)
        return False, 'Maximum attempts exceeded. Please request a new OTP.'
        
    current_time = datetime.now().timestamp()
    if current_time - session[time_key] > 300:
        clear_session_otp(purpose)
        return False, 'OTP has expired. Please request a new one.'
        
    if str(user_otp) != str(session[otp_key]):
        return False, 'Invalid OTP.'
        
    clear_session_otp(purpose)
    return True, 'OTP verified successfully.'

def clear_session_otp(purpose):
    session.pop(f'{purpose}_otp', None)
    session.pop(f'{purpose}_otp_time', None)
    session.pop(f'{purpose}_otp_attempts', None)

def send_otp_email(to_email, otp, context="Authentication"):
    sender_email = os.environ.get("SMTP_EMAIL")
    sender_password = os.environ.get("SMTP_PASSWORD")

    if not sender_email or not sender_password:
        print(f"[DEV MODE] SMTP not configured. OTP for {to_email} is {otp}")
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"Your AutoTime Verification Code: {otp}"
    msg['From'] = f"AutoTime <{sender_email}>"
    msg['To'] = to_email

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
        <div style="max-width: 500px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
          <h2 style="color: #0d6efd; text-align: center; margin-bottom: 20px;">AutoTime</h2>
          <p style="font-size: 16px; color: #333;">Hello,</p>
          <p style="font-size: 16px; color: #333;">You have requested a verification code for <strong>{context}</strong>.</p>
          <div style="background-color: #f8f9fa; border-left: 4px solid #0d6efd; padding: 15px; margin: 20px 0; text-align: center;">
            <span style="font-size: 24px; font-weight: bold; letter-spacing: 5px; color: #0d6efd;">{otp}</span>
          </div>
          <p style="font-size: 14px; color: #666; margin-top: 20px;">This code will expire in 5 minutes. Do not share this code with anyone.</p>
          <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
          <p style="font-size: 12px; color: #999; text-align: center;">&copy; 2026 AutoTime. All rights reserved.</p>
        </div>
      </body>
    </html>
    """
    
    msg.attach(MIMEText(html, 'html'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        print(f"[DEV MODE fallback] OTP for {to_email} is {otp}")
        return False


def get_dynamic_time_slots(inst_code):
    # Get settings from DB
    settings = Settings.query.filter_by(institute_code=inst_code).all()
    s = {st.key: st.value for st in settings}
    
    # Fallback default values (agar admin ne settings save nahi ki)
    total_lectures = int(s.get('total_lectures', 4))
    start_time_str = s.get('start_time', '08:00')
    lec_duration = int(s.get('lecture_duration', 45))
    break_duration = int(s.get('break_time', 30))
    lunch_after = int(s.get('lunch_after_lecture', 2))

    time_slots = []
    # Convert string to datetime object for calculation
    current_time = datetime.strptime(start_time_str, '%H:%M')

    for i in range(1, total_lectures + 1):
        end_time = current_time + timedelta(minutes=lec_duration)
        
        # Format time to "08:00 AM" style
        start_str = current_time.strftime('%I:%M %p')
        end_str = end_time.strftime('%I:%M %p')
        
        time_slots.append((start_str, end_str))
        
        current_time = end_time
        
        # Add Lunch Break duration after the specified lecture
        if i == lunch_after:
            current_time = current_time + timedelta(minutes=break_duration)
            
    return time_slots

def trim_time_slots(schedule, time_slots, lunch_after):
    max_slot_index = -1
    for day, slots in schedule.items():
        for i, slot in enumerate(time_slots):
            if slot[0] in slots:
                max_slot_index = max(max_slot_index, i)
    
    if max_slot_index != -1:
        # Keep at least up to lunch_after so break UI doesn't crash
        cutoff = max(max_slot_index + 1, lunch_after)
        return time_slots[:cutoff]
    return time_slots

def get_val(r, *keys):
    for k in keys:
        if k in r and r[k] is not None and str(r[k]).strip() != '': return str(r[k]).strip()
    for k in keys:
        target = str(k).lower().replace(' ', '').replace('_', '').replace('/', '')
        for rk in r.keys():
            if rk is not None:
                if str(rk).lower().replace(' ', '').replace('_', '').replace('/', '') == target:
                    if r[rk] is not None and str(r[rk]).strip() != '':
                        return str(r[rk]).strip()
    return ''