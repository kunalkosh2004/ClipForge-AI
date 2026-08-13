# ClipForge AI

An AI-powered Video Intelligence Platform that automatically transforms long-form videos into viral-ready short-form content. Competing with Opus Clip, Captions AI, Vizard, Klap, and Munch.

## Architecture

```
ClipForge-AI/
├── backend/                  # Python 3.12+, FastAPI, Clean Architecture
│   ├── src/clipforge/
│   │   ├── api/              # FastAPI app, middleware, dependency injection
│   │   ├── common/           # Errors, IDs, logging, pagination, ports
│   │   ├── identity/         # Auth module (register, login, JWT)
│   │   ├── videos/           # Project & video management
│   │   ├── analysis/         # AI analysis, transcripts, subtitles
│   │   ├── clips/            # Clip extraction, thumbnails, delivery
│   │   ├── processing/       # Job management, Redis status streaming
│   │   ├── rendering/        # FFmpeg video processing
│   │   ├── ai/               # AI provider abstraction (Gemini + Mock)
│   │   ├── storage/          # Storage abstraction (local + S3)
│   │   ├── worker/           # Dramatiq background worker
│   │   └── scripts/          # Seed script, utilities
│   ├── tests/                # Unit + integration tests (48 passing)
│   └── alembic/              # Database migrations
├── frontend/                 # Next.js 15, React 19, Tailwind CSS 4
│   └── src/
│       ├── app/              # App router pages
│       └── lib/              # API client
├── infra/                    # Docker Compose, deployment configs
└── Makefile                  # Build/run commands
```

### Design Principles

- **Clean Architecture**: Presentation → Application → Domain → Infrastructure
- **Provider Abstraction**: AI, Storage, Queue, Cache all behind interfaces (supports local dev without GPU or API keys)
- **Microservices-style Monolith**: Each bounded context (identity, videos, analysis, clips) has its own domain, application, and infrastructure layers
- **UUIDv7**: Time-ordered primary keys for database performance

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic |
| Database | PostgreSQL, Redis |
| Queue | Dramatiq (Redis broker) |
| AI | Google Gemini API (with Mock provider for testing) |
| Video | FFmpeg (metadata extraction, clip cutting, thumbnails) |
| Frontend | Next.js 15, React 19, TypeScript, Tailwind CSS 4 |
| Auth | JWT (access + refresh tokens), Argon2 password hashing |
| Infra | Docker Compose, Makefile |

## Quick Start

### Prerequisites
- Python 3.12+
- Docker & Docker Compose
- Node.js 18+ (for frontend)
- FFmpeg (for video processing)

### 1. Start Infrastructure
```bash
make up
```
This starts PostgreSQL (`localhost:5436`), Redis (`localhost:6382`), API (`localhost:8000`), and Worker.

### 2. Seed Database
```bash
make seed
```
Creates demo user: `demo@clipforge.ai` / `demo1234`

### 3. Start Frontend
```bash
cd frontend && npm install && npm run dev
```
Open `http://localhost:3000`

### 4. Run Tests
```bash
cd backend && .venv/bin/pytest tests/ -v
```

## API Endpoints

### Authentication
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Register new user |
| POST | `/api/v1/auth/login` | Login, get tokens |
| POST | `/api/v1/auth/refresh` | Refresh access token |
| GET | `/api/v1/auth/me` | Get current user |

### Projects
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/projects` | Create project |
| GET | `/api/v1/projects` | List projects (paginated) |
| DELETE | `/api/v1/projects/{id}` | Delete project |

### Videos
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/videos/upload` | Start upload (returns signed URL) |
| POST | `/api/v1/videos/complete` | Complete upload |
| GET | `/api/v1/projects/{id}/videos` | List videos (paginated) |
| DELETE | `/api/v1/videos/{id}` | Delete video |
| GET | `/api/v1/videos/{id}/status/stream` | SSE status stream |

### Analysis & Clips
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/videos/{id}/transcript` | Get transcript |
| GET | `/api/v1/videos/{id}/analysis` | Get AI analysis |
| GET | `/api/v1/videos/{id}/clips` | List clips (paginated) |
| GET | `/api/v1/videos/{id}/clips/export` | Download all clips as ZIP |
| GET | `/api/v1/clips/{id}/download` | Download single clip |
| DELETE | `/api/v1/clips/{id}` | Delete clip |
| GET | `/api/v1/videos/{id}/subtitles` | Export subtitles (SRT/VTT) |

### Infrastructure
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Health check |
| GET | `/docs` | Swagger UI |
| GET | `/api/v1/openapi.json` | OpenAPI spec |

## Background Pipeline

The worker runs a 3-stage pipeline when a video is uploaded:

1. **Metadata Extraction**: FFprobe extracts duration, resolution, codec info
2. **AI Analysis**: Gemini (or Mock) generates transcript + video understanding + editing plan with clip timestamps
3. **Clip Extraction**: FFmpeg cuts clips + generates thumbnails

Status updates are streamed to the frontend via Redis PubSub + Server-Sent Events (SSE).

## Testing

```bash
# Run all tests (requires Docker services running)
cd backend && .venv/bin/pytest tests/ -v

# Unit tests only (no Docker needed)
cd backend && .venv/bin/pytest tests/unit/ -v

# API integration tests (requires Docker)
cd backend && .venv/bin/pytest tests/api/ -v
```

## Development

```bash
make help          # Show all commands
make up            # Start all services
make down          # Stop all services
make logs          # View logs
make migrate       # Run database migrations
make seed          # Seed demo data
make lint          # Lint code
make frontend-dev  # Start frontend dev server
```

## License

MIT
