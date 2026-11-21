import csv
import io
import os
import re
import uuid
from datetime import datetime, timezone
from functools import wraps
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

# По умолчанию используется SQLite. Для PostgreSQL укажите DATABASE_URL в файле .env
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///shop.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 МБ
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)


# --- Работа с файлами изображений ---
def save_image(file):
    if not file or file.filename == "":
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return None
    filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    return f"/static/uploads/{filename}"


def delete_image_file(image_url):
    if not image_url or not image_url.startswith("/static/uploads/"):
        return
    filename = os.path.basename(image_url)
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    if os.path.isfile(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass


# --- Модели базы данных ---
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default="user", nullable=False)  # user, manager, admin
    is_blocked = db.Column(db.Boolean, default=False, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "is_blocked": self.is_blocked,
        }


class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)

    def to_dict(self):
        return {"id": self.id, "name": self.name}


class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, default="")
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, default=10, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    tags = db.Column(db.String(200), default="")
    image_url = db.Column(db.String(300), default="")

    category = db.relationship("Category", backref="products")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "price": self.price,
            "stock": self.stock,
            "category_id": self.category_id,
            "category_name": self.category.name if self.category else "Без категории",
            "tags": self.tags or "",
            "image_url": self.image_url or "https://placehold.co/400x300/e2e8f0/1e293b?text=Товар",
        }


class PromoCode(db.Model):
    __tablename__ = "promo_codes"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False)
    discount_percent = db.Column(db.Integer, nullable=False)
    max_uses = db.Column(db.Integer, default=0, nullable=False)  # 0 = безлимит
    used_count = db.Column(db.Integer, default=0, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    def is_valid_now(self):
        if not self.is_active:
            return False, "Промокод отключен"
        if self.max_uses > 0 and self.used_count >= self.max_uses:
            return False, "Лимит использований промокода исчерпан"
        if self.expires_at:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            exp = self.expires_at.replace(tzinfo=None)
            if now > exp:
                return False, "Срок действия промокода истек"
        return True, ""

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "discount_percent": self.discount_percent,
            "max_uses": self.max_uses,
            "used_count": self.used_count,
            "expires_at": self.expires_at.strftime("%Y-%m-%d") if self.expires_at else "",
            "is_active": self.is_active,
        }


class Order(db.Model):
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    customer_name = db.Column(db.String(80), nullable=False)
    items = db.Column(db.JSON, nullable=False)
    subtotal = db.Column(db.Float, default=0.0, nullable=False)
    discount_amount = db.Column(db.Float, default=0.0, nullable=False)
    delivery_cost = db.Column(db.Float, default=0.0, nullable=False)
    promo_code = db.Column(db.String(40), nullable=True)
    total_price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(30), default="Новый")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "customer_name": self.customer_name,
            "items": self.items,
            "subtotal": self.subtotal,
            "discount_amount": self.discount_amount,
            "delivery_cost": self.delivery_cost,
            "promo_code": self.promo_code or "",
            "total_price": self.total_price,
            "status": self.status,
            "created_at": self.created_at.strftime("%d.%m.%Y %H:%M"),
        }


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    action = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "action": self.action,
            "created_at": self.created_at.strftime("%d.%m.%Y %H:%M:%S"),
        }


class StoreSetting(db.Model):
    __tablename__ = "store_settings"
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.Text, default="", nullable=False)


DEFAULT_SETTINGS = {
    "store_name": "TechStore",
    "hero_title": "Каталог товаров",
    "hero_subtitle": "Актуальные гаджеты с быстрой доставкой",
    "contact_info": "support@techstore.ru • +7 (999) 000-00-00",
    "delivery_cost": "0",
}


def get_settings_dict():
    result = dict(DEFAULT_SETTINGS)
    for row in StoreSetting.query.all():
        result[row.key] = row.value
    return result


def log_action(action_text):
    entry = AuditLog(
        username=session.get("username", "system"),
        role=session.get("role", "system"),
        action=action_text[:255],
    )
    db.session.add(entry)


# --- Проверка блокировки и актуальности роли на каждом запросе ---
@app.before_request
def check_user_status():
    if request.path.startswith("/static/"):
        return
    user_id = session.get("user_id")
    if user_id:
        user = db.session.get(User, user_id)
        if not user or user.is_blocked:
            session.clear()
            if request.path.startswith("/api/") and request.path not in ("/api/me", "/api/login", "/api/register"):
                return jsonify({"error": "Ваш аккаунт заблокирован"}), 403
        else:
            session["role"] = user.role


# --- Декоратор для проверки ролей ---
def roles_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get("role") not in allowed_roles:
                return jsonify({"error": "Недостаточно прав для этого действия"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


# --- Валидация логина и пароля ---
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
PASSWORD_RE = re.compile(r"^[A-Za-z0-9!@#$%^&*()_+\-=\[\]{};:'\",.<>/?]+$")


def validate_credentials(username, password):
    if len(username) < 3:
        return "Логин должен содержать минимум 3 символа"
    if not USERNAME_RE.match(username):
        return "Логин должен состоять только из латинских букв, цифр и _"
    if len(password) < 5:
        return "Пароль должен содержать минимум 5 символов"
    if not PASSWORD_RE.match(password):
        return "Пароль должен содержать только латиницу, цифры и спецсимволы (без кириллицы и пробелов)"
    return None


# --- Главная страница ---
@app.route("/")
def index():
    return render_template("index.html")


# --- API Авторизации ---
@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    error = validate_credentials(username, password)
    if error:
        return jsonify({"error": error}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Пользователь с таким именем уже существует"}), 400

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        role="user",
    )
    db.session.add(user)
    db.session.commit()

    session["user_id"] = user.id
    session["username"] = user.username
    session["role"] = user.role
    return jsonify({"id": user.id, "username": user.username, "role": user.role}), 201


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not USERNAME_RE.match(username) or not PASSWORD_RE.match(password):
        return jsonify({"error": "Логин и пароль должны быть написаны латиницей"}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Неверный логин или пароль"}), 401

    if user.is_blocked:
        return jsonify({"error": "Ваш аккаунт заблокирован администратором"}), 403

    session["user_id"] = user.id
    session["username"] = user.username
    session["role"] = user.role
    return jsonify({"id": user.id, "username": user.username, "role": user.role})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Вы вышли из аккаунта"})


@app.route("/api/me", methods=["GET"])
def me():
    if "user_id" in session:
        return jsonify({
            "logged_in": True,
            "id": session["user_id"],
            "username": session["username"],
            "role": session.get("role", "user"),
        })
    return jsonify({"logged_in": False})


# --- API Настроек магазина ---
@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(get_settings_dict())


@app.route("/api/settings", methods=["PUT"])
@roles_required("admin")
def update_settings():
    data = request.get_json() or {}
    for key in DEFAULT_SETTINGS:
        if key in data:
            val = str(data[key]).strip()
            if key == "delivery_cost":
                try:
                    val = str(max(0.0, float(val)))
                except ValueError:
                    return jsonify({"error": "Некорректная стоимость доставки"}), 400
            setting = db.session.get(StoreSetting, key)
            if setting:
                setting.value = val
            else:
                db.session.add(StoreSetting(key=key, value=val))
    log_action("Обновил настройки магазина")
    db.session.commit()
    return jsonify(get_settings_dict())


# --- API Категорий ---
@app.route("/api/categories", methods=["GET"])
def get_categories():
    categories = Category.query.order_by(Category.name.asc()).all()
    return jsonify([c.to_dict() for c in categories])


@app.route("/api/categories", methods=["POST"])
@roles_required("admin")
def create_category():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if len(name) < 2:
        return jsonify({"error": "Название категории от 2 символов"}), 400
    if Category.query.filter_by(name=name).first():
        return jsonify({"error": "Такая категория уже существует"}), 400

    cat = Category(name=name)
    db.session.add(cat)
    log_action(f"Создал категорию «{name}»")
    db.session.commit()
    return jsonify(cat.to_dict()), 201


@app.route("/api/categories/<int:cat_id>", methods=["DELETE"])
@roles_required("admin")
def delete_category(cat_id):
    cat = db.session.get(Category, cat_id)
    if not cat:
        return jsonify({"error": "Категория не найдена"}), 404

    Product.query.filter_by(category_id=cat.id).update({"category_id": None})
    name = cat.name
    db.session.delete(cat)
    log_action(f"Удалил категорию «{name}»")
    db.session.commit()
    return jsonify({"message": "Категория удалена"})


# --- API Товаров ---
@app.route("/api/products", methods=["GET"])
def get_products():
    products = Product.query.order_by(Product.id.desc()).all()
    return jsonify([p.to_dict() for p in products])


@app.route("/api/products", methods=["POST"])
@roles_required("admin", "manager")
def add_product():
    try:
        price = float(request.form.get("price", 0))
        stock = int(request.form.get("stock", 10))
    except (ValueError, TypeError):
        return jsonify({"error": "Некорректная цена или остаток"}), 400

    name = (request.form.get("name") or "").strip()
    if not name or price <= 0 or stock < 0:
        return jsonify({"error": "Укажите название, цену > 0 и остаток >= 0"}), 400

    cat_raw = request.form.get("category_id")
    category_id = int(cat_raw) if cat_raw and cat_raw.isdigit() else None
    tags = (request.form.get("tags") or "").strip()

    image_file = request.files.get("image")
    image_url = save_image(image_file) or ""

    product = Product(
        name=name,
        description=(request.form.get("description") or "").strip(),
        price=price,
        stock=stock,
        category_id=category_id,
        tags=tags,
        image_url=image_url,
    )
    db.session.add(product)
    log_action(f"Добавил товар «{name}» ({price} ₽, остаток {stock} шт.)")
    db.session.commit()
    return jsonify(product.to_dict()), 201


@app.route("/api/products/<int:product_id>", methods=["PUT"])
@roles_required("admin", "manager")
def update_product(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({"error": "Товар не найден"}), 404

    try:
        new_price = float(request.form.get("price", product.price))
        new_stock = int(request.form.get("stock", product.stock))
    except (ValueError, TypeError):
        return jsonify({"error": "Некорректная цена или остаток"}), 400

    if new_price <= 0 or new_stock < 0:
        return jsonify({"error": "Цена должна быть > 0, остаток >= 0"}), 400

    product.name = (request.form.get("name") or product.name).strip()
    product.description = (request.form.get("description") or "").strip()
    product.price = new_price
    product.stock = new_stock
    product.tags = (request.form.get("tags") or "").strip()

    cat_raw = request.form.get("category_id")
    product.category_id = int(cat_raw) if cat_raw and cat_raw.isdigit() else None

    old_image_url = product.image_url
    image_file = request.files.get("image")
    new_image_url = save_image(image_file)

    if new_image_url:
        product.image_url = new_image_url

    log_action(f"Изменил товар #{product.id} «{product.name}» ({new_price} ₽, остаток {new_stock} шт.)")
    db.session.commit()

    if new_image_url and old_image_url != new_image_url:
        delete_image_file(old_image_url)

    return jsonify(product.to_dict())


@app.route("/api/products/<int:product_id>", methods=["DELETE"])
@roles_required("admin", "manager")
def delete_product(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({"error": "Товар не найден"}), 404

    old_image_url = product.image_url
    name = product.name
    db.session.delete(product)
    log_action(f"Удалил товар #{product_id} «{name}»")
    db.session.commit()

    delete_image_file(old_image_url)
    return jsonify({"message": "Товар удален"})


# --- API Промокодов ---
@app.route("/api/promocodes/validate", methods=["POST"])
def validate_promocode():
    data = request.get_json() or {}
    code = (data.get("code") or "").strip().upper()
    if not code:
        return jsonify({"error": "Введите промокод"}), 400

    promo = PromoCode.query.filter_by(code=code).first()
    if not promo:
        return jsonify({"error": "Промокод не найден"}), 404

    valid, reason = promo.is_valid_now()
    if not valid:
        return jsonify({"error": reason}), 400

    return jsonify({"code": promo.code, "discount_percent": promo.discount_percent})


@app.route("/api/promocodes", methods=["GET"])
@roles_required("admin")
def get_promocodes():
    promos = PromoCode.query.order_by(PromoCode.id.desc()).all()
    return jsonify([p.to_dict() for p in promos])


@app.route("/api/promocodes", methods=["POST"])
@roles_required("admin")
def create_promocode():
    data = request.get_json() or {}
    code = (data.get("code") or "").strip().upper()
    if len(code) < 2 or not re.match(r"^[A-Z0-9_-]+$", code):
        return jsonify({"error": "Код: от 2 символов (латиница, цифры, _ или -)"}), 400

    try:
        discount = int(data.get("discount_percent", 0))
        max_uses = int(data.get("max_uses") or 0)
    except (ValueError, TypeError):
        return jsonify({"error": "Некорректная скидка или лимит"}), 400

    if discount < 1 or discount > 90:
        return jsonify({"error": "Скидка должна быть от 1% до 90%"}), 400
    if max_uses < 0:
        return jsonify({"error": "Лимит использований не может быть отрицательным"}), 400
    if PromoCode.query.filter_by(code=code).first():
        return jsonify({"error": "Такой промокод уже существует"}), 400

    expires_at = None
    exp_str = (data.get("expires_at") or "").strip()
    if exp_str:
        try:
            expires_at = datetime.strptime(exp_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except ValueError:
            return jsonify({"error": "Некорректная дата окончания"}), 400

    promo = PromoCode(
        code=code,
        discount_percent=discount,
        max_uses=max_uses,
        expires_at=expires_at,
        is_active=True,
    )
    db.session.add(promo)
    log_action(f"Создал промокод {code} (-{discount}%)")
    db.session.commit()
    return jsonify(promo.to_dict()), 201


@app.route("/api/promocodes/<int:promo_id>/toggle", methods=["PATCH"])
@roles_required("admin")
def toggle_promocode(promo_id):
    promo = db.session.get(PromoCode, promo_id)
    if not promo:
        return jsonify({"error": "Промокод не найден"}), 404
    promo.is_active = not promo.is_active
    state = "Включил" if promo.is_active else "Отключил"
    log_action(f"{state} промокод {promo.code}")
    db.session.commit()
    return jsonify(promo.to_dict())


@app.route("/api/promocodes/<int:promo_id>", methods=["DELETE"])
@roles_required("admin")
def delete_promocode(promo_id):
    promo = db.session.get(PromoCode, promo_id)
    if not promo:
        return jsonify({"error": "Промокод не найден"}), 404
    code = promo.code
    db.session.delete(promo)
    log_action(f"Удалил промокод {code}")
    db.session.commit()
    return jsonify({"message": "Промокод удален"})


# --- API Заказов ---
@app.route("/api/orders", methods=["POST"])
def create_order():
    data = request.get_json() or {}
    product_ids = data.get("product_ids") or []
    promo_input = (data.get("promo_code") or "").strip().upper()

    if not product_ids:
        return jsonify({"error": "Корзина пуста"}), 400

    counts = {}
    for pid in product_ids:
        counts[pid] = counts.get(pid, 0) + 1

    products = Product.query.filter(Product.id.in_(counts.keys())).all()
    if not products:
        return jsonify({"error": "Товары не найдены"}), 400

    # Проверяем наличие на складе
    for p in products:
        qty = counts[p.id]
        if p.stock < qty:
            return jsonify({"error": f"Недостаточно товара «{p.name}» на складе (доступно: {p.stock} шт.)"}), 400

    # Проверяем промокод, если передан
    promo = None
    if promo_input:
        promo = PromoCode.query.filter_by(code=promo_input).first()
        if not promo:
            return jsonify({"error": "Промокод не найден"}), 400
        valid, reason = promo.is_valid_now()
        if not valid:
            return jsonify({"error": reason}), 400

    order_items = []
    subtotal = 0.0
    for p in products:
        qty = counts[p.id]
        p.stock -= qty
        subtotal += p.price * qty
        order_items.append({"name": p.name, "price": p.price, "qty": qty})

    discount_amount = 0.0
    applied_code = None
    if promo:
        discount_amount = round(subtotal * promo.discount_percent / 100.0, 2)
        applied_code = promo.code
        promo.used_count += 1

    settings = get_settings_dict()
    try:
        delivery_cost = float(settings.get("delivery_cost", 0))
    except ValueError:
        delivery_cost = 0.0

    total_price = round(max(0.0, subtotal - discount_amount) + delivery_cost, 2)

    order = Order(
        user_id=session.get("user_id"),
        customer_name=session.get("username", "Гость"),
        items=order_items,
        subtotal=subtotal,
        discount_amount=discount_amount,
        delivery_cost=delivery_cost,
        promo_code=applied_code,
        total_price=total_price,
    )
    db.session.add(order)
    db.session.commit()
    return jsonify(order.to_dict()), 201


@app.route("/api/orders", methods=["GET"])
@roles_required("admin", "manager")
def get_orders():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return jsonify([o.to_dict() for o in orders])


@app.route("/api/my-orders", methods=["GET"])
def get_my_orders():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Требуется авторизация"}), 401

    orders = Order.query.filter_by(user_id=user_id).order_by(Order.created_at.desc()).all()
    return jsonify([o.to_dict() for o in orders])


@app.route("/api/orders/<int:order_id>", methods=["PATCH"])
@roles_required("admin", "manager")
def update_order_status(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({"error": "Заказ не найден"}), 404

    data = request.get_json() or {}
    new_status = data.get("status")
    if new_status not in ("Новый", "В обработке", "Выполнен", "Отменен"):
        return jsonify({"error": "Недопустимый статус"}), 400

    old_status = order.status
    order.status = new_status
    log_action(f"Изменил статус заказа #{order.id}: {old_status} -> {new_status}")
    db.session.commit()
    return jsonify(order.to_dict())


@app.route("/api/orders/<int:order_id>", methods=["DELETE"])
@roles_required("admin")
def delete_order(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({"error": "Заказ не найден"}), 404
    customer = order.customer_name
    db.session.delete(order)
    log_action(f"Удалил заказ #{order_id} ({customer})")
    db.session.commit()
    return jsonify({"message": "Заказ удален"})


# --- API Управления пользователями (только для admin) ---
@app.route("/api/users", methods=["GET"])
@roles_required("admin")
def get_users():
    users = User.query.order_by(User.id.asc()).all()
    return jsonify([u.to_dict() for u in users])


@app.route("/api/users/<int:user_id>/role", methods=["PATCH"])
@roles_required("admin")
def update_user_role(user_id):
    if user_id == session.get("user_id"):
        return jsonify({"error": "Нельзя изменить роль самому себе"}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "Пользователь не найден"}), 404

    new_role = (request.get_json() or {}).get("role")
    if new_role not in ("user", "manager", "admin"):
        return jsonify({"error": "Недопустимая роль"}), 400

    old_role = user.role
    user.role = new_role
    log_action(f"Изменил роль пользователя {user.username}: {old_role} -> {new_role}")
    db.session.commit()
    return jsonify(user.to_dict())


@app.route("/api/users/<int:user_id>/block", methods=["PATCH"])
@roles_required("admin")
def toggle_user_block(user_id):
    if user_id == session.get("user_id"):
        return jsonify({"error": "Нельзя заблокировать самого себя"}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "Пользователь не найден"}), 404

    user.is_blocked = not user.is_blocked
    verb = "Заблокировал" if user.is_blocked else "Разблокировал"
    log_action(f"{verb} пользователя {user.username}")
    db.session.commit()
    return jsonify(user.to_dict())


# --- API Статистики, Логов и Экспорта (только для admin) ---
@app.route("/api/admin/stats", methods=["GET"])
@roles_required("admin")
def get_admin_stats():
    orders = Order.query.all()
    valid_orders = [o for o in orders if o.status != "Отменен"]

    total_revenue = round(sum(o.total_price for o in valid_orders), 2)
    avg_check = round(total_revenue / len(valid_orders), 2) if valid_orders else 0.0

    product_sales = {}
    for o in valid_orders:
        for item in (o.items or []):
            name = item.get("name", "Товар")
            qty = int(item.get("qty", 1))
            rev = float(item.get("price", 0)) * qty
            if name not in product_sales:
                product_sales[name] = {"name": name, "qty": 0, "revenue": 0.0}
            product_sales[name]["qty"] += qty
            product_sales[name]["revenue"] += rev

    top_products = sorted(product_sales.values(), key=lambda x: x["qty"], reverse=True)[:5]

    return jsonify({
        "total_revenue": total_revenue,
        "total_orders": len(orders),
        "active_orders": sum(1 for o in orders if o.status in ("Новый", "В обработке")),
        "completed_orders": sum(1 for o in orders if o.status == "Выполнен"),
        "avg_check": avg_check,
        "total_users": User.query.count(),
        "blocked_users": User.query.filter_by(is_blocked=True).count(),
        "total_products": Product.query.count(),
        "out_of_stock_products": Product.query.filter(Product.stock <= 0).count(),
        "top_products": top_products,
    })


@app.route("/api/admin/logs", methods=["GET"])
@roles_required("admin")
def get_admin_logs():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all()
    return jsonify([l.to_dict() for l in logs])


@app.route("/api/admin/export/orders", methods=["GET"])
@roles_required("admin")
def export_orders_csv():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM для корректного открытия в Excel
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID", "Дата", "Покупатель", "Товары", "Подытог", "Скидка", "Промокод", "Доставка", "Итого", "Статус"])
    for o in orders:
        items_str = ", ".join(f"{i['name']} x{i['qty']}" for i in (o.items or []))
        writer.writerow([
            o.id,
            o.created_at.strftime("%d.%m.%Y %H:%M"),
            o.customer_name,
            items_str,
            o.subtotal,
            o.discount_amount,
            o.promo_code or "",
            o.delivery_cost,
            o.total_price,
            o.status,
        ])

    log_action("Выгрузил заказы в CSV")
    db.session.commit()
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=orders.csv"},
    )


@app.route("/api/admin/export/products", methods=["GET"])
@roles_required("admin")
def export_products_csv():
    products = Product.query.order_by(Product.id.asc()).all()
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID", "Название", "Категория", "Цена", "Остаток", "Теги", "Описание"])
    for p in products:
        writer.writerow([
            p.id,
            p.name,
            p.category.name if p.category else "Без категории",
            p.price,
            p.stock,
            p.tags or "",
            p.description or "",
        ])

    log_action("Выгрузил каталог товаров в CSV")
    db.session.commit()
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=products.csv"},
    )


# --- Инициализация БД и тестовых данных ---
def init_db():
    with app.app_context():
        db.create_all()

        # Настройки по умолчанию
        for key, val in DEFAULT_SETTINGS.items():
            if not db.session.get(StoreSetting, key):
                db.session.add(StoreSetting(key=key, value=val))

        # Админ по умолчанию
        if not User.query.filter_by(username="admin").first():
            admin = User(
                username="admin",
                password_hash=generate_password_hash("admin"),
                role="admin",
            )
            db.session.add(admin)

        # Категории по умолчанию
        if Category.query.count() == 0:
            cat_audio = Category(name="Аудио")
            cat_periph = Category(name="Периферия")
            cat_home = Category(name="Умный дом")
            db.session.add_all([cat_audio, cat_periph, cat_home])
            db.session.flush()
        else:
            cat_audio = Category.query.filter_by(name="Аудио").first()
            cat_periph = Category.query.filter_by(name="Периферия").first()
            cat_home = Category.query.filter_by(name="Умный дом").first()

        # Тестовые товары
        if Product.query.count() == 0:
            demo_products = [
                Product(
                    name="Беспроводные наушники",
                    description="Активное шумоподавление, до 30 часов работы от батареи.",
                    price=7990,
                    stock=15,
                    category_id=cat_audio.id if cat_audio else None,
                    tags="bluetooth, музыка, хиты",
                    image_url="https://placehold.co/400x300/4f46e5/ffffff?text=Наушники",
                ),
                Product(
                    name="Механическая клавиатура",
                    description="Компактный формат 75%, RGB-подсветка, тихие переключатели.",
                    price=6490,
                    stock=8,
                    category_id=cat_periph.id if cat_periph else None,
                    tags="игры, rgb, пк",
                    image_url="https://placehold.co/400x300/0f172a/ffffff?text=Клавиатура",
                ),
                Product(
                    name="Умная колонка",
                    description="Чистый объемный звук и голосовое управление домом.",
                    price=4990,
                    stock=5,
                    category_id=cat_home.id if cat_home else None,
                    tags="дом, ассистент, звук",
                    image_url="https://placehold.co/400x300/059669/ffffff?text=Колонка",
                ),
            ]
            db.session.add_all(demo_products)

        # Тестовый промокод
        if PromoCode.query.count() == 0:
            db.session.add(PromoCode(code="SALE15", discount_percent=15, max_uses=100, is_active=True))

        db.session.commit()


if __name__ == "__main__":
    init_db()
    app.run(debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
