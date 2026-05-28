import { useEffect } from 'react';
import { useDeckStore } from '../stores/deckStore';
import { useGameStore } from '../stores/gameStore';
import DeckCard from './DeckCard';

interface DeckManagerProps {
  onPlayWithDeck: (deckId: string) => void;
}

export default function DeckManager({ onPlayWithDeck }: DeckManagerProps) {
  const { decks, loading, loadDecks } = useDeckStore();
  const { cardImages } = useGameStore();

  useEffect(() => { loadDecks(); }, [loadDecks]);

  return (
    <div className="p-6 pb-10 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-[11px] font-mono text-sky-500 uppercase tracking-widest mb-1">Configuration</div>
          <h2 className="text-xl font-bold text-slate-50">Deck Collection</h2>
          <p className="text-xs text-slate-500 mt-1">
            {decks.length > 0
              ? `${decks.length} deck${decks.length !== 1 ? 's' : ''} available · click to start a game`
              : 'No decks loaded'}
          </p>
        </div>
        {decks.length > 0 && (
          <span className="px-3 py-1 rounded-md bg-slate-800 border border-slate-700 text-slate-500 text-xs font-mono">
            {decks.length} decks
          </span>
        )}
      </div>

      {/* Grid */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-60 rounded-xl bg-slate-900 border border-slate-800 animate-pulse" />
          ))}
        </div>
      ) : decks.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-slate-600">
          <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="mb-4 opacity-40">
            <rect x="2" y="5" width="20" height="14" rx="2" /><path d="M2 10h20" />
          </svg>
          <p className="text-sm font-medium">No decks found</p>
          <p className="text-xs mt-1 font-mono text-slate-700">Add .txt deck files to ptcg-engine/src/ptcg/decks/</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {decks.map(deck => (
            <DeckCard key={deck.id} deck={deck} cardImages={cardImages} onPlay={onPlayWithDeck} />
          ))}
        </div>
      )}
    </div>
  );
}
