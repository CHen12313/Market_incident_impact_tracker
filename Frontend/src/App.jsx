import { useCallback, useEffect, useState } from 'react'
import { Link, NavLink, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip as ChartTooltip, XAxis, YAxis } from 'recharts'
import { api, USE_MOCK } from './api'

const typeLabel = (type) => type ? type[0].toUpperCase() + type.slice(1) : 'Other'
const signed = (number, suffix = '%') => number == null ? '—' : `${number > 0 ? '+' : number < 0 ? '−' : ''}${Math.abs(number).toFixed(1)}${suffix}`
const load = (callback, setValue, setError) => callback().then(setValue).catch((error) => setError?.(error.message))

function Tip({ label, children }) { return <span className="term" title={children}> {label}<span aria-hidden="true">ⓘ</span></span> }
function Footer() { return <footer>Information about past price moves, not investment advice.</footer> }
function Shell({ children }) { return <><header><Link className="brand" to="/">Market Incident Tracker</Link><nav><NavLink to="/">Alerts</NavLink><NavLink to="/events">All events</NavLink><NavLink to="/tracked">Tracked</NavLink></nav>{USE_MOCK && <span className="mock">Demo data</span>}</header><main>{children}</main><Footer /></> }

function Watchlist() {
  const [tickers, setTickers] = useState([]); const [input, setInput] = useState(''); const [error, setError] = useState('')
  const refresh = useCallback(() => load(api.watchlist, (data) => setTickers(data.tickers), setError), [])
  useEffect(() => { refresh() }, [refresh])
  const add = async (event) => { event.preventDefault(); if (!input.trim()) return; try { const data = await api.addWatchlist(input); setTickers(data.tickers); setInput('') } catch (e) { setError(e.message) } }
  return <section className="watchlist"><div><h2>Your watchlist</h2><p>We’ll highlight events that may affect these stocks.</p></div><form onSubmit={add}><input value={input} onChange={(e) => setInput(e.target.value.toUpperCase())} placeholder="Add ticker, e.g. AAPL" aria-label="Ticker symbol" /><button>Add</button></form><div className="chips">{tickers.length ? tickers.map((ticker) => <span className="chip" key={ticker}>{ticker}<button onClick={() => api.removeWatchlist(ticker).then((data) => setTickers(data.tickers))} aria-label={`Remove ${ticker}`}>×</button></span>) : <span className="muted">No stocks added yet.</span>}</div>{error && <p className="error">{error}</p>}</section>
}

function EventCard({ event, alert = false }) { const navigate = useNavigate(); const [tracking, setTracking] = useState(false); const [tracked, setTracked] = useState(false); const ticker = alert ? event.matched?.[0]?.ticker || event.top_impact?.ticker : event.top_impact?.ticker; const track = async (click) => { click.stopPropagation(); if (!ticker) return; setTracking(true); try { await api.addTracked(event.event_id, ticker); setTracked(true) } finally { setTracking(false) } }; return <article className="event-card" role="link" tabIndex={0} onClick={() => navigate(`/events/${event.event_id}`)} onKeyDown={(key) => { if (key.key === 'Enter') navigate(`/events/${event.event_id}`) }}><div className="event-heading"><span className={`pill ${event.event_type}`}>{typeLabel(event.event_type)}</span>{event.status === 'early' && <span className="early">Early, still tracking</span>}<time>{event.event_date}</time></div><h3>{event.headline}</h3>{alert && <div className="matches">{event.matched.map((item) => <span key={item.ticker}>{item.ticker} · {item.relation === 'direct' ? 'direct impact' : `${item.relation} impact`} · <strong className={item.car_pct < 0 ? 'down' : 'up'}>{signed(item.car_pct)}</strong>{item.is_significant && ' · significant'}</span>)}</div>}<p className="impact-line">Largest measured impact: <strong className={event.top_impact?.car_pct < 0 ? 'down' : 'up'}>{event.top_impact ? `${event.top_impact.ticker} ${signed(event.top_impact.car_pct)}` : 'Not available'}</strong></p>{ticker && <button className="quick-track" onClick={track} disabled={tracking || tracked}>{tracked ? `Tracking ${ticker}` : tracking ? 'Tracking…' : `Track ${ticker}`}</button>}</article> }

function Alerts() { const [alerts, setAlerts] = useState(null); const [error, setError] = useState(''); const refresh = useCallback(() => load(api.alerts, setAlerts, setError), []); useEffect(() => { refresh() }, [refresh]); return <Shell><div className="hero"><p className="eyebrow">YOUR ALERTS</p><h1>News that may move the stocks you follow</h1><p>Start here: the cards below show only events connected to your watchlist.</p></div><Watchlist /><section><div className="section-title"><div><h2>Relevant events</h2><p>Click an event to see what happened and how the price moved.</p></div><button className="secondary" onClick={refresh}>Refresh</button></div>{error && <p className="error">{error}</p>}{alerts === null ? <Loading /> : alerts.length ? <div className="card-list">{alerts.map((event) => <EventCard event={event} alert key={event.event_id} />)}</div> : <Empty text="No current alerts. Add a ticker to your watchlist or check all events." />}</section><GraphPlaceholder /></Shell> }

<<<<<<< Updated upstream
function Pipeline({ onComplete }) { const [state, setState] = useState(null); const [error, setError] = useState('')
  const fallback = (runId) => { const timer = setInterval(async () => { try { const status = await api.pipelineStatus(runId); setState({ ...status, live: false }); if (status.state !== 'running') { clearInterval(timer); if (status.state === 'done') onComplete() } } catch (e) { clearInterval(timer); setError(e.message) } }, 2000) }
  const run = async () => { setError(''); try { const { run_id } = await api.runPipeline({ event_types: [], days_back: 3 }); setState({ state: 'running', completed: 0, total: 0, last_message: 'Starting scan…', live: true }); try { const source = new EventSource(`/api/pipeline/stream/${run_id}`); source.addEventListener('progress', (event) => { const data = JSON.parse(event.data); setState((old) => ({ ...old, ...data, state: 'running', live: true })) }); source.addEventListener('info', (event) => { const data = JSON.parse(event.data); setState((old) => ({ ...old, last_message: data.message, state: 'running', live: true })) }); source.addEventListener('result', (event) => { const data = JSON.parse(event.data); source.close(); setState((old) => ({ ...old, state: data.success ? 'done' : 'error', last_message: data.success ? 'Scan complete.' : 'Scan failed.' })); if (data.success) onComplete() }); source.addEventListener('error', () => { source.close(); fallback(run_id) }) } catch { fallback(run_id) } } catch (e) { setError(e.message) } }
=======
function Pipeline({ onComplete }) {
  const [state, setState] = useState(null)
  const [error, setError] = useState('')
  const active = useRef(null)
  useEffect(() => () => {
    active.current?.stop()
    active.current = null
  }, [])

  const run = async () => {
    if (active.current) return
    let source
    let timer
    const session = { stop: () => { source?.close(); clearTimeout(timer) } }
    active.current = session
    const isActive = () => active.current === session
    const finish = (message, failed = false) => {
      if (!isActive()) return
      session.stop()
      active.current = null
      setState((previous) => ({ ...previous, state: failed ? 'error' : 'done', last_message: message }))
      if (failed) setError(message)
      else onComplete()
    }

    setError('')
    setState({ state: 'running', completed: 0, total: 0, last_message: 'Starting scan…' })
    try {
      const { run_id } = await api.runPipeline({})
      if (!isActive()) return
      const poll = async () => {
        try {
          const status = await api.pipelineStatus(run_id)
          if (!isActive()) return
          setState(status)
          if (status.state === 'running') timer = setTimeout(poll, 1500)
          else if (status.state === 'done') finish(status.exit_reason || 'Scan complete.')
          else finish(status.error_message || 'Scan failed.', true)
        } catch (error) {
          finish(error.message, true)
        }
      }
      if (USE_MOCK || typeof EventSource === 'undefined') {
        timer = setTimeout(poll, 1000)
        return
      }
      try {
        source = new EventSource(`/api/pipeline/stream/${run_id}`)
      } catch {
        void poll()
        return
      }
      source.addEventListener('progress', (event) => {
        const progress = JSON.parse(event.data)
        if (isActive()) setState((previous) => ({ ...previous, ...progress }))
      })
      source.addEventListener('info', (event) => {
        const { message } = JSON.parse(event.data)
        if (isActive()) setState((previous) => ({ ...previous, last_message: message }))
      })
      source.addEventListener('done', (event) => {
        const { exit_reason } = JSON.parse(event.data)
        finish(exit_reason || 'Scan complete.')
      })
      source.addEventListener('error', (event) => {
        if (!isActive()) return
        source.close()
        if (event.data) finish(JSON.parse(event.data).message, true)
        else void poll()
      })
    } catch (error) {
      finish(error.message, true)
    }
  }
>>>>>>> Stashed changes
  const pct = state?.total ? Math.round((state.completed / state.total) * 100) : 0
  return <div className="pipeline"><button onClick={run} disabled={state?.state === 'running'}>{state?.state === 'running' ? 'Scanning…' : 'Scan latest news'}</button>{state && <div className="progress-wrap"><div className="progress"><span style={{ width: `${pct}%` }} /></div><p>{state.last_message} {state.total ? `(${state.completed}/${state.total})` : ''}</p></div>}{error && <p className="error">{error}</p>}</div> }

function Events() { const [events, setEvents] = useState(null); const [error, setError] = useState(''); const refresh = useCallback(() => load(api.events, setEvents, setError), []); useEffect(() => { refresh() }, [refresh]); return <Shell><div className="section-title"><div><p className="eyebrow">EVENT DATABASE</p><h1>All market events</h1><p>Scan for fresh events or explore the analysis already available.</p></div><Pipeline onComplete={refresh} /></div>{error && <p className="error">{error}</p>}{events === null ? <Loading /> : events.length ? <div className="card-list">{events.map((event) => <EventCard event={event} key={event.event_id} />)}</div> : <Empty text="No events found yet. Run a news scan to get started." />}</Shell> }

function Detail() { const { event_id } = useParams(); const navigate = useNavigate(); const [detail, setDetail] = useState(null); const [selected, setSelected] = useState(0); const [error, setError] = useState(''); const [refreshing, setRefreshing] = useState(false); const [tracked, setTracked] = useState(false)
  const get = useCallback(() => load(() => api.event(event_id), setDetail, setError), [event_id]); useEffect(() => { get() }, [get]);
  if (error) return <Shell><p className="error">{error}</p><button onClick={() => navigate('/events')}>Back to events</button></Shell>; if (!detail) return <Shell><Loading /></Shell>
  const impacts = [...detail.impacts].sort((a, b) => (a.relation === 'direct' ? -1 : b.relation === 'direct' ? 1 : 0)); const impact = impacts[selected] || impacts[0]; const { study } = impact; const verdictClass = study.is_significant ? (study.car_pct < 0 ? 'verdict down-bg' : 'verdict up-bg') : 'verdict neutral-bg'
  const refresh = async () => { setRefreshing(true); try { setDetail(await api.refreshEvent(event_id)) } catch (e) { setError(e.message) } finally { setRefreshing(false) } }
  const track = async () => { try { await api.addTracked(event_id, impact.ticker); setTracked(true) } catch (e) { setError(e.message) } }
  return <Shell><button className="back" onClick={() => navigate(-1)}>← Back</button><article className="detail"><p className="eyebrow">{typeLabel(detail.event.event_type)} · {detail.event.event_date}</p><h1>{detail.event.headline}</h1><p className="summary">{detail.event.summary}</p><a className="source" href={detail.event.source_url} target="_blank" rel="noreferrer">Read original source ↗</a><div className="actions"><button onClick={track} disabled={tracked}>{tracked ? 'Tracking' : `Track ${impact.ticker}`}</button><button className="secondary" onClick={refresh} disabled={refreshing}>{refreshing ? <><span className="spinner" /> Refreshing</> : 'Refresh analysis'}</button></div><section className="company-tabs"><h2>Who was affected?</h2><div>{impacts.map((item, index) => <button className={index === selected ? 'active' : ''} onClick={() => setSelected(index)} key={item.ticker}><strong>{item.ticker}</strong><span>{item.company_name}</span><em>{item.relation}</em></button>)}</div><p>{impact.reason}</p></section><section className={verdictClass}><p className="eyebrow">THE BOTTOM LINE · {impact.ticker}</p><h2>{study.verdict_text}</h2></section><section className="prediction"><div><p className="eyebrow">PREDICTION VS ACTUAL</p><h2><span className={impact.expected_direction === 'down' ? 'down' : 'up'}>{impact.expected_direction === 'down' ? '↓' : impact.expected_direction === 'up' ? '↑' : '—'}</span> AI expected this stock to move {impact.expected_direction === 'unclear' ? 'unclearly' : impact.expected_direction}.</h2></div><div className={`prediction-result ${impact.prediction_match === true ? 'match' : impact.prediction_match === false ? 'miss' : ''}`}>{impact.prediction_match === true ? '✓ Prediction matched' : impact.prediction_match === false ? '✕ Prediction missed' : '— Not enough data'}</div></section><section className="chart-section"><div className="section-title"><div><h2>Price move around the event</h2><p>Actual stock performance compared with the market-based expectation.</p></div></div><div className="chart"><ResponsiveContainer width="100%" height={340}><LineChart data={study.daily} margin={{ top: 10, right: 16, left: -15, bottom: 0 }}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="day" label={{ value: 'Trading days relative to event', position: 'insideBottom', offset: -4 }} /><YAxis tickFormatter={(value) => `${value}%`} /><ChartTooltip formatter={(value) => value == null ? '—' : signed(value)} labelFormatter={(label) => `Day ${label}`} /><Legend /><ReferenceLine x={0} stroke="#253858" strokeDasharray="4 4" label="event" /><Line type="monotone" dataKey="cum_actual_pct" name="Actual stock move" stroke="#246bce" strokeWidth={3} dot={false} /><Line type="monotone" dataKey="cum_expected_pct" name="Expected from market" stroke="#6b7280" strokeDasharray="7 5" dot={false} /><Line type="monotone" dataKey="car_pct" name="Event impact (CAR)" stroke="#dc5b39" strokeWidth={2.5} dot={false} connectNulls={false} /></LineChart></ResponsiveContainer></div></section><Metrics study={study} /></article></Shell> }

function Metrics({ study }) { const items = [['Stock move', study.raw_return_pct, ''], ['Market move', study.market_return_pct, ''], ['Beta', study.beta, 'How strongly this stock usually follows the market.'], ['Expected', study.expected_return_pct, ''], ['Event impact (CAR)', study.car_pct, 'How much the stock moved because of this news, after removing the overall market’s move.'], ['t-stat', study.t_stat, 'Whether the move is bigger than this stock’s normal day-to-day noise.']]; return <section className="metrics"><h2>Key numbers</h2><div>{items.map(([label, value, help]) => <article key={label}><p>{help ? <Tip label={label}>{help}</Tip> : label}</p><strong className={typeof value === 'number' && value < 0 ? 'down' : typeof value === 'number' && value > 0 ? 'up' : ''}>{label === 'Beta' || label === 't-stat' ? value?.toFixed(1) : signed(value)}</strong>{label === 'Event impact (CAR)' && <small>{study.is_significant ? 'Significant' : 'Not significant'}</small>}</article>)}</div></section> }

function Tracked() { const [items, setItems] = useState(null); const [error, setError] = useState(''); useEffect(() => { void load(api.tracked, setItems, setError) }, []); return <Shell><p className="eyebrow">SAVED FOR FOLLOW-UP</p><h1>Tracked events</h1><p className="page-intro">Keep an eye on event-stock pairs you want to revisit.</p>{error && <p className="error">{error}</p>}{items === null ? <Loading /> : items.length ? <div className="card-list">{items.map((item) => <Link className="event-card" to={`/events/${item.event_id}`} key={`${item.event_id}-${item.ticker}`}><h3>{item.ticker}</h3><p>{item.event_id}</p><time>Tracked {new Date(item.tracked_at).toLocaleDateString()}</time></Link>)}</div> : <Empty text="Nothing is being tracked yet. Choose Track on an event detail page." />}</Shell> }
function GraphPlaceholder() { return <section className="graph-placeholder" aria-label="Graph placeholder"><div><p className="eyebrow">COMING NEXT</p><h2>Market impact overview</h2><p>This space is reserved for a portfolio-level graph.</p></div><span aria-hidden="true">Graph placeholder</span></section> }
function Loading() { return <div className="loading">Loading…</div> } function Empty({ text }) { return <div className="empty">{text}</div> }
export default function App() { return <Routes><Route path="/" element={<Alerts />} /><Route path="/events" element={<Events />} /><Route path="/events/:event_id" element={<Detail />} /><Route path="/tracked" element={<Tracked />} /><Route path="*" element={<Alerts />} /></Routes> }
