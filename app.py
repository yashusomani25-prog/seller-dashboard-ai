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
db            = SQLAlchemy(app)
mail          = Mail(app)
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
    if "dropbox.com" in url:
        return url.replace("www.dropbox.com", "dl.dropboxusercontent.com").replace("?dl=0", "?raw=1")
    if "1drv.ms" in url or "onedrive.live.com" in url:
        return url
    if "daraz" in url or "lazada" in url or "alicdn" in url:
        return url
    if "amazon.com" in url or "amazonaws.com" in url or "ssl-images-amazon" in url:
        return url
    if "shopify.com" in url or "cdn.shopify" in url:
        return url
    if any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".svg"]):
        return url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return "https://placehold.co/600x400?text=No+Image"

def fix_google_drive_link(url):
    return process_image_url(url)

app.jinja_env.globals.update(process_image_url=process_image_url)


# =========================================================
# HELPERS
# =========================================================
def find_column(df, keywords):
    for col in df.columns:
        for keyword in keywords:
            if keyword in col.lower():
                return col
    return None

def generate_sku(title):
    title = str(title).upper()
    words = title.split()[:3]
    short = ''.join(word[:3] for word in words)
    random_part = ''.join(random.choices(string.digits, k=4))
    return f"{short}-{random_part}"

def generate_tags(title, category):
    title_words    = str(title).lower().split()
    category_words = str(category).lower().split()
    tags = list(set(title_words + category_words))
    return ', '.join(tags[:8])

def ai_optimize_product(title, description, category=""):
    title       = str(title).replace("nan", "").strip()
    description = str(description).replace("nan", "").strip()
    category    = str(category).replace("nan", "").strip()
    optimized_title = f"Premium {title} | Best {category} Product in Nepal"
    bullet_points = [
        "✔ High quality & durable build",
        "✔ Fast delivery all over Nepal",
        "✔ Trusted seller product",
        "✔ Excellent value for money",
        "✔ Ideal for everyday usage"
    ]
    seo_keywords = [word.lower() for word in title.split() if len(word) > 3]
    seo_tags     = ", ".join(seo_keywords[:10])
    optimized_description = (
        f"{title}\n\n{description}\n\n"
        "Why choose this product?\n"
        "• Premium quality materials\n"
        "• Reliable performance\n"
        "• Affordable pricing\n"
        "• Fast nationwide delivery\n\n"
        f"Perfect for customers looking for quality {category} products in Nepal.\n\n"
        f"SEO Tags: {seo_tags}"
    )
    return {
        "optimized_title":       optimized_title,
        "bullet_points":         bullet_points,
        "optimized_description": optimized_description,
        "seo_tags":              seo_tags
    }

def send_email(to, subject, body):
    try:
        msg = Message(subject, sender=app.config['MAIL_FROM'], recipients=[to])
        msg.html = body
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


# =========================================================
# AUTH STYLES (shared)
# =========================================================
AUTH_STYLE = """
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'Inter',sans-serif;background:linear-gradient(135deg,#1d4ed8 0%,#7c3aed 60%,#db2777 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;}
.card{background:white;border-radius:24px;padding:40px 36px;width:100%;max-width:420px;box-shadow:0 24px 64px rgba(0,0,0,0.25);animation:slideUp 0.5s cubic-bezier(.16,1,.3,1);}
@keyframes slideUp{from{opacity:0;transform:translateY(30px);}to{opacity:1;transform:translateY(0);}}
.logo{text-align:center;margin-bottom:28px;}
.logo-icon{width:64px;height:64px;border-radius:18px;background:linear-gradient(135deg,#1d4ed8,#7c3aed);display:inline-flex;align-items:center;justify-content:center;font-size:30px;margin-bottom:12px;}
.logo h1{font-size:22px;font-weight:800;color:#0f172a;}
.logo p{font-size:13px;color:#64748b;margin-top:4px;}
.error{background:#fee2e2;color:#dc2626;padding:10px 14px;border-radius:10px;font-size:13px;margin-bottom:16px;}
.success{background:#dcfce7;color:#15803d;padding:10px 14px;border-radius:10px;font-size:13px;margin-bottom:16px;}
.info{background:#eff6ff;color:#1d4ed8;padding:10px 14px;border-radius:10px;font-size:13px;margin-bottom:16px;}
.error a{color:#dc2626;font-weight:700;}
label{display:block;font-size:13px;font-weight:600;color:#374151;margin-bottom:6px;}
input{width:100%;padding:12px 16px;border:1.5px solid #e2e8f0;border-radius:10px;font-size:14px;font-family:'Inter',sans-serif;color:#0f172a;outline:none;transition:border-color 0.2s;margin-bottom:16px;}
input:focus{border-color:#7c3aed;box-shadow:0 0 0 3px rgba(124,58,237,0.1);}
button{width:100%;padding:13px;background:linear-gradient(135deg,#1d4ed8,#7c3aed);color:white;border:none;border-radius:10px;font-size:15px;font-weight:700;font-family:'Inter',sans-serif;cursor:pointer;transition:all 0.2s;margin-top:4px;}
button:hover{opacity:0.9;transform:translateY(-1px);}
.link{text-align:center;margin-top:16px;font-size:13px;color:#64748b;}
.link a{color:#7c3aed;font-weight:600;text-decoration:none;}
.forgot{text-align:right;margin-top:-10px;margin-bottom:16px;}
.forgot a{font-size:12px;color:#7c3aed;text-decoration:none;font-weight:500;}
</style>
"""

AUTH_HEAD = """
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
"""


# =========================================================
# REGISTER
# =========================================================
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
    error_html = f'<div class="error">&#x26A0; {error}</div>' if error else ''
    return f"""<!DOCTYPE html>
<html><head>{AUTH_HEAD}<title>Register - Seller AI</title>{AUTH_STYLE}</head><body>
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


# =========================================================
# VERIFY EMAIL
# =========================================================
@app.route('/verify/<token>')
def verify_email(token):
    user = User.query.filter_by(verify_token=token).first()
    if user:
        user.is_verified  = True
        user.verify_token = None
        db.session.commit()
        return redirect('/login?msg=verified')
    return redirect('/login?msg=invalid')


# =========================================================
# RESEND VERIFICATION  ← NEW
# =========================================================
@app.route('/resend-verification', methods=['GET', 'POST'])
def resend_verification():
    message   = ""
    msg_type  = ""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user  = User.query.filter_by(email=email).first()
        if user and not user.is_verified:
            token             = secrets.token_urlsafe(32)
            user.verify_token = token
            db.session.commit()
            verify_url = f"{request.host_url}verify/{token}"
            send_email(email, "Verify your Seller AI account",
                "<div style='font-family:Arial;max-width:500px;margin:0 auto;padding:20px;'>"
                f"<h2 style='color:#1d4ed8;'>Verify your Seller AI account</h2>"
                "<p>You requested a new verification link. Click below to verify your email.</p>"
                f"<a href='{verify_url}' style='display:inline-block;background:#1d4ed8;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;margin:16px 0;'>Verify Email</a>"
                "<p style='color:#64748b;font-size:13px;'>If you did not request this, ignore this email.</p>"
                "</div>"
            )
        message  = "If that email exists and is unverified, a new verification link has been sent."
        msg_type = "info"
    msg_html = f'<div class="{msg_type}">&#x2709; {message}</div>' if message else ''
    return f"""<!DOCTYPE html>
<html><head>{AUTH_HEAD}<title>Resend Verification - Seller AI</title>{AUTH_STYLE}</head><body>
<div class="card">
    <div class="logo">
        <div class="logo-icon">&#x2709;</div>
        <h1>Resend Verification</h1>
        <p>We'll send you a new verification link</p>
    </div>
    {msg_html}
    <form method="POST">
        <label>Email</label>
        <input name="email" type="email" placeholder="you@example.com" required>
        <button type="submit">Send Verification Link &#x2192;</button>
    </form>
    <div class="link"><a href="/login">&#x2190; Back to login</a></div>
</div>
</body></html>"""


# =========================================================
# FORGOT PASSWORD
# =========================================================
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    message = ""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user  = User.query.filter_by(email=email).first()
        if user:
            token             = secrets.token_urlsafe(32)
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
    msg_html = f'<div class="info">&#x2709; {message}</div>' if message else ''
    return f"""<!DOCTYPE html>
<html><head>{AUTH_HEAD}<title>Forgot Password - Seller AI</title>{AUTH_STYLE}</head><body>
<div class="card">
    <div class="logo">
        <div class="logo-icon">&#x1F511;</div>
        <h1>Forgot Password</h1>
        <p>We'll send you a reset link</p>
    </div>
    {msg_html}
    <form method="POST">
        <label>Email</label>
        <input name="email" type="email" placeholder="you@example.com" required>
        <button type="submit">Send Reset Link &#x2192;</button>
    </form>
    <div class="link"><a href="/login">&#x2190; Back to login</a></div>
</div>
</body></html>"""


# =========================================================
# RESET PASSWORD
# =========================================================
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
            user.password     = generate_password_hash(password)
            user.reset_token  = None
            user.reset_expiry = None
            db.session.commit()
            return redirect('/login?msg=reset')
    error_html = f'<div class="error">&#x26A0; {error}</div>' if error else ''
    return f"""<!DOCTYPE html>
<html><head>{AUTH_HEAD}<title>Reset Password - Seller AI</title>{AUTH_STYLE}</head><body>
<div class="card">
    <div class="logo">
        <div class="logo-icon">&#x1F511;</div>
        <h1>New Password</h1>
        <p>Choose a strong password</p>
    </div>
    {error_html}
    <form method="POST">
        <label>New Password</label>
        <input name="password" type="password" placeholder="Min 6 characters" required>
        <button type="submit">Save Password &#x2192;</button>
    </form>
</div>
</body></html>"""


# =========================================================
# LOGIN
# =========================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    error    = ""
    msg      = request.args.get('msg', '')
    msg_map  = {
        'verify':   ('info',    'Account created! Please check your email to verify your account.'),
        'verified': ('success', 'Email verified! You can now login.'),
        'reset':    ('success', 'Password reset successfully! Please login.'),
        'expired':  ('error',   'Reset link expired. Please request a new one.'),
        'invalid':  ('error',   'Invalid verification link.'),
    }
    msg_type, msg_text = msg_map.get(msg, ('', ''))
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user     = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            if not user.is_verified:
                # Show error WITH resend link
                error = "Please verify your email first. <a href='/resend-verification'>Resend verification email &rarr;</a>"
            else:
                login_user(user)
                return redirect('/')
        else:
            error = "Invalid email or password"
    error_html = f'<div class="error">&#x26A0; {error}</div>' if error else ''
    msg_html   = f'<div class="{msg_type}">{"&#x2705;" if msg_type=="success" else "&#x2139;"} {msg_text}</div>' if msg_type else ''
    return f"""<!DOCTYPE html>
<html><head>{AUTH_HEAD}<title>Login - Seller AI</title>{AUTH_STYLE}</head><body>
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
    <div class="link" style="margin-top:10px;">Didn't get verification email? <a href="/resend-verification">Resend it</a></div>
</div>
</body></html>"""


# =========================================================
# DELETE / EDIT / LOGOUT
# =========================================================
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


# =========================================================
# MAIN DASHBOARD
# =========================================================
@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    global uploaded_df
    cards                  = ""
    total_products         = 0
    duplicate_products     = 0
    missing_images         = 0
    avg_price              = 0
    category_labels        = []
    category_counts        = []
    total_inventory_value  = 0
    low_stock_count        = 0
    total_potential_profit = 0
    category_options       = ""

    if request.method == 'POST':
        file = request.files.get('file')
        if file and file.filename:
            if file.filename.endswith('.csv'):
                uploaded_df = pd.read_csv(file)
            else:
                uploaded_df = pd.read_excel(file)

            catalog_dir  = 'catalogs'
            os.makedirs(catalog_dir, exist_ok=True)
            catalog_path = os.path.join(catalog_dir, f'catalog_{current_user.id}.csv')
            uploaded_df.to_csv(catalog_path, index=False)
            current_user.catalog_path = catalog_path
            current_user.catalog_data = uploaded_df.to_csv(index=False)
            db.session.commit()

            uploaded_df.columns = uploaded_df.columns.str.strip().str.lower()
            title_col        = find_column(uploaded_df, ['product title', 'title', 'name']) or uploaded_df.columns[0]
            desc_col         = find_column(uploaded_df, ['description', 'details']) or title_col
            image_col        = find_column(uploaded_df, ['image', 'photo', 'img']) or title_col
            price_col        = find_column(uploaded_df, ['price', 'sale price']) or title_col
            category_col     = find_column(uploaded_df, ['category', 'type']) or title_col
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
                existing = Product.query.filter_by(title=title, user_id=current_user.id).first()
                if not existing:
                    db.session.add(Product(
                        user_id=current_user.id,
                        title=title, description=description,
                        category=category, image=image,
                        price=price, stock=stock
                    ))
            db.session.commit()

    # AUTO-LOAD CATALOG IF NO PRODUCTS
    if not Product.query.filter_by(user_id=current_user.id).first():
        auto_csv = None
        auto_df  = None
        if current_user.catalog_path and os.path.exists(current_user.catalog_path):
            auto_csv = current_user.catalog_path
        elif current_user.catalog_data:
            auto_df  = pd.read_csv(io.StringIO(current_user.catalog_data))
            auto_csv = "from_db"
        if auto_csv:
            if auto_csv != "from_db":
                auto_df = pd.read_csv(auto_csv)
            auto_df.columns  = auto_df.columns.str.strip().str.lower()
            _title_col    = find_column(auto_df, ['product title', 'title', 'name']) or auto_df.columns[0]
            _desc_col     = find_column(auto_df, ['description', 'details']) or _title_col
            _image_col    = find_column(auto_df, ['image', 'photo', 'img']) or _title_col
            _price_col    = find_column(auto_df, ['price', 'sale price']) or _title_col
            _category_col = find_column(auto_df, ['category', 'type']) or _title_col
            _stock_col    = find_column(auto_df, ['availability', 'stock', 'quantity', 'qty', 'inventory'])
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
        data = [{
            "id":          p.id,
            "title":       p.title,
            "description": p.description,
            "category":    p.category,
            "image":       p.image,
            "price":       p.price,
            "stock":       p.stock
        } for p in products]
        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip().str.lower()

        title_col    = "title"
        desc_col     = "description"
        image_col    = "image"
        price_col    = "price"
        category_col = "category"
        link_col     = None
        stock_col    = "stock"

        search = request.args.get('search', '').lower()
        if search:
            df = df[df[title_col].astype(str).str.lower().str.contains(search)]

        sort_option   = request.args.get('sort', '')
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
            title        = str(row.get(title_col, 'Untitled Product')).replace("nan", "").strip() or "Untitled Product"
            description  = str(row.get(desc_col, 'No description')).strip()
            category     = str(row.get(category_col, 'General')).replace("nan", "").strip()
            if not category or category.lower() in ['google_product_category', 'category', 'type']:
                category = "General"

            image         = fix_google_drive_link(row.get(image_col, ''))
            image_warning = ""
            image_class   = ""
            if "placehold.co" in image or not image or image == "nan":
                image_warning = "<div class='image-warning'>&#x26A0; Missing Image</div>"
                image_class   = "bad-image"
            elif not (image.startswith("http://") or image.startswith("https://")):
                image_warning = "<div class='image-warning'>&#x26A0; Invalid Image URL</div>"
                image_class   = "bad-image"

            try:
                raw_price = str(row.get(price_col, 0)).replace(",", "").strip()
                price     = 0 if raw_price.lower() == "nan" else float(raw_price)
            except:
                price = 0

            updated_price = round(price * (1 + bulk_percent / 100), 2)
            cost_price    = round(price * 0.7, 2)
            profit        = round(updated_price - cost_price, 2)

            try:
                stock = int(float(str(row.get(stock_col, 0)).replace(',', '').strip())) if stock_col else 0
            except:
                stock = 0

            if stock <= 5:
                stock_status = "&#x1F534; Low Stock"
                stock_class  = "low-stock"
                low_stock_count += 1
            else:
                stock_status = "&#x1F7E2; In Stock"
                stock_class  = "in-stock"

            profit_per_sale        = round(price * 0.30, 2)
            inventory_value        = round(updated_price * stock, 2)
            total_inventory_value  += inventory_value
            total_potential_profit += profit_per_sale * stock

            sku        = generate_sku(title)
            tags       = generate_tags(title, category)
            short_desc = description[:140] + "..." if len(description) > 140 else description

            daraz_link = str(row.get(link_col, '')).strip() if link_col else ''
            daraz_btn  = f'<a href="{daraz_link}" target="_blank"><button class="daraz-btn">&#x1F6D2; View on Daraz</button></a>' if daraz_link and daraz_link.lower() != 'nan' else ''

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
                {"<div class='duplicate-badge'>Duplicate</div>" if is_duplicate else ""}
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
                    <button class="ai-btn" onclick="optimizeProduct({i})">&#x2728; AI Optimize Listing</button>
                    {daraz_btn}
                    <button class="view-btn" onclick="openModal({i})">&#x1F441; View Product</button>
                    <a href="/edit/{row['id']}" style="display:block;margin-top:5px;"><button class="blue" style="width:100%;padding:11px;border-radius:10px;font-size:13px;">&#x270F;&#xFE0F; Edit</button></a>
                    <a href="/delete/{row['id']}" style="display:block;margin-top:5px;"><button class="orange" style="width:100%;padding:11px;border-radius:10px;font-size:13px;">&#x1F5D1;&#xFE0F; Delete</button></a>
                </div>
            </div>
            """

    category_labels_json = json.dumps(category_labels)
    category_counts_json = json.dumps(category_counts)

    return f"""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Seller Automation Dashboard</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{ font-family: 'Inter', Arial, sans-serif; background: #f0f2f8; color: #1e293b; }}
            .dark {{ background: #0a0f1e !important; color: #e2e8f0 !important; }}
            .dark .header {{ background: linear-gradient(135deg, #1e1b4b, #312e81) !important; }}
            .dark .stat-card {{ background: #1e293b !important; color: #e2e8f0 !important; }}
            .dark .card {{ background: #1e293b !important; color: #e2e8f0 !important; }}
            .dark .chart-box {{ background: #1e293b !important; }}
            .dark .modal-box {{ background: #1e293b !important; color: #e2e8f0 !important; }}
            .dark input, .dark select {{ background: #1e293b; color: #e2e8f0; border-color: #334155; }}
            .dark .title {{ color: #f1f5f9 !important; }}
            .dark .price-section {{ background: #0f172a !important; }}
            .dark .modal-stat {{ background: #0f172a !important; }}
            .dark .modal-description {{ background: #0f172a !important; color: #cbd5e1 !important; }}
            .header {{ background: linear-gradient(135deg, #1d4ed8, #7c3aed); padding: 28px 32px; box-shadow: 0 4px 24px rgba(29,78,216,0.3); }}
            .header h1 {{ margin: 0; font-size: 32px; font-weight: 800; color: white; letter-spacing: -0.5px; }}
            .header h3 {{ color: rgba(255,255,255,0.75); font-weight: 400; font-size: 14px; margin-top: 4px; }}
            .controls {{ display: flex; gap: 10px; margin-top: 20px; flex-wrap: wrap; align-items: center; }}
            input, select {{ padding: 11px 16px; border-radius: 10px; border: 1.5px solid rgba(255,255,255,0.25); background: rgba(255,255,255,0.15); color: white; font-size: 14px; font-family: 'Inter', sans-serif; min-width: 180px; backdrop-filter: blur(4px); }}
            input::placeholder {{ color: rgba(255,255,255,0.6); }}
            select option {{ background: #1e293b; color: white; }}
            button {{ padding: 11px 20px; border: none; border-radius: 10px; color: white; cursor: pointer; font-size: 13px; font-weight: 600; font-family: 'Inter', sans-serif; transition: all 0.2s ease; white-space: nowrap; }}
            button:hover {{ opacity: 0.88; transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.2); }}
            .blue   {{ background: rgba(255,255,255,0.2); backdrop-filter: blur(4px); border: 1.5px solid rgba(255,255,255,0.3); }}
            .green  {{ background: #059669; }}
            .orange {{ background: #ea580c; }}
            .pink   {{ background: #db2777; }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 18px; padding: 28px 32px; }}
            .stat-card {{ background: white; padding: 24px; border-radius: 16px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; transition: all 0.25s ease; position: relative; overflow: hidden; }}
            .stat-card::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, #1d4ed8, #7c3aed); border-radius: 16px 16px 0 0; }}
            .stat-card:hover {{ transform: translateY(-4px); box-shadow: 0 8px 24px rgba(0,0,0,0.1); }}
            .stat-number {{ font-size: 28px; font-weight: 800; color: #1d4ed8; line-height: 1.2; }}
            .stat-card p {{ color: #64748b; font-size: 13px; margin-top: 6px; font-weight: 500; }}
            .charts-container {{ padding: 0 32px 20px; }}
            .chart-box {{ background: white; padding: 24px; border-radius: 16px; margin: 0 auto; box-shadow: 0 2px 12px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; max-width: 600px; }}
            #categoryChart {{ max-height: 360px; }}
            .products {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 22px; padding: 8px 32px 40px; }}
            .card {{ background: white; border-radius: 18px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; position: relative; transition: all 0.3s ease; }}
            .card:hover {{ transform: translateY(-5px); box-shadow: 0 12px 32px rgba(0,0,0,0.12); }}
            .product-image {{ width: 100%; height: 260px; object-fit: cover; background: #f8fafc; }}
            .card-body {{ padding: 20px; }}
            .category-badge {{ position: absolute; top: 12px; left: 12px; background: linear-gradient(135deg, #1d4ed8, #7c3aed); color: white; padding: 5px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; z-index: 5; letter-spacing: 0.3px; text-transform: uppercase; }}
            .title {{ font-size: 16px; font-weight: 700; color: #0f172a; line-height: 1.4; margin-bottom: 10px; }}
            .description {{ font-size: 13px; color: #64748b; line-height: 1.6; margin-top: 8px; }}
            .price-section {{ background: linear-gradient(135deg, #eff6ff, #f0fdf4); padding: 12px 14px; border-radius: 12px; margin: 12px 0; border: 1px solid #dbeafe; }}
            .old-price {{ color: #94a3b8; font-size: 12px; margin-bottom: 2px; }}
            .new-price {{ color: #059669; font-size: 20px; font-weight: 800; }}
            .low-stock {{ color: #dc2626; font-weight: 600; font-size: 13px; }}
            .in-stock  {{ color: #059669; font-weight: 600; font-size: 13px; }}
            .duplicate-card {{ border: 2px solid #ef4444; box-shadow: 0 0 0 3px rgba(239,68,68,0.15); }}
            .duplicate-badge {{ position: absolute; top: 44px; left: 12px; background: #ef4444; color: white; padding: 4px 10px; border-radius: 999px; font-size: 10px; font-weight: 700; z-index: 10; text-transform: uppercase; }}
            .image-warning {{ position: absolute; top: 12px; right: 12px; background: #ea580c; color: white; padding: 5px 10px; border-radius: 8px; font-size: 11px; font-weight: 700; z-index: 5; }}
            .bad-image {{ border-bottom: 3px solid #ea580c; }}
            .ai-btn {{ background: linear-gradient(135deg, #7c3aed, #db2777); width: 100%; margin: 10px 0 6px; font-weight: 700; font-size: 13px; padding: 12px; border-radius: 10px; }}
            .daraz-btn {{ background: linear-gradient(135deg, #f85606, #f59e0b); width: 100%; margin: 4px 0; font-weight: 700; font-size: 13px; padding: 11px; border-radius: 10px; }}
            .view-btn {{ width: 100%; margin-top: 6px; background: #0f172a; color: white; padding: 12px; border-radius: 10px; font-weight: 600; font-size: 13px; }}
            .view-btn:hover {{ background: #1d4ed8; }}
            .modal-overlay {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.65); backdrop-filter: blur(4px); z-index: 1000; overflow-y: auto; padding: 40px 20px; box-sizing: border-box; }}
            .modal-overlay.active {{ display: block; }}
            .modal-box {{ background: white; border-radius: 20px; max-width: 820px; width: 100%; box-shadow: 0 24px 64px rgba(0,0,0,0.35); animation: slideUp 0.3s cubic-bezier(.16,1,.3,1); margin: 0 auto 40px auto; overflow: hidden; }}
            @keyframes slideUp {{ from {{ transform: translateY(50px); opacity: 0; }} to {{ transform: translateY(0); opacity: 1; }} }}
            .modal-image {{ width: 100%; height: 280px; object-fit: contain; background: #f8fafc; display: block; }}
            .modal-header-wrap {{ position: relative; border-bottom: 1px solid #f1f5f9; }}
            .modal-body {{ padding: 28px; }}
            .modal-title {{ font-size: 22px; font-weight: 800; margin: 0 0 14px; color: #0f172a; line-height: 1.3; }}
            .modal-badges {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }}
            .modal-badge {{ padding: 4px 12px; border-radius: 999px; font-size: 12px; font-weight: 600; }}
            .badge-blue  {{ background: #dbeafe; color: #1d4ed8; }}
            .badge-green {{ background: #dcfce7; color: #059669; }}
            .modal-stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 18px 0; }}
            .modal-stat {{ background: #f8fafc; border-radius: 12px; padding: 14px; text-align: center; border: 1px solid #e2e8f0; }}
            .modal-stat-number {{ font-size: 18px; font-weight: 800; color: #1d4ed8; }}
            .modal-stat-label  {{ font-size: 11px; color: #94a3b8; margin-top: 4px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.4px; }}
            .modal-section-title {{ font-size: 13px; font-weight: 700; color: #64748b; margin: 18px 0 8px; text-transform: uppercase; letter-spacing: 0.6px; }}
            .modal-description {{ font-size: 14px; color: #475569; line-height: 1.7; background: #f8fafc; padding: 14px; border-radius: 10px; border: 1px solid #e2e8f0; }}
            .modal-ai-box {{ background: linear-gradient(135deg, #f3e8ff, #fce7f3); border-radius: 12px; padding: 16px; margin-top: 14px; border: 1px solid #e9d5ff; }}
            .modal-ai-box p {{ font-size: 14px; color: #6b21a8; margin: 5px 0; line-height: 1.6; }}
            .modal-close {{ position: absolute; top: 14px; right: 14px; font-size: 18px; cursor: pointer; background: white; border: 1px solid #e2e8f0; border-radius: 50%; width: 34px; height: 34px; color: #64748b; box-shadow: 0 2px 8px rgba(0,0,0,0.1); z-index: 10; transition: all 0.2s; display: flex; align-items: center; justify-content: center; }}
            .modal-close:hover {{ background: #fee2e2; color: #dc2626; border-color: #fecaca; }}
            #splash {{ position: fixed; inset: 0; background: linear-gradient(135deg, #1d4ed8 0%, #7c3aed 60%, #db2777 100%); z-index: 9999; display: flex; flex-direction: column; align-items: center; justify-content: center; transition: opacity 0.6s ease, transform 0.6s ease; }}
            #splash.hide {{ opacity: 0; transform: translateY(-30px); pointer-events: none; }}
            .splash-logo {{ width: 90px; height: 90px; background: rgba(255,255,255,0.15); border-radius: 24px; display: flex; align-items: center; justify-content: center; font-size: 44px; border: 2px solid rgba(255,255,255,0.3); box-shadow: 0 8px 32px rgba(0,0,0,0.2); animation: logoPulse 1.2s ease-in-out infinite alternate; }}
            .splash-name {{ color: white; font-size: 28px; font-weight: 800; margin-top: 20px; }}
            .splash-sub  {{ color: rgba(255,255,255,0.65); font-size: 14px; margin-top: 8px; }}
            .splash-dots {{ display: flex; gap: 8px; margin-top: 40px; }}
            .splash-dots span {{ width: 8px; height: 8px; background: rgba(255,255,255,0.5); border-radius: 50%; animation: dotBounce 1.2s ease-in-out infinite; }}
            .splash-dots span:nth-child(2) {{ animation-delay: 0.2s; }}
            .splash-dots span:nth-child(3) {{ animation-delay: 0.4s; }}
            @keyframes logoPulse {{ from {{ transform: scale(1); }} to {{ transform: scale(1.08); }} }}
            @keyframes dotBounce {{ 0%,100% {{ transform: translateY(0); opacity:0.5; }} 50% {{ transform: translateY(-8px); opacity:1; }} }}
            @media (max-width: 768px) {{
                .header {{ padding: 20px 16px; }}
                .header h1 {{ font-size: 22px; }}
                .stats {{ grid-template-columns: repeat(2,1fr); gap: 12px; padding: 16px; }}
                .charts-container {{ padding: 0 16px 16px; }}
                .products {{ grid-template-columns: 1fr; gap: 16px; padding: 8px 16px 32px; }}
                .product-image {{ height: 200px; }}
                .modal-stats {{ grid-template-columns: repeat(2,1fr); }}
                .modal-body {{ padding: 18px; }}
            }}
        </style>
    </head>
    <body>
        <div id="splash">
            <div class="splash-logo">&#x1F6D2;</div>
            <div class="splash-name">Seller AI</div>
            <div class="splash-sub">Automation Dashboard</div>
            <div class="splash-dots"><span></span><span></span><span></span></div>
        </div>

        <div class="header">
            <h1>&#x1F6D2; Seller AI Dashboard</h1>
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

        <div class="modal-overlay" id="productModal">
            <div class="modal-box">
                <div class="modal-header-wrap">
                    <img id="modal-image" src="" class="modal-image" onerror="this.src='https://placehold.co/860x420/f1f1f1/888?text=No+Image';">
                    <button class="modal-close" onclick="closeModal()">&#x2715;</button>
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
                    <div class="modal-section-title">&#x1F4DD; Full Description</div>
                    <div class="modal-description" id="modal-desc"></div>
                    <div class="modal-section-title">&#x1F3F7;&#xFE0F; Tags</div>
                    <div class="modal-description" id="modal-tags"></div>
                    <div class="modal-section-title">&#x2728; AI Insights</div>
                    <div class="modal-ai-box" id="modal-ai-box">
                        <p>Click below to generate AI insights for this product.</p>
                        <button class="ai-btn" id="modal-ai-btn" style="margin-top:10px;">&#x2728; Generate AI Insights</button>
                    </div>
                </div>
            </div>
        </div>

        <script>
            window.addEventListener('load', function() {{
                setTimeout(function() {{
                    document.getElementById('splash').classList.add('hide');
                    setTimeout(function() {{ document.getElementById('splash').style.display = 'none'; }}, 650);
                }}, 1800);
            }});
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
                const btn  = card.querySelector('.ai-btn');
                const oldText = btn.innerHTML;
                btn.innerHTML = "&#x23F3; Optimizing...";
                btn.disabled  = true;
                try {{
                    const res  = await fetch('/optimize', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{
                            title:       card.dataset.title,
                            description: card.dataset.desc,
                            category:    card.dataset.category
                        }})
                    }});
                    const data = await res.json();
                    card.querySelector('.title').innerHTML       = "&#x2726; " + data.optimized_title;
                    card.querySelector('.description').innerHTML = data.optimized_description;
                    alert("&#x2705; AI Listing Optimized!");
                }} catch(e) {{
                    alert("AI Error");
                }} finally {{
                    btn.innerHTML = oldText;
                    btn.disabled  = false;
                }}
            }}
            function openModal(index) {{
                const card = document.querySelectorAll('.card')[index];
                if (!card) return;
                const d = card.dataset;
                document.getElementById('modal-image').src           = d.image;
                document.getElementById('modal-title').innerText     = d.title;
                document.getElementById('modal-category').innerText  = d.category;
                document.getElementById('modal-sku').innerText       = d.sku;
                document.getElementById('modal-price').innerText     = d.price;
                document.getElementById('modal-updated').innerText   = d.updated;
                document.getElementById('modal-stock').innerText     = d.stock;
                document.getElementById('modal-profit').innerText    = d.profit;
                document.getElementById('modal-inventory').innerText = d.inventory;
                document.getElementById('modal-desc').innerText      = d.desc;
                document.getElementById('modal-tags').innerText      = d.tags;
                document.getElementById('modal-tag-count').innerText = d.tags.split(',').length + ' tags';
                document.getElementById('modal-ai-box').innerHTML    =
                    '<p>Click below to generate AI insights for this product.</p>' +
                    '<button class="ai-btn" onclick="optimizeModalProduct()" style="margin-top:10px;">&#x2728; Generate AI Insights</button>';
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
                box.innerHTML = '<p>&#x23F3; Generating AI insights...</p>';
                try {{
                    const res  = await fetch('/optimize', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{title: title, description: ''}})
                    }});
                    const data = await res.json();
                    box.innerHTML =
                        '<p><b>&#x2726; Optimized Title:</b> '    + data.optimized_title + '</p>' +
                        '<p><b>&#x1F4CC; Key Points:</b> '        + data.bullet_points.join(' &middot; ') + '</p>' +
                        '<p><b>&#x1F4DD; Description:</b> '       + data.optimized_description + '</p>';
                }} catch(e) {{
                    box.innerHTML = '<p>&#x274C; AI Error. Try again.</p>';
                }}
            }}
            const ctx = document.getElementById('categoryChart');
            if (ctx) {{
                new Chart(ctx, {{
                    type: 'pie',
                    data: {{
                        labels: {category_labels_json},
                        datasets: [{{ label: 'Products', data: {category_counts_json}, borderWidth: 1 }}]
                    }},
                    options: {{ layout: {{ padding: 20 }}, plugins: {{ legend: {{ position: 'bottom' }} }} }}
                }});
            }}
        </script>
    </body>
    </html>
    """


# =========================================================
# AI OPTIMIZE ROUTE
# =========================================================
@app.route('/optimize', methods=['POST'])
def optimize_product():
    data        = request.get_json() or {}
    title       = data.get('title', '')
    description = data.get('description', '')
    category    = data.get('category', '')
    return jsonify(ai_optimize_product(title, description, category))


# =========================================================
# EXPORT ROUTES
# =========================================================
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

    if platform == "daraz":
        export_df = pd.DataFrame({
            "Product Name": df["title"],
            "Description":  df["description"],
            "Price":        df["price"],
            "Main Images":  df["image"],
            "Category":     df["category"]
        })
    elif platform == "shopify":
        export_df = pd.DataFrame({
            "Title":         df["title"],
            "Body (HTML)":   df["description"],
            "Variant Price": df["price"],
            "Image Src":     df["image"],
            "Type":          df["category"]
        })
    elif platform == "facebook":
        export_df = pd.DataFrame({
            "title":        df["title"],
            "description":  df["description"],
            "availability": "in stock",
            "condition":    "new",
            "price":        df["price"].astype(str) + " NPR",
            "image_link":   df["image"]
        })
    elif platform == "instagram":
        export_df = pd.DataFrame({
            "id":                      range(1, len(df) + 1),
            "title":                   df["title"],
            "description":             df["description"],
            "availability":            "in stock",
            "condition":               "new",
            "price":                   df["price"].astype(str) + " NPR",
            "image_link":              df["image"],
            "brand":                   "MyBrand",
            "google_product_category": df["category"]
        })
    elif platform == "tiktok":
        export_df = pd.DataFrame({
            "Product Name":        df["title"],
            "Product Description": df["description"],
            "Price":               df["price"],
            "Main Image":          df["image"],
            "Category":            df["category"]
        })
    else:
        return "Invalid platform"

    csv_data = export_df.to_csv(index=False)
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={platform}_export.csv"}
    )


@app.route('/health')
def health():
    return 'OK', 200


# =========================================================
# DB INIT
# =========================================================
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
    app.run()