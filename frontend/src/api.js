const API = "http://127.0.0.1:8000/api"

export async function syncDeveloper(username) {
  const res = await fetch(`${API}/developer/${encodeURIComponent(username)}/sync/`, { method: "POST" })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || "Sync failed")
  return data
}

export async function getDashboard(username, days) {
  const res = await fetch(`${API}/developer/${encodeURIComponent(username)}/dashboard/?days=${days}`)
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || "Dashboard request failed")
  return data
}

export async function getTimeline(username, days) {
  const res = await fetch(`${API}/developer/${encodeURIComponent(username)}/timeline/?days=${days}`)
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || "Timeline request failed")
  return data
}

export async function getLanguages(username) {
  const res = await fetch(`${API}/developer/${encodeURIComponent(username)}/languages/`)
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || "Language request failed")
  return data
}
