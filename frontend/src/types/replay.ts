import { GameState, PlayerId } from './game';

export interface ReplayActionData {
  playerId: string;
  actionType: string;
  source?: string;
  target?: string;
  attack?: { name: string; damage: number };
  ability?: string;
  position?: string;
  chosen?: string[];
}

export interface ReplayFrame {
  frameIndex: number;
  state: GameState;
  action: ReplayActionData | null;
  turn: PlayerId;
}

export interface ReplayFile {
  filename: string;
  size: number;
  mtime: number;
}

// Raw JSONL event shapes
export interface RawReplayEvent {
  type: 'game_start' | 'action' | 'state' | 'termination';
  timestamp: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: Record<string, any>;
}
