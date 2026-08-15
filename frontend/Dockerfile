FROM node:24-alpine AS development

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev"]


FROM node:24-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# tsc -b runs first, so a type error fails the build rather than shipping.
RUN npm run build


# nginx serves the built assets and proxies /api to the back-end, so the browser
# talks to exactly one origin in production as it does behind the Vite dev proxy
# in development. That is what keeps the application free of CORS, and CORS with
# credentials is the hole the CSRF checks in backend/app/csrf.py are built to
# close. No API base URL is baked into the bundle.
FROM nginx:alpine AS production

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
