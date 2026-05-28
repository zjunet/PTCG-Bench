// Game Types - Corresponding to Python backend

export type PlayerId = 'player1' | 'player2';

export interface GameState {
  player1: PlayerState;
  player2: PlayerState;
  stadium: StadiumCard[];
  turn: PlayerId;
  timestep: number;
  turn_number: number;
}

export interface PlayerState {
  active: PokemonCard[];
  bench: PokemonCard[];
  hand: Card[];
  deck: Card[];
  discard: Card[];
  prize: Card[];
  lostZone: Card[];
  onceUsed: OnceUsed;
}

export interface PokemonCard {
  name: string;
  hp: number;
  tool: string[];
  energy: string[];
  evolved: string[];
  attachment: string[];
}

export interface EnergyCard {
  name: string;
  provides: string[];
  energyType: 'BASIC' | 'SPECIAL';
}

export interface TrainerCard {
  name: string;
  trainerType: 'ITEM' | 'SUPPORTER' | 'STADIUM' | 'TOOL';
}

export interface StadiumCard {
  name: string;
  playedFrom: string;
}

export type Card = PokemonCard | EnergyCard | TrainerCard;

export interface OnceUsed {
  supporter: string;
  energy: string;
  stadiumPlayed: string;
  stadiumUsed: string;
  retreat: string;
}

export interface Action {
  playerId: string;
  actionType: string;
  source?: string;
  target?: string;
  attack?: {
    name: string;
    damage: number;
  };
  ability?: string;
  position?: string;
  /** Present on ChooseCardAction – which cards this action selects */
  chosen?: string[];
  /** Present on ChooseCardAction – all candidate card names */
  candidates?: string[];
}

export interface ChooseCardPrompt {
  minCnt: number;
  maxCnt: number;
  candidates: string[];
  hidden: boolean;
  tips: string;
  source?: string;
}

export interface GameInfo {
  gameId: string;
  state: GameState;
  availableActions: Action[];
  turn: PlayerId;
  done: boolean;
  winner?: PlayerId;
}

export interface CreateGameRequest {
  deck1?: string;
  deck2?: string;
  seed: number;
}

export interface ActionRequest {
  action_index: number;
}

export interface DeckInfo {
  id: string;
  displayName: string;
  pokemonCount: number;
  trainerCount: number;
  energyCount: number;
  keyPokemon: string[];
  energyTypes: string[]; // uppercase codes: R, L, P, W, G, F, M, D, C
}

export interface AgentRating {
  agent_id: string;
  mu: number;
  phi: number;
  sigma: number;
  wins: number;
  losses: number;
  draws: number;
}

export interface LogEntry {
  id: number;
  timestep: number;
  turn_number: number;
  player: PlayerId;
  actionType: string;
  source?: string;
  target?: string;
  attack?: { name: string; damage: number };
  ability?: string;
  position?: string;
  chosen?: string[];
}
