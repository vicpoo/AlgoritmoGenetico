# wsgi.py
"""
Punto de entrada para Gunicorn en producción (AWS).

Uso local de prueba:
    gunicorn --bind 0.0.0.0:5000 wsgi:app

En AWS Elastic Beanstalk (plataforma Python), Beanstalk busca por defecto
un archivo llamado application.py con una variable `application`. Si usas
Elastic Beanstalk, copia este contenido también a application.py (o crea
ese archivo apuntando aquí). Si usas EC2/Lightsail con tu propio Gunicorn +
Nginx, este wsgi.py es todo lo que necesitas.
"""
from app import app

if __name__ == "__main__":
    app.run()