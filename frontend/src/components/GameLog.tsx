import { useEffect, useRef } from 'react';
import { useGameStore } from '../stores/gameStore';
import { LogEntry } from '../types/game';

// ─── Action type metadata ─────────────────────────────────────────────────────
const ACTION_META: Record<string, { label: string; color: string }> = {
  AttackAction:         { label: 'Attack',          color: 'bg-rose-500/15 text-rose-400 border-rose-500/30' },
  PlayPokemonAction:    { label: 'Play Pokémon',    color: 'bg-sky-500/15 text-sky-400 border-sky-500/30' },
  EvolvePokemonAction:  { label: 'Evolve',          color: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' },
  AttachEnergyAction:   { label: 'Attach Energy',   color: 'bg-amber-500/15 text-amber-400 border-amber-500/30' },
  RetreatAction:        { label: 'Retreat',         color: 'bg-violet-500/15 text-violet-400 border-violet-500/30' },
  UseAbilityAction:     { label: 'Ability',         color: 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30' },
  UseItemAction:        { label: 'Item',            color: 'bg-indigo-500/15 text-indigo-400 border-indigo-500/30' },
  UseSupporterAction:   { label: 'Supporter',       color: 'bg-pink-500/15 text-pink-400 border-pink-500/30' },
  UseToolAction:        { label: 'Tool',            color: 'bg-orange-500/15 text-orange-400 border-orange-500/30' },
  PutStadiumAction:     { label: 'Stadium',         color: 'bg-teal-500/15 text-teal-400 border-teal-500/30' },
  DiscardStadiumAction: { label: 'Discard Stadium', color: 'bg-teal-500/15 text-teal-400 border-teal-500/30' },
  UseStadiumAction:     { label: 'Use Stadium',     color: 'bg-teal-500/15 text-teal-400 border-teal-500/30' },
  PassTurn:             { label: 'Pass',            color: 'bg-slate-600/20 text-slate-500 border-slate-600/30' },
  ChooseCardAction:     { label: 'Choose Card',     color: 'bg-violet-500/15 text-violet-400 border-violet-500/30' },
  EffectAction:         { label: 'Effect',          color: 'bg-amber-500/15 text-amber-400 border-amber-500/30' },
};

function getActionMeta(type: string) {
  return ACTION_META[type] ?? { label: type, color: 'bg-slate-600/20 text-slate-500 border-slate-600/30' };
}

function buildDescription(entry: LogEntry): string {
  const parts: string[] = [];
  if (entry.attack) {
    parts.push(entry.attack.name);
    if (entry.attack.damage > 0) parts.push(`${entry.attack.damage} dmg`);
  }
  if (entry.source) parts.push(entry.source);
  if (entry.target) parts.push(`→ ${entry.target}`);
  if (entry.ability) parts.push(entry.ability);
  if (entry.position) parts.push(`pos ${entry.position}`);
  if (entry.chosen && entry.chosen.length > 0) parts.push(entry.chosen.join(', '));
  return parts.join(' · ') || '—';
}

function LogRow({ entry, prevEntry }: { entry: LogEntry; prevEntry?: LogEntry }) {
  const meta = getActionMeta(entry.actionType);
  const isP1 = entry.player === 'player1';
  const showDivider = prevEntry === undefined || prevEntry.turn_number !== entry.turn_number;

  return (
    <>
      {showDivider && (
        <div className="flex items-center gap-2 px-2 py-1.5">
          <div className="h-px flex-1 bg-slate-800" />
          <span className="text-[10px] font-mono font-medium tracking-widest text-slate-600 uppercase">
            T{entry.turn_number}
          </span>
          <div className="h-px flex-1 bg-slate-800" />
        </div>
      )}
      <div className="flex items-start gap-2 px-2 py-1.5 rounded hover:bg-slate-800/40 transition-colors">
        <div
          className={`mt-1 flex-shrink-0 w-1.5 h-1.5 rounded-full ${isP1 ? 'bg-sky-400' : 'bg-amber-400'}`}
          title={isP1 ? 'Player 1' : 'Player 2'}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className={`text-[10px] font-mono font-bold uppercase ${isP1 ? 'text-sky-400' : 'text-amber-400'}`}>
              {isP1 ? 'P1' : 'P2'}
            </span>
            <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${meta.color}`}>
              {meta.label}
            </span>
          </div>
          <p className="text-[11px] text-slate-400 mt-0.5 leading-relaxed break-words">
            {buildDescription(entry)}
          </p>
        </div>
      </div>
    </>
  );
}

export default function GameLog() {
  const { gameLog } = useGameStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [gameLog]);

  return (
    <div className="bg-slate-900 rounded-lg border border-slate-800 flex flex-col h-full min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-800 flex-shrink-0">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
          Game Log
        </h3>
        <span className="text-[11px] font-mono text-slate-600">{gameLog.length}</span>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto py-1 min-h-0">
        {gameLog.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-center px-4 py-8">
            <svg className="w-7 h-7 text-slate-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
            <p className="text-xs text-slate-600">Actions will appear here.</p>
          </div>
        ) : (
          gameLog.map((entry, idx) => (
            <LogRow key={entry.id} entry={entry} prevEntry={gameLog[idx - 1]} />
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 px-4 py-2 border-t border-slate-800 flex-shrink-0">
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-sky-400" />
          <span className="text-[10px] text-slate-600 font-mono">P1</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-amber-400" />
          <span className="text-[10px] text-slate-600 font-mono">P2</span>
        </div>
      </div>
    </div>
  );
}
