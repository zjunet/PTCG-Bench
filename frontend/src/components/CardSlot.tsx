import { useState } from 'react';
import { Card, PokemonCard } from '../types/game';
import EnergyIcon from './EnergyIcon';

export interface CardSlotProps {
  card?: Card | null;
  imageUrl?: string;
  faceDown?: boolean;
  isActive?: boolean;
  count?: number;
  onClick?: (card: Card, imageUrl?: string) => void;
}

export default function CardSlot({
  card = null,
  imageUrl,
  faceDown = false,
  isActive = false,
  count,
  onClick,
}: CardSlotProps) {
  const [imgError, setImgError] = useState(false);
  const isEmpty = !card && !faceDown && (count === undefined || count === 0);

  const handleClick = () => { if (onClick && card) onClick(card, imageUrl); };

  let content: React.ReactNode = null;
  if (!isEmpty) {
    if (faceDown) {
      content = <img src="/card-back.png" alt="Card" className="w-full h-full object-cover" />;
    } else if (card && imageUrl && !imgError) {
      content = (
        <img
          src={imageUrl}
          alt={card.name}
          className="w-full h-full object-cover"
          onError={() => setImgError(true)}
        />
      );
    } else {
      content = <img src="/card-back.png" alt={card?.name ?? 'Card'} className="w-full h-full object-cover" />;
    }
  }

  return (
    <div
      className={[
        'relative flex-shrink-0 rounded-lg overflow-hidden transition-all duration-150',
        'w-[70px] h-[98px] border-2',
        isEmpty
          ? isActive
            ? 'border-dashed border-sky-800/50 bg-sky-950/10'
            : 'border-dashed border-slate-700 bg-slate-900/20'
          : isActive
          ? 'border-sky-400/80 shadow-sm shadow-sky-400/20 cursor-pointer hover:scale-[1.04] hover:border-sky-300'
          : 'border-slate-700 cursor-pointer hover:border-sky-500/60 hover:shadow-sm hover:shadow-sky-500/10 hover:scale-[1.04]',
      ].join(' ')}
      onClick={handleClick}
    >
      {content}

      {/* Energy icons */}
      {card && !faceDown && 'energy' in card && (card as PokemonCard).energy.length > 0 && (
        <div className="absolute bottom-0 left-0 right-0 flex justify-center flex-wrap gap-[2px] px-[2px] pb-[3px] bg-gradient-to-t from-black/70 to-transparent pt-1">
          {(card as PokemonCard).energy.map((e, i) => (
            <EnergyIcon key={i} type={e} size={14} />
          ))}
        </div>
      )}

      {/* Count badge */}
      {typeof count === 'number' && count > 0 && (
        <span className="absolute bottom-1 right-1 bg-slate-950/90 text-slate-200 text-[10px] font-mono font-bold rounded px-1 py-0.5 min-w-[18px] text-center leading-none">
          {count}
        </span>
      )}
    </div>
  );
}
