FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    squid-openssl \
    python3 \
    python3-pip \
    python3-requests \
    python3-bs4 \
    openssl \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p \
    /var/log/squid \
    /run/squid \
    /var/spool/squid/ssl_db \
    /etc/squid/ssl

COPY squid.conf /etc/squid/squid.conf
COPY scripts/squid_redirector.py /usr/local/bin/squid_redirector.py
COPY scripts/squid_https_blocker.py /usr/local/bin/squid_https_blocker.py
COPY scripts/keywords.py /usr/local/bin/keywords.py
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x \
    /usr/local/bin/squid_redirector.py \
    /usr/local/bin/squid_https_blocker.py \
    /entrypoint.sh

RUN chown -R proxy:proxy \
    /var/log/squid \
    /run/squid \
    /var/spool/squid

EXPOSE 3128 3129

CMD ["/entrypoint.sh"]
