import { create } from 'zustand';
import { Card, Action } from '../types/game';

export interface MatchedAction {
  action: Action;
  actionIndex: number;
}

interface DragStore {
  draggedCard: Card | null;
  matchedActions: MatchedAction[];
  isDragging: boolean;
  startDrag: (card: Card, actions: MatchedAction[]) => void;
  endDrag: () => void;
}

export const useDragStore = create<DragStore>((set) => ({
  draggedCard: null,
  matchedActions: [],
  isDragging: false,
  startDrag: (card, actions) =>
    set({ draggedCard: card, matchedActions: actions, isDragging: true }),
  endDrag: () =>
    set({ draggedCard: null, matchedActions: [], isDragging: false }),
}));
