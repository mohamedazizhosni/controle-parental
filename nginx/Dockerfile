FROM nginx:alpine

# Installer certbot
RUN apk add --no-cache certbot certbot-nginx

# Copier les configurations
COPY nginx.conf /etc/nginx/nginx.conf
COPY ssl-params.conf /etc/nginx/ssl-params.conf

# Créer les dossiers nécessaires
RUN mkdir -p /var/www/certbot
RUN mkdir -p /etc/letsencrypt

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
