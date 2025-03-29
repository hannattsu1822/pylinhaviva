from flask import Flask
from flask_mysqldb import MySQL
import os
from dotenv import load_dotenv

load_dotenv()

mysql = MySQL()

def create_app():
    # Configuração de caminhos
    base_dir = os.path.abspath(os.path.dirname(__file__))
    
    app = Flask(__name__,
               template_folder=os.path.join(base_dir, 'templates'),
               static_folder=os.path.join(base_dir, 'static'))
    
    # Configurações
    app.config.update({
        'SECRET_KEY': os.getenv('SECRET_KEY') or 'fallback_secret_key',
        'MYSQL_HOST': 'yamanote.proxy.rlwy.net',
        'MYSQL_USER': 'root',
        'MYSQL_PASSWORD': 'YapHJHzRdhESbzsQdtdqvbvNRcSpeNpw',
        'MYSQL_DB': 'railway',
        'MYSQL_PORT': 51790,
        'MYSQL_CURSORCLASS': 'DictCursor',
        'UPLOAD_FOLDER': os.path.join(base_dir, 'uploads'),
        'MAX_CONTENT_LENGTH': 16 * 1024 * 1024  # 16MB
    })

    # Cria pasta de uploads se não existir
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    mysql.init_app(app)
    
    from . import routes, auth
    app.register_blueprint(routes.main_bp)
    app.register_blueprint(auth.auth_bp)
    
    return app