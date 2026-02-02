# Build stage
FROM node:20-slim AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source
COPY . .

# Override output to local directory for Docker build
RUN npm run build -- --outDir ./dist

# Production stage
FROM nginx:alpine

# Copy built files from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx config (will be mounted or copied separately)
# Note: nginx.conf should be copied in docker-compose or here

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
