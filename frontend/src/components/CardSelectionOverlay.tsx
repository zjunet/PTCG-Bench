import { useState, useEffect } from 'react';
import { useGameStore } from '../stores/gameStore';

interface SelectableCardProps {
  cardName: string;
  imageUrl?: string;
  selected: boolean;
  disabled: boolean;
  onClick: () => void;
}

function SelectableCard({ cardName, imageUrl, selected, disabled, onClick }: SelectableCardProps) {
  const [imgError, setImgError] = useState(false);

  return (
    <div
      className={[
        'relative flex-shrink-0 rounded-lg overflow-hidden border-2 transition-all duration-150 cursor-pointer',
        'w-[80px] h-[112px]',
        selected
          ? 'border-sky-400 shadow-md shadow-sky-500/20 scale-110 z-10'
          : disabled
          ? 'border-slate-800 opacity-40 cursor-not-allowed'
          : 'border-slate-700 hover:border-sky-500/60 hover:scale-[1.04]',
      ].join(' ')}
      onClick={disabled && !selected ? undefined : onClick}
      title={cardName}
    >
      {imageUrl && !imgError ? (
        <img src={imageUrl} alt={cardName} className="w-full h-full object-cover" onError={() => setImgError(true)} />
      ) : (
        <img src="/card-back.png" alt={cardName} className="w-full h-full object-cover" />
      )}

      {selected && (
        <>
          <div className="absolute inset-0 bg-sky-500/15 pointer-events-none" />
          <div className="absolute top-1 right-1 w-5 h-5 bg-sky-500 rounded-full flex items-center justify-center shadow-md">
            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          </div>
        </>
      )}

      <div className="absolute bottom-0 left-0 right-0 bg-slate-950/80 px-1 py-0.5">
        <span className="text-[8px] text-slate-300 font-medium leading-tight line-clamp-2 block text-center">
          {cardName}
        </span>
      </div>
    </div>
  );
}

export default function CardSelectionOverlay() {
  const { isChoosingCard, chooseCardPrompt, availableActions = [], cardImages, executeAction, loading,
    vsAgent, agentPlayer, turn } = useGameStore();

  const [selectedCards, setSelectedCards] = useState<string[]>([]);

  useEffect(() => { setSelectedCards([]); }, [chooseCardPrompt]);

  const sourceName = chooseCardPrompt?.source ?? '';
  const isAgentChoosing = vsAgent && turn === agentPlayer;
  if (!isChoosingCard || !chooseCardPrompt || isAgentChoosing) return null;

  const { minCnt, maxCnt, candidates, tips, hidden } = chooseCardPrompt;
  const isMultiSelect = maxCnt > 1;
  const selectedCount = selectedCards.length;
  const canSelectMore = selectedCount < maxCnt;
  const isConfirmable = selectedCount >= minCnt && selectedCount <= maxCnt;
  const candidateItems = candidates.map((name, idx) => ({ name, idx }));
  const selectionHint = minCnt === maxCnt
    ? `Select ${minCnt} card${minCnt !== 1 ? 's' : ''}`
    : `Select ${minCnt}–${maxCnt} cards`;

  const handleToggle = (cardName: string, idx: number) => {
    const key = `${cardName}__${idx}`;
    const isAlreadySelected = selectedCards.includes(key);
    if (isAlreadySelected) { setSelectedCards((prev) => prev.filter((k) => k !== key)); return; }
    if (!canSelectMore) return;
    const next = [...selectedCards, key];
    setSelectedCards(next);
    if (!isMultiSelect && next.length === 1) handleConfirm(next);
  };

  const handleConfirm = (keys: string[] = selectedCards) => {
    const chosenNames = keys.map((k) => k.split('__')[0]).sort();
    const actionIndex = availableActions.findIndex((action) => {
      if (action.actionType !== 'ChooseCardAction') return false;
      const actionChosen = [...(action.chosen ?? [])].sort();
      return JSON.stringify(actionChosen) === JSON.stringify(chosenNames);
    });
    if (actionIndex >= 0) executeAction(actionIndex);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl w-full max-w-3xl flex flex-col" style={{ maxHeight: '85vh' }}>
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex-shrink-0">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-base font-semibold text-slate-100">
                Choose Card
                {sourceName && (
                  <span className="ml-2 text-sm font-normal text-sky-400">— {sourceName}</span>
                )}
              </h2>
              {tips && <p className="text-xs text-slate-400 mt-1 leading-relaxed">{tips}</p>}
            </div>
            <div className={[
              'flex-shrink-0 px-3 py-1 rounded-full text-xs font-mono font-semibold border transition-colors',
              isConfirmable
                ? 'bg-sky-950/40 border-sky-700/60 text-sky-400'
                : 'bg-slate-800 border-slate-700 text-slate-500',
            ].join(' ')}>
              {isMultiSelect ? `${selectedCount} / ${maxCnt}` : selectionHint}
            </div>
          </div>

          {isMultiSelect && (
            <div className="mt-3">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-[11px] text-slate-600">{selectionHint}</span>
                {selectedCount >= minCnt && (
                  <span className="text-[11px] text-emerald-400 font-medium">Ready to confirm</span>
                )}
              </div>
              <div className="h-1 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-200 ${isConfirmable ? 'bg-sky-500' : 'bg-sky-700'}`}
                  style={{ width: `${Math.min((selectedCount / maxCnt) * 100, 100)}%` }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Card grid */}
        <div className="flex-1 overflow-y-auto p-6">
          {candidates.length === 0 ? (
            <div className="text-center text-slate-600 py-10 text-sm">No candidate cards</div>
          ) : (
            <div className="flex flex-wrap gap-3 justify-center">
              {candidateItems.map(({ name, idx }) => {
                const key = `${name}__${idx}`;
                const isSelected = selectedCards.includes(key);
                const isDisabled = !isSelected && !canSelectMore;
                return (
                  <SelectableCard
                    key={key}
                    cardName={name}
                    imageUrl={hidden ? undefined : cardImages[name]}
                    selected={isSelected}
                    disabled={isDisabled}
                    onClick={() => handleToggle(name, idx)}
                  />
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        {(isMultiSelect || minCnt === 0) && (
          <div className="px-6 py-3.5 border-t border-slate-800 flex items-center justify-between flex-shrink-0">
            <button
              onClick={() => setSelectedCards([])}
              disabled={selectedCount === 0 || loading}
              className="text-xs text-slate-500 hover:text-slate-300 disabled:opacity-30 transition-colors"
            >
              Clear
            </button>
            <button
              onClick={() => handleConfirm()}
              disabled={!isConfirmable || loading}
              className={[
                'px-5 py-2 rounded-lg font-medium text-sm transition-all duration-150',
                isConfirmable && !loading
                  ? 'bg-sky-600 hover:bg-sky-500 text-white shadow-md'
                  : 'bg-slate-800 text-slate-600 cursor-not-allowed border border-slate-700',
              ].join(' ')}
            >
              {loading ? 'Confirming…' : selectedCount === 0 && minCnt === 0 ? 'Skip' : `Confirm (${selectedCount})`}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
