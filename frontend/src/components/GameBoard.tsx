import { useState } from 'react';
import { Card, TrainerCard } from '../types/game';
import { useGameStore } from '../stores/gameStore';
import { useDragStore, MatchedAction } from '../stores/dragStore';
import PlayerArea from './PlayerArea';

interface Props {
  onCardClick?: (card: Card, imageUrl?: string) => void;
}

const PLAY_ZONE_TYPES = ['UseItemAction', 'UseSupporterAction', 'PutStadiumAction'];

function getPlayZoneAction(matched: MatchedAction[]): MatchedAction | undefined {
  return matched.find(({ action }) => PLAY_ZONE_TYPES.includes(action.actionType));
}

function getPlayZoneLabel(matched: MatchedAction[]): string {
  const types = matched.map((a) => a.action.actionType);
  if (types.includes('UseSupporterAction')) return 'Play Supporter';
  if (types.includes('UseItemAction')) return 'Play Item';
  if (types.includes('PutStadiumAction')) return 'Play Stadium';
  return 'Play Card';
}

export default function GameBoard({ onCardClick }: Props) {
  const { state, turn, cardImages, executeAction, vsAgent, agentPlayer, agentType } = useGameStore();
  const { isDragging, matchedActions } = useDragStore();
  const [isOver, setIsOver] = useState(false);

  if (!state) return null;

  const stadiumCard = state.stadium && state.stadium.length > 0 ? state.stadium[0] : null;

  const handleStadiumClick = () => {
    if (!stadiumCard || !onCardClick) return;
    const asTrainerCard: TrainerCard = { name: stadiumCard.name, trainerType: 'STADIUM' };
    onCardClick(asTrainerCard, cardImages[stadiumCard.name]);
  };

  const isPlayZone = isDragging && !!getPlayZoneAction(matchedActions);

  return (
    <div
      className={[
        'space-y-2 relative rounded-xl transition-all duration-150',
        isPlayZone ? 'ring-1 ring-emerald-500/40' : '',
        isOver && isPlayZone ? 'ring-emerald-400/60 shadow-lg shadow-emerald-500/10' : '',
      ].join(' ')}
      onDragOver={(e) => { if (isPlayZone) e.preventDefault(); }}
      onDragEnter={(e) => { if (isPlayZone) { e.preventDefault(); setIsOver(true); } }}
      onDragLeave={(e) => {
        if (!e.relatedTarget || !e.currentTarget.contains(e.relatedTarget as Node)) setIsOver(false);
      }}
      onDrop={(e) => {
        if (!isPlayZone) return;
        e.preventDefault();
        setIsOver(false);
        const action = getPlayZoneAction(matchedActions);
        if (action) executeAction(action.actionIndex);
      }}
    >
      {/* Drop overlay */}
      {isPlayZone && isOver && (
        <div className="absolute inset-0 bg-emerald-500/5 rounded-xl pointer-events-none flex items-end justify-center pb-36 z-20">
          <span className="bg-slate-950/95 text-emerald-400 text-xs font-semibold uppercase tracking-widest px-4 py-1.5 rounded-lg border border-emerald-500/40">
            {getPlayZoneLabel(matchedActions)}
          </span>
        </div>
      )}

      {/* Game info bar */}
      <div className="bg-slate-900 rounded-lg px-4 py-2 flex items-center justify-between text-sm border border-slate-800">
        <div className="text-slate-400 text-xs">
          Turn: <span className="text-sky-400 font-mono font-medium uppercase ml-1">{turn ?? '—'}</span>
        </div>
        <div className="text-slate-500 text-xs">
          Step: <span className="text-slate-300 font-mono font-medium ml-1">{state.timestep ?? '—'}</span>
        </div>
      </div>

      {/* Player 2 */}
      <PlayerArea
        player={state.player2}
        isOpponent
        playerName="Player 2"
        cardImages={cardImages}
        onCardClick={onCardClick}
        isAgent={vsAgent && agentPlayer === 'player2'}
        agentType={vsAgent && agentPlayer === 'player2' ? agentType : null}
      />

      {/* Stadium divider */}
      <div className="flex items-center gap-3 px-2">
        <div className="h-px flex-1 bg-slate-800" />
        <div
          className={[
            'flex items-center gap-2 px-3 py-1 rounded-full border transition-all duration-150',
            stadiumCard
              ? 'border-sky-500/50 bg-sky-950/20 cursor-pointer hover:border-sky-400 hover:bg-sky-950/40'
              : 'border-slate-800 bg-slate-950/40',
          ].join(' ')}
          onClick={stadiumCard ? handleStadiumClick : undefined}
          title={stadiumCard ? `Click to view ${stadiumCard.name}` : undefined}
        >
          <span className="text-[10px] uppercase tracking-widest text-slate-600 font-semibold">
            Stadium
          </span>
          {stadiumCard && (
            <span className="text-xs text-sky-400 font-medium">— {stadiumCard.name}</span>
          )}
        </div>
        <div className="h-px flex-1 bg-slate-800" />
      </div>

      {/* Player 1 */}
      <PlayerArea
        player={state.player1}
        isOpponent={false}
        playerName="Player 1"
        cardImages={cardImages}
        onCardClick={onCardClick}
      />
    </div>
  );
}
