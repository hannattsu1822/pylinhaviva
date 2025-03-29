from flask import Blueprint, render_template, request, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from . import mysql

auth_bp = Blueprint('auth', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logado'):
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        matricula = request.form.get('matricula', '').strip()
        senha = request.form.get('senha', '').strip()
        
        if not matricula or not senha:
            return render_template('login.html', erro="Preencha todos os campos!")
        
        try:
            with mysql.connection.cursor() as cur:
                cur.execute("""
                    SELECT id, matricula, nome, cargo, senha 
                    FROM usuarios 
                    WHERE matricula = %s
                    LIMIT 1
                """, (matricula,))
                
                user = cur.fetchone()
                
                if user:
                    if user['senha'] == senha:  # Senha em texto puro (migração)
                        senha_hash = generate_password_hash(senha)
                        cur.execute("UPDATE usuarios SET senha = %s WHERE id = %s", 
                                  (senha_hash, user['id']))
                        mysql.connection.commit()
                    elif not check_password_hash(user['senha'], senha):
                        return render_template('login.html', erro="Credenciais inválidas!")
                    
                    session.permanent = True
                    session.update({
                        'logado': True,
                        'user_id': user['id'],
                        'matricula': user['matricula'],
                        'nome': user['nome'],
                        'cargo': user['cargo']
                    })
                    return redirect(url_for('main.dashboard'))
                else:
                    return render_template('login.html', erro="Usuário não encontrado!")
        except Exception as e:
            print(f"Erro no banco: {str(e)}")
            return render_template('login.html', erro="Erro no sistema. Tente novamente.")
    
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))