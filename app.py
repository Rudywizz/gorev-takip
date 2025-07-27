from flask import Flask, render_template, request, redirect, url_for, session, make_response
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import pandas as pd
from io import BytesIO, StringIO
from xhtml2pdf import pisa

app = Flask(__name__)
app.secret_key = 'gizli_anahtar'
DATABASE = 'gorev_takip.db'

def init_db():
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    title TEXT,
                    location TEXT,
                    materials TEXT,
                    date TEXT,
                    needs_support TEXT,
                    status TEXT,
                    assigned_to INTEGER,
                    accepted TEXT DEFAULT 'Bekliyor',
                    completed TEXT DEFAULT 'Hayir',
                    completion_note TEXT DEFAULT '',
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(assigned_to) REFERENCES users(id)
                )
            ''')
            conn.commit()
    except Exception as e:
        print("Veritabanı hatası:", e)

@app.route('/')
def index():
    return redirect(url_for('dashboard')) if 'user_id' in session else redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        try:
            with sqlite3.connect(DATABASE) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
                conn.commit()
        except sqlite3.IntegrityError:
            return "Kullanıcı adı zaten var."
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with sqlite3.connect(DATABASE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, password FROM users WHERE username=?", (username,))
            user = cursor.fetchone()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            return redirect(url_for('dashboard'))
        return "Hatalı giriş"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, username FROM users")
        all_users = cursor.fetchall()

        if request.method == 'POST':
            title = request.form['title']
            location = request.form['location']
            materials = request.form['materials']
            date = request.form['date']
            needs_support = request.form['needs_support']
            status = request.form['status']
            assigned_to = request.form.get('assigned_to')

            if not assigned_to or assigned_to.strip() == "":
                assigned_to = user_id
            else:
                assigned_to = int(assigned_to)

            cursor.execute('''
                INSERT INTO tasks (user_id, title, location, materials, date, needs_support, status, assigned_to)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (user_id, title, location, materials, date, needs_support, status, assigned_to))
            conn.commit()

        cursor.execute('''
            SELECT tasks.*, assigner.username as assigner_name, assignee.username as assignee_name
            FROM tasks
            LEFT JOIN users AS assigner ON tasks.user_id = assigner.id
            LEFT JOIN users AS assignee ON tasks.assigned_to = assignee.id
        ''')
        tasks = cursor.fetchall()

    return render_template('dashboard.html', tasks=tasks, all_users=all_users, current_user=user_id)

@app.route('/assigned_tasks')
def assigned_tasks():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT tasks.*, assigner.username as assigner_name, assignee.username as assignee_name
            FROM tasks
            LEFT JOIN users AS assigner ON tasks.user_id = assigner.id
            LEFT JOIN users AS assignee ON tasks.assigned_to = assignee.id
            WHERE tasks.assigned_to = ? AND tasks.completed = 'Hayir'
        ''', (user_id,))
        tasks = cursor.fetchall()

    return render_template('assigned_tasks.html', tasks=tasks, current_user=user_id)

@app.route('/completed_tasks')
def completed_tasks():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT tasks.*, assigner.username as assigner_name, assignee.username as assignee_name
            FROM tasks
            LEFT JOIN users AS assigner ON tasks.user_id = assigner.id
            LEFT JOIN users AS assignee ON tasks.assigned_to = assignee.id
            WHERE tasks.assigned_to = ? AND tasks.completed = 'Evet'
        ''', (user_id,))
        tasks = cursor.fetchall()

    return render_template('completed_tasks.html', tasks=tasks)

@app.route('/report')
def report():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT tasks.*, assigner.username as assigner_name, assignee.username as assignee_name
            FROM tasks
            LEFT JOIN users AS assigner ON tasks.user_id = assigner.id
            LEFT JOIN users AS assignee ON tasks.assigned_to = assignee.id
        ''')
        tasks = cursor.fetchall()

    return render_template('report.html', tasks=tasks)

@app.route('/export/excel')
def export_excel():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        df = pd.read_sql_query("""
            SELECT 
                t.title as Görev,
                t.location as Yer,
                t.date as Tarih,
                t.materials as Malzemeler,
                t.needs_support as Destek,
                t.status as Durum,
                u1.username as Gorevi_Giren,
                u2.username as Atanan,
                t.completion_note as Aciklama
            FROM tasks t
            LEFT JOIN users u1 ON t.user_id = u1.id
            LEFT JOIN users u2 ON t.assigned_to = u2.id
            WHERE t.completed = 'Evet'
        """, conn)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Tamamlanan Görevler')
    output.seek(0)

    response = make_response(output.read())
    response.headers["Content-Disposition"] = "attachment; filename=rapor.xlsx"
    response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return response

@app.route('/export/pdf')
def export_pdf():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                t.title, t.location, t.date, t.materials, 
                t.needs_support, t.status, t.completion_note, 
                u1.username, u2.username
            FROM tasks t
            LEFT JOIN users u1 ON t.user_id = u1.id
            LEFT JOIN users u2 ON t.assigned_to = u2.id
            WHERE t.completed = 'Evet'
        """)
        tasks = cursor.fetchall()

    rendered = render_template("report_pdf.html", tasks=tasks)
    pdf = BytesIO()
    pisa.CreatePDF(StringIO(rendered), dest=pdf)
    pdf.seek(0)

    response = make_response(pdf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=rapor.pdf'
    return response

@app.route('/accept_task/<int:task_id>', methods=['POST'])
def accept_task(task_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET accepted='Evet' WHERE id=? AND assigned_to=?", (task_id, user_id))
        conn.commit()

    return redirect(url_for('assigned_tasks'))

@app.route('/complete_task/<int:task_id>', methods=['GET', 'POST'])
def complete_task(task_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    if request.method == 'POST':
        note = request.form['note']
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks SET completed='Evet', completion_note=?, status='Tamamlandi'
                WHERE id=? AND assigned_to=?
            """, (note, task_id, user_id))
            conn.commit()
        return redirect(url_for('assigned_tasks'))

    return render_template('complete_task.html', task_id=task_id)

@app.route('/delete_task/<int:task_id>', methods=['POST'])
def delete_task(task_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM tasks WHERE id=?", (task_id,))
        result = cursor.fetchone()
        if result and result[0] == user_id:
            cursor.execute("DELETE FROM tasks WHERE id=?", (task_id,))
            conn.commit()

    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
