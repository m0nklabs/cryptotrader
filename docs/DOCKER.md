# Docker Setup Guide

This guide covers running cryptotrader with Docker Compose for development and production.

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 4GB+ RAM allocated to Docker
- 10GB+ disk space

## Quick Start

### Development Environment

1. **Clone and configure**:
   ```bash
   git clone https://github.com/m0nklabs/cryptotrader.git
   cd cryptotrader
   cp docker-compose.env.example .env
   # Edit .env with your settings
   ```

2. **Start all services**:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
   ```

3. **Access services**:
   - Frontend: http://localhost:5176
   - API: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - PostgreSQL: localhost:5432

4. **View logs**:
   ```bash
   # All services
   docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f
   
   # Specific service
   docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f api
   ```

5. **Stop services**:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml down
   ```

### Seed Sample Data

After starting services, seed sample market data for testing:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec api bash -c "export DATABASE_URL=postgresql://cryptotrader:cryptotrader@postgres:5432/cryptotrader && ./scripts/seed-data.sh"
```

## Service Details

### PostgreSQL Database

- **Image**: postgres:16-alpine
- **Port**: 5432
- **Data**: Persisted in `./data/postgres/`
- **Init**: Automatically runs `scripts/init-db.sh` and applies `db/schema.sql` on first start

### Backend API

- **Image**: Built from root `Dockerfile`
- **Port**: 8000
- **Hot-reload**: Enabled in dev mode via `--reload` flag
- **Environment**: Configured via `.env` file
- **Health**: `/health` endpoint for status checks

### Frontend

- **Image**: Built from `frontend/Dockerfile`
- **Port**: 5176 (Vite dev server)
- **Hot-reload**: Enabled via volume mounts
- **API URL**: Configured via `VITE_API_URL` environment variable

## Development Workflow

### Hot Reload

Code changes are automatically detected:

- **Backend**: Python files mounted as read-only volumes, uvicorn `--reload` flag restarts on changes
- **Frontend**: Source files mounted, Vite HMR provides instant updates

### Database Migrations

Run migrations manually:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec api python -m scripts.migrate
```

### Running Tests

```bash
# Backend tests
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec api pytest

# Frontend tests
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec frontend npm test
```

### Accessing Containers

```bash
# Backend shell
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec api bash

# Frontend shell
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec frontend sh

# Database shell
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec postgres psql -U cryptotrader -d cryptotrader
```

## Production Deployment

### Production Build

For production, use multi-stage builds without dev overrides:

```bash
# Build images
docker compose build

# Start services
docker compose up -d

# No hot-reload, optimized builds
```

### Environment Variables

Production should use secrets management (Docker secrets, Kubernetes secrets, etc.):

```bash
# Example with Docker secrets
echo "my_secure_password" | docker secret create postgres_password -
```

Update `docker-compose.yml` to use secrets instead of environment variables.

### Health Checks

All services include health checks:

```bash
# Check service health
docker compose ps

# Detailed health status
docker inspect cryptotrader-api --format='{{.State.Health.Status}}'
```

### Logs and Monitoring

```bash
# Export logs
docker compose logs --since 24h > logs/docker-$(date +%Y%m%d).log

# Monitor resource usage
docker stats cryptotrader-api cryptotrader-frontend cryptotrader-postgres
```

## Troubleshooting

### Database Connection Issues

```bash
# Check if postgres is healthy
docker compose ps postgres

# Test connection from API container
docker compose exec api python scripts/healthcheck.py

# Check postgres logs
docker compose logs postgres
```

### Port Conflicts

If ports 5432, 8000, or 5176 are in use:

1. Stop conflicting services
2. Or modify port mappings in `docker-compose.dev.yml`:
   ```yaml
   ports:
     - "8001:8000"  # Map to different host port
   ```

### Disk Space

Clean up unused resources:

```bash
# Remove stopped containers
docker compose down

# Clean up volumes (WARNING: deletes data)
docker compose down -v

# Clean up images
docker system prune -a
```

### Fresh Start

To reset everything:

```bash
# Stop and remove everything
docker compose -f docker-compose.yml -f docker-compose.dev.yml down -v

# Remove data directory
rm -rf ./data/postgres

# Rebuild and start
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

## Platform-Specific Notes

### Linux

- Docker runs natively, best performance
- Ensure user is in `docker` group: `sudo usermod -aG docker $USER`

### macOS

- Docker Desktop required
- File watching may be slower due to VM filesystem overhead
- Allocate at least 4GB RAM in Docker Desktop settings

### Windows (WSL2)

- Docker Desktop with WSL2 backend required
- Clone repo inside WSL2 filesystem for best performance
- Avoid mounting from Windows filesystem (`/mnt/c/`)

## Advanced Configuration

### Custom Network

```yaml
# Add to docker-compose.dev.yml
networks:
  cryptotrader:
    driver: bridge
    ipam:
      config:
        - subnet: 172.28.0.0/16
```

### External Database

To use an external PostgreSQL instance:

1. Remove `postgres` service from compose file
2. Set `DATABASE_URL` to external instance
3. Ensure network connectivity

### Scaling

Scale services horizontally:

```bash
# Multiple API instances behind load balancer
docker compose up -d --scale api=3
```

Note: Frontend and database should remain single instance in dev mode.

## See Also

- [Development Guide](DEVELOPMENT.md) - Manual setup without Docker
- [Architecture](ARCHITECTURE.md) - System design overview
- [Operations](OPERATIONS.md) - Production deployment guide
