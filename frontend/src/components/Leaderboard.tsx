import { useEffect, useState, useCallback } from 'react';
import { api } from '../services/api';
import { AgentRating } from '../types/game';

function winRate(r: AgentRating): number {
  const total = r.wins + r.losses + r.draws;
  if (total === 0) return 0;
  return (r.wins + r.draws * 0.5) / total;
}

function formatAgentName(id: string): string {
  if (id === 'random') return 'Random Agent';
  if (id === 'charizard_heuristic') return 'Charizard Heuristic';
  if (id.startsWith('react:')) return id.slice(6);
  if (id.startsWith('llm:')) return id.slice(4);
  return id;
}

function agentTag(id: string): { label: string; classes: string } {
  if (id === 'random') return { label: 'Random', classes: 'bg-slate-800 text-slate-400 border-slate-700' };
  if (id === 'charizard_heuristic') return { label: 'Heuristic', classes: 'bg-amber-950/60 text-amber-400 border-amber-800/60' };
  if (id.startsWith('react:')) return { label: 'ReAct', classes: 'bg-sky-950/60 text-sky-400 border-sky-800/60' };
  if (id.startsWith('llm:')) return { label: 'LLM', classes: 'bg-sky-950/60 text-sky-400 border-sky-800/60' };
  return { label: 'Agent', classes: 'bg-slate-800 text-slate-400 border-slate-700' };
}

function RatingBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="w-full h-1 bg-slate-800 rounded-full overflow-hidden">
      <div
        className="h-full rounded-full bg-sky-500 transition-all duration-700"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function WinRateBar({ rate }: { rate: number }) {
  const pct = Math.round(rate * 100);
  const color =
    pct >= 60 ? 'bg-emerald-500' :
    pct >= 40 ? 'bg-amber-500' :
    'bg-rose-500';
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1 bg-slate-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color} transition-all duration-700`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[11px] font-mono text-slate-400 w-8">{pct}%</span>
    </div>
  );
}

function RankBadge({ rank }: { rank: number }) {
  if (rank <= 3) {
    const colors = ['text-amber-400', 'text-slate-400', 'text-amber-700'];
    return <span className={`text-sm font-mono font-bold ${colors[rank - 1]}`}>{rank}</span>;
  }
  return <span className="text-xs font-mono text-slate-600">{rank}</span>;
}

function LeaderboardRow({ rating, rank, maxMu }: { rating: AgentRating; rank: number; maxMu: number }) {
  const tag = agentTag(rating.agent_id);
  const total = rating.wins + rating.losses + rating.draws;
  const wr = winRate(rating);

  return (
    <tr className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
      <td className="px-4 py-3 text-center w-10">
        <RankBadge rank={rank} />
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border flex-shrink-0 ${tag.classes}`}>
            {tag.label}
          </span>
          <span className="text-sm font-medium text-slate-200 truncate">
            {formatAgentName(rating.agent_id)}
          </span>
        </div>
      </td>
      <td className="px-4 py-3 min-w-[130px]">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-baseline gap-1.5">
            <span className="text-sm font-mono font-bold text-slate-100">{Math.round(rating.mu)}</span>
            <span className="text-[11px] font-mono text-slate-600">±{Math.round(rating.phi)}</span>
          </div>
          <RatingBar value={rating.mu} max={maxMu} />
        </div>
      </td>
      <td className="px-4 py-3"><WinRateBar rate={wr} /></td>
      <td className="px-4 py-3 text-center">
        <span className="text-sm font-mono font-semibold text-emerald-400">{rating.wins}</span>
      </td>
      <td className="px-4 py-3 text-center">
        <span className="text-sm font-mono font-semibold text-rose-400">{rating.losses}</span>
      </td>
      <td className="px-4 py-3 text-center">
        <span className="text-sm font-mono text-slate-500">{rating.draws}</span>
      </td>
      <td className="px-4 py-3 text-center">
        <span className="text-sm font-mono text-slate-600">{total}</span>
      </td>
    </tr>
  );
}

export default function Leaderboard() {
  const [ratings, setRatings] = useState<AgentRating[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchLeaderboard = useCallback(async () => {
    try {
      setError(null);
      const data = await api.getLeaderboard();
      setRatings(data);
      setLastUpdated(new Date());
    } catch {
      setError('Failed to load leaderboard data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchLeaderboard(); }, [fetchLeaderboard]);

  const maxMu = ratings.length > 0 ? Math.max(...ratings.map((r) => r.mu)) : 2000;

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex items-end justify-between mb-6">
        <div>
          <div className="text-[11px] font-mono text-sky-500 uppercase tracking-widest mb-1">Evaluation Results</div>
          <h2 className="text-xl font-bold text-slate-50">Agent Leaderboard</h2>
          <p className="text-xs text-slate-500 mt-1">
            Glicko-2 ratings · sorted by rating
            {lastUpdated && (
              <span className="ml-2 font-mono text-slate-700">
                · {lastUpdated.toLocaleTimeString()}
              </span>
            )}
          </p>
        </div>
        <button
          onClick={fetchLeaderboard}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-slate-800 border border-slate-700 hover:border-sky-700/60 hover:bg-slate-700 text-slate-300 transition-all disabled:opacity-40"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
            className={loading ? 'animate-spin' : ''}>
            <polyline points="23 4 23 10 17 10" />
            <polyline points="1 20 1 14 7 14" />
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
          </svg>
          Refresh
        </button>
      </div>

      {/* Summary metrics */}
      {!loading && !error && ratings.length > 0 && (
        <div className="grid grid-cols-3 gap-3 mb-6">
          {[
            { label: 'Total Agents', value: ratings.length, mono: true },
            { label: 'Total Games', value: Math.round(ratings.reduce((s, r) => s + r.wins + r.losses + r.draws, 0) / 2), mono: true },
            { label: 'Top Agent', value: formatAgentName(ratings[0]?.agent_id ?? '—'), mono: false },
          ].map(({ label, value, mono }) => (
            <div key={label} className="bg-slate-900 border border-slate-800 rounded-lg p-4">
              <p className="text-[10px] text-slate-600 uppercase tracking-wider font-medium mb-1.5">{label}</p>
              <p className={`text-lg font-bold text-slate-100 ${mono ? 'font-mono' : ''} truncate`}>{value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16 text-slate-600 gap-2 text-sm">
            <svg className="animate-spin" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
            </svg>
            Loading…
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <p className="text-sm text-rose-400">{error}</p>
            <button onClick={fetchLeaderboard} className="text-xs text-sky-500 hover:text-sky-400 underline underline-offset-2">Try again</button>
          </div>
        ) : ratings.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-slate-600 gap-3">
            <p className="text-sm">No rating data yet.</p>
            <p className="text-xs">
              Run <code className="bg-slate-800 px-1.5 py-0.5 rounded text-sky-400 font-mono">python -m ptcgbench.bench.eval_pipeline --global-ratings</code>
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-800">
                  {['#', 'Agent', 'Rating', 'Win Rate', 'W', 'L', 'D', 'N'].map((h, i) => (
                    <th key={h} className={`px-4 py-2.5 text-[10px] font-semibold font-mono text-slate-600 uppercase tracking-wider ${i >= 4 ? 'text-center' : ''}`}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ratings.map((r, i) => (
                  <LeaderboardRow key={r.agent_id} rating={r} rank={i + 1} maxMu={maxMu} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {!loading && !error && ratings.length > 0 && (
        <p className="text-[10px] font-mono text-slate-700 mt-3 text-right">
          μ = Glicko-2 rating · φ = rating deviation
        </p>
      )}
    </div>
  );
}
