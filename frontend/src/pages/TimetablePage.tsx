import { Link, useNavigate, useParams } from "react-router-dom";
import { useCallback, useEffect, useState } from "react";
import { api, Course, getToken, setToken, TimetableSession } from "../api";
import type { TimetableGrid } from "../types";
import { WeekGridView } from "../components/WeekGridView";

export function TimetablePage() {
  const { sessionId: sessionIdParam } = useParams();
  const sessionId = Number(sessionIdParam);
  const navigate = useNavigate();

  const [sessions, setSessions] = useState<TimetableSession[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [courseId, setCourseId] = useState<number | null>(null);
  const [grid, setGrid] = useState<TimetableGrid | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [seeding, setSeeding] = useState(false);

  const loadGrid = useCallback(async (sid: number, cid: number) => {
    const data = await api.timetable(sid, cid);
    setGrid(data);
  }, []);

  useEffect(() => {
    if (!getToken()) {
      navigate("/login");
      return;
    }
    if (!sessionId) {
      setError("Invalid session");
      setLoading(false);
      return;
    }
    (async () => {
      try {
        const orgs = await api.orgs();
        if (!orgs.length) throw new Error("No organization");
        const sess = await api.sessions(orgs[0].id);
        setSessions(sess);
        let courseList = await api.courses(sessionId);
        if (!courseList.length) {
          await api.seedDemo(sessionId);
          courseList = await api.courses(sessionId);
        }
        setCourses(courseList);
        const cid = courseList[0]?.id ?? null;
        setCourseId(cid);
        if (cid) await loadGrid(sessionId, cid);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load");
        if (String(err).includes("401")) {
          setToken(null);
          navigate("/login");
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [sessionId, navigate, loadGrid]);

  async function onCourseChange(cid: number) {
    setCourseId(cid);
    setLoading(true);
    try {
      await loadGrid(sessionId, cid);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }

  async function onSeedDemo() {
    setSeeding(true);
    setError(null);
    try {
      await api.seedDemo(sessionId);
      const courseList = await api.courses(sessionId);
      setCourses(courseList);
      const cid = courseList[0]?.id ?? null;
      setCourseId(cid);
      if (cid) await loadGrid(sessionId, cid);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Seed failed");
    } finally {
      setSeeding(false);
    }
  }

  const sessionName = sessions.find((s) => s.id === sessionId)?.name ?? `Session #${sessionId}`;

  return (
    <main className="page wide">
      <header className="header row">
        <div>
          <p className="breadcrumb">
            <Link to="/dashboard">Dashboard</Link> / {sessionName}
          </p>
          <h1>{grid?.course_code ?? "Timetable"}</h1>
          <p className="subtitle muted">{grid?.week_label ?? "Repeating week"} · read-only</p>
        </div>
        <div className="toolbar row gap">
          {courses.length > 1 && (
            <select
              value={courseId ?? ""}
              onChange={(e) => onCourseChange(Number(e.target.value))}
            >
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code}
                </option>
              ))}
            </select>
          )}
          <button type="button" className="secondary" onClick={onSeedDemo} disabled={seeding}>
            {seeding ? "Seeding…" : "Load demo data"}
          </button>
        </div>
      </header>

      {error && <p className="error">{error}</p>}
      {loading && !grid && <p className="muted">Loading timetable…</p>}
      {!loading && courses.length === 0 && (
        <section className="card">
          <p>No courses in this session yet.</p>
          <button type="button" onClick={onSeedDemo} disabled={seeding}>
            Load demo timetable
          </button>
        </section>
      )}
      {grid && (
        <>
          {grid.violations.length > 0 && (
            <section className="card violations-strip">
              <h2>Warnings</h2>
              <ul>
                {grid.violations.slice(0, 5).map((v, i) => (
                  <li key={i} className={v.severity}>
                    {v.message}
                  </li>
                ))}
              </ul>
            </section>
          )}
          <WeekGridView grid={grid} />
        </>
      )}
    </main>
  );
}
