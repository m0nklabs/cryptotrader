# Development Dockerfile for frontend
FROM node:20-slim

WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm install

# Copy application code
COPY . .

# Expose Vite dev server port
EXPOSE 5176

# Run Vite dev server
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
