import { Card, GameState, TrainerCard } from '../types/game';
import PlayerArea from './PlayerArea';

interface Props {
  state: GameState;
  cardImages: Record<string, string>;
  onCardClick?: (card: Card, imageUrl?: string) => void;
}

export default function ReplayBoard({ state, cardImages, onCardClick }: Props) {
  const stadiumCard = state.stadium && state.stadium.length > 0 ? state.stadium[0] : null;

  const handleStadiumClick = () => {
    if (!stadiumCard || !onCardClick) return;
    const asTrainerCard: TrainerCard = { name: stadiumCard.name, trainerType: 'STADIUM' };
    onCardClick(asTrainerCard, cardImages[stadiumCard.name]);
  };

  return (
    <div className="space-y-2" data-testid="replay-board">
      {/* Game info bar */}
      <div className="bg-slate-900 rounded-lg px-4 py-2 flex items-center justify-between text-sm border border-slate-800">
        <div className="text-slate-500 text-xs">
          Turn: <span className="text-sky-400 font-mono font-medium uppercase ml-1">{state.turn ?? '—'}</span>
        </div>
        <div className="text-slate-600 text-xs">
          Step: <span className="text-slate-300 font-mono font-medium ml-1">{state.timestep ?? '—'}</span>
        </div>
      </div>

      {/* Player 2 */}
      <PlayerArea player={state.player2} isOpponent playerName="Player 2" cardImages={cardImages} onCardClick={onCardClick} />

      {/* Stadium divider */}
      <div className="flex items-center gap-3 px-2">
        <div className="h-px flex-1 bg-slate-800" />
        <div
          className={[
            'flex items-center gap-2 px-3 py-1 rounded-full border transition-all duration-150',
            stadiumCard
              ? 'border-sky-500/40 bg-sky-950/20 cursor-pointer hover:border-sky-400'
              : 'border-slate-800 bg-slate-950/40',
          ].join(' ')}
          onClick={stadiumCard ? handleStadiumClick : undefined}
          title={stadiumCard ? `Click to view ${stadiumCard.name}` : undefined}
        >
          <span className="text-[10px] uppercase tracking-widest text-slate-600 font-semibold">Stadium</span>
          {stadiumCard && <span className="text-xs text-sky-400 font-medium">— {stadiumCard.name}</span>}
        </div>
        <div className="h-px flex-1 bg-slate-800" />
      </div>

      {/* Player 1 */}
      <PlayerArea player={state.player1} isOpponent={false} playerName="Player 1" cardImages={cardImages} onCardClick={onCardClick} />
    </div>
  );
}
