from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import imaplib
import email
from email.header import decode_header
import json
import os
import secrets
import hashlib
import sys
import traceback

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")
DATA_FOLDER = os.path.join(BASE_DIR, "user_data")
ADMIN_PASSWORD = "admin123"
ADMIN_SECRET_PATH = "admin-secret-123"

if not os.path.exists(DATA_FOLDER):
    os.makedirs(DATA_FOLDER)

# Catégories par défaut (modifiables dans l'interface)
DEFAULT_CATEGORIES = {
    "Voyage": ["vol", "hotel", "reservation", "voyage", "avion", "bagage", "vacances"],
    "Pro": ["facture", "devis", "travail", "client", "mission", "boulot"],
    "Pub": ["newsletter", "promo", "publicite", "marketing", "pub", "offre"],
    "Perso": ["famille", "amis", "personnel", "prive", "coucou"],
    "Shopping": ["achat", "commande", "livraison", "amazon", "ebay"],
    "Jeux": ["jeu", "playstation", "xbox", "nintendo", "steam"]
}

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)

def load_user_data(username):
    file_path = os.path.join(DATA_FOLDER, f"{username}.json")
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
    return {
        "email": "",
        "gmail_pass": "",
        "categories": DEFAULT_CATEGORIES.copy()
    }

def save_user_data(username, data):
    with open(os.path.join(DATA_FOLDER, f"{username}.json"), 'w') as f:
        json.dump(data, f, indent=4)

def test_gmail(email, password):
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email, password)
        mail.logout()
        return True, "Connexion réussie"
    except Exception as e:
        return False, str(e)

def classify_by_keywords(sender, subject, categories_dict):
    text = f"{sender} {subject}".lower()
    best_cat = list(categories_dict.keys())[0]  # première par défaut
    best_score = 0
    for cat, keywords in categories_dict.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best_cat = cat
    return best_cat, best_score

@app.route('/')
def home():
    if 'username' in session:
        return redirect(url_for('bot'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        users = load_users()
        if username in users and users[username].get("password") == password:
            session['username'] = username
            return redirect(url_for('bot'))
        return render_template('login.html', error="Identifiants incorrects")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm = request.form.get('confirm')
        if not username or not password:
            return render_template('register.html', error="Tous les champs sont requis")
        if password != confirm:
            return render_template('register.html', error="Les mots de passe ne correspondent pas")
        users = load_users()
        if username in users:
            return render_template('register.html', error="Nom d'utilisateur déjà pris")
        users[username] = {"password": password}
        save_users(users)
        save_user_data(username, {})
        return render_template('register.html', success=f"Compte {username} créé !")
    return render_template('register.html')

@app.route('/bot')
def bot():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('bot.html', username=session['username'])

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ADMIN (raccourci)
@app.route(f'/{ADMIN_SECRET_PATH}', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        return render_template('admin_login.html', error="Mot de passe incorrect")
    return render_template('admin_login.html')

@app.route(f'/{ADMIN_SECRET_PATH}/dashboard')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    users = load_users()
    users_list = [{"username": u, **d} for u, d in users.items()]
    return render_template('admin_dashboard.html', users=users_list)

@app.route(f'/{ADMIN_SECRET_PATH}/delete/<username>')
def admin_delete(username):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    users = load_users()
    if username in users:
        del users[username]
        save_users(users)
    return redirect(url_for('admin_dashboard'))

@app.route(f'/{ADMIN_SECRET_PATH}/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('home'))

# API
@app.route('/api/user_data')
def api_user_data():
    if 'username' not in session:
        return jsonify({"error": "Non connecté"}), 401
    data = load_user_data(session['username'])
    return jsonify({
        "email": data.get("email", ""),
        "categories": data.get("categories", {})
    })

@app.route('/api/save_gmail', methods=['POST'])
def api_save_gmail():
    if 'username' not in session:
        return jsonify({"error": "Non connecté"}), 401
    data = request.json
    email = data.get('email')
    password = data.get('password')
    user_data = load_user_data(session['username'])
    user_data["email"] = email
    user_data["gmail_pass"] = password
    save_user_data(session['username'], user_data)
    return jsonify({"success": True})

@app.route('/api/test_gmail', methods=['POST'])
def api_test_gmail():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    success, msg = test_gmail(email, password)
    return jsonify({"success": success, "message": msg})

@app.route('/api/save_categories', methods=['POST'])
def api_save_categories():
    if 'username' not in session:
        return jsonify({"error": "Non connecté"}), 401
    data = request.json
    categories = data.get('categories', {})
    user_data = load_user_data(session['username'])
    user_data["categories"] = categories
    save_user_data(session['username'], user_data)
    return jsonify({"success": True})

@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    if 'username' not in session:
        return jsonify({"error": "Non connecté"}), 401
    user_data = load_user_data(session['username'])
    email = user_data.get("email")
    password = user_data.get("gmail_pass")
    if not email or not password:
        return jsonify({"error": "Gmail non configuré"})
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email, password)
        mail.select("INBOX")
        result, data = mail.search(None, "UNSEEN")
        count = len(data[0].split()) if data[0] else 0
        mail.logout()
        return jsonify({"success": True, "count": count})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/classify', methods=['POST'])
def api_classify():
    if 'username' not in session:
        return jsonify({"error": "Non connecté"}), 401
    user_data = load_user_data(session['username'])
    email = user_data.get("email")
    password = user_data.get("gmail_pass")
    categories_dict = user_data.get("categories", {})
    if not email or not password:
        return jsonify({"error": "Gmail non configuré"})
    if not categories_dict:
        return jsonify({"error": "Aucune catégorie définie"})
    
    logs = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email, password)
        logs.append("Connexion IMAP réussie")
        
        for cat in categories_dict:
            try:
                mail.create(cat)
                logs.append(f"Dossier '{cat}' créé/vérifié")
            except Exception as e:
                logs.append(f"Dossier '{cat}' : {e}")
        
        mail.select("INBOX")
        result, data = mail.search(None, "ALL")
        ids = data[0].split()
        total = len(ids)
        logs.append(f"Total emails dans INBOX : {total}")
        
        if total == 0:
            mail.logout()
            return jsonify({"success": True, "count": 0, "total": 0, "logs": logs})
        
        max_emails = min(total, 200)
        classified = 0
        for idx, email_id in enumerate(ids[:max_emails]):
            try:
                result, msg_data = mail.fetch(email_id, "(RFC822)")
                raw_email = None
                for part in msg_data:
                    if isinstance(part, tuple):
                        raw_email = part[1]
                        break
                if raw_email is None:
                    logs.append(f"[{idx+1}] Aucun contenu")
                    continue
                if isinstance(raw_email, str):
                    raw_email = raw_email.encode('utf-8')
                msg = email.message_from_bytes(raw_email)
                subject = msg.get("Subject", "")
                if isinstance(subject, bytes):
                    subject = subject.decode(errors="ignore")
                sender = msg.get("From", "")
                cat, score = classify_by_keywords(sender, subject, categories_dict)
                try:
                    mail.copy(email_id, cat)
                    classified += 1
                    logs.append(f"[{idx+1}] {cat} (score={score}) : {subject[:50]}")
                except Exception as e:
                    logs.append(f"[{idx+1}] ERREUR copie dans {cat} : {e}")
            except Exception as e:
                logs.append(f"[{idx+1}] Erreur traitement : {str(e)}")
        mail.close()
        mail.logout()
        return jsonify({"success": True, "count": classified, "total": total, "logs": logs})
    except Exception as e:
        logs.append(f"Exception générale : {str(e)}\n{traceback.format_exc()}")
        return jsonify({"error": str(e), "logs": logs})

if __name__ == '__main__':
    app.run(debug=True)