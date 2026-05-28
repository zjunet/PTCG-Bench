/**
 * EnergyIcon — maps a Pokémon TCG energy type string to its PNG icon.
 *
 * Energy strings arrive from the backend as lowercase CardType enum names
 * (e.g. "fire", "water", "dark", "colorless", …).
 */

interface EnergyIconProps {
  /** Lowercase energy type, e.g. "fire", "water", "dark", "colorless" */
  type: string;
  /** Icon size in pixels (width = height). Default 20. */
  size?: number;
  /** Extra CSS class string */
  className?: string;
}

/**
 * Map from backend energy-type string → public asset filename (without extension).
 * "dark" is the enum value but the icon file is named "darkness".
 */
const TYPE_TO_FILENAME: Record<string, string> = {
  colorless: 'colorless',
  grass: 'grass',
  fire: 'fire',
  water: 'water',
  lightning: 'lightning',
  psychic: 'psychic',
  fighting: 'fighting',
  dark: 'darkness',
  darkness: 'darkness',
  metal: 'metal',
  dragon: 'colorless',   // no dedicated dragon icon — fall back to colorless
  fairy: 'psychic',      // no dedicated fairy icon — fall back to psychic
  rainbow: 'rainbow',
  any: 'colorless',
  none: 'colorless',
};

/** Background colours for the circular border ring that frames each icon */
const TYPE_TO_RING: Record<string, string> = {
  colorless: '#a8a878',
  grass: '#78c850',
  fire: '#f08030',
  water: '#6890f0',
  lightning: '#f8d030',
  psychic: '#f85888',
  fighting: '#c03028',
  dark: '#705848',
  darkness: '#705848',
  metal: '#b8b8d0',
  dragon: '#7038f8',
  fairy: '#ee99ac',
  rainbow: '#888',
  any: '#888',
  none: '#888',
};

export default function EnergyIcon({ type, size = 20, className = '' }: EnergyIconProps) {
  const key = type.toLowerCase();
  const file = TYPE_TO_FILENAME[key] ?? 'colorless';
  const ring = TYPE_TO_RING[key] ?? '#888';

  return (
    <div
      className={`inline-flex items-center justify-center rounded-full flex-shrink-0 ${className}`}
      style={{
        width: size,
        height: size,
        boxShadow: `0 0 0 1.5px ${ring}, 0 1px 3px rgba(0,0,0,0.5)`,
        background: '#1a1a2e',
      }}
      title={type.charAt(0).toUpperCase() + type.slice(1)}
    >
      <img
        src={`/energy/${file}.png`}
        alt={type}
        style={{ width: size - 3, height: size - 3 }}
        className="rounded-full object-cover select-none"
        draggable={false}
      />
    </div>
  );
}
