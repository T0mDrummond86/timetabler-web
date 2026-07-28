/** Assign edit / read-only access to each user in a global workspace —
 *  group-wide, and overridden per individual session where needed. */
import { useCallback, useEffect, useState } from "react";
import { api, type AccessLevel, type GlobalAccessMatrix, type UserAccessRow } from "../api";

type Props = {
  globalSessionId: number;
};

const LEVEL_LABEL: Record<AccessLevel, string> = {
  edit: "Edit",
  read_only: "Read-only",
};

/** What the user ends up with on a session, mirroring the backend's order. */
function resolved(
  row: UserAccessRow,
  sessionId: number,
  createdById: number | null,
): { level: AccessLevel; source: string } {
  if (row.is_admin) return { level: "edit", source: "admin" };
  if (row.org_role === "owner") return { level: "edit", source: "org owner" };
  if (createdById != null && createdById === row.user_id)
    return { level: "edit", source: "creator" };
  const override = row.session_levels[String(sessionId)];
  if (override) return { level: override, source: "session" };
  if (row.global_level) return { level: row.global_level, source: "group" };
  return {
    level: row.org_role === "viewer" ? "read_only" : "edit",
    source: "org role",
  };
}

export function AccessLevelsPanel({ globalSessionId }: Props) {
  const [matrix, setMatrix] = useState<GlobalAccessMatrix | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setMatrix(await api.accessMatrix(globalSessionId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load access levels");
    } finally {
      setLoading(false);
    }
  }, [globalSessionId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(key: string, fn: () => Promise<unknown>) {
    setSaving(key);
    setError(null);
    try {
      await fn();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update access");
    } finally {
      setSaving(null);
    }
  }

  if (loading) return <p className="panel-empty">Loading access levels…</p>;
  if (!matrix) return <p className="panel-empty">{error ?? "No data"}</p>;

  const { can_manage: canManage, owner_user_id: ownerId, sessions, users } = matrix;
  const owner = users.find((u) => u.user_id === ownerId);
  // The owner and platform admins always edit; listing them as configurable
  // would imply their access can be reduced here, which it cannot.
  const rows = users.filter((u) => !u.is_admin && u.user_id !== ownerId);
  const members = rows.filter((u) => u.global_level);
  const outsiders = rows.filter((u) => !u.global_level);

  return (
    <section className="access-panel">
      {error && <div className="error-banner">{error}</div>}
      <p className="muted entity-hint">
        {canManage
          ? "Set each person's default for the whole workspace, then override it on individual sessions where needed. People can always edit sessions they created themselves, and read-only users can still run every export."
          : `This workspace is owned by ${owner ? owner.name || owner.username : "another user"}. Only the owner can invite people or change access levels — ask them if you need a change.`}
      </p>

      {!users.length && <p className="panel-empty">No users in this organisation.</p>}

      {owner && (
        <p className="muted entity-hint">
          Owner: <strong>{owner.name || owner.username}</strong> — created this workspace,
          and always keeps edit access to everything in it.
        </p>
      )}

      {!!members.length && (
        <div className="access-table-wrap">
          <table className="access-table">
            <thead>
              <tr>
                <th>User</th>
                <th title="Applies to every session in this workspace">Group default</th>
                {sessions.map((s) => (
                  <th key={s.id} title={s.name}>
                    {s.name}
                  </th>
                ))}
                {canManage && <th>Member</th>}
              </tr>
            </thead>
            <tbody>
              {members.map((u) => (
                <tr key={u.user_id}>
                  <td>
                    <span className="access-user">{u.name || u.username}</span>
                    <span className="access-username muted">{u.username}</span>
                  </td>
                  <td>
                    {u.global_level ? (
                      <select
                        className="field-select"
                        value={u.global_level}
                        disabled={!canManage || saving === `g-${u.user_id}`}
                        onChange={(e) =>
                          void run(`g-${u.user_id}`, () =>
                            api.setGroupAccessLevel(
                              globalSessionId,
                              u.user_id,
                              e.target.value as AccessLevel,
                            ),
                          )
                        }
                      >
                        <option value="edit">Edit</option>
                        <option value="read_only">Read-only</option>
                      </select>
                    ) : (
                      <span className="muted" title="This user has no access to this workspace">
                        No access
                      </span>
                    )}
                  </td>
                  {sessions.map((s) => {
                    const override = u.session_levels[String(s.id)];
                    const eff = resolved(u, s.id, s.created_by_id);
                    const locked = eff.source === "creator";
                    const key = `s-${s.id}-${u.user_id}`;
                    return (
                      <td key={s.id}>
                        {locked ? (
                          <span
                            className="access-pill access-pill--fixed"
                            title="They created this session, so they always keep edit access"
                          >
                            Owner
                          </span>
                        ) : (
                          <select
                            className="field-select"
                            value={override ?? ""}
                            disabled={!canManage || saving === key}
                            title={`Currently ${LEVEL_LABEL[eff.level]} (from ${eff.source})`}
                            onChange={(e) =>
                              void run(key, () =>
                                e.target.value === ""
                                  ? api.clearSessionAccessLevel(s.id, u.user_id)
                                  : api.setSessionAccessLevel(
                                      s.id,
                                      u.user_id,
                                      e.target.value as AccessLevel,
                                    ),
                              )
                            }
                          >
                            <option value="">
                              Default ({LEVEL_LABEL[eff.level]})
                            </option>
                            <option value="edit">Edit</option>
                            <option value="read_only">Read-only</option>
                          </select>
                        )}
                      </td>
                    );
                  })}
                  {canManage && (
                    <td>
                      <button
                        type="button"
                        className="btn-secondary btn-xs"
                        disabled={saving === `r-${u.user_id}`}
                        title="Remove this person from the workspace entirely"
                        onClick={() =>
                          void run(`r-${u.user_id}`, () =>
                            api.removeFromWorkspace(globalSessionId, u.user_id),
                          )
                        }
                      >
                        Remove
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {canManage && (
        <div className="access-invite">
          <span className="access-invite-label">Add people to this workspace</span>
          {outsiders.length ? (
            <div className="access-invite-list">
              {outsiders.map((u) => (
                <button
                  key={u.user_id}
                  type="button"
                  className="btn-secondary btn-xs"
                  disabled={saving === `i-${u.user_id}`}
                  title={`Give ${u.name || u.username} edit access to this workspace`}
                  onClick={() =>
                    void run(`i-${u.user_id}`, () =>
                      api.inviteToWorkspace(globalSessionId, u.user_id),
                    )
                  }
                >
                  + {u.name || u.username}
                </button>
              ))}
            </div>
          ) : (
            <p className="muted entity-hint">
              Everyone with an account in this organisation is already a member.
            </p>
          )}
        </div>
      )}

      {!sessions.length && (
        <p className="muted entity-hint">
          Link sessions to this workspace to set per-session access.
        </p>
      )}
    </section>
  );
}
