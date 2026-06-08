# UI — React/Vite control panel, built to static assets and served by nginx.
#
# VITE_API_BASE is baked in AT BUILD TIME (Vite inlines import.meta.env into the
# bundle), so it must be passed as a build-arg, not a runtime env var. The CI
# workflow / deploy sets it to the public analysis API URL.
FROM node:20-slim AS build

WORKDIR /app

# Install deps from the lockfile first for layer caching.
COPY package.json package-lock.json ./
RUN npm ci

# Build-time API base; defaults to same-origin /api if not provided.
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=${VITE_API_BASE}

COPY . .
RUN npm run build

# --- runtime: nginx serving the static bundle ---
FROM nginx:1.27-alpine

# SPA routing config (try_files → index.html).
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
