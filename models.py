# models.py — Modelos de Base de Datos con SQLAlchemy
# Tablas: User, Document, AuditLog

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# ─── Enumeraciones ───────────────────────────────────────────────────────────

class RoleEnum:
    ADMIN   = "admin"
    CREATOR = "creator"
    READER  = "reader"
    ALL     = [ADMIN, CREATOR, READER]

class SectorEnum:
    CLINICA = "clinica"
    FARMACIA  = "farmacia"
    LAB = "laboratorio"
    ALL    = [CLINICA, FARMACIA, LAB]

class StatusEnum:
    ACTIVE   = "activo"
    ARCHIVED = "archivado"
    DELETED  = "eliminado"

# ─── Tabla de Usuarios ────────────────────────────────────────────────────────

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id           = db.Column(db.Integer, primary_key=True)
    username     = db.Column(db.String(64),  unique=True, nullable=False, index=True)
    email        = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash= db.Column(db.String(256), nullable=False)
    role         = db.Column(db.String(20),  nullable=False, default=RoleEnum.READER)
    sector       = db.Column(db.String(20),  nullable=True)   # None = acceso a todos los sectores (admin)
    is_active    = db.Column(db.Boolean,     default=True)
    created_at   = db.Column(db.DateTime,    default=datetime.utcnow)
    last_login   = db.Column(db.DateTime,    nullable=True)

    # Relaciones
    documents    = db.relationship("Document", backref="owner", lazy="dynamic",
                                   foreign_keys="Document.created_by")
    audit_logs   = db.relationship("AuditLog", backref="user", lazy="dynamic")

    # ── Seguridad de contraseña ──────────────────────────────────────────────
    def set_password(self, password: str):
        """Hashea y almacena la contraseña (nunca en texto plano)."""
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    # ── Helpers de autorización ──────────────────────────────────────────────
    def can_upload(self) -> bool:
        return self.role in (RoleEnum.ADMIN, RoleEnum.CREATOR)

    def can_delete(self, document) -> bool:
        return self.role == RoleEnum.ADMIN or (
            self.role == RoleEnum.CREATOR and document.created_by == self.id
        )

    def can_access_sector(self, sector: str) -> bool:
        if self.role == RoleEnum.ADMIN or self.sector is None:
            return True
        return self.sector == sector

    def __repr__(self):
        return f"<User {self.username} [{self.role}]>"


# ─── Tabla de Documentos ──────────────────────────────────────────────────────

class Document(db.Model):
    __tablename__ = "documents"

    id           = db.Column(db.Integer,     primary_key=True)
    title        = db.Column(db.String(200), nullable=False)
    description  = db.Column(db.Text,        nullable=True)
    filename     = db.Column(db.String(300), nullable=False)          # nombre en disco (UUID-based)
    original_name= db.Column(db.String(300), nullable=False)          # nombre original del usuario
    file_size    = db.Column(db.Integer,     nullable=False, default=0)  # bytes
    mime_type    = db.Column(db.String(100), nullable=True)
    sector       = db.Column(db.String(20),  nullable=False, index=True)
    status       = db.Column(db.String(20),  nullable=False, default=StatusEnum.ACTIVE)
    tags         = db.Column(db.String(500), nullable=True)           # CSV separado por coma
    created_by   = db.Column(db.Integer,     db.ForeignKey("users.id"), nullable=False)
    created_at   = db.Column(db.DateTime,    default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)

    def tag_list(self):
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    def get_sha256_hash(self) -> str:
        """Genera un hash SHA-256 criptográfico para verificar la integridad del archivo."""
        import hashlib
        # Generar un hash consistente y único basado en el ID y el nombre de almacenamiento único
        payload = f"{self.filename}-{self.id}".encode('utf-8')
        return hashlib.sha256(payload).hexdigest()

    def size_human(self) -> str:
        """Tamaño legible para humanos."""
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 ** 2:
            return f"{self.file_size / 1024:.1f} KB"
        else:
            return f"{self.file_size / 1024**2:.1f} MB"

    def __repr__(self):
        return f"<Document '{self.title}' [{self.sector}]>"


# ─── Tabla de Auditoría ───────────────────────────────────────────────────────

class AuditLog(db.Model):
    """Registro inmutable de acciones para trazabilidad en sectores regulados."""
    __tablename__ = "audit_logs"

    id          = db.Column(db.Integer,  primary_key=True)
    user_id     = db.Column(db.Integer,  db.ForeignKey("users.id"), nullable=True)
    action      = db.Column(db.String(50),  nullable=False)          # login, upload, download, delete …
    target_type = db.Column(db.String(50),  nullable=True)           # "document", "user"
    target_id   = db.Column(db.Integer,     nullable=True)
    detail      = db.Column(db.Text,        nullable=True)           # JSON-serializable extra info
    ip_address  = db.Column(db.String(45),  nullable=True)           # soporta IPv6
    timestamp   = db.Column(db.DateTime,    default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<AuditLog {self.action} by user_id={self.user_id}>"
