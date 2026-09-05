import { useEffect, useState } from "react"
import { syncDeveloper, getDashboard, getTimeline, getLanguages } from "./api"
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, PieChart, Pie, Cell, BarChart, Bar
} from "recharts"

// A small, deliberately limited palette — max 5 top languages + 1 neutral
// "Other" — instead of cycling through many hues for many categories.
const LANG_COLORS = ["#17191c", "#5b8def", "#30a46c", "#f5a623", "#e5484d"]
const OTHER_COLOR = "#b6bcc7"

function colorFor(name, index) {
  return name === "Other" ? OTHER_COLOR : LANG_COLORS[index % LANG_COLORS.length]
}

// Default Recharts tooltips just show "Other: 15%" with no way to see
// what's actually inside that bucket. For "Other" specifically, this shows
// ONLY the grouped-language breakdown — not the aggregate number too —
// since the breakdown IS the useful information here.
function LanguageTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null
  const item = payload[0].payload

  if (item.name === "Other" && item.breakdown) {
    return (
      <div className="chart-tooltip">
        <div className="chart-tooltip-title">Other — grouped languages</div>
        <div className="chart-tooltip-breakdown">
          {item.breakdown.map(b => (
            <div key={b.language}>{b.language}: {b.count !== undefined ? b.count : `${b.percent}%`}</div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-title">{item.name}: {item.value}</div>
    </div>
  )
}

// The evolution chart uses <Tooltip shared={false}> so hovering a single
// stacked segment reports ONLY that segment, not every language in the
// stack. When the hovered segment is "Other", show just its breakdown —
// not the other top languages' values too.
function EvolutionTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null
  const entry = payload[0]
  const yearRow = entry.payload

  if (entry.dataKey === "Other" && yearRow.__otherBreakdown) {
    return (
      <div className="chart-tooltip">
        <div className="chart-tooltip-title">Other ({entry.value}%) — grouped languages</div>
        <div className="chart-tooltip-breakdown">
          {yearRow.__otherBreakdown.map(b => (
            <div key={b.language}>{b.language}: {b.percent}%</div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-title">{entry.dataKey}: {entry.value}%</div>
    </div>
  )
}

function SectionHeader({ title, subtitle }) {
  return (
    <div className="section-header">
      <h2>{title}</h2>
      {subtitle && <p>{subtitle}</p>}
    </div>
  )
}

function MetricCard({ label, value, change }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {change !== undefined && (
        <div className={change >= 0 ? "change positive" : "change negative"}>
          {change >= 0 ? "↑" : "↓"} {Math.abs(change)}% vs previous period
        </div>
      )}
    </div>
  )
}

function GrowthIndexCard({ growthIndex }) {
  const labels = {
    activity: "Activity",
    consistency: "Consistency",
    technical_growth: "Technical Growth",
    collaboration: "Collaboration",
    project_development: "Project Development",
  }
  return (
    <div className="card">
      <h3>Developer Growth Index</h3>
      <p>Equal-weighted composite across the five scores below</p>
      <div className="growth-overall">{growthIndex.overall}</div>
      {Object.entries(growthIndex.sub_scores).map(([key, value]) => (
        <div key={key} className="growth-row">
          <div className="growth-row-label">
            <span>{labels[key] || key}</span>
            <span className="muted">{value}/100</span>
          </div>
          <div className="growth-bar-track">
            <div className="growth-bar-fill" style={{ width: `${value}%` }} />
          </div>
        </div>
      ))}
    </div>
  )
}

function RecommendationsCard({ recommendations }) {
  return (
    <div className="card">
      <h3>Recommendations</h3>
      <p>What might help improve this profile</p>
      {recommendations.map((r, i) => (
        <div key={i} className={`rec rec-${r.severity}`}>
          <b>{r.title}</b>
          <p>{r.detail}</p>
        </div>
      ))}
    </div>
  )
}

function RepoGrowthChart({ repoGrowth }) {
  return (
    <div className="card">
      <h3>Repository growth</h3>
      <p>Cumulative repository count by creation date (all public, non-fork repos)</p>
      <div className="chart small">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={repoGrowth}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Line type="stepAfter" dataKey="cumulative_repos" stroke={LANG_COLORS[1]} strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

// Technical breadth: pie chart when categories are few (still readable),
// horizontal bar chart when there are more — thin pie slices for many
// categories are hard to compare, a sorted bar is not.
function TechnicalBreadthChart({ data }) {
  const total = data.reduce((a, b) => a + b.value, 0)
  if (total === 0) return <div className="muted">No language data available.</div>

  if (data.length <= 5) {
    return (
      <div className="pie">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={2}>
              {data.map((entry, i) => <Cell key={i} fill={colorFor(entry.name, i)} />)}
            </Pie>
            <Tooltip content={(props) => <LanguageTooltip {...props} />} />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </div>
    )
  }

  const sorted = [...data].sort((a, b) => b.value - a.value)
  return (
    <div className="chart small">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={sorted} layout="vertical" margin={{ left: 24 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis type="number" allowDecimals={false} />
          <YAxis type="category" dataKey="name" tick={{ fontSize: 12 }} width={90} />
          <Tooltip content={(props) => <LanguageTooltip {...props} />} />
          <Bar dataKey="value" fill={LANG_COLORS[1]} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function reshapeEvolutionByYear(evolution) {
  const years = {}
  const languages = new Set()
  for (const row of evolution) {
    years[row.year] = years[row.year] || { year: row.year }
    years[row.year][row.language] = row.percent
    languages.add(row.language)
    if (row.language === "Other" && row.breakdown) {
      years[row.year].__otherBreakdown = row.breakdown
    }
  }
  // "Other" always plotted last so it reads as the residual, not a main category.
  const ordered = Array.from(languages).filter(l => l !== "Other")
  if (languages.has("Other")) ordered.push("Other")
  return { data: Object.values(years).sort((a, b) => a.year - b.year), languages: ordered }
}

function LanguageEvolutionChart({ languageEvolution }) {
  if (!languageEvolution || languageEvolution.length === 0) return null
  const { data, languages } = reshapeEvolutionByYear(languageEvolution)
  const hasOther = languages.includes("Other")
  return (
    <div className="card wide">
      <h3>Language evolution</h3>
      <p>Top 5 languages by code volume, grouped by repository creation year — everything else folded into "Other". Approximation: GitHub doesn't expose per-commit language history cheaply.</p>
      {hasOther && (
        <div className="hover-hint">
          <span className="hover-hint-swatch" style={{ background: OTHER_COLOR }} />
          Hover the grey "Other" segment on any bar to see which languages it contains
        </div>
      )}
      <div className="chart small">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="year" tick={{ fontSize: 11 }} />
            <YAxis unit="%" />
            <Tooltip content={(props) => <EvolutionTooltip {...props} />} shared={false} />
            <Legend />
            {languages.map((lang, i) => (
              <Bar key={lang} dataKey={lang} stackId="a" fill={colorFor(lang, i)} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function RepoHealthCard({ summary }) {
  if (!summary) return null
  const { counts, most_active, most_stale } = summary
  const total = counts.active + counts.maintenance + counts.inactive || 1
  const segments = [
    { key: "active", label: "Active (≤30d)", color: "#30a46c" },
    { key: "maintenance", label: "Maintenance (≤6mo)", color: "#f5a623" },
    { key: "inactive", label: "Inactive (6mo+)", color: "#b6bcc7" },
  ]
  return (
    <div className="card">
      <h3>Repository health</h3>
      <p>By time since last push</p>
      <div className="health-bar">
        {segments.map(s => (
          counts[s.key] > 0 && (
            <div key={s.key} style={{ width: `${(counts[s.key] / total) * 100}%`, background: s.color }} />
          )
        ))}
      </div>
      <div className="health-legend">
        {segments.map(s => (
          <div key={s.key}><span style={{ background: s.color }} />{s.label}: {counts[s.key]}</div>
        ))}
      </div>
      {most_stale.length > 0 && (
        <div className="health-list">
          <div className="muted">Most stale:</div>
          {most_stale.map(r => <div key={r.name}>{r.name} — {r.days_since_push}d ago</div>)}
        </div>
      )}
    </div>
  )
}

export default function App() {
  const [username, setUsername] = useState("")
  const [activeUser, setActiveUser] = useState("")
  const [days, setDays] = useState(180)
  const [dashboard, setDashboard] = useState(null)
  const [timeline, setTimeline] = useState([])
  const [languages, setLanguages] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  async function load(user = activeUser) {
    if (!user) return
    setLoading(true)
    setError("")
    try {
      const [d, t, l] = await Promise.all([
        getDashboard(user, days),
        getTimeline(user, days),
        getLanguages(user),
      ])
      setDashboard(d)
      setTimeline(t)
      setLanguages(l)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleSync(e) {
    e.preventDefault()
    const user = username.trim()
    if (!user) return
    setLoading(true)
    setError("")
    try {
      await syncDeveloper(user)
      setActiveUser(user)
      await load(user)
    } catch (e) {
      setError(e.message)
      setLoading(false)
    }
  }

  useEffect(() => {
    if (activeUser) load()
  }, [days])

  const profile = dashboard?.developer
  const m = dashboard?.metrics
  const c = dashboard?.changes || {}

  // Use the backend's Top-5-grouped breakdown so this chart matches the
  // language evolution chart's categories exactly.
  const languageData = (dashboard?.language_breakdown_count || []).map(x => ({ name: x.language, value: x.count, breakdown: x.breakdown }))

  return (
    <div className="app">
      <header>
        <div>
          <div className="eyebrow">GITHUB ANALYTICS</div>
          <h1>Developer Growth</h1>
          <p>Understand how your development activity changes over time.</p>
        </div>
        <form onSubmit={handleSync} className="search">
          <input value={username} onChange={e => setUsername(e.target.value)} placeholder="GitHub username" />
          <button disabled={loading}>{loading ? "Loading..." : "Analyse"}</button>
        </form>
      </header>

      {error && <div className="error">{error}</div>}

      {!dashboard && !loading && (
        <section className="empty">
          <h2>Start with a GitHub username</h2>
          <p>Enter a GitHub username above and hit Analyse. The first sync imports public profile, repository, and activity history — a full year of overall activity, plus exact commit/PR/issue detail for roughly the last 90 days.</p>
        </section>
      )}

      {dashboard && (
        <>
          <section className="profile">
            <img src={profile.avatar_url} alt="" />
            <div>
              <h2>{profile.name || profile.username}</h2>
              <span>@{profile.username}</span>
              {profile.bio && <p>{profile.bio}</p>}
            </div>
            <div className="period">
              <span>ANALYSIS PERIOD</span>
              <select value={days} onChange={e => setDays(Number(e.target.value))}>
                <option value={30}>30 days</option>
                <option value={90}>90 days</option>
                <option value={180}>6 months</option>
                <option value={365}>1 year</option>
              </select>
            </div>
          </section>

          <SectionHeader title="Overview" subtitle="Headline numbers for the selected period" />
          <section className="metrics">
            <MetricCard label="Commits" value={m.commits} change={c.commits} />
            <MetricCard label="Pull requests" value={m.pull_requests} change={c.pull_requests} />
            <MetricCard label="Issues" value={m.issues} change={c.issues} />
            <MetricCard label="Consistency" value={`${dashboard.consistency.score}/100`} />
            <MetricCard label="Growth Index" value={dashboard.growth_index.overall} />
            <MetricCard label="Repositories" value={m.repositories} />
          </section>

          <SectionHeader title="Activity trend" subtitle="What happened, and how it compares to the period before" />
          <section className="grid single">
            <div className="card wide">
              <div className="card-head">
                <div>
                  <h3>Development activity</h3>
                  <p>Commits, pull requests, and issues over the selected period. Exact for roughly the last 90 days (from public events); estimated further back, proportional to yearly totals.</p>
                </div>
              </div>
              <div className="chart">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={timeline}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="commits" stroke={LANG_COLORS[1]} strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="pull_requests" stroke={LANG_COLORS[2]} strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="issues" stroke={LANG_COLORS[3]} strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </section>

          <section className="card">
            <h3>What changed?</h3>
            <p className="muted">Current period vs. the immediately preceding period of the same length — raw counts alongside the percentage, since percentages alone can overstate small changes (1→2 reads as "+100%") and understate large ones (50→48 reads as "-4%").</p>
            <div className="comparison">
              <div><b>Commits</b><span className="comparison-detail">{dashboard.previous.commits} → {m.commits}</span><strong>{c.commits >= 0 ? "+" : ""}{c.commits}%</strong></div>
              <div><b>Pull requests</b><span className="comparison-detail">{dashboard.previous.pull_requests} → {m.pull_requests}</span><strong>{c.pull_requests >= 0 ? "+" : ""}{c.pull_requests}%</strong></div>
              <div><b>Issues</b><span className="comparison-detail">{dashboard.previous.issues} → {m.issues}</span><strong>{c.issues >= 0 ? "+" : ""}{c.issues}%</strong></div>
              <div><b>Active days</b><span className="comparison-detail">{dashboard.previous.active_days} → {m.active_days}</span><strong>{c.active_days >= 0 ? "+" : ""}{c.active_days}%</strong></div>
            </div>
          </section>

          <SectionHeader title="Technical profile" subtitle="What languages this developer works in, and how that's shifted over time" />
          <section className="grid">
            <div className="card">
              <h3>Technical breadth</h3>
              <p>Repository count by primary language (top 5 + Other)</p>
              {languageData.some(d => d.name === "Other") && (
                <div className="hover-hint">
                  <span className="hover-hint-swatch" style={{ background: OTHER_COLOR }} />
                  Hover "Other" to see which languages it contains
                </div>
              )}
              <TechnicalBreadthChart data={languageData} />
            </div>
            <RepoGrowthChart repoGrowth={dashboard.repo_growth} />
          </section>

          <section className="grid single">
            <LanguageEvolutionChart languageEvolution={dashboard.language_evolution} />
          </section>

          <SectionHeader title="Repositories" subtitle="How maintained is this developer's public work" />
          <section className="grid single">
            <RepoHealthCard summary={dashboard.repo_health_summary} />
          </section>

          <SectionHeader title="Growth & recommendations" subtitle="A composite score, and what might help improve it" />
          <section className="grid">
            <GrowthIndexCard growthIndex={dashboard.growth_index} />
            <RecommendationsCard recommendations={dashboard.recommendations} />
          </section>
        </>
      )}
    </div>
  )
}
