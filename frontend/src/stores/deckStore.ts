import { create } from 'zustand';
import { DeckInfo } from '../types/game';
import { api } from '../services/api';

interface DeckStore {
  decks: DeckInfo[];
  loading: boolean;
  loadDecks: () => Promise<void>;
}

export const useDeckStore = create<DeckStore>((set, get) => ({
  decks: [],
  loading: false,

  loadDecks: async () => {
    if (get().decks.length > 0) return; // already loaded
    set({ loading: true });
    try {
      const decks = await api.listDecks();
      set({ decks, loading: false });
    } catch (err) {
      console.error('Failed to load decks:', err);
      set({ loading: false });
    }
  },
}));
