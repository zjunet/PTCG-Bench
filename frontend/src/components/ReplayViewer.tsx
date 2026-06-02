import { useEffect, useState } from 'react';
import { useReplayStore } from '../stores/replayStore';
import { useGameStore } from '../stores/gameStore';
import ReplayBoard from './ReplayBoard';
import ReplayControls from './ReplayControls';
import CardModal from './CardModal';
import { Card, PlayerId } from '../types/game';
import { ReplayActionData } from '../types/replay';
import { getCardNamesFromState, preloadCardImagesByName } from '../services/cardImagePreloader';

// ─── Action colour map ────────────────────────────────────────────────────────
const ACTION_COLOR: Record<string, string> = {
  AttackAction:        'bg-rose-500/15 text-rose-400 border-rose-500/30',
  PlayPokemonAction:   'bg-sky-500/15 text-sky-400 border-sky-500/30',
  EvolvePokemonAction: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  AttachEnergyAction:  'bg-amber-500/15 text-amber-400 border-amber-500/30',
  RetreatAction:       'bg-violet-500/15 text-violet-400 border-violet-500/30',
  UseAbilityAction:    'bg-cyan-500/15 text-cyan-400 border-cyan-500/30',
  UseItemAction:       'bg-indigo-500/15 text-indigo-400 border-indigo-500/30',
  UseSupporterAction:  'bg-pink-500/15 text-pink-400 border-pink-500/30',
  UseToolAction:       'bg-orange-500/15 text-orange-400 border-orange-500/30',
  PutStadiumAction:    'bg-teal-500/15 text-teal-400 border-teal-500/30',
  PassTurn:            'bg-slate-600/20 text-slate-500 border-slate-600/30',
  ChooseCardAction:    'bg-violet-500/15 text-violet-400 border-violet-500/30',
  EffectAction:        'bg-amber-500/15 text-amber-400 border-amber-500/30',
};

function getColor(type: string) {
  return ACTION_COLOR[type] ?? 'bg-slate-600/20 text-slate-500 border-slate-600/30';
}

function playerLabel(id: string): { label: string; color: string } {
  if ((id ?? '').toLowerCase().includes('player2')) return { label: 'P2', color: 'text-amber-400' };
  return { label: 'P1', color: 'text-sky-400' };
}

// ─── Replay Log ───────────────────────────────────────────────────────────────
function ReplayLog() {
  const { frames, currentFrame, goToFrame } = useReplayStore();

  const entries = frames
    .filter((f) => f.action !== null)
    .map((f) => ({ frameIndex: f.frameIndex, action: f.action as ReplayActionData, turn: f.turn }));

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg flex flex-col h-full min-h-0">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-800 flex-shrink-0">
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
          Action Log
        </h3>
        <span className="text-[11px] font-mono text-slate-700">{entries.length}</span>
      </div>

      <div className="flex-1 overflow-y-auto py-1 min-h-0">
        {entries.map((entry, idx) => {
          const isActive = entry.frameIndex === currentFrame;
          const isPast = entry.frameIndex < currentFrame;
          const { label, color } = playerLabel(entry.action.playerId);
          const actionColor = getColor(entry.action.actionType);
          const prevEntry = entries[idx - 1];
          const showDivider = !prevEntry || frames[prevEntry.frameIndex]?.state.timestep !== frames[entry.frameIndex]?.state.timestep;

          return (
            <div key={entry.frameIndex}>
              {showDivider && (
                <div className="flex items-center gap-2 px-2 py-1.5">
                  <div className="h-px flex-1 bg-slate-800" />
                  <span className="text-[10px] font-mono font-medium tracking-widest text-slate-600 uppercase">
                    T{frames[entry.frameIndex]?.state.timestep}
                  </span>
                  <div className="h-px flex-1 bg-slate-800" />
                </div>
              )}
              <button
                onClick={() => goToFrame(entry.frameIndex)}
                className={[
                  'w-full text-left flex items-start gap-2 px-2 py-1.5 rounded transition-all',
                  isActive ? 'bg-sky-950/30 ring-1 ring-sky-800/50' : 'hover:bg-slate-800/40',
                  isPast ? 'opacity-50' : '',
                ].join(' ')}
              >
                <div className={`mt-1 flex-shrink-0 w-1.5 h-1.5 rounded-full ${label === 'P1' ? 'bg-sky-400' : 'bg-amber-400'}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className={`text-[10px] font-mono font-bold uppercase ${color}`}>{label}</span>
                    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${actionColor}`}>
                      {entry.action.actionType.replace('Action', '')}
                    </span>
                  </div>
                  {(entry.action.source || entry.action.target) && (
                    <p className="text-[11px] text-slate-500 mt-0.5 truncate">
                      {entry.action.source}
                      {entry.action.target && ` → ${entry.action.target}`}
                    </p>
                  )}
                </div>
              </button>
            </div>
          );
        })}
      </div>

      <div className="border-t border-slate-800 flex-shrink-0">
        <div className="flex items-center gap-4 px-4 py-2 border-b border-slate-800">
          <div className="flex items-center gap-1.5"><div className="w-1.5 h-1.5 rounded-full bg-sky-400" /><span className="text-[10px] text-slate-600 font-mono">P1</span></div>
          <div className="flex items-center gap-1.5"><div className="w-1.5 h-1.5 rounded-full bg-amber-400" /><span className="text-[10px] text-slate-600 font-mono">P2</span></div>
        </div>
        <ReplayControls embedded />
      </div>
    </div>
  );
}

// ─── File List ────────────────────────────────────────────────────────────────
function FileList({ onBack }: { onBack: () => void }) {
  const { availableFiles, filesLoading, replayLoading, error, loadReplay, fetchFileList } = useReplayStore();

  useEffect(() => { fetchFileList(); }, [fetchFileList]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-md p-6 shadow-2xl">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-sky-400">
              <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18" />
              <line x1="7" y1="2" x2="7" y2="22" /><line x1="17" y1="2" x2="17" y2="22" />
              <line x1="2" y1="12" x2="22" y2="12" />
              <line x1="2" y1="7" x2="7" y2="7" /><line x1="2" y1="17" x2="7" y2="17" />
              <line x1="17" y1="17" x2="22" y2="17" /><line x1="17" y1="7" x2="22" y2="7" />
            </svg>
            Replay Library
          </h2>
          <button onClick={onBack} className="text-xs text-slate-500 hover:text-slate-300 transition-colors flex items-center gap-1">
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5m7-7-7 7 7 7"/>
            </svg>
            Back
          </button>
        </div>

        {error && (
          <div className="mb-4 px-3 py-2 bg-rose-950/40 border border-rose-800/50 rounded-lg text-rose-400 text-xs">{error}</div>
        )}

        {filesLoading ? (
          <div className="text-center py-8 text-slate-600 text-sm">Loading replays…</div>
        ) : availableFiles.length === 0 ? (
          <div className="text-center py-8 text-slate-600 text-sm">
            No replay files found in <code className="text-slate-500 font-mono">backend/battle_log/</code>
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {availableFiles.map((file) => (
              <button
                key={file.filename}
                onClick={() => loadReplay(file.filename)}
                disabled={replayLoading}
                className="flex items-center justify-between px-4 py-2.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-sky-700/50 rounded-lg transition-all group disabled:opacity-50"
              >
                <div className="flex items-center gap-2.5">
                  <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-slate-500 group-hover:text-sky-400 transition-colors">
                    <polygon points="5 3 19 12 5 21 5 3" />
                  </svg>
                  <span className="text-xs font-mono text-slate-300">{file.filename}</span>
                </div>
                <span className="text-[10px] font-mono text-slate-600">{(file.size / 1024).toFixed(1)} KB</span>
              </button>
            ))}
          </div>
        )}

        {replayLoading && (
          <div className="mt-4 text-center text-xs text-sky-500 animate-pulse font-mono">Loading replay…</div>
        )}
      </div>
    </div>
  );
}

// ─── Main ReplayViewer ────────────────────────────────────────────────────────
interface Props {
  onBack: () => void;
}

export default function ReplayViewer({ onBack }: Props) {
  const { frames, currentFrame, filename } = useReplayStore();
  const { cardImages, loadCardImages, imagesLoaded } = useGameStore();
  const [selectedCard, setSelectedCard] = useState<{ card: Card; imageUrl?: string } | null>(null);

  useEffect(() => { if (!imagesLoaded) loadCardImages(); }, [imagesLoaded, loadCardImages]);
  useEffect(() => {
    if (!imagesLoaded || frames.length === 0) return;

    const names = new Set<string>();
    frames.forEach((frame) => {
      getCardNamesFromState(frame.state).forEach((name) => names.add(name));
    });
    preloadCardImagesByName(Array.from(names), cardImages);
  }, [cardImages, frames, imagesLoaded]);

  if (!filename) return <FileList onBack={onBack} />;

  const frame = frames[currentFrame];

  return (
    <div className="p-2 flex flex-col overflow-hidden" style={{ height: 'calc(100vh - 44px)' }}>
      <div className="grid grid-cols-12 gap-3 flex-1 min-h-0">
        <div className="col-span-9 min-h-0 overflow-hidden">
          {frame ? (
            <ReplayBoard state={frame.state} cardImages={cardImages} onCardClick={(card, imageUrl) => setSelectedCard({ card, imageUrl })} />
          ) : (
            <div className="flex items-center justify-center h-full text-slate-600 text-sm">No frame data</div>
          )}
        </div>
        <div className="col-span-3 flex flex-col min-h-0"><ReplayLog /></div>
      </div>

      {selectedCard && (
        <CardModal card={selectedCard.card} imageUrl={selectedCard.imageUrl} isOpen={true} onClose={() => setSelectedCard(null)} />
      )}
    </div>
  );
}

export { playerLabel as normalizePlayerLabel };
export type { PlayerId };
