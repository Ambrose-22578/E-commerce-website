from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
# Removed unused import for models

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-very-secret-key-123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    image = db.Column(db.String(100))
    stock = db.Column(db.Integer, nullable=False, default=0)
    category = db.Column(db.String(50))

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    total = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='Processing')
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    items = db.relationship('OrderItem', backref='order', lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)

# Create database and add sample data
with app.app_context():
    db.create_all()
    
    # Add sample products if none exist
    if Product.query.count() == 0:
        sample_products = [
            Product(
                name="MacBook Pro 16\"",
                description="Apple M1 Pro chip, 16GB RAM, 512GB SSD",
                price=2399.00,
                stock=15,
                category="Laptops",
                image="download.jpeg"
            ),
            Product(
                name="iPhone 15 Pro",
                description="6.1-inch Super Retina XDR display, A16 Bionic chip",
                price=999.00,
                stock=30,
                category="Phones",
                image="phone.jpg"
            ),
            Product(
                name="Sony WH-1000XM5",
                description="Industry-leading noise canceling wireless headphones",
                price=399.99,
                stock=25,
                category="Headphones",
                image="headphones.jpg"
            )
        ]
        db.session.add_all(sample_products)
        
        # Create admin user if none exists
        if User.query.count() == 0:
            admin = User(
                username="admin",
                email="admin@store.com",
                password=generate_password_hash("admin123"),
                is_admin=True
            )
            db.session.add(admin)
        
        db.session.commit()

# Main Routes
@app.route('/')
def home():
    products = Product.query.all()
    return render_template('index.html', products=products)

@app.route('/product/<int:id>')
def product(id):
    product = Product.query.get_or_404(id)
    return render_template('product.html', product=product)

@app.route('/cart')
def cart():
    if 'cart' not in session:
        session['cart'] = []
    
    cart_items = []
    total = 0
    for item in session['cart']:
        product = Product.query.get(item['product_id'])
        if product:
            item_total = product.price * item['quantity']
            total += item_total
            cart_items.append({
                'product': product,
                'quantity': item['quantity'],
                'total': item_total
            })
    
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/add-to-cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    if 'cart' not in session:
        session['cart'] = []
    
    quantity = int(request.form.get('quantity', 1))
    product = Product.query.get_or_404(product_id)
    
    # Check stock availability
    if quantity > product.stock:
        flash(f'Only {product.stock} available in stock', 'warning')
        return redirect(url_for('product', id=product_id))
    
    # Check if product already in cart
    for item in session['cart']:
        if item['product_id'] == product_id:
            new_quantity = item['quantity'] + quantity
            if new_quantity > product.stock:
                flash(f'Cannot add more than available stock', 'warning')
                return redirect(url_for('product', id=product_id))
            item['quantity'] = new_quantity
            break
    else:
        session['cart'].append({
            'product_id': product_id,
            'quantity': quantity
        })
    
    session.modified = True
    flash(f'{product.name} added to cart!', 'success')
    return redirect(url_for('cart'))

@app.route('/remove-from-cart/<int:index>')
def remove_from_cart(index):
    if 'cart' in session and 0 <= index < len(session['cart']):
        removed_product = Product.query.get(session['cart'][index]['product_id'])
        session['cart'].pop(index)
        session.modified = True
        flash(f'{removed_product.name} removed from cart', 'info')
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user_id' not in session:
        flash('Please login to checkout', 'warning')
        return redirect(url_for('login'))
    
    if 'cart' not in session or not session['cart']:
        flash('Your cart is empty', 'warning')
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        user_id = session['user_id']
        cart_items = []
        total = 0
        
        # Verify stock and calculate total
        for item in session['cart']:
            product = Product.query.get(item['product_id'])
            if not product or product.stock < item['quantity']:
                flash(f'Sorry, {product.name if product else "Item"} is no longer available', 'danger')
                return redirect(url_for('cart'))
            total += product.price * item['quantity']
            cart_items.append({
                'product': product,
                'quantity': item['quantity']
            })
        
        # Create order
        order = Order(
            user_id=user_id,
            total=total
        )
        db.session.add(order)
        db.session.commit()
        
        # Add order items and update stock
        for item in cart_items:
            order_item = OrderItem(
                order_id=order.id,
                product_id=item['product'].id,
                quantity=item['quantity'],
                price=item['product'].price
            )
            item['product'].stock -= item['quantity']
            db.session.add(order_item)
            db.session.add(item['product'])
        
        db.session.commit()
        
        # Clear cart
        session['cart'] = []
        return redirect(url_for('order_confirmation', order_id=order.id))
    
    # Calculate total for GET request
    total = 0
    cart_items = []
    for item in session['cart']:
        product = Product.query.get(item['product_id'])
        if product:
            item_total = product.price * item['quantity']
            total += item_total
            cart_items.append({
                'product': product,
                'quantity': item['quantity'],
                'total': item_total
            })
    
    return render_template('checkout.html', cart_items=cart_items, total=total)

@app.route('/order-confirmation/<int:order_id>')
def order_confirmation(order_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    order = Order.query.get_or_404(order_id)
    if order.user_id != session['user_id'] and not User.query.get(session['user_id']).is_admin:
        flash('You cannot view this order', 'danger')
        return redirect(url_for('home'))
    
    order_items = OrderItem.query.filter_by(order_id=order_id).all()
    products = []
    for item in order_items:
        product = Product.query.get(item.product_id)
        products.append({
            'product': product,
            'quantity': item.quantity,
            'price': item.price,
            'total': item.price * item.quantity
        })
    
    return render_template('order_confirmation.html', order=order, products=products)

# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['is_admin'] = user.is_admin
            flash('Login successful!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'danger')
            return redirect(url_for('register'))
        
        hashed_password = generate_password_hash(password)
        new_user = User(
            username=username,
            email=email,
            password=hashed_password
        )
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('is_admin', None)
    flash('You have been logged out', 'info')
    return redirect(url_for('home'))

# Admin Routes
@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session or not User.query.get(session['user_id']).is_admin:
        return redirect(url_for('home'))
    
    products_count = Product.query.count()
    orders_count = Order.query.count()
    users_count = User.query.count()
    
    return render_template('admin/dashboard.html',
                         products_count=products_count,
                         orders_count=orders_count,
                         users_count=users_count)

@app.route('/admin/products')
def admin_products():
    if 'user_id' not in session or not User.query.get(session['user_id']).is_admin:
        return redirect(url_for('home'))
    
    products = Product.query.all()
    return render_template('admin/products.html', products=products)

@app.route('/admin/products/new', methods=['GET', 'POST'])
def admin_add_product():
    if 'user_id' not in session or not User.query.get(session['user_id']).is_admin:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        product = Product(
            name=request.form['name'],
            description=request.form['description'],
            price=float(request.form['price']),
            stock=int(request.form['stock']),
            category=request.form['category'],
            image=request.form['image']
        )
        db.session.add(product)
        db.session.commit()
        flash('Product added successfully', 'success')
        return redirect(url_for('admin_products'))
    
    return render_template('admin/add_product.html')

if __name__ == '__main__':
    app.run(debug=True)