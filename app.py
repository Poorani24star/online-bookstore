
import os
import sqlite3

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash
)

app = Flask(__name__)
app.secret_key = "bookstore-demo-key"

# Always use the database file in the same folder as app.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "bookstore.db")


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer TEXT NOT NULL,
            book_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            FOREIGN KEY (book_id) REFERENCES books(id)
        )
    """)

    # Insert sample books only when the books table is empty
    count = conn.execute(
        "SELECT COUNT(*) FROM books"
    ).fetchone()[0]

    if count == 0:
        conn.executemany(
            """
            INSERT INTO books (title, author, price, stock)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("Python Programming", "John Smith", 450, 10),
                ("Web Development Basics", "Mary Jones", 350, 8),
                ("Database Management", "David Brown", 500, 6)
            ]
        )

    conn.commit()
    conn.close()


@app.route("/")
def index():
    conn = get_db()

    books = conn.execute(
        "SELECT * FROM books ORDER BY id"
    ).fetchall()

    conn.close()

    return render_template("index.html", books=books)


@app.route("/add", methods=["GET", "POST"])
def add_book():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()

        try:
            price = float(request.form.get("price", ""))
            stock = int(request.form.get("stock", ""))

            if not title or not author or price < 0 or stock < 0:
                raise ValueError

        except ValueError:
            flash("Enter valid book details.")
            return redirect(url_for("add_book"))

        conn = get_db()

        try:
            conn.execute(
                """
                INSERT INTO books (title, author, price, stock)
                VALUES (?, ?, ?, ?)
                """,
                (title, author, price, stock)
            )

            conn.commit()

        except sqlite3.Error:
            conn.rollback()
            app.logger.exception("Failed to add book")
            flash("Unable to save the book. Please try again.")

        else:
            flash("Book added successfully!")

        finally:
            conn.close()

        return redirect(url_for("index"))

    return render_template("book_form.html", book=None)


@app.route("/edit/<int:book_id>", methods=["GET", "POST"])
def edit_book(book_id):
    conn = get_db()

    book = conn.execute(
        "SELECT * FROM books WHERE id = ?",
        (book_id,)
    ).fetchone()

    if book is None:
        conn.close()
        flash("Book not found.")
        return redirect(url_for("index"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()

        try:
            price = float(request.form.get("price", ""))
            stock = int(request.form.get("stock", ""))

            if not title or not author or price < 0 or stock < 0:
                raise ValueError

        except ValueError:
            conn.close()
            flash("Enter valid book details.")
            return redirect(url_for("edit_book", book_id=book_id))

        try:
            conn.execute(
                """
                UPDATE books
                SET title = ?, author = ?, price = ?, stock = ?
                WHERE id = ?
                """,
                (title, author, price, stock, book_id)
            )

            conn.commit()

        except sqlite3.Error:
            conn.rollback()
            app.logger.exception("Failed to update book")
            flash("Unable to update the book.")

        else:
            flash("Book updated successfully!")

        finally:
            conn.close()

        return redirect(url_for("index"))

    conn.close()

    return render_template("book_form.html", book=book)


@app.route("/delete/<int:book_id>", methods=["POST"])
def delete_book(book_id):
    conn = get_db()

    try:
        order = conn.execute(
            "SELECT id FROM orders WHERE book_id = ? LIMIT 1",
            (book_id,)
        ).fetchone()

        if order:
            flash("This book has orders and cannot be deleted.")
        else:
            result = conn.execute(
                "DELETE FROM books WHERE id = ?",
                (book_id,)
            )

            conn.commit()

            if result.rowcount:
                flash("Book deleted successfully!")
            else:
                flash("Book not found.")

    except sqlite3.Error:
        conn.rollback()
        app.logger.exception("Failed to delete book")
        flash("Unable to delete the book.")

    finally:
        conn.close()

    return redirect(url_for("index"))


@app.route("/orders")
def orders():
    conn = get_db()

    all_orders = conn.execute("""
        SELECT orders.id, orders.customer, books.title,
               orders.quantity, orders.status
        FROM orders
        JOIN books ON orders.book_id = books.id
        ORDER BY orders.id DESC
    """).fetchall()

    books = conn.execute(
        "SELECT * FROM books WHERE stock > 0 ORDER BY title"
    ).fetchall()

    conn.close()

    return render_template(
        "orders.html",
        orders=all_orders,
        books=books
    )


@app.route("/orders/add", methods=["POST"])
def add_order():
    customer = request.form.get("customer", "").strip()

    try:
        book_id = int(request.form.get("book_id", ""))
        quantity = int(request.form.get("quantity", ""))

        if not customer or quantity <= 0:
            raise ValueError

    except ValueError:
        flash("Enter valid customer and order details.")
        return redirect(url_for("orders"))

    conn = get_db()

    try:
        book = conn.execute(
            "SELECT * FROM books WHERE id = ?",
            (book_id,)
        ).fetchone()

        if book is None or book["stock"] < quantity:
            flash("Book unavailable or insufficient stock.")
            return redirect(url_for("orders"))

        conn.execute(
            """
            INSERT INTO orders (customer, book_id, quantity, status)
            VALUES (?, ?, ?, 'Pending')
            """,
            (customer, book_id, quantity)
        )

        conn.execute(
            "UPDATE books SET stock = stock - ? WHERE id = ?",
            (quantity, book_id)
        )

        conn.commit()
        flash("Customer order created successfully!")

    except sqlite3.Error:
        conn.rollback()
        app.logger.exception("Failed to create order")
        flash("Unable to create the order.")

    finally:
        conn.close()

    return redirect(url_for("orders"))


@app.route("/orders/update/<int:order_id>", methods=["POST"])
def update_order(order_id):
    status = request.form.get("status", "")

    allowed_statuses = [
        "Pending",
        "Processing",
        "Shipped",
        "Completed"
    ]

    if status not in allowed_statuses:
        flash("Invalid order status.")
        return redirect(url_for("orders"))

    conn = get_db()

    try:
        result = conn.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (status, order_id)
        )

        conn.commit()

        if result.rowcount:
            flash("Order status updated successfully!")
        else:
            flash("Order not found.")

    except sqlite3.Error:
        conn.rollback()
        app.logger.exception("Failed to update order")
        flash("Unable to update the order.")

    finally:
        conn.close()

    return redirect(url_for("orders"))


# Initialize database tables when the application starts
init_db()


if __name__ == "__main__":
    app.run(debug=True)
