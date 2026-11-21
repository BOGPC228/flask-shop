from sqlalchemy import inspect, text
from app import app, db, init_db

MIGRATIONS = {
    "users": [
        ("role", "VARCHAR(20) NOT NULL DEFAULT 'user'"),
        ("is_blocked", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ],
    "products": [
        ("stock", "INTEGER NOT NULL DEFAULT 10"),
        ("category_id", "INTEGER"),
        ("tags", "VARCHAR(200) DEFAULT ''"),
    ],
    "orders": [
        ("subtotal", "FLOAT NOT NULL DEFAULT 0"),
        ("discount_amount", "FLOAT NOT NULL DEFAULT 0"),
        ("delivery_cost", "FLOAT NOT NULL DEFAULT 0"),
        ("promo_code", "VARCHAR(40)"),
    ],
}

with app.app_context():
    inspector = inspect(db.engine)
    existing_tables = inspector.get_table_names()

    for table, columns in MIGRATIONS.items():
        if table not in existing_tables:
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table)}

        for col_name, col_def in columns:
            if col_name not in existing_cols:
                db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))
                print(f"+ Добавлена колонка {table}.{col_name}")

        # Если обновлялись с самой первой версии (где был is_admin), переносим права админа
        if table == "users" and "is_admin" in existing_cols:
            db.session.execute(text("UPDATE users SET role = 'admin' WHERE is_admin = TRUE"))

        # Заполняем subtotal у старых заказов, чтобы статистика считалась ровно
        if table == "orders":
            db.session.execute(text("UPDATE orders SET subtotal = total_price WHERE subtotal = 0 AND total_price > 0"))

    db.session.commit()

# Создаст недостающие новые таблицы и дефолтные настройки/промокод
init_db()
print("Миграция успешно завершена! Старые данные сохранены.")