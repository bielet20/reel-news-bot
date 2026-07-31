# Frontend – Next.js en modo desarrollo
FROM node:20-alpine

WORKDIR /app

# Instalar dependencias en la imagen (se sobreescribirán con named volume)
COPY package.json package-lock.json ./
RUN npm ci

ENV NEXT_TELEMETRY_DISABLED=1

EXPOSE 3000

CMD ["npm", "run", "dev"]
