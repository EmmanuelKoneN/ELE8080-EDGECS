# Image d'une passerelle DER. Construire depuis la racine du dépôt :
#   docker build -f gateway/Dockerfile -t edgecs-gateway .
# L'image ne contient pas derms/ : la passerelle ne parle au DERMS que par DNP3.
# Le port DNP3 se choisit au lancement : docker run edgecs-gateway python -m gateway.main 20001

# Même version de Python que la CI (target-version = "py311").
FROM python:3.11-slim

# Journal affiché sans délai par « docker compose logs », sans fichiers .pyc dans l'image.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    EDGECS_LISTEN_ADDRESS=0.0.0.0

WORKDIR /app

# Les dépendances d'abord : Docker réutilise cette couche tant que requirements.txt ne change pas.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY points_dnp3.yaml .
COPY gateway/ gateway/

# La passerelle n'a pas besoin des droits d'administrateur.
RUN useradd --no-create-home edgecs
USER edgecs

EXPOSE 20000
CMD ["python", "-m", "gateway.main"]
