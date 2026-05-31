from datetime import datetime, timedelta
import secrets
from flask import Flask, request, jsonify, redirect, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
import pandas as pd
import json
import random
import string
import os
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mysecretkey123')
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'sandbox.smtp.mailtrap.io')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 2525))
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_FROM'] = os.environ.get('MAIL_FROM', 'noreply@sellerai.com')

basedir = os.path.abspath(os.path.dirname(__file__))
os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)
database_url = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'instance', 'seller_dashboard.db'))
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
mail = Mail(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=False)
    password = db.Column(db.String(500), nullable=False)
    catalog_path = db.Column(db.String(500), nullable=True)
    catalog_data = db.Column(db.Text, nullable=True)
    is_verified = db.Column(db.Boolean, default=False)
    verify_token = db.Column(db.String(200), nullable=True)
    reset_token = db.Column(db.String(200), nullable=True)
    reset_expiry = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    title = db.Column(db.String(500))
    description = db.Column(db.Text)
    category = db.Column(db.String(200))
    image = db.Column(db.Text)
    price = db.Column(db.Float)
    stock = db.Column(db.Integer)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def process_image_url