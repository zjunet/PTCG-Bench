import { useState } from 'react';
import { PlayerState, Card, PokemonCard, Action } from '../types/game';
import CardSlot from './CardSlot';
import DiscardModal from './DiscardModal';
import { useDragStore, MatchedAction } from '../stores/dragStore';
import { useGameStore } from '../stores/gameStore';

interface Props {
  player: PlayerState;
  isOpponent: boolean;
  playerName: string;
  cardImages: Record<string, string>;
  onCardClick?: (card: Card, imageUrl?: string) => void;
  isAgent?: boolean;
  agentType?: string | null;
}

function ZoneLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] font-medium uppercase tracking-widest text-slate-500 text-center mb-0.5">
      {children}
    </p>
  );
}

function getMatchedActionsForCard(card: Card, availableActions: Action[]): MatchedAction[] {
  return availableActions
    .map((action, idx) => ({ action, actionIndex: idx }))
    .filter(({ action }) => action.source === card.name);
}

function positionIncludes(pos: string | undefined, keyword: string): boolean {
  return (pos ?? '').toUpperCase().includes(keyword);
}

function canDropOnActive(matched: MatchedAction[], hasActivePokemon: boolean, pokemonName?: string): boolean {
  return matched.some(({ action }) => {
    switch (action.actionType) {
      case 'PlayPokemonAction': return positionIncludes(action.position, 'ACTIVE');
      case 'AttachEnergyAction':
      case 'UseToolAction':
      case 'EvolvePokemonAction':
        if (!hasActivePokemon) return false;
        if (action.target && pokemonName) return action.target === pokemonName;
        return true;
      default: return false;
    }
  });
}

function canDropOnBenchSlot(matched: MatchedAction[], slotHasPokemon: boolean, pokemonName?: string): boolean {
  return matched.some(({ action }) => {
    switch (action.actionType) {
      case 'PlayPokemonAction': return positionIncludes(action.position, 'BENCH') && !slotHasPokemon;
      case 'AttachEnergyAction':
      case 'UseToolAction':
      case 'EvolvePokemonAction':
        if (!slotHasPokemon) return false;
        if (action.target && pokemonName) return action.target === pokemonName;
        return true;
      default: return false;
    }
  });
}

function getActionForActive(matched: MatchedAction[], hasActivePokemon: boolean, pokemonName?: string): MatchedAction | undefined {
  return matched.find(({ action }) => {
    switch (action.actionType) {
      case 'PlayPokemonAction': return positionIncludes(action.position, 'ACTIVE');
      case 'AttachEnergyAction':
      case 'UseToolAction':
      case 'EvolvePokemonAction':
        if (!hasActivePokemon) return false;
        if (action.target && pokemonName) return action.target === pokemonName;
        return true;
      default: return false;
    }
  });
}

function getActionForBenchSlot(matched: MatchedAction[], slotHasPokemon: boolean, pokemonName?: string): MatchedAction | undefined {
  return matched.find(({ action }) => {
    switch (action.actionType) {
      case 'PlayPokemonAction': return positionIncludes(action.position, 'BENCH') && !slotHasPokemon;
      case 'AttachEnergyAction':
      case 'UseToolAction':
      case 'EvolvePokemonAction':
        if (!slotHasPokemon) return false;
        if (action.target && pokemonName) return action.target === pokemonName;
        return true;
      default: return false;
    }
  });
}

function getDropLabel(matched: MatchedAction[]): string {
  const types = matched.map((a) => a.action.actionType);
  if (types.includes('EvolvePokemonAction')) return 'Evolve';
  if (types.includes('PlayPokemonAction')) return 'Play';
  if (types.includes('AttachEnergyAction')) return 'Attach';
  if (types.includes('UseToolAction')) return 'Tool';
  if (types.includes('UseSupporterAction')) return 'Supporter';
  if (types.includes('UseItemAction')) return 'Item';
  if (types.includes('PutStadiumAction')) return 'Stadium';
  return 'Drop';
}

// ─── Drop Target ──────────────────────────────────────────────────────────────
function DropTarget({ isValid, onDrop, label = 'Drop', children }: {
  isValid: boolean; onDrop: () => void; label?: string; children: React.ReactNode;
}) {
  const [isOver, setIsOver] = useState(false);
  return (
    <div
      className={[
        'relative rounded-lg transition-all duration-150',
        isValid ? 'ring-1 ring-emerald-500/50 shadow-sm shadow-emerald-500/10' : '',
        isOver && isValid ? 'ring-emerald-400 shadow-md shadow-emerald-500/20 scale-[1.04]' : '',
      ].join(' ')}
      onDragOver={(e) => { if (isValid) { e.preventDefault(); e.stopPropagation(); } }}
      onDragEnter={(e) => { if (isValid) { e.preventDefault(); setIsOver(true); } }}
      onDragLeave={(e) => {
        if (!e.relatedTarget || !e.currentTarget.contains(e.relatedTarget as Node)) setIsOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault(); e.stopPropagation(); setIsOver(false);
        if (isValid) onDrop();
      }}
    >
      {children}
      {isValid && isOver && (
        <div className="absolute inset-0 bg-emerald-500/15 rounded-lg flex items-center justify-center pointer-events-none z-10">
          <span className="bg-slate-950/90 text-emerald-400 text-[9px] font-semibold uppercase tracking-widest px-1.5 py-0.5 rounded border border-emerald-500/40">
            {label}
          </span>
        </div>
      )}
    </div>
  );
}

// ─── Prize Zone ───────────────────────────────────────────────────────────────
function PrizeZone({ prize }: { prize: Card[] }) {
  return (
    <div className="flex flex-col items-center">
      <ZoneLabel>Prize ({prize.length})</ZoneLabel>
      <div className="grid grid-cols-2 gap-1">
        {Array.from({ length: 6 }).map((_, i) => (
          <CardSlot key={i} faceDown={i < prize.length} />
        ))}
      </div>
    </div>
  );
}

// ─── Bench Zone ───────────────────────────────────────────────────────────────
function BenchZone({ bench, cardImages, onCardClick, enableDrop = false }: {
  bench: PokemonCard[]; cardImages: Record<string, string>;
  onCardClick?: (card: Card, imageUrl?: string) => void; enableDrop?: boolean;
}) {
  const { isDragging, matchedActions } = useDragStore();
  const { executeAction } = useGameStore();
  const label = getDropLabel(matchedActions);
  return (
    <div className="flex flex-col items-center">
      <ZoneLabel>Bench</ZoneLabel>
      <div className="flex gap-1">
        {Array.from({ length: 5 }).map((_, i) => {
          const slotCard = bench[i] ?? null;
          const slotHasPokemon = !!slotCard;
          const pokemonName = slotCard?.name;
          const isValidDrop = enableDrop && isDragging && canDropOnBenchSlot(matchedActions, slotHasPokemon, pokemonName);
          return (
            <DropTarget key={i} isValid={isValidDrop} label={label} onDrop={() => {
              const action = getActionForBenchSlot(matchedActions, slotHasPokemon, pokemonName);
              if (action) executeAction(action.actionIndex);
            }}>
              <CardSlot card={slotCard} imageUrl={slotCard ? cardImages[slotCard.name] : undefined} onClick={onCardClick} />
            </DropTarget>
          );
        })}
      </div>
    </div>
  );
}

// ─── Active Zone ──────────────────────────────────────────────────────────────
function ActiveZone({ active, cardImages, onCardClick, enableDrop = false }: {
  active: PokemonCard[]; cardImages: Record<string, string>;
  onCardClick?: (card: Card, imageUrl?: string) => void; enableDrop?: boolean;
}) {
  const { isDragging, matchedActions } = useDragStore();
  const { executeAction } = useGameStore();
  const activeCard = active[0] ?? null;
  const hasActivePokemon = !!activeCard;
  const pokemonName = activeCard?.name;
  const isValidDrop = enableDrop && isDragging && canDropOnActive(matchedActions, hasActivePokemon, pokemonName);
  const label = getDropLabel(matchedActions);
  return (
    <div className="flex flex-col items-center">
      <ZoneLabel>Active</ZoneLabel>
      <DropTarget isValid={isValidDrop} label={label} onDrop={() => {
        const action = getActionForActive(matchedActions, hasActivePokemon, pokemonName);
        if (action) executeAction(action.actionIndex);
      }}>
        <CardSlot card={active[0] ?? null} imageUrl={active[0] ? cardImages[active[0].name] : undefined} isActive onClick={onCardClick} />
      </DropTarget>
    </div>
  );
}

// ─── Deck + Discard ───────────────────────────────────────────────────────────
function DeckDiscardZone({ deck, discard, cardImages }: { deck: Card[]; discard: Card[]; cardImages: Record<string, string>; }) {
  const [showDiscard, setShowDiscard] = useState(false);
  const discardTop = discard.length > 0 ? discard[discard.length - 1] : null;
  return (
    <>
      <div className="flex flex-col items-center gap-2">
        <div className="flex flex-col items-center">
          <ZoneLabel>Deck</ZoneLabel>
          <CardSlot faceDown={deck.length > 0} count={deck.length > 0 ? deck.length : undefined} />
        </div>
        <div className="flex flex-col items-center">
          <ZoneLabel>Discard</ZoneLabel>
          <div
            className={[
              'relative flex-shrink-0 rounded-lg overflow-hidden border-2 transition-all duration-150',
              'w-[clamp(56px,3.25vw,62px)] h-[clamp(78px,4.55vw,87px)]',
              discard.length > 0
                ? 'border-slate-600 cursor-pointer hover:border-sky-500/60 hover:shadow-sm hover:shadow-sky-500/10 hover:scale-[1.03]'
                : 'border-dashed border-slate-700 bg-slate-900/20',
            ].join(' ')}
            onClick={discard.length > 0 ? () => setShowDiscard(true) : undefined}
            title={discard.length > 0 ? `View discard pile (${discard.length} cards)` : undefined}
          >
            {discardTop ? (
              cardImages[discardTop.name] ? (
                <img src={cardImages[discardTop.name]} alt={discardTop.name} className="w-full h-full object-cover" />
              ) : (
                <img src="/card-back.png" alt={discardTop.name} className="w-full h-full object-cover" />
              )
            ) : null}
            {discard.length > 0 && (
              <span className="absolute bottom-1 right-1 bg-slate-950/90 text-slate-200 text-[10px] font-mono font-bold rounded px-1 py-0.5 min-w-[18px] text-center leading-none">
                {discard.length}
              </span>
            )}
          </div>
        </div>
      </div>
      <DiscardModal discard={discard} cardImages={cardImages} isOpen={showDiscard} onClose={() => setShowDiscard(false)} />
    </>
  );
}

// ─── Hand Zone ────────────────────────────────────────────────────────────────
function HandZone({ hand, cardImages, onCardClick }: {
  hand: Card[]; cardImages: Record<string, string>; onCardClick?: (card: Card, imageUrl?: string) => void;
}) {
  const [draggingIdx, setDraggingIdx] = useState<number | null>(null);
  const { isDragging } = useDragStore();
  const { availableActions, turn } = useGameStore();
  const isMyTurn = turn === 'player1';

  const handleDragStart = (e: React.DragEvent<HTMLDivElement>, card: Card, idx: number) => {
    const matched = getMatchedActionsForCard(card, availableActions);
    useDragStore.getState().startDrag(card, matched);
    setDraggingIdx(idx);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragEnd = () => { useDragStore.getState().endDrag(); setDraggingIdx(null); };

  return (
    <div className="border-t border-slate-800/60 px-3 pt-1.5 pb-2 flex-shrink-0 overflow-hidden">
      <ZoneLabel>Hand ({hand.length})</ZoneLabel>
      <div className="flex gap-1 mt-1 h-[90] items-center overflow-x-auto overflow-y-hidden overscroll-x-contain px-1 py-2">
        {hand.length === 0 ? (
          <span className="text-xs text-slate-600 py-2 px-1">No cards in hand</span>
        ) : (
          hand.map((card, i) => {
            const matched = isMyTurn ? getMatchedActionsForCard(card, availableActions) : [];
            const isDraggable = matched.length > 0;
            const isThisCardDragging = draggingIdx === i;
            return (
              <div
                key={i}
                draggable={isDraggable}
                onDragStart={(e) => handleDragStart(e, card, i)}
                onDragEnd={handleDragEnd}
                title={isDraggable ? 'Drag to play' : undefined}
                className={[
                  'relative transition-all duration-150 select-none',
                  isDraggable ? 'cursor-grab active:cursor-grabbing' : 'cursor-default',
                  isThisCardDragging
                    ? 'opacity-40 scale-95'
                    : isDragging
                    ? isDraggable ? 'opacity-100' : 'opacity-50'
                    : isDraggable ? 'hover:scale-105 hover:-translate-y-1' : '',
                ].join(' ')}
              >
                <CardSlot card={card} imageUrl={cardImages[card.name]} onClick={onCardClick} />
                {isDraggable && !isDragging && (
                  <span className="absolute -top-1 -right-1 w-3.5 h-3.5 bg-sky-500 rounded-full flex items-center justify-center pointer-events-none opacity-90">
                    <svg className="w-2 h-2 text-white" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M11 18c0 1.1-.9 2-2 2s-2-.9-2-2 .9-2 2-2 2 .9 2 2zm-2-8c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0-6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm6 4c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z" />
                    </svg>
                  </span>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

// ─── Opponent Hand Zone ───────────────────────────────────────────────────────
function OpponentHandZone({ hand, cardImages, onCardClick }: {
  hand: Card[]; cardImages: Record<string, string>; onCardClick?: (card: Card, imageUrl?: string) => void;
}) {
  const [revealed, setRevealed] = useState(false);
  return (
    <div className="border-b border-slate-800/60 px-3 pt-1.5 pb-2 flex-shrink-0 overflow-hidden">
      <div className="relative flex items-center justify-center mb-1">
        <p className="text-[10px] font-medium uppercase tracking-widest text-slate-500 text-center">
          Hand ({hand.length})
        </p>
        <button
          onClick={() => setRevealed((v) => !v)}
          className={[
            'absolute right-0 flex items-center gap-1 text-[10px] font-medium uppercase tracking-wider px-2 py-0.5 rounded transition-all duration-150',
            revealed
              ? 'bg-rose-950/50 text-rose-400 hover:bg-rose-900/50'
              : 'bg-slate-800 text-slate-500 hover:text-slate-300',
          ].join(' ')}
        >
          {revealed ? (
            <>
              <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
                <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
                <line x1="1" y1="1" x2="23" y2="23"/>
              </svg>
              Hide
            </>
          ) : (
            <>
              <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
              </svg>
              Reveal
            </>
          )}
        </button>
      </div>
      <div className="flex gap-1 mt-1 h-[90] items-center overflow-x-auto overflow-y-hidden overscroll-x-contain px-1 py-2">
        {hand.length === 0 ? (
          <span className="text-xs text-slate-600 py-2 px-1">No cards in hand</span>
        ) : revealed ? (
          hand.map((card, i) => <CardSlot key={i} card={card} imageUrl={cardImages[card.name]} onClick={onCardClick} />)
        ) : (
          hand.map((_, i) => <CardSlot key={i} faceDown />)
        )}
      </div>
    </div>
  );
}

// ─── Main PlayerArea ──────────────────────────────────────────────────────────
export default function PlayerArea({ player, isOpponent, playerName, cardImages, onCardClick, isAgent, agentType }: Props) {
  const prizeZone = <PrizeZone prize={player.prize} />;
  const benchZone = <BenchZone bench={player.bench} cardImages={cardImages} onCardClick={onCardClick} enableDrop={!isOpponent} />;
  const activeZone = <ActiveZone active={player.active} cardImages={cardImages} onCardClick={onCardClick} enableDrop={!isOpponent} />;
  const deckDiscardZone = <DeckDiscardZone deck={player.deck} discard={player.discard} cardImages={cardImages} />;

  const borderClass = isOpponent
    ? 'border-amber-900/30 bg-slate-900/40'
    : 'border-sky-900/40 bg-slate-900/60';

  return (
    <div className={`h-full min-h-0 rounded-xl border flex flex-col overflow-hidden ${borderClass}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-1.5 border-b border-slate-800/60 flex-shrink-0">
        <span className={`text-xs font-semibold flex items-center gap-1.5 ${isAgent ? 'text-sky-400' : isOpponent ? 'text-amber-400' : 'text-sky-400'}`}>
          {isAgent && (
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="currentColor" className="opacity-80">
              <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 0 2h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1 0-2h1a7 7 0 0 1 7-7h1V5.73A2 2 0 0 1 10 4a2 2 0 0 1 2-2m0 7a5 5 0 0 0-5 5v2h10v-2a5 5 0 0 0-5-5M8.5 16a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3m7 0a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3z"/>
            </svg>
          )}
          {playerName}
          <span className="text-slate-600 font-normal ml-0.5">
            {isAgent
              ? `· ${agentType === 'llm' ? 'LLM Agent' : agentType === 'random' ? 'Random Agent' : 'AI Agent'}`
              : isOpponent ? '· Opponent' : '· You'}
          </span>
        </span>
        <div className="flex gap-3 text-[11px] text-slate-600 font-mono">
          <span>Hand <span className="text-slate-400">{player.hand.length}</span></span>
          <span>Deck <span className="text-slate-400">{player.deck.length}</span></span>
          <span>Disc <span className="text-slate-400">{player.discard.length}</span></span>
          <span>Prize <span className="text-slate-400">{player.prize.length}</span></span>
        </div>
      </div>

      {isOpponent && <OpponentHandZone hand={player.hand} cardImages={cardImages} onCardClick={onCardClick} />}

      <div className="flex-1 min-h-0 flex items-center gap-3 px-3 py-2 overflow-hidden">
        {isOpponent ? (
          <>
            {deckDiscardZone}
            <div className="flex-1 min-w-0 flex flex-col items-center justify-center gap-2">{benchZone}{activeZone}</div>
            {prizeZone}
          </>
        ) : (
          <>
            {prizeZone}
            <div className="flex-1 min-w-0 flex flex-col items-center justify-center gap-2">{activeZone}{benchZone}</div>
            {deckDiscardZone}
          </>
        )}
      </div>

      {!isOpponent && <HandZone hand={player.hand} cardImages={cardImages} onCardClick={onCardClick} />}
    </div>
  );
}
