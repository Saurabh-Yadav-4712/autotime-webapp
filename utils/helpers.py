import hashlib
import hmac
import logging
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import secrets
import time
from flask import current_app, session
import string
from datetime import datetime, timedelta, date
try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo
from models import Settings

def get_local_now() -> datetime:
    tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    return datetime.now(tz)

def get_local_date() -> date:
    return get_local_now().date()

class ScheduleConfig:
    def __init__(self, inst_code: str):
        settings = Settings.query.filter_by(institute_code=inst_code).all()
        s = {st.key: st.value for st in settings}
        self.working_days = [d.strip() for d in s.get("working_days", "Mon,Tue,Wed,Thu,Fri,Sat").split(",") if d.strip()]
        if not self.working_days:
            self.working_days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

        self.total_lectures = int(s.get("total_lectures", 4))
        self.start_time_str = s.get("start_time", "08:00")
        self.lec_duration = int(s.get("lecture_duration", 45))
        self.break_duration = int(s.get("break_time", 30))
        self.lunch_after = int(s.get("lunch_after_lecture", 2))
        self.weeks_per_semester = int(s.get("weeks_per_semester", 15))

    def get_dynamic_time_slots(self):
        time_slots = []
        current_time = datetime.strptime(self.start_time_str, "%H:%M")

        for i in range(1, self.total_lectures + 1):
            end_time = current_time + timedelta(minutes=self.lec_duration)
            start_str = current_time.strftime("%I:%M %p")
            end_str = end_time.strftime("%I:%M %p")
            time_slots.append((start_str, end_str))

            current_time = end_time
            if i == self.lunch_after:
                current_time = current_time + timedelta(minutes=self.break_duration)
        return time_slots

logger = logging.getLogger(__name__)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def generate_institute_code(prefix="INS"):
    chars = string.ascii_uppercase + string.digits
    return f"{prefix}-{''.join(secrets.choice(chars) for _ in range(8))}"


def normalize_email(value):
    return (value or "").strip().lower()


def is_valid_email(value):
    return bool(value and len(value) <= 254 and EMAIL_PATTERN.fullmatch(value))


def validate_password(value):
    if len(value or "") < 8:
        return False, "Password must contain at least 8 characters."
    if len(value) > 128:
        return False, "Password must contain at most 128 characters."
    return True, None


def _otp_digest(purpose, otp):
    secret = current_app.config["SECRET_KEY"].encode("utf-8")
    payload = f"{purpose}:{otp}".encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def generate_and_store_otp(purpose):
    otp = "".join(str(secrets.randbelow(10)) for _ in range(6))
    session[f"{purpose}_otp"] = _otp_digest(purpose, otp)
    session[f"{purpose}_otp_time"] = time.time()
    session[f"{purpose}_otp_attempts"] = 0
    return otp


def verify_session_otp(purpose, user_otp):
    otp_key = f"{purpose}_otp"
    time_key = f"{purpose}_otp_time"
    attempts_key = f"{purpose}_otp_attempts"

    if otp_key not in session or time_key not in session:
        return False, "No OTP session found. Please request a new OTP."

    session[attempts_key] = session.get(attempts_key, 0) + 1
    if session[attempts_key] > 3:
        clear_session_otp(purpose)
        return False, "Maximum attempts exceeded. Please request a new OTP."

    current_time = time.time()
    if current_time - session[time_key] > 300:
        clear_session_otp(purpose)
        return False, "OTP has expired. Please request a new one."

    supplied_digest = _otp_digest(purpose, str(user_otp))
    if not hmac.compare_digest(supplied_digest, session[otp_key]):
        return False, "Invalid OTP."

    clear_session_otp(purpose)
    return True, "OTP verified successfully."


def clear_session_otp(purpose):
    session.pop(f"{purpose}_otp", None)
    session.pop(f"{purpose}_otp_time", None)
    session.pop(f"{purpose}_otp_attempts", None)


def send_otp_email(to_email, otp, context="Authentication"):
    sender_email = os.environ.get("SMTP_EMAIL")
    sender_password = os.environ.get("SMTP_PASSWORD")

    if not sender_email or not sender_password:
        logger.warning("SMTP is not configured; verification email was not sent")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your AutoTime verification code"
    msg["From"] = f"AutoTime <{sender_email}>"
    msg["To"] = to_email

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

    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        return True
    except Exception:
        logger.exception("Failed to send OTP email")
        return False


def get_dynamic_time_slots(inst_code):
    return ScheduleConfig(inst_code).get_dynamic_time_slots()


def trim_time_slots(schedule, time_slots, lunch_after):
    max_slot_index = -1
    slot_indices = {slot[0]: index for index, slot in enumerate(time_slots)}
    for slots in schedule.values():
        for start_time in slots:
            if start_time in slot_indices:
                max_slot_index = max(max_slot_index, slot_indices[start_time])

    if max_slot_index != -1:
        # Keep at least up to lunch_after so break UI doesn't crash
        cutoff = max(max_slot_index + 1, lunch_after)
        return time_slots[:cutoff]
    return time_slots


def get_val(r, *keys):
    for k in keys:
        if k in r and r[k] is not None and str(r[k]).strip() != "":
            return str(r[k]).strip()
    for k in keys:
        target = str(k).lower().replace(" ", "").replace("_", "").replace("/", "")
        for rk in r.keys():
            if rk is not None:
                if str(rk).lower().replace(" ", "").replace("_", "").replace("/", "") == target:
                    if r[rk] is not None and str(r[rk]).strip() != "":
                        return str(r[rk]).strip()
    return ""
