import { useGameStore } from '../stores/gameStore';
import { useReplayStore } from '../stores/replayStore';

type AppMode = 'home' | 'game' | 'replay' | 'decks' | 'leaderboard';

interface Props {
  mode: AppMode;
  onNavigate: (mode: AppMode) => void;
  onBattleHuman: () => void;
  onBattleAI: () => void;
}

interface Tab {
  id: AppMode;
  label: string;
  icon: React.ReactNode;
  alwaysEnabled?: boolean;
}

function HomeIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <polyline points="9 22 9 12 15 12 15 22" />
    </svg>
  );
}

function GameIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="7" width="20" height="14" rx="2" />
      <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
    </svg>
  );
}

function ReplayIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="5 3 19 12 5 21 5 3" />
    </svg>
  );
}

function DecksIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="7" width="20" height="14" rx="2" />
      <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
      <line x1="12" y1="12" x2="12" y2="17" />
      <line x1="9.5" y1="14.5" x2="14.5" y2="14.5" />
    </svg>
  );
}

function LeaderboardIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  );
}

// ─── Status badge ─────────────────────────────────────────────────────────────
function StatusBadge() {
  const { gameId, done, winner, turn, loading } = useGameStore();
  const { filename: replayFilename, frames, currentFrame } = useReplayStore();

  if (replayFilename) {
    return (
      <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-800 border border-slate-700 text-[11px] font-mono text-slate-400">
        <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse flex-shrink-0" />
        {currentFrame + 1}/{frames.length}
      </div>
    );
  }

  if (!gameId) return null;

  if (loading) {
    return (
      <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-800 border border-slate-700 text-[11px] text-slate-500">
        <span className="w-1.5 h-1.5 rounded-full bg-slate-500 animate-pulse flex-shrink-0" />
        Processing…
      </div>
    );
  }

  if (done) {
    return (
      <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-amber-950/40 border border-amber-800/50 text-[11px] font-semibold text-amber-300">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400 flex-shrink-0" />
        {winner === 'player1' ? 'P1' : 'P2'} Wins
      </div>
    );
  }

  const isP1 = turn === 'player1';
  return (
    <div className={[
      'flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-[11px] font-medium',
      isP1
        ? 'bg-sky-950/40 border-sky-800/50 text-sky-300'
        : 'bg-amber-950/30 border-amber-800/40 text-amber-300',
    ].join(' ')}>
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${isP1 ? 'bg-sky-400' : 'bg-amber-400'}`} />
      <span className="font-mono">{turn?.replace('player', 'P')}</span> turn
    </div>
  );
}

// ─── NavBar ───────────────────────────────────────────────────────────────────
export default function NavBar({ mode, onNavigate, onBattleHuman, onBattleAI }: Props) {
  const { gameId, done } = useGameStore();

  const tabs: Tab[] = [
    { id: 'home', label: 'Home', icon: <HomeIcon />, alwaysEnabled: true },
    { id: 'decks', label: 'Decks', icon: <DecksIcon />, alwaysEnabled: true },
    { id: 'game', label: 'Game', icon: <GameIcon /> },
    { id: 'replay', label: 'Replay', icon: <ReplayIcon />, alwaysEnabled: true },
    { id: 'leaderboard', label: 'Leaderboard', icon: <LeaderboardIcon />, alwaysEnabled: true },
  ];

  const canNavigateTo = (id: AppMode) => {
    if (id === 'game') return !!gameId;
    return true;
  };

  return (
    <nav className="fixed top-0 inset-x-0 z-50 h-11 flex items-center px-4 bg-slate-900/95 backdrop-blur-md border-b border-slate-800">
      {/* Logo */}
      <div className="flex items-center gap-2 min-w-0 flex-shrink-0">
        <svg width="18" height="18" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="20" cy="20" r="19" stroke="#475569" strokeWidth="2" />
          <path d="M1 20h38" stroke="#475569" strokeWidth="2" />
          <path d="M1 20a19 19 0 0 1 38 0" fill="#0ea5e9" fillOpacity="0.5" />
          <circle cx="20" cy="20" r="6" fill="#0f172a" stroke="#475569" strokeWidth="2" />
          <circle cx="20" cy="20" r="3" fill="#64748b" />
        </svg>
        <span className="text-sm font-semibold text-sky-400 font-mono hidden sm:block whitespace-nowrap tracking-tight">
          Open-PTCG
        </span>
      </div>

      {/* Tabs (centered) */}
      <div className="flex-1 flex items-center justify-center">
        <div className="flex items-center gap-0.5 bg-slate-800/60 rounded-lg p-0.5">
          {tabs.map((tab) => {
            const active = mode === tab.id;
            const disabled = !canNavigateTo(tab.id);

            return (
              <button
                key={tab.id}
                onClick={() => !disabled && onNavigate(tab.id)}
                disabled={disabled}
                title={disabled ? 'Start a game first' : undefined}
                className={[
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150',
                  active
                    ? 'bg-sky-600 text-white shadow-sm'
                    : disabled
                      ? 'text-slate-700 cursor-not-allowed'
                      : 'text-slate-400 hover:text-slate-100 hover:bg-slate-700/60',
                ].join(' ')}
              >
                {tab.icon}
                {tab.label}
                {tab.id === 'game' && gameId && !done && (
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 flex-shrink-0" />
                )}
                {tab.id === 'game' && gameId && done && (
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400 flex-shrink-0" />
                )}
              </button>
            );
          })}

          <div className="w-px h-4 bg-slate-700 mx-0.5" />

          {/* vs Human */}
          <button
            onClick={onBattleHuman}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150 text-slate-400 hover:text-sky-300 hover:bg-sky-950/40"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
              <circle cx="9" cy="7" r="4"/>
              <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
              <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
            vs Human
          </button>

          {/* vs AI */}
          <button
            onClick={onBattleAI}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150 text-slate-400 hover:text-sky-300 hover:bg-sky-950/40"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 0 2h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1 0-2h1a7 7 0 0 1 7-7h1V5.73A2 2 0 0 1 10 4a2 2 0 0 1 2-2m0 7a5 5 0 0 0-5 5v2h10v-2a5 5 0 0 0-5-5M8.5 16a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3m7 0a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3z"/>
            </svg>
            vs AI
          </button>
        </div>
      </div>

      {/* Right: status */}
      <div className="flex-shrink-0 flex items-center justify-end min-w-[100px]">
        <StatusBadge />
      </div>
    </nav>
  );
}
