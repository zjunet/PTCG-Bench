import { useReplayStore } from '../stores/replayStore';

const SPEEDS = [0.25, 0.5, 1, 2, 4];

function IconSkipBack() {
  return <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h2v12H6zm3.5 6 8.5 6V6z" /></svg>;
}
function IconSkipForward() {
  return <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M6 18l8.5-6L6 6v12zm2.5-6 5.5 3.9V8.1L8.5 12zM16 6h2v12h-2z" /></svg>;
}
function IconStepBack() {
  return <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M15.41 16.59 10.83 12l4.58-4.59L14 6l-6 6 6 6 1.41-1.41z" /></svg>;
}
function IconStepForward() {
  return <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M8.59 16.59 13.17 12 8.59 7.41 10 6l6 6-6 6-1.41-1.41z" /></svg>;
}
function IconPlay() {
  return <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>;
}
function IconPause() {
  return <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" /></svg>;
}

interface Props {
  embedded?: boolean;
}

export default function ReplayControls({ embedded = false }: Props) {
  const { frames, currentFrame, isPlaying, playbackSpeed, winner, filename, togglePlay, prevFrame, nextFrame, goToFrame, setSpeed, unloadReplay } = useReplayStore();

  const total = frames.length;
  const atStart = currentFrame === 0;
  const atEnd = currentFrame >= total - 1;
  const currentAction = frames[currentFrame]?.action;
  const isLastFrame = atEnd && winner !== null;

  return (
    <div className={[
      'bg-slate-900 px-4 py-3 flex flex-col gap-2',
      embedded ? 'border-0 rounded-none' : 'border border-slate-800 rounded-lg',
    ].join(' ')}>
      {/* Winner */}
      {isLastFrame && (
        <div className="text-center text-xs font-semibold font-mono text-amber-400 tracking-wide">
          {winner?.toUpperCase()} wins
        </div>
      )}

      {/* Current action */}
      <div className="min-h-[16px] text-center">
        {currentAction ? (
          <span className="text-[11px] text-slate-500">
            <span className={`font-mono font-bold ${currentAction.playerId.toLowerCase().includes('player1') ? 'text-sky-400' : 'text-amber-400'}`}>
              {currentAction.playerId.toLowerCase().includes('player1') ? 'P1' : 'P2'}
            </span>
            {' · '}
            <span className="text-slate-400">{currentAction.actionType.replace('Action', '')}</span>
            {currentAction.source && <> · <span className="text-slate-400">{currentAction.source}</span></>}
            {currentAction.target && <> → <span className="text-slate-500">{currentAction.target}</span></>}
          </span>
        ) : (
          <span className="text-[11px] text-slate-700 font-mono">{currentFrame === 0 ? 'start' : '—'}</span>
        )}
      </div>

      {/* Progress slider */}
      <div className="flex items-center gap-2">
        <span className="text-[10px] font-mono text-slate-600 w-8 text-right">{currentFrame}</span>
        <input
          type="range"
          min={0}
          max={Math.max(0, total - 1)}
          value={currentFrame}
          onChange={(e) => goToFrame(Number(e.target.value))}
          className="flex-1 accent-sky-500 h-1"
        />
        <span className="text-[10px] font-mono text-slate-600 w-8">{total - 1}</span>
      </div>

      {/* Controls row */}
      <div className="flex items-center justify-between">
        {/* Filename */}
        <div className="flex items-center gap-2 min-w-0">
          <button onClick={unloadReplay} title="Back to replay list"
            className="text-slate-600 hover:text-slate-300 transition-colors flex-shrink-0">
            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
              <path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z" />
            </svg>
          </button>
          <span className="text-[10px] font-mono text-slate-600 truncate" title={filename ?? ''}>{filename}</span>
        </div>

        {/* Playback buttons */}
        <div className="flex items-center gap-0.5">
          {[
            { fn: () => goToFrame(0), disabled: atStart, title: 'Start', icon: <IconSkipBack /> },
            { fn: prevFrame, disabled: atStart, title: 'Previous', icon: <IconStepBack /> },
          ].map((btn, i) => (
            <button key={i} onClick={btn.fn} disabled={btn.disabled} title={btn.title}
              className="p-1.5 rounded text-slate-500 hover:text-slate-200 hover:bg-slate-800 disabled:opacity-25 disabled:cursor-not-allowed transition-all">
              {btn.icon}
            </button>
          ))}

          <button onClick={togglePlay} title={isPlaying ? 'Pause' : 'Play'}
            className="p-1.5 mx-1 rounded-full bg-sky-600 hover:bg-sky-500 text-white transition-colors">
            {isPlaying ? <IconPause /> : <IconPlay />}
          </button>

          {[
            { fn: nextFrame, disabled: atEnd, title: 'Next', icon: <IconStepForward /> },
            { fn: () => goToFrame(total - 1), disabled: atEnd, title: 'End', icon: <IconSkipForward /> },
          ].map((btn, i) => (
            <button key={i} onClick={btn.fn} disabled={btn.disabled} title={btn.title}
              className="p-1.5 rounded text-slate-500 hover:text-slate-200 hover:bg-slate-800 disabled:opacity-25 disabled:cursor-not-allowed transition-all">
              {btn.icon}
            </button>
          ))}
        </div>

        {/* Speed control */}
        <div className="flex items-center gap-0.5">
          {SPEEDS.map((s) => (
            <button key={s} onClick={() => setSpeed(s)}
              className={[
                'text-[10px] px-1.5 py-0.5 rounded font-mono font-medium transition-all',
                playbackSpeed === s
                  ? 'bg-sky-600 text-white'
                  : 'bg-slate-800 text-slate-500 hover:text-slate-300 hover:bg-slate-700',
              ].join(' ')}
            >
              {s}×
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
