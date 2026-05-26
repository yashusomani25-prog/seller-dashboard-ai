from flask import Flask, request, jsonify, redirect, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import random
import string

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mysecretkey123'

# ====================== DATABASE ======================
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL") or 'sqlite:///seller_dashboard.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ====================== MODELS ======================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=False)
    password = db.Column(db.String(500), nullable=False)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    title = db.Column(db.String(500))
    description = db.Column(db.Text)
    price = db.Column(db.Float)
    stock = db.Column(db.Integer)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ====================== ROUTES ======================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = generate_password_hash(request.form.get('password'))
        if User.query.filter_by(email=email).first():
            return "User already exists"
        new_user = User(username=username, email=email, password=password)
        db.session.add(new_user)
        db.session.commit()
        return redirect('/login')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        if email == "admin@seller.com" and password == "admin123":
            user = User.query.filter_by(email=email).first()
            if not user:
                user = User(username="admin", email=email, password=generate_password_hash(password))
                db.session.add(user)
                db.session.commit()
            login_user(user)
            return redirect('/')
        return "Invalid credentials"
    return render_template('login.html')

@app.route('/')
@login_required
def dashboard():
    try:
        products = Product.query.filter_by(user_id=current_user.id).all()
        return render_template('dashboard.html', products=products, user=current_user)
    except Exception as e:
        return f"Dashboard Error: {str(e)}", 500

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/login')

@app.route('/health')
def health():
    return 'OK'

# ====================== STARTUP ======================
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)