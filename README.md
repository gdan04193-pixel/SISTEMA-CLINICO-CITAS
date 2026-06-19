# DocVault — Sistema de Gestión de Documentos

Sistema de gestión documental para sectores de **Salud**, **Legal** y **Gobierno** construido con Flask, PostgreSQL y Jinja2.

## Estructura del proyecto

```
docvault/
├── app.py              ← Backend principal (Flask + todas las rutas)
├── models.py           ← Modelos de base de datos (SQLAlchemy)
├── requirements.txt    ← Dependencias Python
├── .env.example        ← Plantilla de variables de entorno
├── uploads/            ← Archivos subidos (creado automáticamente)
├── static/
│   ├── css/main.css    ← Estilos globales
│   └── js/main.js      ← Scripts de interfaz
└── templates/
    ├── base.html           ← Layout base (navbar, flash, footer)
    ├── login.html          ← Pantalla de inicio de sesión
    ├── dashboard.html      ← Lista/búsqueda de documentos
    ├── upload.html         ← Subir nuevo documento
    ├── document_detail.html← Detalle de un documento
    ├── admin_users.html    ← Gestión de usuarios (admin)
    ├── admin_audit.html    ← Log de auditoría (admin)
    └── error.html          ← Páginas 403/404
```

## Instalación rápida

### 1. Clonar y preparar entorno

```bash
cd docvault
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
# Edita .env con tu SECRET_KEY y DATABASE_URL
```

### 3. Crear la base de datos en PostgreSQL

```sql
CREATE DATABASE docvault;
```

### 4. Ejecutar

```bash
python app.py
```

La app crea las tablas automáticamente y carga datos de demostración en el primer arranque.

Abre `http://localhost:5000` en tu navegador.

---

## Cuentas de demostración

| Usuario   | Contraseña  | Rol     | Sector    |
|-----------|-------------|---------|-----------|
| admin     | Admin123!   | admin   | Todos     |
| dr_vera   | Salud456!   | creator | Salud     |
| lic_ruiz  | Legal789!   | creator | Legal     |
| oficial   | Gov000!     | reader  | Gobierno  |

---

## Funcionalidades

- **Roles:** `admin` (todo), `creator` (subir/ver/eliminar propios), `reader` (sólo ver/descargar)
- **Sectores:** Salud, Legal, Gobierno — cada usuario accede sólo a su sector (excepto admin)
- **Búsqueda:** Por título, descripción y etiquetas
- **Auditoría:** Cada login, subida, descarga y eliminación queda registrada con IP y timestamp
- **Soft-delete:** Los documentos eliminados se marcan, no se borran físicamente

## Seguridad implementada

| Amenaza         | Solución                                              |
|-----------------|-------------------------------------------------------|
| SQL Injection   | SQLAlchemy ORM — consultas parametrizadas siempre     |
| XSS             | Jinja2 autoescapa `{{ }}` + CSP en `<meta>`           |
| CSRF            | Flask-WTF genera y valida token en cada formulario    |
| Sesiones        | `HttpOnly`, `SameSite=Lax`, expiración 2 h            |
| Contraseñas     | `werkzeug.security` PBKDF2-SHA256 + salt 16 bytes     |
| Archivos        | `secure_filename` + UUID + whitelist de extensiones   |
| Autorización    | Decoradores `@role_required` + `can_access_sector()`  |

## Para producción

1. Cambia `SESSION_COOKIE_SECURE = True` (requiere HTTPS)
2. Usa `FLASK_DEBUG=0` y un servidor WSGI como Gunicorn
3. Sirve archivos estáticos con Nginx
4. Rota `SECRET_KEY` periódicamente
