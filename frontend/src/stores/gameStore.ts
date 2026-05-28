import { create } from 'zustand';
import { GameState, Action, ChooseCardPrompt, LogEntry } from '../types/game';
import { api } from '../services/api';
import axios from 'axios';

interface GameStore {
  gameId: string | null;
  state: GameState | null;
  availableActions: Action[];
  turn: 'player1' | 'player2' | null;
  done: boolean;
  winner: 'player1' | 'player2' | null;
  loading: boolean;
  error: string | null;
  cardImages: Record<string, string>;
  imagesLoaded: boolean;
  isChoosingCard: boolean;
  chooseCardPrompt: ChooseCardPrompt | null;
  gameLog: LogEntry[];

  // Agent mode
  vsAgent: boolean;
  agentPlayer: 'player1' | 'player2';
  agentType: string | null;
  agentModel: string | null;
  isAgentThinking: boolean;

  createGame: (config: { deck1?: string; deck2?: string; seed: number; agent?: string; agentPlayer?: string; agentModel?: string }) => Promise<void>;
  executeAction: (actionIndex: number) => Promise<void>;
  agentStep: () => Promise<void>;
  reset: () => void;
  loadCardImages: () => Promise<void>;
  getCardImageUrl: (cardName: string) => string | undefined;
}

export const useGameStore = create<GameStore>((set, get) => ({
  gameId: null,
  state: null,
  availableActions: [],
  turn: null,
  done: false,
  winner: null,
  loading: false,
  error: null,
  cardImages: {},
  imagesLoaded: false,
  isChoosingCard: false,
  chooseCardPrompt: null,
  gameLog: [],

  vsAgent: false,
  agentPlayer: 'player2',
  agentType: null,
  agentModel: null,
  isAgentThinking: false,

  createGame: async (config) => {
    set({ loading: true, error: null });
    try {
      const data = await api.createGame(config);
      const newTurn = data.turn?.toLowerCase() as 'player1' | 'player2' | null;
      const agentPlayer = (data.agentPlayer?.toLowerCase() ?? config.agentPlayer ?? 'player2') as 'player1' | 'player2';
      const vsAgent = data.vsAgent ?? false;

      set({
        gameId: data.gameId,
        state: data.state,
        availableActions: data.availableActions,
        turn: newTurn,
        done: data.done,
        winner: data.winner,
        loading: false,
        isChoosingCard: data.isChoosingCard ?? false,
        chooseCardPrompt: data.chooseCardPrompt ?? null,
        vsAgent,
        agentPlayer,
        agentType: data.agentType ?? null,
        agentModel: data.agentModel ?? null,
        isAgentThinking: false,
      });

      // If agent goes first, trigger agent steps immediately
      if (vsAgent && !data.done && newTurn === agentPlayer) {
        get().agentStep();
      }
    } catch (error) {
      set({ error: 'Failed to create game', loading: false });
      console.error(error);
    }
  },

  executeAction: async (actionIndex) => {
    const { gameId, availableActions, turn, gameLog, state } = get();
    if (!gameId) return;

    // Capture the action being executed before the API call
    const action = availableActions[actionIndex];

    set({ loading: true, error: null });
    try {
      const data = await api.executeAction(gameId, actionIndex);
      const newTurn = data.turn?.toLowerCase() as 'player1' | 'player2' | null;

      // Build log entry from the action that was executed
      const newEntry: LogEntry = {
        id: gameLog.length,
        timestep: state?.timestep ?? 0,
        turn_number: state?.turn_number ?? 0,
        player: (turn?.toLowerCase() ?? 'player1') as 'player1' | 'player2',
        actionType: action?.actionType ?? 'Unknown',
        source: action?.source,
        target: action?.target,
        attack: action?.attack,
        ability: action?.ability,
        position: action?.position,
        chosen: action?.chosen,
      };

      set({
        state: data.state,
        availableActions: data.availableActions,
        turn: newTurn,
        done: data.done,
        winner: data.winner,
        loading: false,
        isChoosingCard: data.isChoosingCard ?? false,
        chooseCardPrompt: data.chooseCardPrompt ?? null,
        gameLog: [...gameLog, newEntry],
      });

      // Trigger agent if it's now the agent's turn
      const { vsAgent, agentPlayer } = get();
      if (vsAgent && !data.done && newTurn === agentPlayer) {
        get().agentStep();
      }
    } catch (error) {
      set({ error: 'Failed to execute action', loading: false });
      console.error(error);
    }
  },

  agentStep: async () => {
    const { gameId, vsAgent, agentPlayer } = get();
    if (!gameId || !vsAgent) return;

    set({ isAgentThinking: true });
    try {
      // Loop until it's no longer the agent's turn or game is over
      let keepGoing = true;
      while (keepGoing) {
        const data = await api.agentStep(gameId);
        const newTurn = data.turn?.toLowerCase() as 'player1' | 'player2' | null;

        // Build log entry for agent's action
        const { gameLog, state } = get();
        const takenAction = data.actionTaken;
        const newEntry: LogEntry = {
          id: gameLog.length,
          timestep: state?.timestep ?? 0,
          turn_number: state?.turn_number ?? 0,
          player: agentPlayer,
          actionType: takenAction?.actionType ?? 'Unknown',
          source: takenAction?.source,
          target: takenAction?.target,
          attack: takenAction?.attack,
          ability: takenAction?.ability,
          position: takenAction?.position,
          chosen: takenAction?.chosen,
        };

        set({
          state: data.state,
          availableActions: data.availableActions,
          turn: newTurn,
          done: data.done,
          winner: data.winner ?? null,
          isChoosingCard: data.isChoosingCard ?? false,
          chooseCardPrompt: data.chooseCardPrompt ?? null,
          gameLog: [...get().gameLog, newEntry],
        });

        keepGoing = !data.done && newTurn === agentPlayer;
      }
    } catch (error) {
      set({ error: 'Agent failed to take action' });
      console.error(error);
    } finally {
      set({ isAgentThinking: false });
    }
  },

  reset: () => {
    set({
      gameId: null,
      state: null,
      availableActions: [],
      turn: null,
      done: false,
      winner: null,
      loading: false,
      error: null,
      cardImages: get().cardImages, // Keep loaded images
      imagesLoaded: get().imagesLoaded,
      isChoosingCard: false,
      chooseCardPrompt: null,
      gameLog: [],
      vsAgent: false,
      agentPlayer: 'player2',
      agentType: null,
      agentModel: null,
      isAgentThinking: false,
    });
  },

  loadCardImages: async () => {
    try {
      const response = await axios.get('/api/cards/images');
      set({ cardImages: response.data, imagesLoaded: true });
      console.log(`Loaded ${Object.keys(response.data).length} card images`);
    } catch (error) {
      console.error('Failed to load card images:', error);
      set({ imagesLoaded: false });
    }
  },

  getCardImageUrl: (cardName: string) => {
    const { cardImages } = get();
    return cardImages[cardName];
  },
}));
