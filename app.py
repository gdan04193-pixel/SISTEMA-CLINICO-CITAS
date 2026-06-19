# app.py — Backend principal: configuración de Flask + todas las rutas
# Protecciones: SQL Injection (ORM), XSS (Jinja2 autoescaping), sesiones seguras

import os
import uuid
import json
import logging
from datetime import datetime, timedelta
from functools import wraps
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, send_from_directory, abort, session, jsonify)
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)
from flask_wtf import CSRFProtect
from werkzeug.utils import secure_filename

# Gemini AI Import
from google import genai
from pydantic import BaseModel
from fpdf import FPDF
import PyPDF2

from models import db, User, Document, AuditLog, RoleEnum, SectorEnum, StatusEnum

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

def create_app():
    app = Flask(__name__)

    # ── Seguridad de sesión ──────────────────────────────────────────────────
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", os.urandom(32))
    app.config["SESSION_COOKIE_HTTPONLY"]  = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"]   = False
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=2)

    # ── Base de datos (PostgreSQL) ────────────────────────────────────────────
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/docvault" # Mantenemos db actual por simplicidad, o healthvault
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # ── Subida de archivos ────────────────────────────────────────────────────
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    app.config["UPLOAD_FOLDER"]   = os.path.join(BASE_DIR, "uploads")
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB
    ALLOWED_EXTENSIONS = {"pdf", "docx", "xlsx", "txt", "png", "jpg", "jpeg"}

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # ── Extensiones ───────────────────────────────────────────────────────────
    db.init_app(app)
    csrf = CSRFProtect(app)

    login_manager = LoginManager(app)
    login_manager.login_view        = "login"
    login_manager.login_message     = "Inicia sesión para continuar."
    login_manager.login_message_category = "warning"

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("healthvault")

    # ══════════════════════════════════════════════════════════════════════════
    # HELPERS INTERNOS
    # ══════════════════════════════════════════════════════════════════════════

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    def allowed_file(filename: str) -> bool:
        return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

    def log_action(action: str, target_type=None, target_id=None, detail=None):
        entry = AuditLog(
            user_id     = current_user.id if current_user.is_authenticated else None,
            action      = action,
            target_type = target_type,
            target_id   = target_id,
            detail      = json.dumps(detail) if detail else None,
            ip_address  = request.remote_addr,
        )
        db.session.add(entry)
        db.session.commit()

    def role_required(*roles):
        def decorator(f):
            @wraps(f)
            def wrapped(*args, **kwargs):
                if not current_user.is_authenticated:
                    return redirect(url_for("login"))
                if current_user.role not in roles:
                    flash("No tienes permisos para acceder a esta sección.", "danger")
                    return redirect(url_for("dashboard"))
                return f(*args, **kwargs)
            return wrapped
        return decorator

    # ══════════════════════════════════════════════════════════════════════════
    # RUTAS DE AUTENTICACIÓN
    # ══════════════════════════════════════════════════════════════════════════

    @app.route("/", methods=["GET"])
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            user = User.query.filter_by(username=username, is_active=True).first()

            if user and user.check_password(password):
                login_user(user, remember=False)
                session.permanent = True
                user.last_login = datetime.utcnow()
                db.session.commit()
                log_action("login", detail={"username": username})
                flash(f"Bienvenido a HealthVault, {user.username}.", "success")
                next_page = request.args.get("next")
                return redirect(next_page or url_for("dashboard"))
            else:
                log_action("login_failed", detail={"username": username})
                flash("Credenciales incorrectas.", "danger")

        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        log_action("logout")
        logout_user()
        flash("Sesión cerrada correctamente.", "success")
        return redirect(url_for("login"))

    # ══════════════════════════════════════════════════════════════════════════
    # RUTAS PRINCIPALES — DOCUMENTOS
    # ══════════════════════════════════════════════════════════════════════════

    @app.route("/dashboard")
    @login_required
    def dashboard():
        sector_filter = request.args.get("sector", "")
        search_query  = request.args.get("q", "").strip()
        page          = request.args.get("page", 1, type=int)

        query = Document.query.filter_by(status=StatusEnum.ACTIVE)

        if current_user.role != RoleEnum.ADMIN and current_user.sector:
            query = query.filter_by(sector=current_user.sector)
        elif sector_filter and sector_filter in SectorEnum.ALL:
            query = query.filter_by(sector=sector_filter)

        if search_query:
            like = f"%{search_query}%"
            query = query.filter(
                db.or_(
                    Document.title.ilike(like),
                    Document.description.ilike(like),
                    Document.tags.ilike(like),
                )
            )

        docs = query.order_by(Document.created_at.desc()).paginate(page=page, per_page=12)

        stats = {
            "total":       Document.query.filter_by(status=StatusEnum.ACTIVE).count(),
            "clinica":     Document.query.filter_by(status=StatusEnum.ACTIVE, sector=SectorEnum.CLINICA).count(),
            "farmacia":    Document.query.filter_by(status=StatusEnum.ACTIVE, sector=SectorEnum.FARMACIA).count(),
            "laboratorio": Document.query.filter_by(status=StatusEnum.ACTIVE, sector=SectorEnum.LAB).count(),
        }

        return render_template("dashboard.html",
                               docs=docs, stats=stats,
                               sectors=SectorEnum.ALL,
                               sector_filter=sector_filter,
                               search_query=search_query)

    @app.route("/upload", methods=["GET", "POST"])
    @login_required
    def upload():
        if not current_user.can_upload():
            flash("No tienes permiso para subir documentos médicos.", "danger")
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            title       = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            sector      = request.form.get("sector", "").strip()
            tags        = request.form.get("tags", "").strip()
            file        = request.files.get("file")

            errors = []
            if not title or len(title) > 200:
                errors.append("El título es obligatorio (máx. 200 caracteres).")
            if sector not in SectorEnum.ALL:
                errors.append("Sector inválido.")
            if not file or file.filename == "":
                errors.append("Selecciona un archivo.")
            elif not allowed_file(file.filename):
                errors.append("Tipo de archivo no permitido.")
            if not current_user.can_access_sector(sector):
                errors.append("No tienes acceso a esa área médica.")

            if errors:
                for e in errors:
                    flash(e, "danger")
                return render_template("upload.html", sectors=SectorEnum.ALL)

            original_name = secure_filename(file.filename)
            ext = original_name.rsplit(".", 1)[1].lower()
            safe_name = f"{uuid.uuid4().hex}.{ext}"
            file_path = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)
            file.save(file_path)
            file_size = os.path.getsize(file_path)

            doc = Document(
                title         = title,
                description   = description,
                filename      = safe_name,
                original_name = original_name,
                file_size     = file_size,
                mime_type     = file.mimetype,
                sector        = sector,
                tags          = tags,
                created_by    = current_user.id,
            )
            db.session.add(doc)
            db.session.commit()

            log_action("upload", "document", doc.id, {"title": title, "sector": sector})
            flash(f"Documento médico «{title}» subido exitosamente.", "success")
            return redirect(url_for("dashboard"))

        return render_template("upload.html", sectors=SectorEnum.ALL)

    @app.route("/download/<int:doc_id>")
    @login_required
    def download(doc_id):
        doc = Document.query.filter_by(id=doc_id, status=StatusEnum.ACTIVE).first_or_404()
        if not current_user.can_access_sector(doc.sector):
            log_action("download_denied", "document", doc_id)
            abort(403)
        log_action("download", "document", doc_id, {"title": doc.title})
        return send_from_directory(
            app.config["UPLOAD_FOLDER"],
            doc.filename,
            as_attachment=True,
            download_name=doc.original_name,
        )

    @app.route("/preview/<int:doc_id>")
    @login_required
    def preview(doc_id):
        doc = Document.query.filter_by(id=doc_id, status=StatusEnum.ACTIVE).first_or_404()
        if not current_user.can_access_sector(doc.sector):
            abort(403)
        # as_attachment=False permite que el navegador intente renderizar el PDF inline
        return send_from_directory(
            app.config["UPLOAD_FOLDER"],
            doc.filename,
            as_attachment=False,
        )

    @app.route("/document/<int:doc_id>")
    @login_required
    def document_detail(doc_id):
        doc = Document.query.filter_by(id=doc_id, status=StatusEnum.ACTIVE).first_or_404()
        if not current_user.can_access_sector(doc.sector):
            abort(403)
        log_action("view", "document", doc_id)
        logs = AuditLog.query.filter_by(target_type="document", target_id=doc_id).order_by(AuditLog.timestamp.desc()).all()
        return render_template("document_detail.html", doc=doc, logs=logs)

    @app.route("/delete/<int:doc_id>", methods=["POST"])
    @login_required
    def delete_document(doc_id):
        doc = Document.query.filter_by(id=doc_id, status=StatusEnum.ACTIVE).first_or_404()
        if not current_user.can_delete(doc):
            flash("No tienes permiso para eliminar este documento.", "danger")
            return redirect(url_for("dashboard"))

        doc.status = StatusEnum.DELETED
        db.session.commit()
        log_action("delete", "document", doc_id, {"title": doc.title})
        flash(f"Registro médico «{doc.title}» enviado a la papelera.", "warning")
        return redirect(url_for("dashboard"))

    @app.route("/trash")
    @login_required
    def trash():
        query = Document.query.filter_by(status=StatusEnum.DELETED)
        if current_user.role != RoleEnum.ADMIN and current_user.sector:
            query = query.filter_by(sector=current_user.sector)
        
        docs = query.order_by(Document.updated_at.desc()).all()
        return render_template("papelera.html", docs=docs)

    @app.route("/restore/<int:doc_id>", methods=["POST"])
    @login_required
    def restore_document(doc_id):
        doc = Document.query.filter_by(id=doc_id, status=StatusEnum.DELETED).first_or_404()
        if not current_user.can_access_sector(doc.sector):
            abort(403)
            
        doc.status = StatusEnum.ACTIVE
        db.session.commit()
        log_action("restore", "document", doc_id, {"title": doc.title})
        flash(f"Documento «{doc.title}» restaurado exitosamente.", "success")
        return redirect(url_for("trash"))

    @app.route("/hard_delete/<int:doc_id>", methods=["POST"])
    @login_required
    def hard_delete_document(doc_id):
        doc = Document.query.filter_by(id=doc_id, status=StatusEnum.DELETED).first_or_404()
        if not current_user.can_delete(doc):
            abort(403)
            
        try:
            file_path = os.path.join(app.config["UPLOAD_FOLDER"], doc.filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.error(f"Error borrando archivo físico {doc.filename}: {e}")
            
        db.session.delete(doc)
        db.session.commit()
        log_action("hard_delete", "document", 0, {"title": doc.title, "filename": doc.filename})
        flash(f"Documento «{doc.title}» eliminado de forma permanente.", "success")
        return redirect(url_for("trash"))

    # ══════════════════════════════════════════════════════════════════════════
    # RUTAS DE ADMINISTRACIÓN
    # ══════════════════════════════════════════════════════════════════════════

    @app.route("/admin/users")
    @login_required
    @role_required(RoleEnum.ADMIN)
    def admin_users():
        users = User.query.order_by(User.created_at.desc()).all()
        return render_template("admin_users.html", users=users,
                               roles=RoleEnum.ALL, sectors=SectorEnum.ALL)

    @app.route("/admin/users/create", methods=["POST"])
    @login_required
    @role_required(RoleEnum.ADMIN)
    def admin_create_user():
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        role     = request.form.get("role", RoleEnum.READER)
        sector   = request.form.get("sector") or None

        if not username or not email or not password:
            flash("Todos los campos son obligatorios.", "danger")
            return redirect(url_for("admin_users"))
        if role not in RoleEnum.ALL:
            flash("Rol inválido.", "danger")
            return redirect(url_for("admin_users"))
        if User.query.filter(
            db.or_(User.username == username, User.email == email)
        ).first():
            flash("El usuario o correo ya existe.", "danger")
            return redirect(url_for("admin_users"))

        user = User(username=username, email=email, role=role, sector=sector)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        log_action("create_user", "user", user.id, {"username": username, "role": role})
        flash(f"Personal médico «{username}» registrado.", "success")
        return redirect(url_for("admin_users"))

    @app.route("/admin/audit")
    @login_required
    @role_required(RoleEnum.ADMIN)
    def admin_audit():
        page = request.args.get("page", 1, type=int)
        logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=30)
        
        stats = {
            "total": AuditLog.query.count(),
            "alerts": AuditLog.query.filter(AuditLog.action.in_(["download_denied", "login_failed"])).count(),
            "downloads": AuditLog.query.filter_by(action="download").count(),
            "uploads": AuditLog.query.filter_by(action="upload").count(),
        }
        
        return render_template("admin_audit.html", logs=logs, stats=stats)

    # ══════════════════════════════════════════════════════════════════════════
    # RUTA CHATBOT AI GEMINI
    # ══════════════════════════════════════════════════════════════════════════

    @app.route("/api/chat", methods=["POST"])
    @login_required
    # Deshabilitamos CSRF para esta ruta API en específico
    @csrf.exempt
    def api_chat():
        data = request.get_json()
        history = data.get("history")
        if not history or not isinstance(history, list):
            return jsonify({"error": "Historial requerido"}), 400

        api_key = os.environ.get("GEMINI_API_KEY")

        if not api_key:
            return jsonify({
                "response": "Lo siento, la IA no está configurada. Añade GEMINI_API_KEY al entorno."
            })

        try:
            client = genai.Client(api_key=api_key)
            
            # Definir esquema para forzar a Gemini a devolver JSON
            class ChatResponse(BaseModel):
                generate_pdf: bool
                pdf_type: str | None = None
                message: str
                paciente: str | None = None
                edad: str | None = None
                diagnostico: str | None = None
                medicamentos: str | None = None
                indicaciones: str | None = None
                contenido_principal: str | None = None

            # Obtener contexto de BD para el chatbot
            recent_docs = Document.query.filter_by(status=StatusEnum.ACTIVE).order_by(Document.created_at.desc()).limit(50).all()
            db_context = []
            for d in recent_docs:
                db_context.append(f"- ID: {d.id} | Titulo: {d.title} | Sector: {d.sector} | Fecha: {d.created_at.strftime('%Y-%m-%d')} | Autor: {d.owner.username if d.owner else 'Desconocido'}")
            db_context_str = "\n".join(db_context)

            system_instruction = (
                "Eres HealthVault Assistant, un asistente virtual profesional para un sistema médico. "
                "Si el usuario pide crear o generar un documento (receta médica, historial clínico, reporte, o resultados de laboratorio), "
                "PRIMERO debes verificar si tienes el 'nombre del paciente' y su 'edad'. "
                "Si NO tienes el nombre o la edad, pon 'generate_pdf' en false y pregúntale amablemente por esos datos en 'message'. "
                "Si YA TIENES el nombre, la edad y la información necesaria, pon 'generate_pdf' en true. "
                "En ese caso, define 'pdf_type' estrictamente como 'receta', 'clinica', o 'laboratorio' según corresponda al tipo de documento solicitado. "
                "En 'message' pon un texto diciendo que has generado el documento correspondiente. "
                "Rellena 'paciente' y 'edad'. "
                "Si es 'receta': rellena 'diagnostico', 'medicamentos', e 'indicaciones'. "
                "Si es 'clinica' o 'laboratorio': rellena 'contenido_principal' con el reporte médico o los resultados de los análisis clínicos detallados de forma profesional. "
                "Si NO es una petición para generar un documento, pon 'generate_pdf' en false y responde la duda médica general en 'message'.\n\n"
                "=== CONTEXTO DE BASE DE DATOS ===\n"
                "Aquí tienes los últimos 50 documentos subidos al sistema. Usa esta información para responder si el usuario pregunta sobre estadísticas, documentos recientes, cantidad de recetas, etc.:\n"
                f"{db_context_str}\n"
                "================================="
            )
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=history,
                config=genai.types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=ChatResponse,
                )
            )
            
            import json
            data_resp = json.loads(response.text)
            
            if data_resp.get("generate_pdf"):
                def clean_pdf_text(t):
                    if not t: return ""
                    return str(t).encode('latin-1', 'replace').decode('latin-1')
                
                # Generar PDF
                pdf_type = data_resp.get("pdf_type") or "receta"
                pdf_filename = f"{pdf_type}_{uuid.uuid4().hex}.pdf"
                pdf_path = os.path.join(app.config["UPLOAD_FOLDER"], pdf_filename)
                
                pdf = FPDF()
                pdf.add_page()
                
                # Header
                pdf.set_font("Helvetica", 'B', 16)
                if pdf_type == "clinica":
                    pdf.cell(0, 10, "HEALTHVAULT - REPORTE CLINICO", ln=True, align='C')
                    sector_val = SectorEnum.CLINICA
                    doc_desc = "Historial / Reporte Clínico generado por IA"
                elif pdf_type == "laboratorio":
                    pdf.cell(0, 10, "HEALTHVAULT - RESULTADOS DE LABORATORIO", ln=True, align='C')
                    sector_val = SectorEnum.LAB
                    doc_desc = "Resultados de Análisis generados por IA"
                else:
                    pdf.cell(0, 10, "HEALTHVAULT - RECETA MEDICA", ln=True, align='C')
                    sector_val = SectorEnum.FARMACIA
                    doc_desc = "Receta generada por IA"
                    
                pdf.ln(10)
                
                pdf.set_font("Helvetica", '', 12)
                pdf.cell(0, 8, f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True)
                pdf.cell(0, 8, f"Doctor(a): {current_user.username.upper()}", ln=True)
                pdf.ln(5)
                
                pdf.set_font("Helvetica", 'B', 12)
                pdf.cell(0, 8, "Datos del Paciente:", ln=True)
                pdf.set_font("Helvetica", '', 12)
                pdf.cell(0, 8, f"Nombre: {clean_pdf_text(data_resp.get('paciente', 'No especificado'))}", ln=True)
                pdf.cell(0, 8, f"Edad: {clean_pdf_text(data_resp.get('edad', 'No especificada'))}", ln=True)
                
                if pdf_type == "receta":
                    pdf.cell(0, 8, f"Diagnostico: {clean_pdf_text(data_resp.get('diagnostico', 'No especificado'))}", ln=True)
                    pdf.ln(5)
                    pdf.set_font("Helvetica", 'B', 12)
                    pdf.cell(0, 8, "Medicamentos:", ln=True)
                    pdf.set_font("Helvetica", '', 12)
                    pdf.multi_cell(0, 8, clean_pdf_text(data_resp.get('medicamentos', '')))
                    pdf.ln(5)
                    pdf.set_font("Helvetica", 'B', 12)
                    pdf.cell(0, 8, "Indicaciones:", ln=True)
                    pdf.set_font("Helvetica", '', 12)
                    pdf.multi_cell(0, 8, clean_pdf_text(data_resp.get('indicaciones', '')))
                else:
                    pdf.ln(5)
                    pdf.set_font("Helvetica", 'B', 12)
                    pdf.cell(0, 8, "Detalles Clínicos / Resultados:", ln=True)
                    pdf.set_font("Helvetica", '', 12)
                    pdf.multi_cell(0, 8, clean_pdf_text(data_resp.get('contenido_principal', 'Sin detalles especificados.')))
                
                pdf.ln(20)
                pdf.cell(0, 8, "___________________________", ln=True, align='C')
                pdf.cell(0, 8, "Firma del Medico", ln=True, align='C')
                
                pdf.output(pdf_path)
                file_size = os.path.getsize(pdf_path)
                
                doc = Document(
                    title=f"Receta - {data_resp.get('paciente', 'Paciente')}",
                    description="Receta generada por IA",
                    filename=pdf_filename,
                    original_name=f"receta_{data_resp.get('paciente', 'paciente')}.pdf",
                    file_size=file_size,
                    mime_type="application/pdf",
                    sector=SectorEnum.FARMACIA,
                    tags="receta,ia",
                    created_by=current_user.id,
                )
                db.session.add(doc)
                db.session.commit()
                log_action("upload", "document", doc.id, {"title": doc.title})
                
                reply_msg = (
                    f"{data_resp.get('message', 'Receta generada con éxito.')}<br><br>"
                    f"⬇️ <a href='/download/{doc.id}' style='text-decoration:underline; font-weight:bold; color: var(--salud);'>Descargar Receta PDF</a><br><br>"
                    f"👁️ <a href='/document/{doc.id}' style='text-decoration:underline; font-size:0.9em; color: var(--text-muted);'>Ver Detalles y Firma</a>"
                )
                return jsonify({
                    "response": reply_msg, 
                    "is_html": True,
                    "raw_text": response.text
                })
                
            return jsonify({
                "response": data_resp.get("message", response.text), 
                "is_html": False,
                "raw_text": response.text
            })
            
        except Exception as e:
            logger.error(f"Error en Gemini API: {e}")
            import traceback
            traceback.print_exc()
            error_str = str(e)
            if "503" in error_str or "UNAVAILABLE" in error_str:
                return jsonify({"response": "Los servidores de Inteligencia Artificial están experimentando alta demanda. Por favor, intenta de nuevo en unos segundos."}), 500
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                return jsonify({"response": "Has superado el límite de uso de tu clave de API de Google Gemini (Cuota Excedida). Por favor, verifica tu facturación en Google AI Studio o espera unos minutos."}), 500
            return jsonify({"response": f"Hubo un error en el servidor: {error_str}"}), 500

    @app.route("/api/summarize/<int:doc_id>", methods=["POST"])
    @login_required
    @csrf.exempt
    def api_summarize(doc_id):
        doc = Document.query.filter_by(id=doc_id, status=StatusEnum.ACTIVE).first_or_404()
        if not current_user.can_access_sector(doc.sector):
            return jsonify({"error": "Acceso denegado"}), 403
            
        if doc.mime_type != 'application/pdf':
            return jsonify({"error": "Solo se pueden resumir archivos PDF"}), 400
            
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return jsonify({"error": "IA no configurada. Agrega GEMINI_API_KEY"}), 500
            
        try:
            pdf_path = os.path.join(app.config["UPLOAD_FOLDER"], doc.filename)
            text = ""
            with open(pdf_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for i in range(min(5, len(reader.pages))):
                    text += reader.pages[i].extract_text() + "\n"
                    
            client = genai.Client(api_key=api_key)
            prompt = (
                f"Actúa como un médico experto. Resume el siguiente documento médico de forma profesional. "
                f"Devuelve la respuesta en formato HTML (sin ```html), usando <h3> para los títulos principales (ej. Hallazgos Principales, Diagnóstico, Tratamiento) y <ul><li> para listas.\n\n"
                f"Texto del Documento:\n{text}"
            )
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            
            # Limpiar etiquetas markdown por si acaso
            html_content = response.text.replace("```html", "").replace("```", "")
            
            log_action("view", "document", doc.id, {"title": "Resumen IA generado"})
            return jsonify({"summary": html_content})
            
        except Exception as e:
            logger.error(f"Error resumiendo PDF: {e}")
            import traceback
            traceback.print_exc()
            error_str = str(e)
            if "503" in error_str or "UNAVAILABLE" in error_str:
                return jsonify({"error": "Los servidores de IA están muy ocupados. Intenta de nuevo más tarde."}), 500
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                return jsonify({"error": "Has superado la cuota gratuita de tu API Key de Gemini. Verifica tu plan."}), 500
            return jsonify({"error": f"Error del sistema: {error_str}"}), 500

    # ══════════════════════════════════════════════════════════════════════════
    # MANEJADORES DE ERROR
    # ══════════════════════════════════════════════════════════════════════════

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", code=403,
                               msg="Acceso denegado. No tienes permisos para este expediente."), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404,
                               msg="Página o recurso no encontrado en HealthVault."), 404

    @app.errorhandler(413)
    def file_too_large(e):
        flash("El archivo médico supera el límite de 20 MB.", "danger")
        return redirect(url_for("upload"))

    @app.context_processor
    def inject_globals():
        return {"RoleEnum": RoleEnum, "SectorEnum": SectorEnum, "now": datetime.utcnow()}

    # ══════════════════════════════════════════════════════════════════════════
    # INICIALIZACIÓN DE BD Y DATOS DE PRUEBA
    # ══════════════════════════════════════════════════════════════════════════

    with app.app_context():
        # En caso de que las tablas existan con el SectorEnum anterior,
        # esto puede causar errores en Postgres si usamos ENUMs, pero como es VARCHAR(20),
        # no habrá problema a nivel de BD, solo con los datos antiguos.
        db.create_all()
        _seed_data()

    return app


def _seed_data():
    """Crea usuarios y documentos de demostración médicos."""
    if User.query.first():
        return

    demo_users = [
        dict(username="admin_sys",   email="admin@healthvault.mx", role="admin",   sector=None,             password="Admin123!"),
        dict(username="dr_martinez", email="martinez@clinica.mx",  role="creator", sector=SectorEnum.CLINICA,    password="Salud456!"),
        dict(username="farm_gomez",  email="gomez@farmacia.mx",    role="creator", sector=SectorEnum.FARMACIA,   password="Farma789!"),
        dict(username="lab_perez",   email="perez@laboratorio.mx", role="reader",  sector=SectorEnum.LAB,        password="Lab000!"),
    ]
    for d in demo_users:
        u = User(username=d["username"], email=d["email"], role=d["role"], sector=d["sector"])
        u.set_password(d["password"])
        db.session.add(u)

    db.session.flush()
    admin = User.query.filter_by(username="admin_sys").first()

    demo_docs = [
        dict(title="Protocolo UCI - COVID-19",      sector=SectorEnum.CLINICA, tags="protocolo,urgencias,uci"),
        dict(title="Historial Clínico - Paciente X",sector=SectorEnum.CLINICA, tags="historial,cardiologia"),
        dict(title="Receta Médica - Omeprazol",     sector=SectorEnum.FARMACIA, tags="receta,gastro"),
        dict(title="Inventario de Analgésicos Q2",  sector=SectorEnum.FARMACIA, tags="inventario,stock"),
        dict(title="Resultados Sangre - Perfil 1",  sector=SectorEnum.LAB,      tags="analisis,sangre"),
        dict(title="Certificación ISO 9001 - Lab",  sector=SectorEnum.LAB,      tags="certificacion,calidad"),
    ]
    for d in demo_docs:
        doc = Document(
            title=d["title"], description=f"Documento médico: {d['title']}",
            filename=f"demo_{uuid.uuid4().hex}.pdf", original_name=f"{d['title']}.pdf",
            file_size=1024 * 500, mime_type="application/pdf",
            sector=d["sector"], tags=d["tags"], created_by=admin.id,
        )
        db.session.add(doc)

    db.session.commit()


# ── Punto de entrada ──────────────────────────────────────────────────────────
app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
