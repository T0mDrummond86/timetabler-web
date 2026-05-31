import { useQuery } from "@tanstack/react-query";
import { Link, Route, Routes } from "react-router-dom";

const API_BASE = import.meta.env.VITE_API_URL ?? "";

async function fetchHealth() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json() as Promise<{
    status: string;
    database: string;
    grid: { days: number; slots: number };
  }>;
}

function HomePage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 10_000,
  });

  return (
    <main className="page">
      <header className="header">
        <h1>Timetabler</h1>
        <p className="subtitle">Web app — Phase 0 bootstrap</p>
      </header>

      <section className="card">
        <h2>API status</h2>
        {isLoading && <p>Checking backend…</p>}
        {error && (
          <p className="error">
            Cannot reach API at <code>{API_BASE || "(same origin /api proxy)"}</code>.
            Start Docker Compose or run uvicorn locally.
          </p>
        )}
        {data && (
          <ul>
            <li>
              Status: <strong>{data.status}</strong>
            </li>
            <li>
              Database: <strong>{data.database}</strong>
            </li>
            <li>
              Grid: {data.grid.days} days × {data.grid.slots} slots
            </li>
          </ul>
        )}
      </section>

      <section className="card muted">
        <h2>Next (Phase 1)</h2>
        <ul>
          <li>Auth — register / login, JWT</li>
          <li>Organizations and timetable sessions</li>
          <li>PostgreSQL tenancy on domain tables</li>
        </ul>
      </section>
    </main>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route
        path="/timetable"
        element={
          <main className="page">
            <p>
              <Link to="/">← Home</Link>
            </p>
            <h1>Timetable</h1>
            <p className="muted">Read-only grid arrives in Phase 2.</p>
          </main>
        }
      />
    </Routes>
  );
}
