import { Link, useParams, useSearchParams } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { TimetableSplitWorkspace } from "../split/TimetableSplitWorkspace";
import { parseSplitLayout } from "../split/splitLayout";

export function TimetableSplitPage() {
  const { sessionId: sessionIdParam } = useParams();
  const sessionId = Number(sessionIdParam);
  const [searchParams, setSearchParams] = useSearchParams();
  const layout = parseSplitLayout(searchParams.get("layout"));

  function setLayout(next: "2h" | "2v" | "4") {
    const params = new URLSearchParams(searchParams);
    params.set("layout", next);
    setSearchParams(params, { replace: true });
  }

  return (
    <AppShell
      wide
      title="Split screen"
      subtitle="Shared controls · click a pane to make it active"
      breadcrumb={
        <>
          <Link to="/dashboard">Dashboard</Link>
          <span aria-hidden> / </span>
          <Link to={`/timetable/${sessionId}`}>Session #{sessionId}</Link>
          <span aria-hidden> / </span>
          Split screen
        </>
      }
    >
      <div className="tt-toolbar split-toolbar">
        <div className="tt-toolbar-group">
          <span className="tt-toolbar-label">Layout</span>
          <button
            type="button"
            className={`btn-secondary btn-xs${layout === "2h" ? " active-tab" : ""}`}
            onClick={() => setLayout("2h")}
          >
            2-way side-by-side
          </button>
          <button
            type="button"
            className={`btn-secondary btn-xs${layout === "2v" ? " active-tab" : ""}`}
            onClick={() => setLayout("2v")}
          >
            2-way stacked
          </button>
          <button
            type="button"
            className={`btn-secondary btn-xs${layout === "4" ? " active-tab" : ""}`}
            onClick={() => setLayout("4")}
          >
            4-way
          </button>
        </div>
        <div className="tt-toolbar-group">
          <Link to={`/timetable/${sessionId}`} className="btn-secondary btn-xs">
            Back to single view
          </Link>
        </div>
      </div>

      <TimetableSplitWorkspace key={layout} sessionId={sessionId} layout={layout} />
    </AppShell>
  );
}
