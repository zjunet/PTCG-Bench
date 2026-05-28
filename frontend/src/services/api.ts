import axios from 'axios';
import { AgentRating, DeckInfo } from '../types/game';

export interface AgentModelInfo {
  id: string;
  name: string;
  provider: string;
}

export interface AgentInfo {
  id: string;
  name: string;
  description: string;
  requiresModel: boolean;
  available: boolean;
  unavailableReason?: string;
  models?: AgentModelInfo[];
  defaultModel?: string;
}

const API_BASE = '/api';

export const api = {
  async createGame(config: { deck1?: string; deck2?: string; seed: number; agent?: string; agentPlayer?: string; agentModel?: string }) {
    const response = await axios.post(`${API_BASE}/game/create`, {
      deck1: config.deck1,
      deck2: config.deck2,
      seed: config.seed,
      agent: config.agent,
      agent_player: config.agentPlayer,
      agent_model: config.agentModel,
    });
    return response.data;
  },

  async listAgents() {
    const response = await axios.get(`${API_BASE}/agents`);
    return response.data as AgentInfo[];
  },

  async getGameState(gameId: string) {
    const response = await axios.get(`${API_BASE}/game/${gameId}/state`);
    return response.data;
  },

  async executeAction(gameId: string, actionIndex: number) {
    const response = await axios.post(`${API_BASE}/game/${gameId}/action`, {
      action_index: actionIndex,
    });
    return response.data;
  },

  async agentStep(gameId: string) {
    const response = await axios.post(`${API_BASE}/game/${gameId}/agent-step`);
    return response.data;
  },

  async deleteGame(gameId: string) {
    const response = await axios.delete(`${API_BASE}/game/${gameId}`);
    return response.data;
  },

  async listDecks(): Promise<DeckInfo[]> {
    const response = await axios.get(`${API_BASE}/decks`);
    return response.data;
  },

  async getLeaderboard(): Promise<AgentRating[]> {
    const response = await axios.get(`${API_BASE}/leaderboard`);
    return response.data.agents as AgentRating[];
  },

  async listReplays() {
    const response = await axios.get(`${API_BASE}/replays`);
    return response.data;
  },

  async getReplay(filename: string) {
    const response = await axios.get(`${API_BASE}/replays/${encodeURIComponent(filename)}`);
    return response.data;
  },
};
