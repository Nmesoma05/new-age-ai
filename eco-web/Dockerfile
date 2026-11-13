# syntax=docker/dockerfile:1.7
# Web image: Next.js standalone server. API_URL and the other settings are runtime env vars; nothing secret is
# baked into the image (the browser bundle never contains API addresses or keys: checked by the browser tests).
FROM node:22-bookworm-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-bookworm-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
# public/ is NOT included in the standalone output: icons, favicon, sw.js and brand files must be copied explicitly
COPY --from=build --chown=node:node /app/public ./public
COPY --from=build --chown=node:node /app/src/content ./src/content
USER 1000
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=4s --start-period=15s \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/login').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
CMD ["node", "server.js"]
