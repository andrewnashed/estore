import smtplib
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from flask_bootstrap import Bootstrap
from flask_login import UserMixin, login_user, LoginManager, login_required, current_user, logout_user
from functools import wraps
from flask_ckeditor import CKEditor
from contact import send_email
from forms import *
import stripe
from werkzeug.security import check_password_hash, generate_password_hash
import os
from dotenv import load_dotenv
load_dotenv()
app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL').replace("://", "ql://", 1)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
SECRET_KEY = os.urandom(32)
app.config['SECRET_KEY'] = SECRET_KEY
app.config["STRIPE_SECRET_KEY"] = os.getenv("STRIPE_SECRET_KEY")
app.config["STRIPE_PUBLIC_KEY"] = os.getenv("STRIPE_PUBLIC_KEY")
stripe.api_key = app.config["STRIPE_SECRET_KEY"]
ckeditor = CKEditor(app)
Bootstrap(app)
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def admin_only(fun):
    @wraps(fun)
    def decorated_function(*args, **kwargs):
        if current_user.id != 1:
            return abort(403)
        return fun(*args, **kwargs)

    return decorated_function


class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(1000))
    cart = db.relationship("Cart", uselist=False, backref="user")


class Products(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(250), nullable=False, unique=True)
    description = db.Column(db.Text)
    image = db.Column(db.Text)
    price = db.Column(db.Integer, nullable=False)


class Cart(db.Model):
    __tablename__ = 'cart'
    id = db.Column(db.Integer, primary_key=True)
    items = db.Column(db.Text)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))


db.create_all()


@app.route("/", methods=["POST", "GET"])
def home():
    products = Products.query.all()
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        message = request.form["message"]
        send_email(name, email, message)
        return render_template("index.html", products=products, msg_sent=True)
    return render_template("index.html", products=products, current_user=current_user)


@app.route("/product/<int:pid>")
def product(pid):
    selected_product = Products.query.get(pid)
    return render_template("product.html", product=selected_product, current_user=current_user)


@app.route("/add-product", methods=["POST", "GET"])
@admin_only
def new_product():
    form = CreateProductForm()
    if form.validate_on_submit():
        new_post = Products(
            name=form.name.data,
            price=form.price.data,
            image=form.img_url.data,
            description=form.description.data
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for('home'))
    return render_template("add-product.html", form=form, current_user=current_user)


@app.route('/register', methods=["POST", "GET"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            flash(f"User with this email already exists, log in instead!")
            return redirect(url_for('login'))
        else:
            user_password = generate_password_hash(password=form.password.data, method='pbkdf2:sha256', salt_length=8)
            new_user = User(
                email=form.email.data,
                password=user_password,
                name=form.name.data
            )
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
        return redirect(url_for('home'))
    return render_template("register.html", form=form, current_user=current_user)


@app.route('/login', methods=["POST", "GET"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if not user:
            flash("Email does not exist, please try again.")
            return redirect(url_for('login'))
        elif not check_password_hash(user.password, form.password.data):
            flash('Incorrect Password, please try again.')
            return redirect(url_for('login'))
        else:
            login_user(user)
            return redirect(url_for('home'))
    return render_template("login.html", form=form, current_user=current_user)


@login_required
@app.route("/product/<int:pid>/add", methods=["Post", "GET"])
def add(pid):
    product = Products.query.get(pid)
    cart_item = Cart(
        items=product.name,
        product_id=product.id,
        user_id=current_user.id
    )
    db.session.add(cart_item)
    db.session.commit()
    flash(f"{product.name} added to shopping cart!")
    return redirect(url_for('product', pid=pid))


@login_required
@app.route("/cart", methods=["Post", "GET"])
def cart():
    cart = Cart.query.filter_by(user_id=current_user.id).all()
    products = [Products.query.filter_by(id=item.product_id).first() for item in cart]
    total = 0
    for product in products:
        total += product.price
    return render_template("cart.html", products=products, total=total, current_user=current_user)


@login_required
@app.route("/remove/<int:pid>", methods=["Post", "GET"])
def remove_from_cart(pid):
    item_remove = Cart.query.filter_by(product_id=pid).first()
    db.session.delete(item_remove)
    db.session.commit()
    return redirect(url_for('cart'))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


DOMAIN = os.getenv("DOMAIN")

@login_required
@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    cart = Cart.query.filter_by(user_id=current_user.id).all()
    products = [Products.query.filter_by(id=item.product_id).first() for item in cart]
    total = 0
    checkout_items = []
    for product in products:
        total += product.price
        schema = {
            'price_data': {
                'currency': 'usd',
                'product_data': {
                    'name': product.name,
                },
                'unit_amount': int(str(product.price) + "00"),
            },
            'quantity': 1,
        }

        checkout_items.append(schema)
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_intent_data={
                'setup_future_usage': 'off_session',
            },
            customer_email=current_user.email,
            payment_method_types=['card'],
            line_items=checkout_items,
            mode='payment',
            success_url=DOMAIN + '/success',
            cancel_url=DOMAIN + '/cancel',
            shipping_address_collection={
                "allowed_countries": ['US', 'CA'],
            }
        )
        return jsonify({'id': checkout_session.id})
    except Exception as e:
        return jsonify(error=str(e)), 403



@app.route("/success/", methods=["GET", "POST"])
def success():
    cart = Cart.query.filter_by(user_id=current_user.id).all()
    message = f"Subject:New Order\n\nHi {current_user.name}! " \
              f"We received your order! It will arrive to you in 10 business days ."
    with smtplib.SMTP("smtp.gmail.com") as connection:
        connection.starttls()
        connection.login(user=os.getenv("FROM_EMAIL"), password=os.getenv("PASSWORD"))
        connection.sendmail(from_addr=os.getenv("FROM_EMAIL"),
                            to_addrs=current_user.email,
                            msg=f"Subject:hello,{current_user.name}\nMessage:{message}")

    flash("Success, we sent you a confirmation email!")
    for item in cart:
        db.session.delete(item)
        db.session.commit()
    return redirect(url_for("home", alert="alert-success", current_user=current_user))


@login_required
@app.route("/cancel")
def cancel():
    flash("Error has occurred, try again!")
    return redirect(url_for("home", alert="alert-danger", current_user=current_user))


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)