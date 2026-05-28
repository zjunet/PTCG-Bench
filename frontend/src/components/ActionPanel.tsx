import { useGameStore } from '../stores/gameStore';

export default function ActionPanel() {
  const { availableActions = [], executeAction, loading, isChoosingCard, isAgentThinking, vsAgent, turn, agentPlayer } = useGameStore();
  const isMyTurn = !vsAgent || turn !== agentPlayer;

  const displayActions = isChoosingCard || !isMyTurn
    ? []
    : availableActions.filter((a) => a.actionType !== 'ChooseCardAction');

  return (
    <div className="bg-slate-900 rounded-lg p-4 border border-slate-800">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Actions</h3>
        <span className="text-[11px] font-mono text-slate-500">
          {isAgentThinking ? '…' : !isMyTurn ? 'waiting' : isChoosingCard ? 'choosing' : displayActions.length}
        </span>
      </div>

      <div className="space-y-1.5 max-h-60 overflow-y-auto">
        {isAgentThinking ? (
          <div className="flex flex-col items-center gap-2.5 py-6 text-center">
            <div className="relative w-10 h-10">
              <div className="absolute inset-0 rounded-full border border-sky-500/20 animate-ping" />
              <div className="absolute inset-1 rounded-full border border-sky-400/50 animate-spin" style={{ borderTopColor: 'transparent' }} />
              <svg className="absolute inset-0 m-auto w-4 h-4 text-sky-400" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 0 2h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1 0-2h1a7 7 0 0 1 7-7h1V5.73A2 2 0 0 1 10 4a2 2 0 0 1 2-2m0 7a5 5 0 0 0-5 5v2h10v-2a5 5 0 0 0-5-5M8.5 16a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3m7 0a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3z"/>
              </svg>
            </div>
            <p className="text-xs text-sky-400 font-medium">Agent thinking…</p>
          </div>
        ) : !isMyTurn ? (
          <div className="flex flex-col items-center gap-2.5 py-6 text-center">
            <div className="w-10 h-10 rounded-full border border-amber-700/40 flex items-center justify-center">
              <svg className="w-4 h-4 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <p className="text-xs text-amber-400/80">Opponent's turn</p>
          </div>
        ) : isChoosingCard ? (
          <div className="flex flex-col items-center gap-2.5 py-6 text-center">
            <div className="w-10 h-10 rounded-full border border-sky-700/40 flex items-center justify-center animate-pulse">
              <svg className="w-4 h-4 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
            </div>
            <p className="text-xs text-sky-400">Awaiting card selection</p>
          </div>
        ) : displayActions.length === 0 ? (
          <div className="text-slate-600 text-xs text-center py-6">No actions available</div>
        ) : (
          displayActions.map((action, idx) => {
            const trueIdx = availableActions.indexOf(action);
            return (
              <button
                key={idx}
                onClick={() => executeAction(trueIdx)}
                disabled={loading || isAgentThinking || !isMyTurn}
                className="w-full text-left px-3 py-2.5 bg-slate-800 hover:bg-slate-700 border border-slate-700/60 hover:border-sky-500/40 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg transition-all duration-150 group"
              >
                <div className="font-semibold text-xs text-slate-200 group-hover:text-sky-300 transition-colors">
                  {formatActionType(action.actionType)}
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5 leading-snug">
                  {formatActionDescription(action)}
                </div>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}

function formatActionType(type: string): string {
  return type.replace(/([A-Z])/g, ' $1').replace(/^./, (str) => str.toUpperCase()).trim();
}

function formatActionDescription(action: any): string {
  const parts: string[] = [];
  if (action.source) parts.push(action.source);
  if (action.target) parts.push(`→ ${action.target}`);
  if (action.attack) parts.push(`${action.attack.name} · ${action.attack.damage} dmg`);
  if (action.ability) parts.push(`Ability: ${action.ability}`);
  if (action.position) parts.push(`pos ${action.position}`);
  return parts.join(' · ') || '—';
}
