import { EmptyState } from "./ui";

export function TeamSection({
  teamForm,
  setTeamForm,
  handleCreateTeamUser,
  inviteEmail,
  setInviteEmail,
  handleInviteExistingUser,
  teamUsers,
  teamVisibleUsers,
  teamFilterMode,
  setTeamFilterMode,
  teamSearchTerm,
  setTeamSearchTerm,
  teamSearchInputRef,
  teamSortMarker,
  handleTeamSort,
  teamSortKey,
  teamSortDir,
  TEAM_ROLES,
  TEAM_VIEW_PRESETS,
  applyTeamPreset,
  resetTeamView,
  currentUser,
  activeCompany,
  handleRemoveMember,
  audience,
}) {
  return (
    <section className="panel">
      <h3>Team Management</h3>
      <section className="grid-two">
        <article className="panel team-inner">
          <h3>Create Team User</h3>
          <form className="stack-form" onSubmit={handleCreateTeamUser}>
            <input
              placeholder="Username"
              value={teamForm.username}
              onChange={(e) =>
                setTeamForm((prev) => ({ ...prev, username: e.target.value }))
              }
              required
            />
            <input
              type="email"
              placeholder="Email"
              value={teamForm.email}
              onChange={(e) =>
                setTeamForm((prev) => ({ ...prev, email: e.target.value }))
              }
              required
            />
            <input
              type="password"
              placeholder="Temporary Password"
              value={teamForm.password}
              onChange={(e) =>
                setTeamForm((prev) => ({ ...prev, password: e.target.value }))
              }
              required
              minLength={8}
            />
            <select
              value={teamForm.role}
              onChange={(e) =>
                setTeamForm((prev) => ({ ...prev, role: e.target.value }))
              }
            >
              {TEAM_ROLES.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
            <button type="submit">Create User</button>
          </form>

          <div className="team-divider" />

          <h3>Invite Existing User</h3>
          <form className="stack-form" onSubmit={handleInviteExistingUser}>
            <input
              type="email"
              placeholder="Existing user email"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              required
            />
            <button type="submit" className="ghost">
              Invite to Active Company
            </button>
          </form>
        </article>

        <article className="panel team-inner">
          <h3>Users</h3>
          <div className="team-presets-wrap">
            <div className="team-presets-row">
              {TEAM_VIEW_PRESETS.map((preset) => {
                const isActive =
                  teamFilterMode === preset.filter &&
                  teamSortKey === preset.sortKey &&
                  teamSortDir === preset.sortDir &&
                  teamSearchTerm === preset.search;
                return (
                  <button
                    key={preset.key}
                    type="button"
                    className={`preset-chip ${isActive ? "active" : ""}`}
                    onClick={() => applyTeamPreset(preset)}
                  >
                    {preset.label}
                  </button>
                );
              })}
            </div>
            <button
              type="button"
              className="preset-reset-btn"
              onClick={resetTeamView}
            >
              Reset Team View
            </button>
          </div>
          <p className="team-shortcuts-hint">
            Shortcuts: / focus search, R reset, 1-4 apply presets
          </p>
          <div className="team-search-wrap">
            <input
              ref={teamSearchInputRef}
              type="text"
              placeholder="Search by username, email, or role"
              value={teamSearchTerm}
              onChange={(e) => setTeamSearchTerm(e.target.value)}
            />
          </div>
          <div className="team-filter-row">
            {[
              { key: "all", label: "All" },
              { key: "owners", label: "Owners" },
              { key: "members", label: "Members" },
              { key: "you", label: "You" },
            ].map((item) => (
              <button
                key={item.key}
                type="button"
                className={`filter-chip ${teamFilterMode === item.key ? "active" : ""}`}
                onClick={() => setTeamFilterMode(item.key)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="member-summary">
            <span className="member-pill">
              Company Members: {teamUsers.length}
            </span>
            {activeCompany && (
              <span className="member-pill subtle">
                Owner ID: {activeCompany.owner_user_id}
              </span>
            )}
            <span className="member-pill subtle">
              Visible: {teamVisibleUsers.length}
            </span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>
                    <button
                      type="button"
                      className="sort-header-btn"
                      onClick={() => handleTeamSort("username")}
                    >
                      Username {teamSortMarker("username")}
                    </button>
                  </th>
                  <th>Email</th>
                  <th>
                    <button
                      type="button"
                      className="sort-header-btn"
                      onClick={() => handleTeamSort("role")}
                    >
                      Role {teamSortMarker("role")}
                    </button>
                  </th>
                  <th>
                    <button
                      type="button"
                      className="sort-header-btn"
                      onClick={() => handleTeamSort("access")}
                    >
                      Company Access {teamSortMarker("access")}
                    </button>
                  </th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {teamVisibleUsers.length === 0 && (
                  <tr>
                    <td colSpan={6}>
                      <EmptyState
                        tone="team"
                        title={
                          teamUsers.length === 0
                            ? "No team members provisioned"
                            : "No search matches"
                        }
                        description={
                          teamUsers.length === 0
                            ? audience.empty.team
                            : "Try a different username, email, or role filter."
                        }
                      />
                    </td>
                  </tr>
                )}
                {teamVisibleUsers.map((user) => (
                  <tr key={user.id}>
                    <td>{user.id}</td>
                    <td>{user.username}</td>
                    <td>{user.email}</td>
                    <td>{user.role}</td>
                    <td>
                      <div className="member-tags">
                        {activeCompany?.owner_user_id === user.id ? (
                          <span className="member-tag owner">Owner</span>
                        ) : (
                          <span className="member-tag member">Member</span>
                        )}
                        {user.id === currentUser.id && (
                          <span className="member-tag you">You</span>
                        )}
                      </div>
                    </td>
                    <td>
                      {user.id !== currentUser.id &&
                        activeCompany?.owner_user_id !== user.id && (
                          <button
                            type="button"
                            className="ghost"
                            onClick={() =>
                              handleRemoveMember(user.id, user.username)
                            }
                          >
                            Remove
                          </button>
                        )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    </section>
  );
}
