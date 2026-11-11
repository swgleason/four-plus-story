#!/usr/bin/env bash
set -e

# Navigate to project root directory
cd "$(dirname "$0")"

export PORT=${PORT:-3000}

echo "Starting Next.js admin dev server on http://localhost:${PORT}..."
corepack pnpm --filter @four-plus/admin dev