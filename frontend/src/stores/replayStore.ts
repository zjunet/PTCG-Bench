import { create } from 'zustand';
import axios from 'axios';
import { GameState, PlayerId } from '../types/game';
import { ReplayFrame, ReplayFile, RawReplayEvent, ReplayActionData } from '../types/replay';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function normalizePlayerId(id: string): PlayerId {
  const lower = (id ?? '').toLowerCase();
  if (lower.includes('player2')) return 'player2';
  return 'player1';
}

function parseFrames(events: RawReplayEvent[]): { frames: ReplayFrame[]; winner: PlayerId | null } {
  const frames: ReplayFrame[] = [];
  let pendingAction: ReplayActionData | null = null;
  let winner: PlayerId | null = null;

  for (const event of events) {
    if (event.type === 'game_start') {
      const rawState = event.data.state as GameState;
      const turn = normalizePlayerId(event.data.first_player ?? 'player1');
      frames.push({
        frameIndex: 0,
        state: { ...rawState, turn, timestep: 0 },
        action: null,
        turn,
      });
    } else if (event.type === 'action') {
      pendingAction = event.data as ReplayActionData;
    } else if (event.type === 'state') {
      const rawState = event.data as unknown as GameState;
      const turn = normalizePlayerId(rawState.turn ?? 'player1');
      frames.push({
        frameIndex: frames.length,
        state: { ...rawState, turn },
        action: pendingAction,
        turn,
      });
      pendingAction = null;
    } else if (event.type === 'termination') {
      winner = normalizePlayerId(event.data.winner ?? 'player1');
    }
  }

  return { frames, winner };
}

// ─── Store ────────────────────────────────────────────────────────────────────

interface ReplayStore {
  // file list
  availableFiles: ReplayFile[];
  filesLoading: boolean;

  // loaded replay
  frames: ReplayFrame[];
  winner: PlayerId | null;
  filename: string | null;
  replayLoading: boolean;
  error: string | null;

  // playback state
  currentFrame: number;
  isPlaying: boolean;
  playbackSpeed: number; // frames per second
  _intervalId: ReturnType<typeof setInterval> | null;

  // actions
  fetchFileList: () => Promise<void>;
  loadReplay: (filename: string) => Promise<void>;
  unloadReplay: () => void;
  goToFrame: (n: number) => void;
  nextFrame: () => void;
  prevFrame: () => void;
  play: () => void;
  pause: () => void;
  togglePlay: () => void;
  setSpeed: (speed: number) => void;
}

export const useReplayStore = create<ReplayStore>((set, get) => ({
  availableFiles: [],
  filesLoading: false,
  frames: [],
  winner: null,
  filename: null,
  replayLoading: false,
  error: null,
  currentFrame: 0,
  isPlaying: false,
  playbackSpeed: 1,
  _intervalId: null,

  fetchFileList: async () => {
    set({ filesLoading: true, error: null });
    try {
      const res = await axios.get('/api/replays');
      set({ availableFiles: res.data, filesLoading: false });
    } catch {
      set({ error: 'Failed to load replay list', filesLoading: false });
    }
  },

  loadReplay: async (filename) => {
    get().pause();
    set({ replayLoading: true, error: null, frames: [], currentFrame: 0 });
    try {
      const res = await axios.get(`/api/replays/${filename}`);
      const { frames, winner } = parseFrames(res.data.events as RawReplayEvent[]);
      set({ frames, winner, filename, replayLoading: false, currentFrame: 0 });
    } catch {
      set({ error: 'Failed to load replay', replayLoading: false });
    }
  },

  unloadReplay: () => {
    get().pause();
    set({ frames: [], winner: null, filename: null, currentFrame: 0, error: null });
  },

  goToFrame: (n) => {
    const { frames } = get();
    const clamped = Math.max(0, Math.min(n, frames.length - 1));
    set({ currentFrame: clamped });
  },

  nextFrame: () => {
    const { currentFrame, frames, pause } = get();
    if (currentFrame >= frames.length - 1) {
      pause();
      return;
    }
    set({ currentFrame: currentFrame + 1 });
  },

  prevFrame: () => {
    const { currentFrame } = get();
    set({ currentFrame: Math.max(0, currentFrame - 1) });
  },

  play: () => {
    const { isPlaying, playbackSpeed, frames, currentFrame } = get();
    if (isPlaying) return;
    if (currentFrame >= frames.length - 1) {
      // restart from beginning
      set({ currentFrame: 0 });
    }
    const id = setInterval(() => {
      get().nextFrame();
    }, 1000 / playbackSpeed);
    set({ isPlaying: true, _intervalId: id });
  },

  pause: () => {
    const { _intervalId } = get();
    if (_intervalId !== null) clearInterval(_intervalId);
    set({ isPlaying: false, _intervalId: null });
  },

  togglePlay: () => {
    const { isPlaying, play, pause } = get();
    if (isPlaying) pause();
    else play();
  },

  setSpeed: (speed) => {
    const { isPlaying, pause, play } = get();
    set({ playbackSpeed: speed });
    if (isPlaying) {
      pause();
      // Use setTimeout so state settles
      setTimeout(() => play(), 0);
    }
  },
}));
