# Usamos una imagen ligera de Python
FROM python:3.11-slim

# Directorio de trabajo en el contenedor
WORKDIR /app

# Copiamos solo los requerimientos primero para aprovechar la caché de Docker
COPY requirements.txt .

# Instalamos dependencias sin guardar caché temporal
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el resto del código
COPY . .

# Exponemos el puerto y ejecutamos Gunicorn ( Flask app:app )
EXPOSE 8000
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000"]
