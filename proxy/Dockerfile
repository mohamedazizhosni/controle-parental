FROM ubuntu:22.04

RUN apt-get update && apt-get install -y squid python3 && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /var/log/squid /run/squid

COPY squid.conf /etc/squid/squid.conf
COPY scripts/squid_redirector.py /usr/local/bin/squid_redirector.py
COPY scripts/squid_https_blocker.py /usr/local/bin/squid_https_blocker.py
RUN chmod +x /usr/local/bin/squid_redirector.py /usr/local/bin/squid_https_blocker.py

RUN chown -R proxy:proxy /var/log/squid /run/squid

EXPOSE 3128

CMD ["squid", "-NYCd", "1"]
