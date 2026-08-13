# Frontend – Next.js en modo desarrollo
FROM node:20-alpine

WORKDIR /app

# CA local extra (opcional): si en el equipo de build hay un antivirus o
# proxy que hace inspeccion TLS, dejar el certificado en certs/ y pasar su
# ruta como build-arg EXTRA_CA_CERT (ver .env / docker-compose.yml). Vacio
# por defecto: Node ignora NODE_EXTRA_CA_CERTS si esta vacia, no afecta a
# otros equipos.
COPY certs/ /app/certs/
ARG EXTRA_CA_CERT=
ENV NODE_EXTRA_CA_CERTS=${EXTRA_CA_CERT}

# Instalar dependencias en la imagen (se sobreescribirán con named volume)
COPY package.json package-lock.json ./
RUN npm ci

ENV NEXT_TELEMETRY_DISABLED=1

EXPOSE 3000

CMD ["npm", "run", "dev"]
