#!/bin/bash
BASE_URL="http://localhost:8000"

echo "1. Test santé API"
curl -s $BASE_URL/health | jq .

echo "2. Inscription d'un parent"
curl -s -X POST $BASE_URL/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"123456","full_name":"Test"}' | jq .

echo "3. Connexion pour obtenir un token"
TOKEN=$(curl -s -X POST $BASE_URL/api/v1/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test@example.com&password=123456" | jq -r .access_token)

echo "Token obtenu : $TOKEN"

echo "4. Accès à la route protégée /me"
curl -s -X GET $BASE_URL/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN" | jq .
