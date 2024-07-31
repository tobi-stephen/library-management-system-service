import os
import logging
import datetime
import uuid

from functools import wraps

from flask import Flask, jsonify, request, g, Response
from werkzeug.exceptions import InternalServerError

from flask_jwt_extended import (
    JWTManager,
    jwt_required,
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

book_collection = mongo.db.books
book_collection.create_index('guid', unique=True)

history_collection = mongo.db.borrow_history
history_collection.create_index('guid', unique=True)

reservation_collection = mongo.db.reservations
reservation_collection.create_index('guid', unique=True)

LATE_FEE = 5

class UserBookModel(BaseModel):
    user_guid: str
    book_guid: str


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


@app.errorhandler(404)
def notfound(e):
    return jsonify({'message': 'page not found'}), 404


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