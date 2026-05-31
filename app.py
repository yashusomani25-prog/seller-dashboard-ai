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

# ====================== MODELS ======================
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

# ====================== IMAGE PROCESSOR ======================
def process_image_url(url):
    if not url:
        return "https://placehold.co/600x400?text=No+Image"
    url = str(url).strip()
    if not url or url.lower() in ["nan", "none", ""]:
        return "https://placehold.co/600x400?text=No+Image"

    if "drive.google.com" in url:
        try:
            match = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
            if match:
                return f"https://lh3.googleusercontent.com/d/{match.group(1)}=s1200"
            if "id=" in url:
                file_id = url.split("id=")[1].split("&")[0]
                return f"https://lh3.googleusercontent.com/d/{file_id}=s1200"
        except:
            pass
    return url

app.jinja_env.globals.update(process_image_url=process_image_url)

# ====================== DELETE ROUTE ======================
@app.route('/delete/<int:product_id>')
@login_required
def delete_product(product_id):
    product = Product.query.filter_by(id=product_id, user_id=current_user.id).first()
    if product:
        db.session.delete(product)
        db.session.commit()
    return redirect('/')

# ====================== MAIN DASHBOARD ======================
@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    # === Your upload logic (kept minimal - add your full logic here if needed) ===
    if request.method == 'POST':
        # Add your file upload logic here...
        pass

    products = Product.query.filter_by(user_id=current_user.id).all()
    cards = ""

    for p in products:
        image_url = process_image_url(p.image)
        short_desc = str(p.description or "")[:140] + "..." if len(str(p.description or "")) > 140 else str(p.description or "")

        cards += f"""
        <div class="card">
            <div class="category-badge">{p.category or 'General'}</div>
            <img src="{image_url}" class="product-image" 
                 onerror="this.src='https://placehold.co/600x400/f1f1f1/888?text=No+Image';">
            <div class="card-body">
                <h2 class="title">{p.title}</h2>
                <p class="price">Rs. {p.price}</p>
                <p class="description">{short_desc}</p>
                <p><b>Stock:</b> {p.stock}</p>
                
                <button class="view-btn" onclick="alert('View clicked - ID: {p.id}')">👁 View Product</button>
                <a href="/edit/{p.id}"><button class="blue">✏️ Edit</button></a>
                <button onclick="deleteProduct({p.id})" class="orange">🗑️ Delete</button>
            </div>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Seller Automation Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{ font-family: Arial, sans-serif; background: #f4f4f4; margin: 0; padding: 0; }}
            .header {{ background: white; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; }}
            .products {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
                gap: 24px;
                padding: 30px;
                justify-items: center;
                align-items: start;
            }}
            .card {{
                background: white;
                border-radius: 20px;
                overflow: hidden;
                box-shadow: 0 8px 20px rgba(0,0,0,0.1);
                width: 100%;
                max-width: 340px;
                transition: 0.3s;
            }}
            .card:hover {{ transform: translateY(-8px); }}
            .product-image {{
                width: 100%;
                height: 260px;
                object-fit: cover;
            }}
            .card-body {{ padding: 18px; }}
            .category-badge {{ background: #2563eb; color: white; padding: 5px 12px; border-radius: 20px; font-size: 12px; display: inline-block; margin: 10px; }}
            .title {{ font-size: 20px; margin: 10px 0; }}
            .orange {{ background: #ea580c; color: white; border: none; padding: 12px; width: 100%; margin-top: 8px; border-radius: 8px; cursor: pointer; font-weight: bold; }}
            .blue {{ background: #2563eb; color: white; border: none; padding: 12px; width: 100%; margin-top: 8px; border-radius: 8px; cursor: pointer; }}
            .view-btn {{ background: #111827; color: white; border: none; padding: 12px; width: 100%; border-radius: 8px; cursor: pointer; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🚀 Seller Automation Dashboard</h1>
            <p>Welcome, {current_user.username}</p>
        </div>

        <div class="products">
            {cards}
        </div>

        <script>
            function deleteProduct(id) {{
                if (confirm("Are you sure you want to delete this product?")) {{
                    window.location.href = "/delete/" + id;
                }}
            }}
        </script>
    </body>
    </html>
    """

# ====================== OTHER ROUTES (Add your login, register, etc. here) ======================
# ... Add your other routes if needed ...

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)