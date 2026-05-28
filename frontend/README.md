# PTCG-Bench Frontend

React interface for PTCG-Bench game visualization, replay inspection, deck selection, and leaderboard views.

## Quick Start

```bash
# Install dependencies
npm ci

# Start development server
npm run dev
```

The app will be available at http://localhost:5173

During local development, Vite proxies `/api` and `/ws` requests to the backend at http://localhost:8000.

## Production Build

```bash
npm run build
npm run preview
```

## Requirements

- Node.js 18+
- npm
- Backend API running on http://localhost:8000

## Project Structure

```
src/
├── components/      # React components
│   ├── GameBoard.tsx
│   ├── PlayerArea.tsx
│   ├── ReplayViewer.tsx
│   └── ActionPanel.tsx
├── stores/         # Zustand state management
│   └── gameStore.ts
├── services/       # API services
│   └── api.ts
├── types/          # TypeScript types
│   └── game.ts
├── App.tsx         # Main app component
└── main.tsx        # Entry point
```

## Technology Stack

- React 18
- TypeScript
- Tailwind CSS
- Zustand (state management)
- Axios (HTTP client)
- Vite (build tool)
