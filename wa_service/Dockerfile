FROM node:20-slim

# Dependencias de sistema para Chromium (que usa whatsapp-web.js internamente)
RUN apt-get update && apt-get install -y \
    chromium \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

WORKDIR /app
COPY package*.json ./
RUN npm install --omit=dev
COPY server.js .

EXPOSE 3001
CMD ["node", "server.js"]
