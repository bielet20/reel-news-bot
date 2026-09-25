FROM node:20-slim

# Dependencias de sistema para Chromium (que usa whatsapp-web.js internamente)
RUN apt-get update && apt-get install -y \
    chromium \
    git \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

WORKDIR /app
COPY package*.json ./
RUN git config --global url."https://github.com/".insteadOf "ssh://git@github.com/" && \
    git config --global url."https://github.com/".insteadOf "git@github.com:" && \
    npm install --omit=dev
COPY server.js .

COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

EXPOSE 3001
ENTRYPOINT ["./entrypoint.sh"]
