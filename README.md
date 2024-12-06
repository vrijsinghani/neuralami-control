# SEO Client Manager

An advanced SEO management platform that helps agencies and professionals manage their SEO clients, track performance, and automate SEO tasks through AI-powered tools.

## Overview

SEO Client Manager is a Django-based web application designed to streamline SEO workflows and client management. It combines traditional SEO tools with modern AI capabilities to provide a comprehensive solution for SEO professionals.

## Proposed Project Structure

```
seoclientmanager/
├── apps/                      # Application modules
│   ├── agents/               # AI and automation tools
│   │   ├── tools/           # Custom automation tools
│   │   ├── services/        # Agent services
│   │   └── views/           # Agent management views
│   ├── seo_manager/         # Core SEO functionality
│   │   ├── services/        # Business logic layer
│   │   │   ├── keywords/
│   │   │   ├── analytics/
│   │   │   ├── rankings/
│   │   │   └── reports/
│   │   └── views/          # View layer
│   │       ├── keywords/   # Keyword-related views
│   │       ├── projects/   # Project management views
│   │       ├── analytics/  # Analytics views
│   │       └── clients/    # Client management views
│   ├── common/             # Shared utilities
│   └── api/               # API endpoints
├── config/                # Configuration files
│   ├── settings/         # Django settings
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── nginx/           # Nginx configuration
│   └── docker/          # Docker configuration
├── scripts/             # Helper scripts
│   ├── development/
│   │   ├── add_dependencies.py
│   │   └── start_seomanager.sh
│   └── deployment/
│       ├── daphneserver.sh
│       ├── startcelery.sh
│       └── stopservices.sh
├── static/              # Static assets
├── templates/           # HTML templates
├── tests/              # Test suite
│   ├── unit/
│   └── integration/
├── var/                # Variable data
│   ├── log/           # Log files
│   └── run/           # Process IDs and sockets
└── experiments/        # Development experiments
    └── research/      # Research and documentation
```

## Suggested Improvements

### 1. Service Layer Introduction
- Separate business logic from views
- Create dedicated services for each domain (keywords, analytics, etc.)
- Improve code reusability and maintainability

### 2. Configuration Management
- Separate settings for different environments
- Centralize all configuration files
- Better environment variable management

### 3. Process Management
- Organized log and PID storage in var/
- Consistent process handling
- Better debugging capabilities

### 4. Development Workflow
- Structured script organization
- Separate development and deployment scripts
- Improved dependency management

### 5. Testing Structure
- Dedicated test directory
- Separate unit and integration tests
- Better test organization

## Technical Stack

- **Framework**: Django
- **Database**: PostgreSQL
- **Task Queue**: Celery
- **Web Server**: Nginx/Gunicorn/Daphne
- **AI Components**: Custom agents and tools
- **Frontend**: Bootstrap/JavaScript
- **Package Management**: Poetry

## Getting Started

1. Clone the repository

2. Install Poetry:
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

3. Install dependencies:
```bash
poetry install
```

4. Configure environment:
```bash
cp config/settings/.env.example .env
# Edit .env with your settings
```

5. Run migrations:
```bash
poetry run python manage.py migrate
```

## Development

### Helper Scripts

Development scripts are organized in the scripts/ directory:

```bash
# Start development server
./scripts/development/start_seomanager.sh

# Start Celery worker
./scripts/deployment/startcelery.sh

# Run Daphne server
./scripts/deployment/daphneserver.sh

# Stop all services
./scripts/deployment/stopservices.sh

# Add dependencies
python scripts/development/add_dependencies.py
```

## Docker Support

```bash
docker-compose up --build
```

## License

This project is proprietary software. All rights reserved.

## Support

For technical support or feature requests, please contact the development team or open an issue in the project repository.
