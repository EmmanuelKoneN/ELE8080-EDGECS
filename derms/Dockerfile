# Image du serveur DERMS. Construire depuis la racine du dépôt :
#   docker build -f derms/Dockerfile -t edgecs-derms .
# L'image ne contient pas gateway/ : le DERMS ne parle aux passerelles que par DNP3.

# Même version de Python que la CI (target-version = "py311").
FROM python:3.11-slim

# Journal affiché sans délai par « docker compose logs », sans fichiers .pyc dans l'image.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    EDGECS_WEB_ADDRESS=0.0.0.0

WORKDIR /app

# Les dépendances d'abord : Docker réutilise cette couche tant que requirements.txt ne change pas.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY points_dnp3.yaml .
COPY derms/ derms/

# Le serveur n'a pas besoin des droits d'administrateur.
RUN useradd --no-create-home edgecs
USER edgecs

EXPOSE 8000
CMD ["python", "-m", "derms.main"]
