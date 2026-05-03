#!/bin/bash
mkdir -p proxy/ssl
cd proxy/ssl
openssl genrsa -out ca.key 2048
openssl req -new -x509 -days 3650 -key ca.key -out ca.crt -subj "/CN=ParentalControlCA/O=HexaByte/C=TN"
cd ../..
