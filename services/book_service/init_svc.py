import os
import logging
import datetime
import uuid
import threading

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

user_collection = mongo.db.users

book_collection = mongo.db.books
book_collection.create_index('guid', unique=True)

# TODO: use Atlas Search
book_collection.create_index([('title', 'text'), ('author', 'text'),('genre', 'text')],
                             weights={'title': 10, 'author': 4, 'genre': 2})

BOOK_SERVICE_URL = 'localhost:5002'

class BookModel(BaseModel):
    title: str
    author: str
    genre: str
    description: str
    img_url: str
    reserved: bool
    available: bool


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


def notify_book_added(new_book: dict):
    logging.info('sending notification email')

    # fetch users where `likes` matches new book's `genre`
    user_list = list(
        user_collection.find({'likes': new_book.get('genre')})
    )
    logging.info(f'notifying {len(user_list)} users')
    with (app.app_context(), mail.connect() as conn):
        try:
            for user in user_list:
                msg = Message(
                    subject='New Book Added',
                    recipients=[user.get('email')]        
                )
                msg.body = f'Hello {user.get('name')},\nNew book: {new_book.get('title')}.\nLink: {BOOK_SERVICE_URL}/books/{new_book.get('guid')}'
                conn.send(msg)
        except ConnectionRefusedError:
            raise InternalServerError(f'{app.config['MAIL SERVER']} not working')

    return
