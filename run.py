from app import create_app
import os

app = create_app()

if __name__ == '__main__':
    # Verificação adicional
    print(f"Diretório de trabalho atual: {os.getcwd()}")
    print(f"Conteúdo do diretório: {os.listdir()}")
    app.run(debug=True, host='0.0.0.0', port=5000)