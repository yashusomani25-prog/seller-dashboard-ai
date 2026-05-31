from datetime import datetime
import os
import re
import random
import string
import pandas as pd
from flask import Flask, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mysecretkey123')

# Database
basedir = os.path.abspath(os.path.dirname(__file__))
database_url = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'instance', 'seller_dashboard.db'))
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(200))
    image = db.Column(db.Text)
    price = db.Column(db.Float, default=0.0)
    stock = db.Column(db.Integer, default=0)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ====================== IMAGE PROCESSOR ======================
def process_image_url(url):
    if not url:
        return "https://placehold.co/600x400?text=No+Image"
    url = str(url).strip()
    if url.lower() in ["nan", "none", "", "null"]:
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
    return url if url.startswith("http") else "https://placehold.co/600x400?text=No+Image"

# ====================== DASHBOARD ======================
@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST' and 'file' in request.files:
        file = request.files['file']
        if file and file.filename.endswith(('.csv', '.xlsx')):
            try:
                if file.filename.endswith('.csv'):
                    df = pd.read_csv(file)
                else:
                    df = pd.read_excel(file)
                
                for _, row in df.iterrows():
                    product = Product(
                        user_id=current_user.id,
                        title=str(row.get('title', 'Untitled')),
                        description=str(row.get('description', '')),
                        category=str(row.get('category', 'General')),
                        image=str(row.get('image', '')),
                        price=float(row.get('price', 0) or 0),
                        stock=int(row.get('stock', 0) or 0)
                    )
                    db.session.add(product)
                db.session.commit()
            except:
                pass
            return redirect('/')

    products = Product.query.filter_by(user_id=current_user.id).all()

    cards = ""
    total_products = len(products)
    duplicates = 0
    missing_images = 0
    total_value = 0
    seen = {}

    for p in products:
        title_lower = str(p.title).strip().lower()
        if title_lower in seen:
            duplicates += 1
        seen[title_lower] = True

        if not p.image or str(p.image).lower() in ['nan', 'none', '', 'null']:
            missing_images += 1

        price = float(p.price or 0)
        stock = int(p.stock or 0)
        total_value += price * stock

        image_url = process_image_url(p.image)

        cards += f"""
        <div class="product-card">
            <div class="category-badge">{p.category or 'General'}</div>
            <img src="{image_url}" class="product-image" onerror="this.src='https://placehold.co/600x400/f1f1f1/888?text=No+Image';">
            <div class="card-body">
                <h3>{p.title}</h3>
                <p class="desc">{str(p.description or '')[:140]}...</p>
                <div class="price-stock">
                    <strong>Rs. {price:,.0f}</strong>
                    <span>Stock: {stock}</span>
                </div>
                <div class="actions">
                    <button onclick="optimizeProduct({p.id})" class="ai-btn">✨ AI Optimize</button>
                    <button onclick="window.location.href='/edit/{p.id}'" class="edit-btn">✏️ Edit</button>
                    <button onclick="deleteProduct({p.id})" class="delete-btn">🗑️ Delete</button>
                </div>
            </div>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Seller Dashboard</title>
        <style>
            * {{margin:0;padding:0;box-sizing:border-box;}}
            body {{font-family:'Segoe UI',sans-serif;background:#f8f9fa;padding:20px;}}
            h1 {{margin-bottom:20px;color:#222;}}
            .upload-form {{background:white;padding:18px;border-radius:12px;margin-bottom:25px;box-shadow:0 2px 10px rgba(0,0,0,0.1);}}
            .stats {{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:16px;margin-bottom:30px;}}
            .stat-card {{background:white;padding:18px;border-radius:12px;text-align:center;box-shadow:0 2px 10px rgba(0,0,0,0.08);}}
            .products-grid {{display:grid;grid-template-columns:repeat(auto-fill,minmax(285px,1fr));gap:22px;}}
            .product-card {{background:white;border-radius:14px;overflow:hidden;box-shadow:0 4px 15px rgba(0,0,0,0.1);transition:0.3s;position:relative;}}
            .product-card:hover {{transform:translateY(-6px);}}
            .product-image {{width:100%;height:210px;object-fit:cover;}}
            .card-body {{padding:16px;}}
            .category-badge {{position:absolute;top:12px;right:12px;background:#ff9800;color:white;padding:5px 12px;border-radius:30px;font-size:13px;}}
            .desc {{color:#555;font-size:0.93rem;margin:10px 0 12px;}}
            .price-stock {{display:flex;justify-content:space-between;margin:12px 0;font-weight:600;}}
            .actions {{display:flex;flex-direction:column;gap:9px;}}
            button {{padding:11px;border:none;border-radius:8px;cursor:pointer;font-weight:500;}}
            .ai-btn {{background:#6d28d9;color:white;}}
            .edit-btn {{background:#2563eb;color:white;}}
            .delete-btn {{background:#dc2626;color:white;}}
        </style>
    </head>
    <body>
        <h1>🏪 Seller Dashboard</h1>
        
        <div class="upload-form">
            <form method="post" enctype="multipart/form-data">
                <input type="file" name="file" accept=".csv,.xlsx">
                <button type="submit">Upload CSV / Excel</button>
            </form>
        </div>

        <div class="stats">
            <div class="stat-card"><h3>{total_products}</h3><p>Total Products</p></div>
            <div class="stat-card"><h3>{duplicates}</h3><p>Duplicates</p></div>
            <div class="stat-card"><h3>{missing_images}</h3><p>Missing Images</p></div>
            <div class="stat-card"><h3>Rs. {total_value:,.0f}</h3><p>Total Value</p></div>
        </div>

        <div class="products-grid">
            {cards if cards else "<p style='grid-column:1/-1;text-align:center;padding:50px;color:#666;'>No products yet. Upload a file.</p>"}
        </div>

        <script>
            function deleteProduct(id) {{
                if(confirm('Delete this product?')) {{
                    window.location.href = `/delete/${{id}}`;
                }}
            }}
            function optimizeProduct(id) {{
                alert('AI Optimize coming soon!');
            }}
        </script>
    </body>
    </html>
    """

# ====================== DELETE ======================
@app.route('/delete/<int:product_id>')
@login_required
def delete_product(product_id):
    product = Product.query.filter_by(id=product_id, user_id=current_user.id).first()
    if product:
        db.session.delete(product)
        db.session.commit()
    return redirect('/')

# ====================== EDIT ======================
@app.route('/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    product = Product.query.filter_by(id=product_id, user_id=current_user.id).first()
    if not product:
        return redirect('/')
    if request.method == 'POST':
        product.title = request.form.get('title')
        product.description = request.form.get('description')
        product.category = request.form.get('category')
        product.image = request.form.get('image')
        product.price = float(request.form.get('price', 0))
        product.stock = int(request.form.get('stock', 0))
        db.session.commit()
        return redirect('/')
    # Simple edit form
    return f"""
    <h2>Edit Product</h2>
    <form method="POST">
        Title: <input type="text" name="title" value="{product.title}" required><br><br>
        Description: <textarea name="description">{product.description}</textarea><br><br>
        Category: <input type="text" name="category" value="{product.category}"><br><br>
        Image URL: <input type="text" name="image" value="{product.image}"><br><br>
        Price: <input type="number" name="price" value="{product.price}" step="0.01"><br><br>
        Stock: <input type="number" name="stock" value="{product.stock}"><br><br>
        <button type="submit">Save</button> | <a href="/">Cancel</a>
    </form>
    """

# Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ====================== RUN ======================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))