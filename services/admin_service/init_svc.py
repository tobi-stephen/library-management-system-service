import os
import logging
import datetime
import threading

from functools import wraps

from flask import Flask, jsonify, request, g, Response
from werkzeug.security import generate_password_hash
from werkzeug.exceptions import InternalServerError

from flask_jwt_extended import (
    JWTManager,
    get_jwt_identity, 
    get_jwt,
    verify_jwt_in_request
)

from flask_mail import Mail, Message

from flask_pymongo import PyMongo
import pymongo

from pydantic import BaseModel, ValidationError

logging.basicConfig(level=logging.INFO)


app = Flask(__name__)

app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER') or 'localhost'
app.config['MAIL_PORT'] = os.getenv('MAIL_PORT') or 1025
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER') or ('Laplace', 'laplace@lms.com')
mail = Mail(app)

app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY') or 'secret_authentication_key'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = datetime.timedelta(days=1)
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = datetime.timedelta(days=30)
jwtManager = JWTManager(app)

app.config['MONGO_URI'] = os.getenv('MONGO_URI') or 'mongodb://localhost:27017/library_system'
mongo = PyMongo(app)

user_collection = mongo.db.users
user_collection.create_index('guid', unique=True)
user_collection.create_index('email', unique=True)
user_collection.create_index('phone_number', unique=True)
user_collection.create_index([('name', 'text'), ('email', 'text'),('phone_number', 'text')],
                             weights={'name': 10, 'email': 7, 'phone_number': 2})

# creating/updating `super` admin profile
admin_guid = '9b6550a8-1c89-4ff9-9dd6-c20a6abee26e'
admin_pass = os.getenv('ADMIN_PASS') or 'admin_pass'
user_collection.update_one(
    {'guid': admin_guid},
    {'$set': {
        'guid': admin_guid,
        'name': 'Laplace Zen',
        'email': 'laplace@lms.com',
        'password': generate_password_hash(admin_pass),
        'phone_number': '12345678',
        'role': 'admin',
        'activated': True
    }}, upsert=True)


class UserUpdate(BaseModel):
    activated: bool
    address: str
    email: str
    likes: list
    phone_number: str
    name: str
    profile_img: str
    role: str
    new_book_notification: bool


def admin_required():
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            if claims['role'] == 'admin':
                return fn(*args, **kwargs)
            else:
                return jsonify(msg='Admins only!'), 403

        return decorator

    return wrapper


@app.errorhandler(Exception)
def errorhandler(e: Exception):
    logging.error(e)
    return jsonify({'message': 'server error'}), 500


@app.before_request
def before_request():
    g.request_start = datetime.datetime.now()


@app.after_request
def after_request(response: Response):
    request_time: datetime.timedelta = datetime.datetime.now() - g.request_start
    logging.info(f'time taken for `{request.path}` is {request_time.total_seconds()} seconds')

    return response


def send_profile_update_mail(user: dict):
    logging.info('sending profile update email')
    with app.app_context():
        try:
            msg = Message(
                subject='LMS profile updated',
                recipients=[user.get('email')]        
            )
            msg.body = f'Hello {user.get('name')},\nAn update has been made to your profile on LMS'
            mail.send(msg)
        except ConnectionRefusedError:
            raise InternalServerError(f'{app.config['MAIL SERVER']} not working')

    return