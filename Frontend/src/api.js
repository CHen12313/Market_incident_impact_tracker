import mockEvent from './mock/mock_event.json'

// Set to false during integration with Flask. All callers use the API contract below.
export const USE_MOCK = true

let mockWatchlist = ['NMBS']
let mockTracked = []
const mockRuns = new Map()
const wait = () => new Promise((resolve) => setTimeout(resolve, 180))
const summary = (detail = mockEvent) => ({
  event_id: detail.event.event_id,
  event_type: detail.event.event_type,
  headline: detail.event.headline,
  event_date: detail.event.event_date,
  status: detail.status,
  affected_count: detail.impacts.length,
  top_impact: { ticker: detail.impacts[0].ticker, car_pct: detail.impacts[0].study.car_pct, is_significant: detail.impacts[0].study.is_significant },
  touches_watchlist: detail.impacts.some((impact) => mockWatchlist.includes(impact.ticker)),
})

async function request(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...options.headers } })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.error || 'Request failed')
  return data
}

export const api = {
  events: () => USE_MOCK ? Promise.resolve([summary()]) : request('/api/events'),
  event: (id) => USE_MOCK ? (id === mockEvent.event.event_id ? Promise.resolve(mockEvent) : Promise.reject(new Error('Event not found'))) : request(`/api/events/${id}`),
  refreshEvent: (id) => USE_MOCK ? wait().then(() => mockEvent) : request(`/api/events/${id}/refresh`, { method: 'POST' }),
  watchlist: () => USE_MOCK ? Promise.resolve({ tickers: mockWatchlist }) : request('/api/watchlist'),
  addWatchlist: (ticker) => USE_MOCK ? wait().then(() => { mockWatchlist = [...new Set([...mockWatchlist, ticker.trim().toUpperCase()])]; return { tickers: mockWatchlist } }) : request('/api/watchlist', { method: 'POST', body: JSON.stringify({ ticker }) }),
  removeWatchlist: (ticker) => USE_MOCK ? wait().then(() => { mockWatchlist = mockWatchlist.filter((item) => item !== ticker); return { tickers: mockWatchlist } }) : request(`/api/watchlist/${ticker}`, { method: 'DELETE' }),
  alerts: () => USE_MOCK ? Promise.resolve([{
    ...summary(), matched: mockEvent.impacts.filter((impact) => mockWatchlist.includes(impact.ticker)).map((impact) => ({ ticker: impact.ticker, relation: impact.relation, car_pct: impact.study.car_pct, is_significant: impact.study.is_significant })),
  }].filter((item) => item.matched.length)) : request('/api/alerts'),
  tracked: () => USE_MOCK ? Promise.resolve(mockTracked) : request('/api/tracked'),
  addTracked: (event_id, ticker) => USE_MOCK ? wait().then(() => { if (!mockTracked.some((item) => item.event_id === event_id && item.ticker === ticker)) mockTracked = [...mockTracked, { event_id, ticker, tracked_at: new Date().toISOString() }]; return mockTracked }) : request('/api/tracked', { method: 'POST', body: JSON.stringify({ event_id, ticker }) }),
  runPipeline: (body) => USE_MOCK ? wait().then(() => { const run_id = `demo-${Date.now()}`; mockRuns.set(run_id, Date.now()); return { run_id } }) : request('/api/pipeline/run', { method: 'POST', body: JSON.stringify(body) }),
  pipelineStatus: (runId) => USE_MOCK ? Promise.resolve().then(() => { const elapsed = Date.now() - mockRuns.get(runId); const done = elapsed > 2400; return { state: done ? 'done' : 'running', completed: done ? 1 : 0, total: 1, last_message: done ? 'Scan complete.' : 'Checking recent news…' } }) : request(`/api/pipeline/status/${runId}`),
}
