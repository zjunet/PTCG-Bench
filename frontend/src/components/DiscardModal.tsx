import { useState } from 'react';
import { Card } from '../types/game';
import CardModal from './CardModal';

interface Props {
  discard: Card[];
  cardImages: Record<string, string>;
  isOpen: boolean;
  onClose: () => void;
}

export default function DiscardModal({ discard, cardImages, isOpen, onClose }: Props) {
  const [selectedCard, setSelectedCard] = useState<{ card: Card; imageUrl?: string } | null>(null);

  if (!isOpen) return null;

  const cards = [...discard].reverse();

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose();
  };

  return (
    <>
      <div
        className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4"
        onClick={handleBackdropClick}
      >
        <div className="relative bg-slate-900 border border-slate-700 rounded-xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800 flex-shrink-0">
            <h2 className="text-sm font-semibold text-slate-200">
              Discard Pile
              <span className="ml-2 text-xs text-slate-500 font-normal font-mono">
                {discard.length} card{discard.length !== 1 ? 's' : ''}
              </span>
            </h2>
            <button
              onClick={onClose}
              className="text-slate-600 hover:text-slate-300 transition-colors p-1 rounded"
              aria-label="Close"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>

          {/* Cards */}
          <div className="overflow-y-auto p-4 flex-1">
            {cards.length === 0 ? (
              <p className="text-slate-600 text-sm text-center py-8">Discard pile is empty</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {cards.map((card, i) => {
                  const imageUrl = cardImages[card.name];
                  return (
                    <button
                      key={i}
                      className="relative flex-shrink-0 rounded-lg overflow-hidden border-2 border-slate-700 hover:border-sky-500/60 hover:scale-[1.04] transition-all duration-150 focus:outline-none focus:border-sky-500"
                      style={{ width: 70, height: 98 }}
                      title={card.name}
                      onClick={() => setSelectedCard({ card, imageUrl })}
                    >
                      {imageUrl ? (
                        <img src={imageUrl} alt={card.name} className="w-full h-full object-cover" />
                      ) : (
                        <img src="/card-back.png" alt={card.name} className="w-full h-full object-cover" />
                      )}
                      <span className="absolute bottom-1 right-1 bg-slate-950/90 text-slate-300 text-[10px] font-mono font-bold rounded px-1 py-0.5 min-w-[18px] text-center leading-none">
                        {i + 1}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {selectedCard && (
        <CardModal
          card={selectedCard.card}
          imageUrl={selectedCard.imageUrl}
          isOpen={true}
          onClose={() => setSelectedCard(null)}
        />
      )}
    </>
  );
}
