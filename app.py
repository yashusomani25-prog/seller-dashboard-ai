from datetime import datetime, timedelta
import secrets
from flask import Flask, request, send_file, jsonify, redirect, url_for, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user,
    login_required, logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
import pandas as pd
import io
import json
import random
import string
import os
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mysecretkey123')
app.config['MAIL_SERVER']   = os.environ.get('MAIL_SERVER', 'sandbox.smtp.mailtrap.io')
app.config['MAIL_PORT']     = int(os.environ.get('MAIL_PORT', 2525))
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_USE_TLS']  = True
app.config['MAIL_FROM']     = os.environ.get('MAIL_FROM', 'noreply@sellerai.com')
basedir = os.path.abspath(os.path.dirname(__file__))
os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)
database_url = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'instance', 'seller_dashboard.db'))
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db           = SQLAlchemy(app)
mail         = Mail(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login" 
uploaded_df = pd.DataFrame()


class User(UserMixin, db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    username     = db.Column(db.String(100), unique=True, nullable=False)
    email        = db.Column(db.String(200), unique=True, nullable=False)
    password     = db.Column(db.String(500), nullable=False)
    catalog_path = db.Column(db.String(500), nullable=True)
    catalog_data = db.Column(db.Text, nullable=True)
    is_verified  = db.Column(db.Boolean, default=False)
    verify_token = db.Column(db.String(200), nullable=True)
    reset_token  = db.Column(db.String(200), nullable=True)
    reset_expiry = db.Column(db.DateTime, nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)


class Product(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('user.id'))
    title       = db.Column(db.String(500))
    description = db.Column(db.Text)
    category    = db.Column(db.String(200))
    image       = db.Column(db.Text)
    price       = db.Column(db.Float)
    stock       = db.Column(db.Integer)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# =========================================================
# UNIVERSAL IMAGE URL PROCESSOR
# =========================================================
def process_image_url(url):
    if not url:
        return "https://placehold.co/600x400?text=No+Image"

    url = str(url).strip()

    if not url or url.lower() in ["nan", "none", ""]:
        return "https://placehold.co/600x400?text=No+Image"

    # Google Drive
    if "drive.google.com" in url:
        try:
            match = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
            if match:
                file_id = match.group(1)
                return f"https://lh3.googleusercontent.com/d/{file_id}=s1200"
            if "id=" in url:
                file_id = url.split("id=")[1].split("&")[0]
                return f"https://lh3.googleusercontent.com/d/{file_id}=s1200"
        except:
            return "https://placehold.co/600x400?text=Broken+Image"

    # Dropbox - convert to direct link
    if "dropbox.com" in url:
        return url.replace("www.dropbox.com", "dl.dropboxusercontent.com").replace("?dl=0", "?raw=1")

    # OneDrive - convert to direct link
    if "1drv.ms" in url or "onedrive.live.com" in url:
        return url

    # Daraz / Lazada CDN
    if "daraz" in url or "lazada" in url or "alicdn" in url:
        return url

    # Amazon product images
    if "amazon.com" in url or "amazonaws.com" in url or "ssl-images-amazon" in url:
        return url

    # Shopify CDN
    if "shopify.com" in url or "cdn.shopify" in url:
        return url

    # Direct image extensions
    if any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".svg"]):
        return url

    # Any valid http/https URL - try to use it directly
    if url.startswith("http://") or url.startswith("https://"):
        return url

    return "https://placehold.co/600x400?text=No+Image"

# Keep old name as alias for backward compatibility
def fix_google_drive_link(url):
    return process_image_url(url)

app.jinja_env.globals.update(process_image_url=process_image_url)


# =========================================================
# COLUMN FINDER
# =========================================================
def find_column(df, keywords):
    # Exact match first
    for col in df.columns:
        for keyword in keywords:
            if keyword in col.lower():
                return col
    return None


def smart_detect_columns(df):
    cols = {c: c.lower() for c in df.columns}

    # ── TITLE ──────────────────────────────────────────────
    title_keywords = [
        'product name(english)', 'product name (english)',
        'name(english)', 'name (english)',
        'product title', 'product_name', 'item name',
        'title', 'product name', 'item title',
        'listing title', 'ad title',
    ]
    title_col = None
    for kw in title_keywords:
        for col, col_lower in cols.items():
            # Skip columns with 'id', 'nepali', 'look' in them
            if any(skip in col_lower for skip in ['product id', ' id', 'nepali', 'look function']):
                continue
            if kw in col_lower:
                title_col = col
                break
        if title_col:
            break

    # ── DESCRIPTION ────────────────────────────────────────
    desc_keywords = [
        'main description', 'product description',
        'description', 'details', 'detail', 'about',
        'highlights', 'overview', 'body', 'content',
        'long description', 'full description'
    ]
    desc_col = None
    for kw in desc_keywords:
        for col, col_lower in cols.items():
            if kw in col_lower:
                desc_col = col
                break
        if desc_col:
            break

    # ── IMAGE ──────────────────────────────────────────────
    image_keywords = [
        'product images1', 'product images 1',
        '*product images1', 'image src', 'main image',
        'image1', 'image 1', 'photo1', 'photo 1',
        'image', 'photo', 'img', 'picture',
        'thumbnail', 'cover image', 'featured image',
    ]
    image_col = None
    for kw in image_keywords:
        for col, col_lower in cols.items():
            if kw in col_lower:
                image_col = col
                break
        if image_col:
            break

    # ── PRICE ──────────────────────────────────────────────
    price_keywords = [
        '*sale price', 'sale price', '*price',
        'special price', 'selling price', 'retail price',
        'price', 'amount', 'cost', 'mrp',
        'unit price', 'list price', 'offer price'
    ]
    price_col = None
    for kw in price_keywords:
        for col, col_lower in cols.items():
            # Skip ID columns
            if any(skip in col_lower for skip in ['product id', ' id']):
                continue
            if kw in col_lower:
                price_col = col
                break
        if price_col:
            break

    # ── CATEGORY ───────────────────────────────────────────
    category_keywords = [
        'google_product_category', 'product category',
        'category name', 'category', 'type', 'genre',
        'department', 'section', 'collection'
    ]
    category_col = None
    for kw in category_keywords:
        for col, col_lower in cols.items():
            if kw in col_lower:
                # Skip warranty-related columns
                if 'warranty' not in col_lower:
                    category_col = col
                    break
        if category_col:
            break

    # ── STOCK ──────────────────────────────────────────────
    stock_keywords = [
        'availability', 'stock quantity', 'quantity',
        'stock', 'qty', 'inventory', 'units available',
        'available quantity', 'stock level'
    ]
    stock_col = None
    for kw in stock_keywords:
        for col, col_lower in cols.items():
            if kw in col_lower:
                stock_col = col
                break
        if stock_col:
            break

    # ── LINK ───────────────────────────────────────────────
    link_keywords = [
        'product url', 'product link', 'item url',
        'url', 'link', 'product_url', 'listing url',
        'page url', 'shop url'
    ]
    link_col = None
    for kw in link_keywords:
        for col, col_lower in cols.items():
            if kw in col_lower:
                link_col = col
                break
        if link_col:
            break

    # ── FALLBACK to first column for title ─────────────────
    first_col = df.columns[0]
    return {
        'title':    title_col    or first_col,
        'desc':     desc_col     or title_col or first_col,
        'image':    image_col    or title_col or first_col,
        'price':    price_col,
        'category': category_col,
        'stock':    stock_col,
        'link':     link_col,
    }


def detect_duplicate_images(df, image_col):
    if not image_col:
        return set()
    image_counts = df[image_col].astype(str).value_counts()
    duplicates   = set(image_counts[image_counts > 1].index)
    duplicates.discard('nan')
    duplicates.discard('')
    return duplicates


# =========================================================
# SKU & TAGS
# =========================================================
def generate_sku(title):
    title = str(title).upper()
    words = title.split()[:3]
    short = ''.join(word[:3] for word in words)
    random_part = ''.join(random.choices(string.digits, k=4))
    return f"{short}-{random_part}"


def generate_tags(title, category):
    title_words = str(title).lower().split()
    category_words = str(category).lower().split()
    tags = list(set(title_words + category_words))
    return ', '.join(tags[:8])


# ====================== AI OPTIMIZER ======================
def ai_optimize_product(title, description, category=""):
    title = str(title).replace("nan", "").strip()
    description = str(description).replace("nan", "").strip()
    category = str(category).replace("nan", "").strip()

    optimized_title = f"Premium {title} | Best {category} Product in Nepal"

    bullet_points = [
        "✔ High quality & durable build",
        "✔ Fast delivery all over Nepal",
        "✔ Trusted seller product",
        "✔ Excellent value for money",
        "✔ Ideal for everyday usage"
    ]

    seo_keywords = [word.lower() for word in title.split() if len(word) > 3]
    seo_tags = ", ".join(seo_keywords[:10])

    optimized_description = f"""
{title}

{description}

Why choose this product?
• Premium quality materials
• Reliable performance
• Affordable pricing
• Fast nationwide delivery

Perfect for customers looking for quality {category} products in Nepal.

SEO Tags: {seo_tags}
"""

    return {
        "optimized_title": optimized_title,
        "bullet_points": bullet_points,
        "optimized_description": optimized_description,
        "seo_tags": seo_tags
    }


# =========================================================
# HOME ROUTE
# =========================================================
def send_email(to, subject, body):
    try:
        msg = Message(subject, sender=app.config['MAIL_FROM'], recipients=[to])
        msg.html = body
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


@app.route('/register', methods=['GET', 'POST'])
def register():
    error = ""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        if len(password) < 6:
            error = "Password must be at least 6 characters"
        elif User.query.filter_by(email=email).first():
            error = "Email already registered"
        elif User.query.filter_by(username=username).first():
            error = "Username already taken"
        else:
            token = secrets.token_urlsafe(32)
            user  = User(
                username=username, email=email,
                password=generate_password_hash(password),
                verify_token=token, is_verified=False
            )
            db.session.add(user)
            db.session.commit()
            verify_url = f"{request.host_url}verify/{token}"
            send_email(email, "Verify your Seller AI account",
                "<div style='font-family:Arial;max-width:500px;margin:0 auto;padding:20px;'>"
                f"<h2 style='color:#1d4ed8;'>Welcome to Seller AI, {username}!</h2>"
                "<p>Please verify your email to get started.</p>"
                f"<a href='{verify_url}' style='display:inline-block;background:#1d4ed8;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;margin:16px 0;'>Verify Email</a>"
                "<p style='color:#64748b;font-size:13px;'>If you did not register, ignore this email.</p>"
                "</div>"
            )
            return redirect('/login?msg=verify')
    error_html = f'''<div class="error">&#x26A0; {error}</div>''' if error else ''''''
    return f"""<!DOCTYPE html>
<html><head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Register - Seller AI</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:'Inter',sans-serif;background:linear-gradient(135deg,#1d4ed8 0%,#7c3aed 60%,#db2777 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;}}
.card{{background:white;border-radius:24px;padding:40px 36px;width:100%;max-width:420px;box-shadow:0 24px 64px rgba(0,0,0,0.25);animation:slideUp 0.5s cubic-bezier(.16,1,.3,1);}}
@keyframes slideUp{{from{{opacity:0;transform:translateY(30px);}}to{{opacity:1;transform:translateY(0);}}}}
.logo{{text-align:center;margin-bottom:28px;}}
.logo-icon{{width:64px;height:64px;border-radius:18px;background:linear-gradient(135deg,#1d4ed8,#7c3aed);display:inline-flex;align-items:center;justify-content:center;font-size:30px;margin-bottom:12px;}}
.logo h1{{font-size:22px;font-weight:800;color:#0f172a;}}
.logo p{{font-size:13px;color:#64748b;margin-top:4px;}}
.error{{background:#fee2e2;color:#dc2626;padding:10px 14px;border-radius:10px;font-size:13px;margin-bottom:16px;}}
.info{{background:#eff6ff;color:#1d4ed8;padding:10px 14px;border-radius:10px;font-size:13px;margin-bottom:16px;}}
label{{display:block;font-size:13px;font-weight:600;color:#374151;margin-bottom:6px;}}
input{{width:100%;padding:12px 16px;border:1.5px solid #e2e8f0;border-radius:10px;font-size:14px;font-family:'Inter',sans-serif;color:#0f172a;outline:none;transition:border-color 0.2s;margin-bottom:16px;}}
input:focus{{border-color:#7c3aed;box-shadow:0 0 0 3px rgba(124,58,237,0.1);}}
button{{width:100%;padding:13px;background:linear-gradient(135deg,#1d4ed8,#7c3aed);color:white;border:none;border-radius:10px;font-size:15px;font-weight:700;font-family:'Inter',sans-serif;cursor:pointer;transition:all 0.2s;margin-top:4px;}}
button:hover{{opacity:0.9;transform:translateY(-1px);}}
.link{{text-align:center;margin-top:20px;font-size:13px;color:#64748b;}}
.link a{{color:#7c3aed;font-weight:600;text-decoration:none;}}
</style>
</head><body>
<div class="card">
    <div class="logo">
        <div class="logo-icon">&#x1F6D2;</div>
        <h1>Create Account</h1>
        <p>Join Seller AI Dashboard</p>
    </div>
    {error_html}
    <form method="POST">
        <label>Username</label>
        <input name="username" placeholder="Your name" required>
        <label>Email</label>
        <input name="email" type="email" placeholder="you@example.com" required>
        <label>Password</label>
        <input name="password" type="password" placeholder="Min 6 characters" required>
        <button type="submit">Create Account &#x2192;</button>
    </form>
    <div class="link">Already have an account? <a href="/login">Sign in</a></div>
</div>
</body></html>"""


@app.route('/verify/<token>')
def verify_email(token):
    user = User.query.filter_by(verify_token=token).first()
    if user:
        user.is_verified  = True
        user.verify_token = None
        db.session.commit()
        return redirect('/login?msg=verified')
    return redirect('/login?msg=invalid')


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    message = ""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user  = User.query.filter_by(email=email).first()
        if user:
            token = secrets.token_urlsafe(32)
            user.reset_token  = token
            user.reset_expiry = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            reset_url = f"{request.host_url}reset-password/{token}"
            send_email(email, "Reset your Seller AI password",
                "<div style='font-family:Arial;max-width:500px;margin:0 auto;padding:20px;'>"
                "<h2 style='color:#1d4ed8;'>Reset Your Password</h2>"
                "<p>Click the button below to reset your password. Link expires in 1 hour.</p>"
                f"<a href='{reset_url}' style='display:inline-block;background:#1d4ed8;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;margin:16px 0;'>Reset Password</a>"
                "<p style='color:#64748b;font-size:13px;'>If you did not request this, ignore this email.</p>"
                "</div>"
            )
        message = "If that email exists, a reset link has been sent."
    return f"""<!DOCTYPE html>
<html><head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Forgot Password - Seller AI</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:'Inter',sans-serif;background:linear-gradient(135deg,#1d4ed8 0%,#7c3aed 60%,#db2777 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;}}
.card{{background:white;border-radius:24px;padding:40px 36px;width:100%;max-width:420px;box-shadow:0 24px 64px rgba(0,0,0,0.25);}}
.logo{{text-align:center;margin-bottom:28px;}}
.logo-icon{{width:64px;height:64px;border-radius:18px;background:linear-gradient(135deg,#1d4ed8,#7c3aed);display:inline-flex;align-items:center;justify-content:center;font-size:30px;margin-bottom:12px;}}
.logo h1{{font-size:22px;font-weight:800;color:#0f172a;}}
.logo p{{font-size:13px;color:#64748b;margin-top:4px;}}
.info{{background:#eff6ff;color:#1d4ed8;padding:10px 14px;border-radius:10px;font-size:13px;margin-bottom:16px;}}
label{{display:block;font-size:13px;font-weight:600;color:#374151;margin-bottom:6px;}}
input{{width:100%;padding:12px 16px;border:1.5px solid #e2e8f0;border-radius:10px;font-size:14px;font-family:'Inter',sans-serif;outline:none;margin-bottom:16px;}}
input:focus{{border-color:#7c3aed;}}
button{{width:100%;padding:13px;background:linear-gradient(135deg,#1d4ed8,#7c3aed);color:white;border:none;border-radius:10px;font-size:15px;font-weight:700;cursor:pointer;}}
.link{{text-align:center;margin-top:20px;font-size:13px;color:#64748b;}}
.link a{{color:#7c3aed;font-weight:600;text-decoration:none;}}
</style>
</head><body>
<div class="card">
    <div class="logo">
        <div class="logo-icon">&#x1F511;</div>
        <h1>Forgot Password</h1>
        <p>We'll send you a reset link</p>
    </div>
    {"<div class='info'>&#x2709; " + message + "</div>" if message else ""}
    <form method="POST">
        <label>Email</label>
        <input name="email" type="email" placeholder="you@example.com" required>
        <button type="submit">Send Reset Link &#x2192;</button>
    </form>
    <div class="link"><a href="/login">&#x2190; Back to login</a></div>
</div>
</body></html>"""


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user  = User.query.filter_by(reset_token=token).first()
    error = ""
    if not user or (user.reset_expiry and user.reset_expiry < datetime.utcnow()):
        return redirect('/login?msg=expired')
    if request.method == 'POST':
        password = request.form.get('password', '')
        if len(password) < 6:
            error = "Password must be at least 6 characters"
        else:
            user.password    = generate_password_hash(password)
            user.reset_token  = None
            user.reset_expiry = None
            db.session.commit()
            return redirect('/login?msg=reset')
    error_html = f'''<div class="error">&#x26A0; {error}</div>''' if error else ''''''
    return f"""<!DOCTYPE html>
<html><head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Reset Password - Seller AI</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:'Inter',sans-serif;background:linear-gradient(135deg,#1d4ed8 0%,#7c3aed 60%,#db2777 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;}}
.card{{background:white;border-radius:24px;padding:40px 36px;width:100%;max-width:420px;box-shadow:0 24px 64px rgba(0,0,0,0.25);}}
.logo{{text-align:center;margin-bottom:28px;}}
.logo-icon{{width:64px;height:64px;border-radius:18px;background:linear-gradient(135deg,#1d4ed8,#7c3aed);display:inline-flex;align-items:center;justify-content:center;font-size:30px;margin-bottom:12px;}}
.logo h1{{font-size:22px;font-weight:800;color:#0f172a;}}
.error{{background:#fee2e2;color:#dc2626;padding:10px 14px;border-radius:10px;font-size:13px;margin-bottom:16px;}}
label{{display:block;font-size:13px;font-weight:600;color:#374151;margin-bottom:6px;}}
input{{width:100%;padding:12px 16px;border:1.5px solid #e2e8f0;border-radius:10px;font-size:14px;font-family:'Inter',sans-serif;outline:none;margin-bottom:16px;}}
input:focus{{border-color:#7c3aed;}}
button{{width:100%;padding:13px;background:linear-gradient(135deg,#1d4ed8,#7c3aed);color:white;border:none;border-radius:10px;font-size:15px;font-weight:700;cursor:pointer;}}
</style>
</head><body>
<div class="card">
    <div class="logo">
        <div class="logo-icon">&#x1F511;</div>
        <h1>New Password</h1>
    </div>
    {error_html}
    <form method="POST">
        <label>New Password</label>
        <input name="password" type="password" placeholder="Min 6 characters" required>
        <button type="submit">Save Password &#x2192;</button>
    </form>
</div>
</body></html>"""


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = ""
    msg   = request.args.get('msg', '')
    msg_map = {
        'verify':  ('info',    'Account created! Please check your email to verify your account.'),
        'verified':('success', 'Email verified! You can now login.'),
        'reset':   ('success', 'Password reset successfully! Please login.'),
        'expired': ('error',   'Reset link expired. Please request a new one.'),
        'invalid': ('error',   'Invalid verification link.'),
    }
    msg_type, msg_text = msg_map.get(msg, ('', ''))
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user     = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            if not user.is_verified:
                error = "Please verify your email before logging in. Check your inbox!"
            else:
                login_user(user)
                return redirect('/')
        else:
            error = "Invalid email or password"
    error_html = f'''<div class="error">&#x26A0; {error}</div>''' if error else ''''''
    msg_html   = f'''<div class="{msg_type}">{"&#x2705;" if msg_type=="success" else "&#x2139;"} {msg_text}</div>''' if msg_type else ''''''
    return f"""<!DOCTYPE html>
<html><head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Login - Seller AI</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:'Inter',sans-serif;background:linear-gradient(135deg,#1d4ed8 0%,#7c3aed 60%,#db2777 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;}}
.card{{background:white;border-radius:24px;padding:40px 36px;width:100%;max-width:420px;box-shadow:0 24px 64px rgba(0,0,0,0.25);animation:slideUp 0.5s cubic-bezier(.16,1,.3,1);}}
@keyframes slideUp{{from{{opacity:0;transform:translateY(30px);}}to{{opacity:1;transform:translateY(0);}}}}
.logo{{text-align:center;margin-bottom:28px;}}
.logo-icon{{width:64px;height:64px;border-radius:18px;background:linear-gradient(135deg,#1d4ed8,#7c3aed);display:inline-flex;align-items:center;justify-content:center;font-size:30px;margin-bottom:12px;}}
.logo h1{{font-size:22px;font-weight:800;color:#0f172a;}}
.logo p{{font-size:13px;color:#64748b;margin-top:4px;}}
.error{{background:#fee2e2;color:#dc2626;padding:10px 14px;border-radius:10px;font-size:13px;margin-bottom:16px;}}
.success{{background:#dcfce7;color:#15803d;padding:10px 14px;border-radius:10px;font-size:13px;margin-bottom:16px;}}
.info{{background:#eff6ff;color:#1d4ed8;padding:10px 14px;border-radius:10px;font-size:13px;margin-bottom:16px;}}
label{{display:block;font-size:13px;font-weight:600;color:#374151;margin-bottom:6px;}}
input{{width:100%;padding:12px 16px;border:1.5px solid #e2e8f0;border-radius:10px;font-size:14px;font-family:'Inter',sans-serif;color:#0f172a;outline:none;transition:border-color 0.2s;margin-bottom:16px;}}
input:focus{{border-color:#7c3aed;box-shadow:0 0 0 3px rgba(124,58,237,0.1);}}
button{{width:100%;padding:13px;background:linear-gradient(135deg,#1d4ed8,#7c3aed);color:white;border:none;border-radius:10px;font-size:15px;font-weight:700;font-family:'Inter',sans-serif;cursor:pointer;transition:all 0.2s;margin-top:4px;}}
button:hover{{opacity:0.9;transform:translateY(-1px);}}
.link{{text-align:center;margin-top:16px;font-size:13px;color:#64748b;}}
.link a{{color:#7c3aed;font-weight:600;text-decoration:none;}}
.forgot{{text-align:right;margin-top:-10px;margin-bottom:16px;}}
.forgot a{{font-size:12px;color:#7c3aed;text-decoration:none;font-weight:500;}}
</style>
</head><body>
<div class="card">
    <div class="logo">
        <div class="logo-icon">&#x1F6D2;</div>
        <h1>Welcome Back</h1>
        <p>Sign in to Seller AI Dashboard</p>
    </div>
    {msg_html}{error_html}
    <form method="POST">
        <label>Email</label>
        <input name="email" type="email" placeholder="you@example.com" required>
        <label>Password</label>
        <input name="password" type="password" placeholder="Your password" required>
        <div class="forgot"><a href="/forgot-password">Forgot password?</a></div>
        <button type="submit">Sign In &#x2192;</button>
    </form>
    <div class="link">Don't have an account? <a href="/register">Sign up free</a></div>
</div>
</body></html>"""


@app.route('/delete/<int:product_id>')
@login_required
def delete_product(product_id):
    product = Product.query.filter_by(id=product_id, user_id=current_user.id).first()
    if product:
        db.session.delete(product)
        db.session.commit()
    return redirect('/')


@app.route('/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    product = Product.query.filter_by(id=product_id, user_id=current_user.id).first()
    if not product:
        return 'Product not found'
    if request.method == 'POST':
        product.title       = request.form['title']
        product.description = request.form['description']
        product.price       = float(request.form['price'])
        product.stock       = int(request.form['stock'])
        db.session.commit()
        return redirect('/')
    return (
        '<h1>Edit Product</h1>'
        '<form method="POST">'
        f'<input name="title" value="{product.title}"><br><br>'
        f'<textarea name="description">{product.description}</textarea><br><br>'
        f'<input name="price" value="{product.price}"><br><br>'
        f'<input name="stock" value="{product.stock}"><br><br>'
        '<button type="submit">Save Changes</button>'
        '</form>'
    )


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/login')


@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    global uploaded_df
    cards = ""
    total_products = 0
    duplicate_products = 0
    missing_images = 0
    avg_price = 0
    category_labels = []
    category_counts = []
    total_inventory_value = 0
    low_stock_count = 0
    total_potential_profit = 0
    category_options = ""

    if request.method == 'POST':
        file = request.files.get('file')
        if file and file.filename:
            if file.filename.endswith('.csv'):
                uploaded_df = pd.read_csv(file)
            else:
                uploaded_df = pd.read_excel(file)

            # SAVE CATALOG TO DATABASE FOR PERSISTENCE
            catalog_dir = 'catalogs'
            os.makedirs(catalog_dir, exist_ok=True)
            catalog_path = os.path.join(catalog_dir, f'catalog_{current_user.id}.csv')
            uploaded_df.to_csv(catalog_path, index=False)
            current_user.catalog_path = catalog_path
            current_user.catalog_data = uploaded_df.to_csv(index=False)
            db.session.commit()


            uploaded_df.columns = uploaded_df.columns.str.strip()
            detected         = smart_detect_columns(uploaded_df)
            title_col        = detected['title']
            desc_col         = detected['desc']
            image_col        = detected['image']
            price_col        = detected['price']
            category_col     = detected['category']
            stock_col_upload = detected['stock']
            duplicate_images = detect_duplicate_images(uploaded_df, image_col)

            # SAVE PRODUCTS INTO DATABASE
            stock_col_upload = find_column(uploaded_df, ['availability', 'stock', 'quantity', 'qty', 'inventory'])
            for _, row in uploaded_df.iterrows():
                title       = str(row.get(title_col, 'Untitled')).replace("nan", "").strip() or 'Untitled'
                description = str(row.get(desc_col, '')).replace("nan", "").strip()
                category    = str(row.get(category_col, 'General')).replace("nan", "").strip() or 'General'
                image       = fix_google_drive_link(row.get(image_col, ''))
                try:
                    price = float(str(row.get(price_col, 0)).replace(",", "").strip())
                except:
                    price = 0
                try:
                    stock = int(float(str(row.get(stock_col_upload, 0)).replace(',', '').strip())) if stock_col_upload else 0
                except:
                    stock = 0

                db.session.add(Product(
                        user_id=current_user.id,
                        title=title, description=description,
                        category=category, image=image,
                        price=price, stock=stock
                    ))
            db.session.commit()

    # AUTO-LOAD CATALOG IF NO PRODUCTS
    if not Product.query.filter_by(user_id=current_user.id).first():
        # Try file first, fall back to DB stored CSV
        auto_csv = None
        if current_user.catalog_path and os.path.exists(current_user.catalog_path):
            auto_csv = current_user.catalog_path
        elif current_user.catalog_data:
            import io as _io
            auto_df = pd.read_csv(_io.StringIO(current_user.catalog_data))
            auto_csv = "from_db"
        if auto_csv:
            if auto_csv != "from_db":
                auto_df = pd.read_csv(auto_csv)
            auto_df.columns = auto_df.columns.str.strip()
            _detected     = smart_detect_columns(auto_df)
            _title_col    = _detected['title']
            _desc_col     = _detected['desc']
            _image_col    = _detected['image']
            _price_col    = _detected['price']
            _category_col = _detected['category']
            _stock_col    = _detected['stock']
            for _, row in auto_df.iterrows():
                title       = str(row.get(_title_col, 'Untitled')).replace("nan", "").strip() or 'Untitled'
                description = str(row.get(_desc_col, '')).replace("nan", "").strip()
                category    = str(row.get(_category_col, 'General')).replace("nan", "").strip() or 'General'
                image       = fix_google_drive_link(row.get(_image_col, ''))
                try:
                    price = float(str(row.get(_price_col, 0)).replace(",", "").strip())
                except:
                    price = 0
                try:
                    stock = int(float(str(row.get(_stock_col, 0)).replace(',', '').strip())) if _stock_col else 0
                except:
                    stock = 0
                if not Product.query.filter_by(title=title, user_id=current_user.id).first():
                    db.session.add(Product(
                        user_id=current_user.id, title=title, description=description,
                        category=category, image=image, price=price, stock=stock
                    ))
            db.session.commit()

    products = Product.query.filter_by(user_id=current_user.id).all()

    if products:
        data = []
        for product in products:
            data.append({
                "id":          product.id,
                "title":       product.title,
                "description": product.description,
                "category":    product.category,
                "image":       product.image,
                "price":       product.price,
                "stock":       product.stock
            })
        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip().str.lower()

        title_col    = "title"
        desc_col     = "description"
        image_col    = "image"
        price_col    = "price"
        category_col = "category"
        link_col     = None
        stock_col    = "stock" 

        # Search, Sort, Filter
        search = request.args.get('search', '').lower()
        if search:
            df = df[df[title_col].astype(str).str.lower().str.contains(search)]

        sort_option = request.args.get('sort', '')
        df[price_col] = pd.to_numeric(df[price_col], errors='coerce')

        if sort_option == 'low':
            df = df.sort_values(by=price_col, ascending=True)
        elif sort_option == 'high':
            df = df.sort_values(by=price_col, ascending=False)
        elif sort_option == 'az':
            df = df.sort_values(by=title_col, ascending=True)
        elif sort_option == 'za':
            df = df.sort_values(by=title_col, ascending=False)

        selected_category = request.args.get('category', 'All')
        if selected_category != 'All' and selected_category:
            df = df[df[category_col].astype(str) == selected_category]

        for cat in df[category_col].dropna().astype(str).unique():
            category_options += f'<option value="{cat}">{cat}</option>'

        total_products     = len(df)
        duplicate_products = df.duplicated(subset=[title_col]).sum()
        missing_images     = df[image_col].isna().sum()
        avg_price          = round(df[price_col].mean(), 2) if not df.empty else 0

        clean_categories = df[category_col].astype(str).replace("nan", "General")
        category_data    = clean_categories.value_counts()
        category_labels  = [str(x) for x in category_data.index]
        category_counts  = [int(x) for x in category_data.values]

        bulk_percent = float(request.args.get('bulk', 10))

        for i, (_, row) in enumerate(df.iterrows()):
            is_duplicate = df.duplicated(subset=[title_col], keep=False).iloc[i]
            title = str(row.get(title_col, 'Untitled Product')).replace("nan", "").strip()
            if not title:
                title = "Untitled Product"

            description = str(row.get(desc_col, 'No description')).strip()

            category = str(row.get(category_col, 'General')).replace("nan", "").strip()
            if not category or category.lower() in ['google_product_category', 'category', 'type']:
                category = "General"

            image = fix_google_drive_link(row.get(image_col, ''))
            image_warning = ""
            image_class = ""
            if "placehold.co" in image or not image or image == "nan":
                image_warning = "<div class='image-warning'>⚠ Missing Image</div>"
                image_class = "bad-image"
            elif not (image.startswith("http://") or image.startswith("https://")):
                image_warning = "<div class='image-warning'>⚠ Invalid Image URL</div>"
                image_class = "bad-image" 

            try:
                raw_price = str(row.get(price_col, 0)).replace(",", "").strip()
                price = 0 if raw_price.lower() == "nan" else float(raw_price)
            except:
                price = 0

            updated_price   = round(price * (1 + bulk_percent / 100), 2)
            cost_price      = round(price * 0.7, 2)
            profit          = round(updated_price - cost_price, 2)

            try:
                stock = int(float(str(row.get(stock_col, 0)).replace(',', '').strip())) if stock_col else 0
            except:
                stock = 0

            if stock <= 5:
                stock_status = "🔴 Low Stock"
                stock_class  = "low-stock"
                low_stock_count += 1
            else:
                stock_status = "🟢 In Stock"
                stock_class  = "in-stock"

            profit_per_sale        = round(price * 0.30, 2)
            inventory_value        = round(updated_price * stock, 2)
            total_inventory_value  += inventory_value
            total_potential_profit += profit_per_sale * stock

            sku        = generate_sku(title)
            tags       = generate_tags(title, category)
            short_desc = description[:140] + "..." if len(description) > 140 else description

            daraz_link = str(row.get(link_col, '')).strip() if link_col else ''
            daraz_btn  = f'<a href="{daraz_link}" target="_blank"><button class="daraz-btn">🛒 View on Daraz</button></a>' if daraz_link and daraz_link.lower() != 'nan' else ''

            cards += f"""
            <div class="card {'duplicate-card' if is_duplicate else ''}" data-index="{i}" 
                data-title="{title.replace('"', '&quot;')}"
                data-image="{image}"
                data-category="{category}"
                data-sku="{sku}"
                data-tags="{tags.replace('"', '&quot;')}"
                data-stock="{stock}"
                data-price="Rs. {price}"
                data-updated="Rs. {updated_price}"
                data-profit="Rs. {profit_per_sale}"
                data-inventory="Rs. {inventory_value}"
                data-desc="{description.replace('"', '&quot;').replace(chr(10), ' ')}">
                <div class="category-badge">{category}</div>
                {image_warning}
                {"<div class='duplicate-badge'>Duplicate Product</div>" if is_duplicate else ""}
                <img src="{image}" class="product-image {image_class}" onerror="this.src='https://placehold.co/600x400/f1f1f1/888?text=No+Image';">
                <div class="card-body">
                    <h2 class="title">{title}</h2>
                    <div class="price-section">
                        <p class="old-price">Original: Rs. {price}</p>
                        <p class="new-price">Updated ({bulk_percent:+g}%): Rs. {updated_price}</p>
                    </div>
                    <p class="description">{short_desc}</p>
                    <p><b>SKU:</b> {sku}</p>
                    <p><b>Tags:</b> {tags}</p>
                    <p class="{stock_class}"><b>{stock_status}</b></p>
                    <p><b>Stock:</b> {stock}</p>
                    <p><b>Profit Per Sale:</b> Rs. {profit_per_sale}</p>
                    <p><b>Inventory Value:</b> Rs. {inventory_value}</p>
                    <button class="ai-btn" onclick="optimizeProduct({i})">✨ AI Optimize Listing</button>
                    {daraz_btn}
                    <button class="view-btn" onclick="openModal({i})">👁 View Product</button>
                    <a href="/edit/{row['id']}"><button class="blue" style="width:100%;margin-top:5px;">✏️ Edit</button></a>
                    <a href="/delete/{row['id']}"><button class="orange" style="width:100%;margin-top:5px;">🗑️ Delete</button></a>
                </div>
            </div>
            """

    category_labels_json = json.dumps(category_labels)
    category_counts_json = json.dumps(category_counts)

    return f"""
    <html>
    <head>
        <title>Seller Automation Dashboard</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{ font-family: Arial; background: #f4f4f4; margin: 0; padding: 0; }}
            .dark {{ background: #0f172a; color: white; }}
            .header {{ background: white; padding: 25px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            h1 {{ margin: 0; font-size: 42px; }}
            .controls {{ display: flex; gap: 15px; margin-top: 25px; flex-wrap: wrap; }}
            input, select {{ padding: 14px; border-radius: 10px; border: 1px solid #ccc; min-width: 220px; }}
            button {{ padding: 14px 24px; border: none; border-radius: 10px; color: white; cursor: pointer; transition: 0.2s ease; }}
            button:hover {{ opacity: 0.9; transform: scale(1.03); }}
            .blue {{ background: #2563eb; }}
            .green {{ background: #15803d; }}
            .orange {{ background: #ea580c; }}
            .pink {{ background: #db2777; }}
            .ai-btn {{ background: linear-gradient(135deg, #8b5cf6, #ec4899); width:100%; margin:10px 0; font-weight:bold; }}
            .daraz-btn {{ background: #f85606; width:100%; margin:5px 0; font-weight:bold; }}
            .view-btn {{ width: 100%; margin-top: 12px; background: #111827; color: white; padding: 14px; border-radius: 12px; font-weight: bold; transition: 0.2s; }}
            .view-btn:hover {{ background: #2563eb; }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(240px,1fr)); gap: 22px; padding: 25px; }}
            .stat-card {{ background: white; padding: 28px; border-radius: 20px; box-shadow: 0 6px 18px rgba(0,0,0,0.08); transition: 0.25s; }}
            .stat-card:hover {{ transform: translateY(-4px); }}
            .stat-number {{ font-size: 35px; font-weight: bold; color: #2563eb; }}
            .products {{ display: grid; grid-template-columns: repeat(auto-fill,minmax(320px,1fr)); gap: 22px; padding: 8px 32px 40px; justify-items: stretch; }}
            .card {{ background: white; border-radius: 22px; overflow: hidden; box-shadow: 0 8px 25px rgba(0,0,0,0.08); position: relative; transition: 0.3s ease; border: 1px solid #f0f0f0; }}
            .card:hover {{ transform: translateY(-6px); box-shadow: 0 12px 24px rgba(0,0,0,0.15); }}
            .category-badge {{ position: absolute; top: 14px; left: 14px; background: #2563eb; color: white; padding: 8px 14px; border-radius: 999px; font-size: 12px; font-weight: bold; z-index: 5; }}
            .product-image {{ width: 100%; height: 320px; object-fit: cover; background: #f7f7f7; }}
            .charts-container {{ padding: 20px; }}
            .chart-box {{ background: white; padding: 20px; border-radius: 18px; margin: 20px auto; box-shadow: 0 4px 12px rgba(0,0,0,0.08); max-width: 700px; }}
            #categoryChart {{ max-height: 400px; }}
            .card-body {{ padding: 22px; }}
            .title {{ font-size: 24px; line-height: 1.4; margin-bottom: 14px; font-weight: 700; color: #111827; }}
            .description {{ font-size: 15px; color: #4b5563; line-height: 1.7; margin-top: 10px; }}
            .price-section {{ background: #f8fafc; padding: 14px; border-radius: 14px; margin: 15px 0; }}
            .old-price {{ color: #6b7280; margin-bottom: 6px; }}
            .new-price {{ color: #16a34a; font-size: 24px; font-weight: bold; }}
            .low-stock {{ color: #dc2626; font-weight: bold; }}
            .in-stock  {{ color: #16a34a; font-weight: bold; }}
            .duplicate-card {{ border: 4px solid #ef4444; box-shadow: 0 0 20px rgba(239,68,68,0.4); }}
            .duplicate-badge {{ position: absolute; top: 50px; left: 12px; background: #ef4444; color: white; padding: 6px 12px; border-radius: 30px; font-size: 12px; font-weight: bold; z-index: 10; }}
            .image-warning {{ position: absolute; top: 60px; right: 15px; background: #ea580c; color: white; padding: 8px 12px; border-radius: 10px; font-size: 13px; font-weight: bold; z-index: 5; }}
            .bad-image {{ border-bottom: 4px solid #ea580c; }}

            /* MODAL */
            .modal-overlay {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); z-index: 1000; overflow-y: auto; padding: 40px 20px; box-sizing: border-box; }}
            .modal-overlay.active {{ display: block; }}
            .modal-box {{ background: white; border-radius: 24px; max-width: 860px; width: 100%; overflow: visible; box-shadow: 0 20px 60px rgba(0,0,0,0.3); animation: slideUp 0.3s ease; margin: 0 auto 40px auto; }}
            @keyframes slideUp {{ from {{ transform: translateY(40px); opacity: 0; }} to {{ transform: translateY(0); opacity: 1; }} }}
            .modal-image {{ width: 100%; height: 300px; object-fit: contain; background: #f8fafc; display: block; }}
            .modal-header-wrap {{ position: relative; overflow: hidden; border-radius: 24px 24px 0 0; }}
            .modal-body {{ padding: 30px; }}
            .modal-title {{ font-size: 24px; font-weight: bold; margin: 0 0 16px; line-height: 1.4; }}
            .modal-badges {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }}
            .modal-badge {{ padding: 5px 14px; border-radius: 20px; font-size: 13px; font-weight: 600; }}
            .badge-blue {{ background: #dbeafe; color: #1d4ed8; }}
            .badge-green {{ background: #dcfce7; color: #15803d; }}
            .modal-stats {{ display: grid; grid-template-columns: repeat(3,1fr); gap: 14px; margin: 20px 0; }}
            .modal-stat {{ background: #f8fafc; border-radius: 12px; padding: 14px; text-align: center; }}
            .modal-stat-number {{ font-size: 20px; font-weight: bold; color: #2563eb; }}
            .modal-stat-label {{ font-size: 12px; color: #888; margin-top: 4px; }}
            .modal-section-title {{ font-size: 15px; font-weight: bold; color: #333; margin: 20px 0 8px; }}
            .modal-description {{ font-size: 14px; color: #555; line-height: 1.7; background: #f8fafc; padding: 16px; border-radius: 12px; }}
            .modal-ai-box {{ background: linear-gradient(135deg, #f3e8ff, #fce7f3); border-radius: 12px; padding: 16px; margin-top: 16px; }}
            .modal-ai-box p {{ font-size: 14px; color: #555; margin: 6px 0; line-height: 1.6; }}
            .modal-close {{ position: absolute; top: 16px; right: 20px; font-size: 22px; cursor: pointer; color: #333; background: white; border: none; border-radius: 50%; width: 38px; height: 38px; box-shadow: 0 2px 8px rgba(0,0,0,0.15); z-index: 10; }}
            .modal-header-wrap {{ position: relative; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🚀 Seller Automation Dashboard + AI</h1>
            <h3>Welcome, {current_user.username}</h3>
            <form method="POST" enctype="multipart/form-data">
                <div class="controls">
                    <input type="file" name="file">
                    <button class="blue" type="submit">Upload Catalog</button>
                    <input type="text" placeholder="Search products..." onkeyup="searchProducts(this.value)">
                    <input type="number" id="bulkPercent" value="10">
                    <button class="green" type="button" onclick="applyBulkPrice()">Apply Bulk Pricing</button>
                    <input type="number" id="discountPercent" placeholder="Discount %">
                    <button class="orange" type="button" onclick="applyDiscount()">Apply Discount</button>
                    <select onchange="sortProducts(this.value)">
                        <option value="">Sort Products</option>
                        <option value="low">Price Low to High</option>
                        <option value="high">Price High to Low</option>
                        <option value="az">Title A-Z</option>
                        <option value="za">Title Z-A</option>
                    </select>
                    <select onchange="filterCategory(this.value)">
                        <option value="All">All Categories</option>
                        {category_options}
                    </select>
                    <button class="blue" type="button" onclick="toggleDarkMode()">Toggle Dark Mode</button>
                    <a href="/export/daraz"><button class="orange" type="button">Export Daraz</button></a>
                    <a href="/export/shopify"><button class="green" type="button">Export Shopify</button></a>
                    <a href="/export/facebook"><button class="pink" type="button">Export Facebook</button></a>
                    <a href="/export/tiktok"><button class="blue" type="button">Export TikTok</button></a>
                    <a href="/export/instagram"><button class="pink" type="button">Export Instagram</button></a>
                    <a href="/logout"><button class="orange" type="button">Logout</button></a>

                </div>
            </form>
        </div>

        <form method="POST" action="/clear-products" id="clearForm" style="margin:10px 32px;">
            <button class="pink" type="submit" onclick="return confirm('Delete ALL products? This cannot be undone!')" style="padding:11px 20px;border-radius:10px;font-weight:600;font-size:13px;">🗑️ Delete Products</button>
        </form>

        <div class="stats">
            <div class="stat-card"><div class="stat-number">{total_products}</div><p>Total Products</p></div>
            <div class="stat-card"><div class="stat-number">{duplicate_products}</div><p>Duplicate Products</p></div>
            <div class="stat-card"><div class="stat-number">{missing_images}</div><p>Missing Images</p></div>
            <div class="stat-card"><div class="stat-number">Rs. {avg_price}</div><p>Average Price</p></div>
            <div class="stat-card"><div class="stat-number">Rs. {round(total_inventory_value, 2)}</div><p>Total Inventory Value</p></div>
            <div class="stat-card"><div class="stat-number">{low_stock_count}</div><p>Low Stock Products</p></div>
            <div class="stat-card"><div class="stat-number">Rs. {round(total_potential_profit, 2)}</div><p>Potential Profit</p></div>
        </div>

        <div class="charts-container">
            <div class="chart-box">
                <canvas id="categoryChart"></canvas>
            </div>
        </div>

        <div class="products">
            {cards}
        </div>

        <!-- MODAL -->
        <div class="modal-overlay" id="productModal">
            <div class="modal-box">
                <div class="modal-header-wrap">
                    <img id="modal-image" src="" class="modal-image" onerror="this.src='https://placehold.co/860x420/f1f1f1/888?text=No+Image';">
                    <button class="modal-close" onclick="closeModal()">✕</button>
                </div>
                <div class="modal-body">
                    <div class="modal-badges">
                        <span class="modal-badge badge-blue" id="modal-category"></span>
                        <span class="modal-badge badge-green" id="modal-sku"></span>
                    </div>
                    <h2 class="modal-title" id="modal-title"></h2>
                    <div class="modal-stats">
                        <div class="modal-stat"><div class="modal-stat-number" id="modal-price"></div><div class="modal-stat-label">Original Price</div></div>
                        <div class="modal-stat"><div class="modal-stat-number" id="modal-updated"></div><div class="modal-stat-label">Updated Price</div></div>
                        <div class="modal-stat"><div class="modal-stat-number" id="modal-stock"></div><div class="modal-stat-label">Stock</div></div>
                        <div class="modal-stat"><div class="modal-stat-number" id="modal-profit"></div><div class="modal-stat-label">Profit Per Sale</div></div>
                        <div class="modal-stat"><div class="modal-stat-number" id="modal-inventory"></div><div class="modal-stat-label">Inventory Value</div></div>
                        <div class="modal-stat"><div class="modal-stat-number" id="modal-tag-count"></div><div class="modal-stat-label">Tags</div></div>
                    </div>
                    <div class="modal-section-title">📝 Full Description</div>
                    <div class="modal-description" id="modal-desc"></div>
                    <div class="modal-section-title">🏷️ Tags</div>
                    <div class="modal-description" id="modal-tags"></div>
                    <div class="modal-section-title">✨ AI Insights</div>
                    <div class="modal-ai-box" id="modal-ai-box">
                        <p>Click below to generate AI insights for this product.</p>
                        <button class="ai-btn" id="modal-ai-btn" style="margin-top:10px;">✨ Generate AI Insights</button>
                    </div>
                </div>
            </div>
        </div>

        <script>
            function confirmClear() {{
                if (confirm('Delete ALL your products? This cannot be undone!')) {{
                    document.getElementById('clearForm').submit();
                }}
            }}
            function toggleDarkMode() {{ document.body.classList.toggle("dark"); }}
            function searchProducts(value) {{ window.location = "/?search=" + value; }}
            function sortProducts(value) {{ window.location = "/?sort=" + value; }}
            function filterCategory(value) {{ window.location = "/?category=" + value; }}
            function applyBulkPrice() {{
                let percent = document.getElementById("bulkPercent").value || 10;
                window.location = "/?bulk=" + percent;
            }}
            function applyDiscount() {{
                let percent = document.getElementById("discountPercent").value;
                if(percent) window.location = "/?bulk=-" + percent;
            }}

            async function optimizeProduct(index) {{
                const card = document.querySelectorAll('.card')[index];
                const btn = card.querySelector('.ai-btn');
                const oldText = btn.innerHTML;
                btn.innerHTML = "⏳ Optimizing...";
                btn.disabled = true;
                try {{
                    const res = await fetch('/optimize', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{title: "test", description: "test"}})
                    }});
                    const data = await res.json();
                    card.querySelector('.title').innerHTML = "✦ " + data.optimized_title;
                    card.querySelector('.description').innerHTML = data.optimized_description;
                    alert("✅ AI Listing Optimized!");
                }} catch(e) {{
                    alert("AI Error");
                }} finally {{
                    btn.innerHTML = oldText;
                    btn.disabled = false;
                }}
            }}

            function openModal(index) {{
                const card = document.querySelectorAll('.card')[index];
                if (!card) return;
                const d = card.dataset;
                document.getElementById('modal-image').src     = d.image;
                document.getElementById('modal-title').innerText    = d.title;
                document.getElementById('modal-category').innerText = d.category;
                document.getElementById('modal-sku').innerText      = '🏷 ' + d.sku;
                document.getElementById('modal-price').innerText    = d.price;
                document.getElementById('modal-updated').innerText  = d.updated;
                document.getElementById('modal-stock').innerText    = d.stock;
                document.getElementById('modal-profit').innerText   = d.profit;
                document.getElementById('modal-inventory').innerText= d.inventory;
                document.getElementById('modal-desc').innerText     = d.desc;
                document.getElementById('modal-tags').innerText     = d.tags;
                document.getElementById('modal-tag-count').innerText= d.tags.split(',').length + ' tags';
                document.getElementById('modal-ai-box').innerHTML   = '<p>Click below to generate AI insights for this product.</p><button class="ai-btn" onclick="optimizeModalProduct()" style="margin-top:10px;">✨ Generate AI Insights</button>';
                document.getElementById('productModal').classList.add('active');
                document.body.style.overflow = 'hidden';
            }}

            function closeModal() {{
                document.getElementById('productModal').classList.remove('active');
                document.body.style.overflow = '';
            }}

            document.getElementById('productModal').addEventListener('click', function(e) {{
                if (e.target === this) closeModal();
            }});

            document.addEventListener('keydown', function(e) {{
                if (e.key === 'Escape') closeModal();
            }});

            async function optimizeModalProduct() {{
                const title = document.getElementById('modal-title').innerText;
                const box   = document.getElementById('modal-ai-box');
                box.innerHTML = '<p>⏳ Generating AI insights...</p>';
                try {{
                    const res  = await fetch('/optimize', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{title: title, description: ''}})
                    }});
                    const data = await res.json();
                    box.innerHTML = '<p><b>✦ Optimized Title:</b> ' + data.optimized_title + '</p>' +
                                    '<p><b>📌 Key Points:</b> ' + data.bullet_points.join(' · ') + '</p>' +
                                    '<p><b>📝 Description:</b> ' + data.optimized_description + '</p>';
                }} catch(e) {{
                    box.innerHTML = '<p>❌ AI Error. Try again.</p>';
                }}
            }}

            const ctx = document.getElementById('categoryChart');
            if (ctx) {{
                new Chart(ctx, {{
                    type: 'pie',
                    data: {{
                        labels: {category_labels_json},
                        datasets: [{{
                            label: 'Products',
                            data: {category_counts_json},
                            borderWidth: 1
                        }}]
                    }},
                    options: {{
                        layout: {{ padding: 20 }},
                        plugins: {{ legend: {{ position: 'bottom' }} }}
                    }}
                }});
            }}
        </script>
    </body>
    </html>
    """


# AI Route
@app.route('/optimize', methods=['POST'])
def optimize_product():
    return jsonify(ai_optimize_product("", ""))


# EXPORT ROUTES
@app.route('/export/<platform>')
@login_required
def export_platform(platform):
    products = Product.query.filter_by(user_id=current_user.id).all()
    if not products:
        return "No catalog found"

    df = pd.DataFrame([{
        "title":       p.title,
        "description": p.description,
        "price":       p.price,
        "image":       p.image,
        "category":    p.category,
        "stock":       p.stock
    } for p in products])

    title_col    = "title"
    desc_col     = "description"
    image_col    = "image"
    price_col    = "price"
    category_col = "category" 

    if platform == "daraz":
        export_df = pd.DataFrame({
            "Product Name": df[title_col],
            "Description":  df[desc_col],
            "Price":        df[price_col],
            "Main Images":  df[image_col],
            "Category":     df[category_col]
        })
    elif platform == "shopify":
        export_df = pd.DataFrame({
            "Title":        df[title_col],
            "Body (HTML)":  df[desc_col],
            "Variant Price":df[price_col],
            "Image Src":    df[image_col],
            "Type":         df[category_col]
        })
    elif platform == "facebook":
        export_df = pd.DataFrame({
            "title":        df[title_col],
            "description":  df[desc_col],
            "availability": "in stock",
            "condition":    "new",
            "price":        df[price_col].astype(str) + " NPR",
            "image_link":   df[image_col]
        })
    elif platform == "instagram":
        export_df = pd.DataFrame({
            "id":                    range(1, len(df)+1),
            "title":                 df[title_col],
            "description":           df[desc_col],
            "availability":          "in stock",
            "condition":             "new",
            "price":                 df[price_col].astype(str) + " NPR",
            "image_link":            df[image_col],
            "brand":                 "MyBrand",
            "google_product_category": df[category_col]
        })
    elif platform == "tiktok":
        export_df = pd.DataFrame({
            "Product Name":        df[title_col],
            "Product Description": df[desc_col],
            "Price":               df[price_col],
            "Main Image":          df[image_col],
            "Category":            df[category_col]
        })
    else:
        return "Invalid platform"

    csv_data = export_df.to_csv(index=False)
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={platform}_export.csv"}
    )


@app.route('/clear-products', methods=['POST'])
@login_required
def clear_products():
    Product.query.filter_by(user_id=current_user.id).delete(synchronize_session=False)
    db.session.commit()
    return redirect('/')


@app.route('/health')
def health():
    return 'OK', 200


def create_tables():
    with app.app_context():
        from sqlalchemy import text
        db.create_all()
        with db.engine.connect() as conn:
            for sql in [
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS catalog_path VARCHAR(500)',
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS catalog_data TEXT',
                'ALTER TABLE product ADD COLUMN IF NOT EXISTS user_id INTEGER',
                'ALTER TABLE product ADD COLUMN IF NOT EXISTS stock INTEGER DEFAULT 0',
                'ALTER TABLE product ADD COLUMN IF NOT EXISTS category VARCHAR(200)',
                'ALTER TABLE product ADD COLUMN IF NOT EXISTS image TEXT',
                'ALTER TABLE product ADD COLUMN IF NOT EXISTS description TEXT',
                'ALTER TABLE product ADD COLUMN IF NOT EXISTS price FLOAT',
                'ALTER TABLE product ADD COLUMN IF NOT EXISTS title VARCHAR(500)',
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE',
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS verify_token VARCHAR(200)',
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS reset_token VARCHAR(200)',
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS reset_expiry TIMESTAMP',
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS created_at TIMESTAMP',
            ]:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except:
                    pass

create_tables()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)