import { Card } from '../types/game';
import EnergyIcon from './EnergyIcon';

interface Props {
  card: Card;
  imageUrl?: string;
  isOpen: boolean;
  onClose: () => void;
}

export default function CardModal({ card, imageUrl, isOpen, onClose }: Props) {
  if (!isOpen) return null;

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose();
  };

  return (
    <div
      className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onClick={handleBackdropClick}
    >
      <div className="relative max-w-3xl w-full">
        <button
          onClick={onClose}
          className="absolute -top-10 right-0 text-slate-500 hover:text-slate-200 transition-colors flex items-center gap-1.5 text-sm"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
          Close
        </button>

        <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 shadow-2xl">
          <div className="flex flex-col md:flex-row gap-6">
            {/* Image */}
            <div className="flex-shrink-0">
              {imageUrl ? (
                <img src={imageUrl} alt={card.name} className="w-72 h-auto rounded-lg shadow-xl" />
              ) : (
                <div className="w-72 h-[26rem] bg-slate-800 rounded-lg border border-slate-700 flex items-center justify-center">
                  <div className="text-center p-4">
                    <div className="text-5xl mb-3">🃏</div>
                    <div className="text-base font-semibold text-slate-300">{card.name}</div>
                  </div>
                </div>
              )}
            </div>

            {/* Info */}
            <div className="flex-1 min-w-0">
              <h2 className="text-2xl font-bold text-slate-50 mb-1">{card.name}</h2>

              {'hp' in card && (
                <div className="space-y-4 mt-4">
                  <div>
                    <p className="text-[10px] font-mono text-slate-600 uppercase tracking-wider mb-1">HP</p>
                    <p className="text-2xl font-mono font-bold text-emerald-400">{card.hp}</p>
                  </div>

                  <div>
                    <p className="text-[10px] font-mono text-slate-600 uppercase tracking-wider mb-2">Energy Attached</p>
                    <div className="flex flex-wrap gap-2 items-center">
                      {card.energy.length > 0 ? (
                        card.energy.map((e, idx) => (
                          <div key={idx} className="flex flex-col items-center gap-1">
                            <EnergyIcon type={e} size={28} />
                            <span className="text-[10px] text-slate-500 capitalize font-mono">{e}</span>
                          </div>
                        ))
                      ) : (
                        <div className="text-xs text-slate-600">None attached</div>
                      )}
                    </div>
                  </div>

                  {'tool' in card && card.tool.length > 0 && (
                    <div>
                      <p className="text-[10px] font-mono text-slate-600 uppercase tracking-wider mb-1">Tool</p>
                      <p className="text-sm text-sky-400">{card.tool.join(', ')}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
