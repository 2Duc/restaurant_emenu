FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL=http://localhost:8000/api
ARG VITE_WS_BASE_URL=ws://localhost:8000
ARG VITE_MEDIA_BASE_URL=http://localhost:8000
ARG VITE_PUBLIC_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL VITE_WS_BASE_URL=$VITE_WS_BASE_URL VITE_MEDIA_BASE_URL=$VITE_MEDIA_BASE_URL VITE_PUBLIC_URL=$VITE_PUBLIC_URL
RUN npm run build

FROM nginx:alpine
# nginx:alpine tu envsubst moi file trong /etc/nginx/templates/*.template vao /etc/nginx/conf.d/ khi khoi dong (CSP theo env)
ENV CSP_CONNECT_SRC="http://localhost:8000 ws://localhost:8000" CSP_IMG_SRC="http://localhost:8000"
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
