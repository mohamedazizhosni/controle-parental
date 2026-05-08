#!/bin/bash
set -e

SSL_DIR="/etc/squid/ssl"
# Sous-dossier à l'intérieur du volume — peut être créé librement
SSL_DB="/var/spool/squid/ssl_db/certs"

# 1. Générer le certificat CA s'il n'existe pas encore
if [ ! -f "$SSL_DIR/myCA.pem" ]; then
    echo "[entrypoint] Génération du certificat CA..."
    mkdir -p "$SSL_DIR"
    openssl req -new -newkey rsa:2048 -days 3650 -nodes -x509 \
        -subj "/C=FR/ST=France/O=ControleParental/CN=ParentalCA" \
        -keyout "$SSL_DIR/myCA.key" \
        -out "$SSL_DIR/myCA.pem"
    cp "$SSL_DIR/myCA.pem" "$SSL_DIR/ca-certificate.crt"
    echo "[entrypoint] Certificat CA généré."
else
    echo "[entrypoint] Certificat CA déjà présent."
fi

# 2. Initialiser la base SSL si elle n'existe pas encore
if [ ! -d "$SSL_DB" ]; then
    echo "[entrypoint] Initialisation de la base SSL..."
    /usr/lib/squid/security_file_certgen -c -s "$SSL_DB" -M 16MB
    chown -R proxy:proxy "$SSL_DB"
    echo "[entrypoint] Base SSL initialisée."
else
    echo "[entrypoint] Base SSL déjà initialisée."
fi

# 3. Démarrer Squid
echo "[entrypoint] Démarrage de Squid..."
exec squid -NYCd 1
