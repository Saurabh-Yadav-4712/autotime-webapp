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
    sender_email = os.environ.get("EMAIL_USER")
    sender_password = os.environ.get("EMAIL_PASS")

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
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        print(f"[DEV MODE fallback] OTP for {to_email} is {otp}")
        return False
