from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, session
from werkzeug.utils import secure_filename
from .auth import login_required
from . import mysql
import pandas as pd
from datetime import datetime
import os

main_bp = Blueprint('main', __name__)

# Configurations
ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@main_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@main_bp.route('/transformadores')
@login_required
def transformadores():
    try:
        with mysql.connection.cursor() as cur:
            cur.execute("SELECT * FROM transformadores ORDER BY id DESC")
            transformadores = cur.fetchall()
        return render_template('transformadores/main.html', transformadores=transformadores)
    except Exception as e:
        flash(f'Erro ao carregar transformadores: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

@main_bp.route('/transformadores/upload', methods=['GET', 'POST'])
@login_required
def upload_trafo():
    if request.method == 'POST':
        if 'arquivo' not in request.files:
            flash('Nenhum arquivo enviado', 'error')
            return redirect(request.url)
        
        file = request.files['arquivo']
        
        if file.filename == '':
            flash('Nenhum arquivo selecionado', 'error')
            return redirect(request.url)
            
        if not allowed_file(file.filename):
            flash('Tipo de arquivo não permitido. Use Excel (.xlsx, .xls) ou CSV', 'error')
            return redirect(request.url)
        
        try:
            filename = secure_filename(file.filename)
            upload_folder = os.path.join(current_app.root_path, 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            
            df = pd.read_excel(
                filepath,
                sheet_name='TRANSFORMADORES',
                header=1,
                usecols='A:I'
            )
            
            df.columns = [
                'item', 'marca', 'potencia', 'numero_fases', 
                'numero_serie', 'local_retirada', 'regional',
                'motivo_desativacao', 'data_entrada_almoxarifado'
            ]
            
            df = df.where(pd.notnull(df), None)
            
            dados = []
            for _, row in df.iterrows():
                try:
                    data_entrada = None
                    if row['data_entrada_almoxarifado']:
                        if isinstance(row['data_entrada_almoxarifado'], str):
                            data_entrada = datetime.strptime(
                                row['data_entrada_almoxarifado'].split()[0], '%Y-%m-%d'
                            ).date()
                        else:
                            data_entrada = row['data_entrada_almoxarifado'].date()
                    
                    dados.append({
                        'item': str(row['item']).strip(),
                        'marca': str(row['marca']).strip() if row['marca'] else None,
                        'potencia': str(row['potencia']).strip() if row['potencia'] else None,
                        'numero_fases': str(row['numero_fases']).strip() if row['numero_fases'] else None,
                        'numero_serie': str(row['numero_serie']).strip(),
                        'local_retirada': str(row['local_retirada']).strip() if row['local_retirada'] else None,
                        'regional': str(row['regional']).strip() if row['regional'] else None,
                        'motivo_desativacao': str(row['motivo_desativacao']).strip() if row['motivo_desativacao'] else None,
                        'data_entrada_almoxarifado': data_entrada
                    })
                except Exception as e:
                    print(f"Erro processando linha {_}: {str(e)}")
                    continue
            
            success_count = 0
            duplicates = 0
            errors = 0
            with mysql.connection.cursor() as cur:
                for item in dados:
                    try:
                        cur.execute(
                            "SELECT id FROM transformadores WHERE numero_serie = %s",
                            (item['numero_serie'],)
                        )
                        if cur.fetchone():
                            duplicates += 1
                            continue
                            
                        cur.execute("""
                            INSERT INTO transformadores (
                                item, marca, potencia, numero_fases, numero_serie,
                                local_retirada, regional, motivo_desativacao, data_entrada_almoxarifado
                            ) VALUES (
                                %(item)s, %(marca)s, %(potencia)s, %(numero_fases)s, %(numero_serie)s,
                                %(local_retirada)s, %(regional)s, %(motivo_desativacao)s, %(data_entrada_almoxarifado)s
                            )
                        """, item)
                        success_count += 1
                    except Exception as e:
                        print(f"Erro inserindo {item['numero_serie']}: {str(e)}")
                        errors += 1
                
                mysql.connection.commit()
            
            os.remove(filepath)
            
            msg = f"Importação concluída: {success_count} novos registros"
            if duplicates > 0:
                msg += f", {duplicates} duplicados ignorados"
            if errors > 0:
                msg += f", {errors} erros encontrados"
            
            flash(msg, 'success' if success_count > 0 else 'warning')
            return redirect(url_for('main.transformadores'))
            
        except Exception as e:
            mysql.connection.rollback()
            if 'filepath' in locals() and os.path.exists(filepath):
                os.remove(filepath)
            flash(f'Erro ao importar arquivo: {str(e)}', 'error')
            return redirect(request.url)
    
    return render_template('transformadores/upload_trafo.html')

@main_bp.route('/transformadores/inspecao', methods=['GET', 'POST'])
@login_required
def inspecao_trafo():
    if request.method == 'POST':
        try:
            # Processar checkboxes (que enviam listas)
            estado_tanque = ', '.join(request.form.getlist('estado_tanque'))
            
            # Tratar corrosão especial
            corrosao_tanque = None
            if 'COM CORROSÃO' in estado_tanque:
                corrosao_tanque = request.form.get('corrosao_grau')
                estado_tanque = estado_tanque.replace('COM CORROSÃO', '').strip()
                if estado_tanque.endswith(','):
                    estado_tanque = estado_tanque[:-1].strip()

            # Processar data de fabricação
            data_fabricacao = None
            if request.form.get('data_fabricacao'):
                data_fabricacao = datetime.strptime(request.form['data_fabricacao'], '%Y-%m-%d').date()

            # Processar reformado
            reformado = request.form.get('reformado') == 'Sim'
            data_reformado = None
            if reformado and request.form.get('data_reformado'):
                data_reformado = datetime.strptime(request.form['data_reformado'], '%Y-%m-%d').date()

            # Processar buchas primárias
            buchas_primarias = ', '.join(request.form.getlist('buchas_primarias'))
            if 'Normal' in buchas_primarias and len(buchas_primarias.split(',')) > 1:
                buchas_primarias = 'Normal'

            # Processar buchas secundárias
            buchas_secundarias = ', '.join(request.form.getlist('buchas_secundarias'))
            if 'Normal' in buchas_secundarias and len(buchas_secundarias.split(',')) > 1:
                buchas_secundarias = 'Normal'

            # Processar conectores
            conectores = ', '.join(request.form.getlist('conectores'))
            if 'Normal' in conectores and len(conectores.split(',')) > 1:
                conectores = 'Normal'

            with mysql.connection.cursor() as cur:
                form_data = {
                    'numero_serie': request.form['numero_serie'],
                    'detalhes_tanque': estado_tanque,
                    'corrosao_tanque': corrosao_tanque,
                    'data_fabricacao': data_fabricacao,
                    'reformado': reformado,
                    'data_reformado': data_reformado,
                    'buchas_primarias': buchas_primarias,
                    'buchas_secundarias': buchas_secundarias,
                    'conectores': conectores,
                    'avaliacao_bobina_i': request.form['avaliacao_bobina_i'],
                    'avaliacao_bobina_ii': request.form['avaliacao_bobina_ii'],
                    'avaliacao_bobina_iii': request.form['avaliacao_bobina_iii'],
                    'conclusao': request.form['conclusao'],
                    'transformador_destinado': request.form['transformador_destinado'],
                    'matricula_responsavel': session['matricula'],
                    'supervisor_tecnico': 'Eng. Alisson',
                    'observacoes': request.form.get('observacoes', '')
                }

                cur.execute("""
                    INSERT INTO checklist_transformadores (
                        numero_serie, detalhes_tanque, corrosao_tanque,
                        data_fabricacao, reformado, data_reformado,
                        buchas_primarias, buchas_secundarias, conectores,
                        avaliacao_bobina_i, avaliacao_bobina_ii, avaliacao_bobina_iii,
                        conclusao, transformador_destinado, matricula_responsavel,
                        supervisor_tecnico, observacoes, data_formulario
                    ) VALUES (
                        %(numero_serie)s, %(detalhes_tanque)s, %(corrosao_tanque)s,
                        %(data_fabricacao)s, %(reformado)s, %(data_reformado)s,
                        %(buchas_primarias)s, %(buchas_secundarias)s, %(conectores)s,
                        %(avaliacao_bobina_i)s, %(avaliacao_bobina_ii)s, %(avaliacao_bobina_iii)s,
                        %(conclusao)s, %(transformador_destinado)s, %(matricula_responsavel)s,
                        %(supervisor_tecnico)s, %(observacoes)s, NOW()
                    )
                """, form_data)
                
                mysql.connection.commit()
                flash('Inspeção salva com sucesso!', 'success')
                return redirect(url_for('main.transformadores'))

        except Exception as e:
            mysql.connection.rollback()
            current_app.logger.error(f"Erro ao salvar inspeção: {str(e)}", exc_info=True)
            flash(f'Erro ao salvar inspeção: {str(e)}', 'error')
            return redirect(url_for('main.inspecao_trafo'))

    # GET request - mostrar formulário
    with mysql.connection.cursor() as cur:
        # Obter apenas transformadores sem checklist
        cur.execute("""
            SELECT t.numero_serie, t.marca, t.potencia 
            FROM transformadores t
            LEFT JOIN checklist_transformadores c ON t.numero_serie = c.numero_serie
            WHERE c.id IS NULL
            ORDER BY t.numero_serie
        """)
        transformadores = cur.fetchall()
        
        # Obter últimas inspeções para referência
        cur.execute("""
            SELECT c.*, t.item, t.marca, t.potencia 
            FROM checklist_transformadores c
            JOIN transformadores t ON c.numero_serie = t.numero_serie
            ORDER BY c.data_formulario DESC
            LIMIT 10
        """)
        checklists = cur.fetchall()
    
    return render_template(
        'transformadores/inspecao_trafo.html',
        transformadores=transformadores,
        checklists=checklists,
        data_atual=datetime.now().strftime('%d/%m/%Y %H:%M'),
        current_user={
            'nome': session.get('nome'),
            'matricula': session.get('matricula')
        },
        form_data=request.form if request.method == 'POST' else None
    )

@main_bp.route('/transformadores/filtrar')
@login_required
def filtrar_trafos():
    try:
        # Obter parâmetros de filtro
        numero_serie = request.args.get('numero_serie')
        data_inicio = request.args.get('data_inicio')
        data_fim = request.args.get('data_fim')
        conclusao = request.args.getlist('conclusao')
        destinado = request.args.get('destinado')

        # Armazenar filtro na sessão
        session['filtro_atual'] = {
            'numero_serie': numero_serie,
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'conclusao': conclusao,
            'destinado': destinado
        }

        query = """
            SELECT c.id, c.numero_serie, c.data_formulario, c.conclusao, 
                   c.transformador_destinado, t.marca, t.potencia 
            FROM checklist_transformadores c
            JOIN transformadores t ON c.numero_serie = t.numero_serie
            WHERE 1=1
        """
        params = []

        if numero_serie:
            query += " AND c.numero_serie LIKE %s"
            params.append(f"%{numero_serie}%")
        
        if data_inicio:
            query += " AND c.data_formulario >= %s"
            params.append(data_inicio)
        
        if data_fim:
            query += " AND c.data_formulario <= %s"
            params.append(data_fim)
        
        if conclusao:
            placeholders = ','.join(['%s'] * len(conclusao))
            query += f" AND c.conclusao IN ({placeholders})"
            params.extend(conclusao)
        
        if destinado:
            query += " AND c.transformador_destinado = %s"
            params.append(destinado)

        query += " ORDER BY c.data_formulario DESC"

        with mysql.connection.cursor() as cur:
            cur.execute(query, params)
            checklists = cur.fetchall()

        return render_template('transformadores/filtrar_trafo.html', 
                           checklists=checklists,
                           current_user={
                               'matricula': session.get('matricula'),
                               'nome': session.get('nome')
                           },
                           filtros=request.args)

    except Exception as e:
        flash(f'Erro ao filtrar inspeções: {str(e)}', 'error')
        return redirect(url_for('main.transformadores'))


@main_bp.route('/transformadores/checklist/<int:id>')
@login_required
def visualizar_checklist(id):
    try:
        # 1. Verificação robusta de existência do ID
        with mysql.connection.cursor() as check_cur:
            check_cur.execute("SELECT id, numero_serie FROM checklist_transformadores WHERE id = %s", (id,))
            checklist_exists = check_cur.fetchone()
            
            if not checklist_exists:
                # Log de IDs existentes para diagnóstico
                check_cur.execute("SELECT id, numero_serie FROM checklist_transformadores ORDER BY id")
                existing = check_cur.fetchall()
                current_app.logger.error(
                    f"Checklist ID {id} não encontrado. IDs válidos:\n" +
                    "\n".join([f"ID: {row['id']} - N° Série: {row['numero_serie']}" for row in existing])
                )
                flash(f'Checklist ID {id} não encontrado', 'error')
                return redirect(url_for('main.filtrar_trafos'))

        # 2. Consulta principal com tratamento absoluto
        with mysql.connection.cursor() as main_cur:
            current_app.logger.info(f"Buscando dados completos para ID {id}")
            
            main_cur.execute("""
                SELECT 
                    c.id, c.numero_serie, c.detalhes_tanque, c.corrosao_tanque,
                    c.data_fabricacao, c.reformado, c.data_reformado,
                    c.buchas_primarias, c.buchas_secundarias, c.conectores,
                    c.avaliacao_bobina_i, c.avaliacao_bobina_ii, c.avaliacao_bobina_iii,
                    c.conclusao, c.transformador_destinado, c.matricula_responsavel,
                    c.supervisor_tecnico, c.observacoes, c.data_formulario,
                    t.item, t.marca, t.potencia, t.numero_fases
                FROM checklist_transformadores c
                LEFT JOIN transformadores t ON c.numero_serie = t.numero_serie
                WHERE c.id = %s
                LIMIT 1
            """, (id,))
            
            result = main_cur.fetchone()
            
            if not result:
                current_app.logger.error(f"Inconsistência: ID {id} existe mas sem dados")
                flash('Erro interno: dados não encontrados', 'error')
                return redirect(url_for('main.filtrar_trafos'))

            # Formatação dos dados
            checklist = {
                'id': result['id'],
                'numero_serie': result['numero_serie'] or 'N/A',
                'detalhes_tanque': result['detalhes_tanque'] or 'Nenhuma observação',
                'corrosao_tanque': result['corrosao_tanque'],
                'data_fabricacao': result['data_fabricacao'].strftime('%Y-%m-%d') if result['data_fabricacao'] else 'Não informada',
                'reformado': 'Sim' if result['reformado'] else 'Não',
                'data_reformado': result['data_reformado'].strftime('%Y-%m-%d') if result['data_reformado'] else 'Não aplicável',
                'buchas_primarias': result['buchas_primarias'] or 'Não informado',
                'buchas_secundarias': result['buchas_secundarias'] or 'Não informado',
                'conectores': result['conectores'] or 'Não informado',
                'avaliacao_bobina_i': result['avaliacao_bobina_i'],
                'avaliacao_bobina_ii': result['avaliacao_bobina_ii'],
                'avaliacao_bobina_iii': result['avaliacao_bobina_iii'],
                'conclusao': result['conclusao'],
                'transformador_destinado': result['transformador_destinado'],
                'data_formulario': result['data_formulario'].strftime('%d/%m/%Y %H:%M'),
                'item': result['item'],
                'marca': result['marca'],
                'potencia': result['potencia'],
                'numero_fases': result['numero_fases']
            }

        return render_template(
            'transformadores/visualizar_checklist.html',
            checklist=checklist,
            current_user={
                'matricula': session.get('matricula'),
                'nome': session.get('nome'),
                'cargo': session.get('cargo')
            }
        )

    except Exception as e:
        current_app.logger.error(f"Erro ao carregar checklist: {str(e)}", exc_info=True)
        flash(f'Erro ao carregar checklist: {str(e)}', 'error')
        return redirect(url_for('main.filtrar_trafos'))
    
@main_bp.route('/transformadores/checklist/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar_checklist(id):
    try:
        if request.method == 'POST':
            # Processar dados do formulário
            estado_tanque = ', '.join(request.form.getlist('estado_tanque'))
            corrosao_tanque = request.form.get('corrosao_grau') if 'COM CORROSÃO' in estado_tanque else None
            data_fabricacao = request.form.get('data_fabricacao')
            reformado = request.form.get('reformado') == 'Sim'
            data_reforma = request.form.get('data_reforma') if reformado else None

            # Processar buchas primárias
            buchas_primarias = ', '.join(request.form.getlist('buchas_primarias'))
            if 'Normal' in buchas_primarias and len(buchas_primarias.split(',')) > 1:
                buchas_primarias = 'Normal'

            # Processar buchas secundárias
            buchas_secundarias = ', '.join(request.form.getlist('buchas_secundarias'))
            if 'Normal' in buchas_secundarias and len(buchas_secundarias.split(',')) > 1:
                buchas_secundarias = 'Normal'

            # Processar conectores
            conectores = ', '.join(request.form.getlist('conectores'))
            if 'Normal' in conectores and len(conectores.split(',')) > 1:
                conectores = 'Normal'

            with mysql.connection.cursor() as cur:
                cur.execute("""
                    UPDATE checklist_transformadores SET
                        numero_serie = %s,
                        detalhes_tanque = %s,
                        corrosao_tanque = %s,
                        data_fabricacao = %s,
                        reformado = %s,
                        data_reforma = %s,
                        buchas_primarias = %s,
                        buchas_secundarias = %s,
                        conectores = %s,
                        avaliacao_bobina_i = %s,
                        avaliacao_bobina_ii = %s,
                        avaliacao_bobina_iii = %s,
                        conclusao = %s,
                        transformador_destinado = %s,
                        observacoes = %s
                    WHERE id = %s
                """, (
                    request.form['numero_serie'],
                    estado_tanque,
                    corrosao_tanque,
                    data_fabricacao if data_fabricacao else None,
                    reformado,
                    data_reforma if data_reforma else None,
                    buchas_primarias,
                    buchas_secundarias,
                    conectores,
                    request.form['avaliacao_bobina_i'],
                    request.form['avaliacao_bobina_ii'],
                    request.form['avaliacao_bobina_iii'],
                    request.form['conclusao'],
                    request.form['transformador_destinado'],
                    request.form.get('observacoes', ''),
                    id
                ))
                mysql.connection.commit()

            flash('Checklist atualizado com sucesso!', 'success')
            return redirect(url_for('main.visualizar_checklist', id=id))

        # GET request - mostrar formulário de edição
        with mysql.connection.cursor() as cur:
            # Obter o checklist
            cur.execute("""
                SELECT c.*, t.marca, t.potencia, t.numero_fases
                FROM checklist_transformadores c
                JOIN transformadores t ON c.numero_serie = t.numero_serie
                WHERE c.id = %s
            """, (id,))
            checklist = cur.fetchone()

            if not checklist:
                flash('Checklist não encontrado', 'error')
                return redirect(url_for('main.filtrar_trafos'))

            # Converter para dicionário e formatar datas
            checklist = dict(checklist)
            if checklist['data_fabricacao']:
                checklist['data_fabricacao'] = checklist['data_fabricacao'].strftime('%Y-%m-%d')
            if checklist['data_reforma']:
                checklist['data_reforma'] = checklist['data_reforma'].strftime('%Y-%m-%d')

            # Obter todos os transformadores para o dropdown
            cur.execute("SELECT numero_serie, marca, potencia FROM transformadores ORDER BY numero_serie")
            transformadores = cur.fetchall()

        return render_template(
            'transformadores/editar_checklist.html',
            checklist=checklist,
            transformadores=transformadores,
            current_user={
                'nome': session.get('nome'),
                'matricula': session.get('matricula')
            },
            data_atual=datetime.now().strftime('%d/%m/%Y %H:%M')
        )

    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f"Erro ao editar checklist: {str(e)}", exc_info=True)
        flash(f'Erro ao editar checklist: {str(e)}', 'error')
        return redirect(url_for('main.filtrar_trafos'))
    

@main_bp.route('/subestacao')
@login_required
def subestacao():
    return render_template('subestacao.html')

@main_bp.route('/frota')
@login_required
def frota():
    return render_template('frota.html')