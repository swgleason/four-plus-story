# Four Plus Story Library

A shared library of discovered autobiographical stories from PDF books and TXT transcripts, evaluated against relational neuroscience and Christian life model criteria (the Five 4+ Criteria, Four Story Variants, and STEP Analysis).

## Architecture Summary

- **Monorepo**: pnpm workspaces + Turborepo
- **Mobile**: React Native + Expo + TypeScript (`apps/mobile`)
- **Administration**: Next.js + TypeScript (`apps/admin`)
- **Backend API**: Python + FastAPI (`apps/api`)
- **Database & Auth**: Supabase PostgreSQL with `pgvector` & Supabase Auth
- **File Storage**: Supabase Storage
- **Document Processing**: PyMuPDF (`fitz`)
- **AI Processing**: Provider-independent AI service layer
- **Shared Contracts**: Zod & Pydantic validated types

## Repository Structure

```text
├── apps/
│   ├── admin/       # Next.js web application for story curation & ingestion
│   ├── api/         # FastAPI backend service (ingestion, AI classification, search)
│   └── mobile/      # Expo React Native client for public and church readers
├── packages/
│   ├── shared-types/# Universal TypeScript contracts & schemas (Zod)
│   └── eslint-config/# Monorepo linting configurations
├── docs/            # Full architectural, requirements, and design specifications
├── AGENTS.md        # Instructions and rules for AI coding agents
└── turbo.json       # Turborepo task pipeline configuration
```

## Documentation

Full architectural blueprints, schemas, and specifications are located in the [`docs/`](./docs) directory:
- [Project Overview](./docs/PROJECT_OVERVIEW.md)
- [Product Requirements](./docs/PRODUCT_REQUIREMENTS.md)
- [Technical Architecture](./docs/TECHNICAL_ARCHITECTURE.md)
- [Database Schema](./docs/DATABASE_SCHEMA.md)
- [AI Classification Specification](./docs/AI_CLASSIFICATION_SPEC.md)
- [AI Prompt Design](./docs/AI_PROMPT_DESIGN.md)
- [Search Specification](./docs/SEARCH_SPECIFICATION.md)
- [API Specification](./docs/API_SPECIFICATION.md)
- [Security & Rights](./docs/SECURITY_AND_RIGHTS.md)
- [Development Roadmap](./docs/DEVELOPMENT_ROADMAP.md)
- [Implementation Status](./docs/IMPLEMENTATION_STATUS.md)

