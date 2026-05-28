import { useState, useEffect } from 'react';
import { useDeckStore } from '../stores/deckStore';
import EnergyIcon from './EnergyIcon';
import { ENERGY_CODE_TO_TYPE, getDeckColors } from './DeckCard';
import { DeckInfo } from '../types/game';
import { api, AgentInfo } from '../services/api';

// ─── Mini deck card ───────────────────────────────────────────────────────────
interface MiniCardProps {
  deck: DeckInfo;
  selected: boolean;
  onClick: () => void;
}

function MiniDeckCard({ deck, selected, onClick }: MiniCardProps) {
  const colors = getDeckColors(deck.energyTypes);
  const energyTypeNames = deck.energyTypes.map(c => ENERGY_CODE_TO_TYPE[c] ?? 'colorless');

  return (
    <button
      onClick={onClick}
      className={[
        'w-full text-left rounded-lg p-2.5 flex items-start gap-2 transition-all duration-150 border',
        selected
          ? 'bg-slate-800 border-sky-600/60'
          : 'bg-slate-800/50 border-slate-700/50 hover:border-slate-600',
      ].join(' ')}
    >
      <div className="w-0.5 self-stretch rounded-full flex-shrink-0" style={{ background: colors.accent, opacity: selected ? 1 : 0.4 }} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-semibold text-slate-200 truncate">{deck.displayName}</p>
          <div className="flex items-center gap-1 flex-shrink-0">
            {energyTypeNames.slice(0, 2).map((t, i) => <EnergyIcon key={i} type={t} size={13} />)}
          </div>
        </div>
        <p className="text-[10px] text-slate-500 font-mono mt-0.5">
          {deck.pokemonCount}P · {deck.trainerCount}T · {deck.energyCount}E
        </p>
      </div>
      {selected && (
        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none"
          stroke="#38bdf8" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="flex-shrink-0 mt-0.5">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      )}
    </button>
  );
}

// ─── Agent card ───────────────────────────────────────────────────────────────
function AgentCard({ agent, selected, onClick }: { agent: AgentInfo; selected: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      disabled={!agent.available}
      className={[
        'w-full text-left rounded-lg p-3 flex items-start gap-3 transition-all duration-150 border',
        !agent.available ? 'opacity-40 cursor-not-allowed border-slate-800' : '',
        selected
          ? 'bg-slate-800 border-sky-600/60'
          : agent.available
          ? 'bg-slate-800/40 border-slate-700/50 hover:border-slate-600'
          : 'bg-slate-800/20 border-slate-800',
      ].join(' ')}
    >
      <div className={[
        'w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0',
        selected ? 'bg-sky-900/50' : 'bg-slate-800',
      ].join(' ')}>
        {agent.id === 'random' ? (
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke={selected ? '#38bdf8' : '#64748b'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="16 3 21 3 21 8"/><line x1="4" y1="20" x2="21" y2="3"/>
            <polyline points="21 16 21 21 16 21"/><line x1="15" y1="15" x2="21" y2="21"/>
          </svg>
        ) : (
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill={selected ? '#38bdf8' : '#64748b'}>
            <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 0 2h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1 0-2h1a7 7 0 0 1 7-7h1V5.73A2 2 0 0 1 10 4a2 2 0 0 1 2-2m0 7a5 5 0 0 0-5 5v2h10v-2a5 5 0 0 0-5-5M8.5 16a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3m7 0a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3z"/>
          </svg>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className={`text-xs font-semibold ${selected ? 'text-sky-300' : 'text-slate-200'}`}>{agent.name}</p>
          {!agent.available && (
            <span className="text-[9px] font-mono uppercase bg-slate-700 text-slate-500 rounded px-1.5 py-0.5">
              Unavailable
            </span>
          )}
        </div>
        <p className="text-[10px] text-slate-500 mt-0.5 leading-relaxed">{agent.description}</p>
        {!agent.available && agent.unavailableReason && (
          <p className="text-[10px] text-amber-600 mt-1">{agent.unavailableReason}</p>
        )}
      </div>
      {selected && (
        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none"
          stroke="#38bdf8" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="flex-shrink-0 mt-0.5">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      )}
    </button>
  );
}

interface DeckSelectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (deck1?: string, deck2?: string, agent?: string, agentModel?: string) => void;
  defaultDeck1?: string | null;
  defaultVsAgent?: boolean;
}

export default function DeckSelectModal({ isOpen, onClose, onConfirm, defaultDeck1, defaultVsAgent }: DeckSelectModalProps) {
  const { decks, loading, loadDecks } = useDeckStore();
  const [deck1, setDeck1] = useState<string | null>(defaultDeck1 ?? null);
  const [deck2, setDeck2] = useState<string | null>(null);
  const [vsAgent, setVsAgent] = useState(defaultVsAgent ?? false);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(false);
  const [selectedAgentId, setSelectedAgentId] = useState<string>('random');
  const [selectedModel, setSelectedModel] = useState<string>('');

  useEffect(() => {
    if (isOpen) {
      loadDecks();
      const firstId = decks[0]?.id ?? null;
      setDeck1(defaultDeck1 ?? firstId);
      setDeck2(firstId);
      setVsAgent(defaultVsAgent ?? false);
      setAgentsLoading(true);
      api.listAgents()
        .then(data => {
          setAgents(data);
          const first = data.find(a => a.available) ?? data[0];
          if (first) { setSelectedAgentId(first.id); if (first.defaultModel) setSelectedModel(first.defaultModel); }
        })
        .catch(() => {})
        .finally(() => setAgentsLoading(false));
    }
  }, [isOpen, defaultDeck1]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (decks.length > 0) {
      setDeck1(prev => prev ?? decks[0].id);
      setDeck2(prev => prev ?? decks[0].id);
    }
  }, [decks]);

  const handleSelectAgent = (agentId: string) => {
    setSelectedAgentId(agentId);
    const agent = agents.find(a => a.id === agentId);
    setSelectedModel(agent?.defaultModel ?? '');
  };

  if (!isOpen) return null;

  const p1Label = decks.find(d => d.id === deck1)?.displayName ?? deck1 ?? '—';
  const p2Label = decks.find(d => d.id === deck2)?.displayName ?? deck2 ?? '—';
  const selectedAgent = agents.find(a => a.id === selectedAgentId);

  const handleConfirm = () => {
    if (vsAgent) {
      const model = selectedAgent?.requiresModel ? (selectedModel || selectedAgent.defaultModel) : undefined;
      onConfirm(deck1 ?? undefined, deck2 ?? undefined, selectedAgentId, model);
    } else {
      onConfirm(deck1 ?? undefined, deck2 ?? undefined);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={onClose} />
      <div
        className="relative bg-slate-900 border border-slate-700 rounded-xl w-full max-w-2xl flex flex-col shadow-2xl"
        style={{ maxHeight: 'calc(100vh - 80px)' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 flex-shrink-0">
          <div>
            <h2 className="text-sm font-semibold text-slate-100">Select Decks</h2>
            <p className="text-[11px] text-slate-500 mt-0.5">Choose a deck for each player</p>
          </div>
          <div className="flex items-center gap-3">
            {/* Mode toggle */}
            <div className="flex items-center bg-slate-800 border border-slate-700 rounded-lg p-0.5 gap-0.5">
              <button
                onClick={() => setVsAgent(false)}
                className={[
                  'px-3 py-1 rounded-md text-xs font-medium transition-all duration-150',
                  !vsAgent ? 'bg-sky-600 text-white' : 'text-slate-500 hover:text-slate-300',
                ].join(' ')}
              >
                vs Human
              </button>
              <button
                onClick={() => setVsAgent(true)}
                className={[
                  'px-3 py-1 rounded-md text-xs font-medium transition-all duration-150',
                  vsAgent ? 'bg-sky-600 text-white' : 'text-slate-500 hover:text-slate-300',
                ].join(' ')}
              >
                vs AI
              </button>
            </div>
            <button onClick={onClose} className="text-slate-600 hover:text-slate-300 transition-colors p-1 rounded">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-hidden flex min-h-0">
          {/* Player 1 */}
          <div className="flex-1 flex flex-col p-4 border-r border-slate-800/60 min-h-0">
            <div className="flex items-center gap-2 mb-2.5 flex-shrink-0">
              <span className="w-2 h-2 rounded-full bg-sky-400" />
              <h3 className="text-xs font-semibold text-sky-400">Player 1 — You</h3>
            </div>
            <div className="flex-1 overflow-y-auto space-y-1.5">
              {loading ? (
                <p className="text-center text-slate-600 py-6 text-xs">Loading decks…</p>
              ) : decks.map(deck => (
                <MiniDeckCard key={deck.id} deck={deck} selected={deck1 === deck.id} onClick={() => setDeck1(deck.id)} />
              ))}
            </div>
          </div>

          {/* Player 2 / AI */}
          <div className="flex-1 flex flex-col p-4 min-h-0">
            <div className="flex items-center gap-2 mb-2.5 flex-shrink-0">
              <span className={`w-2 h-2 rounded-full ${vsAgent ? 'bg-sky-400' : 'bg-amber-400'}`} />
              <h3 className={`text-xs font-semibold ${vsAgent ? 'text-sky-400' : 'text-amber-400'}`}>
                {vsAgent ? 'AI Agent' : 'Player 2 — Opponent'}
              </h3>
            </div>

            {vsAgent ? (
              <div className="flex-1 flex flex-col gap-3 min-h-0 overflow-y-auto">
                <div>
                  <p className="text-[10px] font-mono text-slate-600 uppercase tracking-wider mb-1.5">Agent Type</p>
                  {agentsLoading ? (
                    <p className="text-center text-slate-600 py-4 text-xs">Loading agents…</p>
                  ) : (
                    <div className="space-y-1.5">
                      {agents.map(agent => (
                        <AgentCard key={agent.id} agent={agent} selected={selectedAgentId === agent.id}
                          onClick={() => agent.available && handleSelectAgent(agent.id)} />
                      ))}
                    </div>
                  )}
                </div>

                {selectedAgent?.requiresModel && selectedAgent.models && (
                  <div className="flex-shrink-0">
                    <p className="text-[10px] font-mono text-slate-600 uppercase tracking-wider mb-1.5">Model</p>
                    <div className="space-y-1">
                      {selectedAgent.models.map(model => (
                        <button
                          key={model.id}
                          onClick={() => setSelectedModel(model.id)}
                          className={[
                            'w-full text-left px-3 py-2 rounded-lg transition-all duration-150 flex items-center justify-between gap-2 border',
                            selectedModel === model.id
                              ? 'bg-slate-800 border-sky-600/60'
                              : 'bg-slate-800/40 border-slate-700/50 hover:border-slate-600',
                          ].join(' ')}
                        >
                          <div>
                            <span className={`text-xs font-medium ${selectedModel === model.id ? 'text-sky-300' : 'text-slate-300'}`}>
                              {model.name}
                            </span>
                            <span className="text-[10px] font-mono text-slate-600 ml-2">{model.provider}</span>
                          </div>
                          {selectedModel === model.id && (
                            <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24"
                              fill="none" stroke="#38bdf8" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                              <polyline points="20 6 9 17 4 12" />
                            </svg>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <div className="flex-shrink-0">
                  <p className="text-[10px] font-mono text-slate-600 uppercase tracking-wider mb-1.5">Agent's Deck</p>
                  <div className="space-y-1.5">
                    {loading ? (
                      <p className="text-center text-slate-600 py-4 text-xs">Loading…</p>
                    ) : decks.map(deck => (
                      <MiniDeckCard key={deck.id} deck={deck} selected={deck2 === deck.id} onClick={() => setDeck2(deck.id)} />
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto space-y-1.5">
                {loading ? (
                  <p className="text-center text-slate-600 py-6 text-xs">Loading decks…</p>
                ) : decks.map(deck => (
                  <MiniDeckCard key={deck.id} deck={deck} selected={deck2 === deck.id} onClick={() => setDeck2(deck.id)} />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 border-t border-slate-800 flex-shrink-0 flex items-center justify-between gap-4">
          <p className="text-[11px] text-slate-600 truncate font-mono">
            <span className="text-sky-400">{p1Label}</span>
            <span className="text-slate-700 mx-2">vs</span>
            {vsAgent ? (
              <span className="text-sky-400">
                {selectedAgent?.name ?? 'AI Agent'}
                {selectedAgent?.requiresModel && selectedModel && (
                  <span className="text-slate-600 ml-1">({selectedModel.split('/').pop()})</span>
                )}
              </span>
            ) : (
              <span className="text-amber-400">{p2Label}</span>
            )}
          </p>
          <button
            onClick={handleConfirm}
            className="flex-shrink-0 px-6 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg font-semibold text-sm transition-colors shadow-md"
          >
            Start Game
          </button>
        </div>
      </div>
    </div>
  );
}
