import os
import logging
import datetime
import uuid
import threading

from flask import Flask, jsonify, request, g, Response
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.exceptions import InternalServerError

from flask_jwt_extended import (
    JWTManager, 
    create_access_token, 
    create_refresh_token,
    get_jwt_identity, 
    jwt_required, 
)

from flask_mail import Mail, Message

from flask_pymongo import PyMongo
import pymongo

import jwt
from pydantic import BaseModel, ValidationError

logging.basicConfig(level=logging.INFO)


app = Flask(__name__)

app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER') or 'localhost'
app.config['MAIL_PORT'] = os.getenv('MAIL_PORT') or 1025
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER') or ('Laplace', 'laplace@lms.com')
mail = Mail(app)

app.config['MONGO_URI'] = os.getenv('MONGO_URI') or 'mongodb://localhost:27017/library_system'
mongo = PyMongo(app)

app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY') or 'secret_authentication_key'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = datetime.timedelta(days=1)
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = datetime.timedelta(days=30)
jwtManager = JWTManager(app)

ACTIVATION_SECRET_KEY = os.getenv('ACTIVATION_SECRET_KEY') or 'secret_activation_key'
ACTIVATION_JWT_ALGO = 'HS256'
ACTIVATION_BASE_URL = 'http://localhost:5000/activate'

RESET_SECRET_KEY = os.getenv('ACTIVATION_SECRET_KEY') or 'secret_reset_key'
RESET_JWT_ALGO = 'HS256'
RESET_BASE_URL = 'http://localhost:5000/reset_password'

user_collection = mongo.db.users
user_collection.create_index('guid', unique=True)
user_collection.create_index('email', unique=True)
user_collection.create_index('phone_number', unique=True)


class UserSignup(BaseModel):
    name: str
    email: str
    password: str
    phone_number: str


class ProfileUpdate(BaseModel):
    name: str
    email: str
    phone_number: str
    address: str
    profile_img: str
    likes: list
    new_book_notification: bool


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


def send_activation_mail(user: dict):
    logging.info('sending activation email')
    payload = {
        'email': user.get('email'), 
        'exp': datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(minutes=2)
    }

    encoded_activation = jwt.encode(payload, ACTIVATION_SECRET_KEY)
    activation_link = f'{ACTIVATION_BASE_URL}/{encoded_activation}'

    with app.app_context():
        try:
            msg = Message(
                subject='Welcome to LMS',
                recipients=[user.get('email')]        
            )
            msg.body = f'Hello {user.get('name')},\nActivate your account here: {activation_link}'
            mail.send(msg)
        except ConnectionRefusedError:
            raise InternalServerError(f'{app.config['MAIL SERVER']} not working')

    return


def send_reset_mail(user: dict):
    logging.info('sending reset email')
    payload = {
        'email': user.get('email'), 
        'exp': datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(minutes=2)
    }

    encoded_reset_payload = jwt.encode(payload, RESET_SECRET_KEY)
    reset_link = f'{RESET_BASE_URL}/{encoded_reset_payload}'

    with app.app_context():
        try:
            msg = Message(
                subject='Reset LMS Password',
                recipients=[user.get('email')]        
            )
            msg.body = f'Hello {user.get('name')},\nReset your account password here: {reset_link}'
            mail.send(msg)
        except ConnectionRefusedError:
            raise InternalServerError(f'{app.config['MAIL SERVER']} not working')

    return


def reset_completed_mail(user: dict):
    logging.info('sending reset completed email')
    with app.app_context():
        try:
            msg = Message(
                subject='LMS password reset complete',
                recipients=[user.get('email')]        
            )
            msg.body = f'Hello {user.get('name')},\nPassword reset complete'
            mail.send(msg)
        except ConnectionRefusedError:
            raise InternalServerError(f'{app.config['MAIL SERVER']} not working')

    return