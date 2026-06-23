# application.py
"""
AWS Elastic Beanstalk (plataforma Python) busca, por convención, un archivo
llamado application.py con una variable `application`. Si despliegas con
Elastic Beanstalk, este archivo es el punto de entrada.

Si en cambio despliegas en una EC2 simple con Gunicorn + Nginx tú mismo,
puedes ignorar este archivo y usar wsgi.py directamente.
"""
from app import app as application

if __name__ == "__main__":
    application.run()