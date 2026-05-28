import { DeckInfo } from '../types/game';
import EnergyIcon from './EnergyIcon';

// ─── Energy code → type name + colors ────────────────────────────────────────
export const ENERGY_CODE_TO_TYPE: Record<string, string> = {
  R: 'fire', L: 'lightning', P: 'psychic', W: 'water', G: 'grass',
  F: 'fighting', M: 'metal', D: 'dark', C: 'colorless', N: 'colorless',
};

const ENERGY_GRADIENT: Record<string, { from: string; to: string; accent: string }> = {
  fire:      { from: '#c2410c', to: '#0c0a09', accent: '#f97316' },
  lightning: { from: '#a16207', to: '#0c0a09', accent: '#facc15' },
  psychic:   { from: '#7e22ce', to: '#0c0a09', accent: '#c084fc' },
  water:     { from: '#1d4ed8', to: '#0c0a09', accent: '#60a5fa' },
  grass:     { from: '#15803d', to: '#0c0a09', accent: '#4ade80' },
  fighting:  { from: '#b45309', to: '#0c0a09', accent: '#fb923c' },
  metal:     { from: '#475569', to: '#0c0a09', accent: '#94a3b8' },
  dark:      { from: '#374151', to: '#0c0a09', accent: '#9ca3af' },
  colorless: { from: '#334155', to: '#0c0a09', accent: '#94a3b8' },
};
const DEFAULT_GRADIENT = { from: '#334155', to: '#0c0a09', accent: '#94a3b8' };

export function getDeckColors(energyTypes: string[]) {
  const typeName = ENERGY_CODE_TO_TYPE[energyTypes[0]] ?? 'colorless';
  return ENERGY_GRADIENT[typeName] ?? DEFAULT_GRADIENT;
}

interface DeckCardProps {
  deck: DeckInfo;
  cardImages: Record<string, string>;
  onPlay?: (deckId: string) => void;
}

export default function DeckCard({ deck, cardImages, onPlay }: DeckCardProps) {
  const colors = getDeckColors(deck.energyTypes);
  const heroImage = deck.keyPokemon[0] ? cardImages[deck.keyPokemon[0]] : undefined;
  const energyTypeNames = deck.energyTypes.map(c => ENERGY_CODE_TO_TYPE[c] ?? 'colorless');

  return (
    <div
      className="relative rounded-xl overflow-hidden border border-slate-800 bg-slate-900 flex flex-col transition-all duration-200 hover:border-slate-700 hover:scale-[1.01] group"
    >
      {/* Gradient header — energy visualization (kept for functional color-coding) */}
      <div
        className="relative h-24 overflow-hidden flex items-end px-4 pb-3"
        style={{ background: `linear-gradient(135deg, ${colors.from} 0%, #0c0a09 100%)` }}
      >
        <div className="absolute inset-0 opacity-20" style={{ background: `radial-gradient(ellipse at 30% 50%, ${colors.accent}50, transparent 70%)` }} />
        {heroImage && (
          <img
            src={heroImage}
            alt={deck.keyPokemon[0]}
            className="absolute right-2 top-1 h-[100px] w-[70px] object-cover rounded-md opacity-75 group-hover:opacity-90 transition-opacity"
            style={{ filter: 'drop-shadow(0 4px 8px rgba(0,0,0,0.7))' }}
          />
        )}
        <div className="relative z-10 flex gap-1.5">
          {energyTypeNames.slice(0, 3).map((type, i) => <EnergyIcon key={i} type={type} size={20} />)}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 p-4 flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-slate-100 leading-tight">{deck.displayName}</h3>

        {/* Stats */}
        <div className="flex gap-1.5 text-[10px] font-mono">
          <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
            {deck.pokemonCount}P
          </span>
          <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
            {deck.trainerCount}T
          </span>
          <span className="px-2 py-0.5 rounded bg-slate-800 border" style={{ color: colors.accent, borderColor: `${colors.accent}30` }}>
            {deck.energyCount}E
          </span>
        </div>

        {/* Key Pokémon */}
        <div>
          <p className="text-[9px] font-mono uppercase tracking-widest text-slate-600 mb-1.5">Key Pokémon</p>
          <div className="flex flex-wrap gap-1">
            {deck.keyPokemon.slice(0, 4).map(name => (
              <span key={name} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700/60">
                {name}
              </span>
            ))}
            {deck.keyPokemon.length > 4 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800/50 text-slate-600 border border-slate-800">
                +{deck.keyPokemon.length - 4}
              </span>
            )}
          </div>
        </div>

        {/* Play button */}
        {onPlay && (
          <button
            onClick={() => onPlay(deck.id)}
            className="mt-auto w-full py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 border hover:brightness-110 active:scale-95"
            style={{ color: colors.accent, borderColor: `${colors.accent}40`, background: `${colors.accent}0f` }}
          >
            Use this Deck
          </button>
        )}
      </div>

      {/* Accent bottom bar */}
      <div className="h-px w-full" style={{ background: `linear-gradient(90deg, ${colors.accent}60, transparent)` }} />
    </div>
  );
}
