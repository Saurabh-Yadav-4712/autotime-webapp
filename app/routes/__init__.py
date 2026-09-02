from flask import Blueprint
main_bp = Blueprint('main', __name__)

from . import auth_routes, admin_routes, teacher_routes, student_routes
