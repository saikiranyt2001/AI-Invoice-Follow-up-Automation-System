import { StatusBadge } from "./ui";

export function RolePermissionsPanel({
  currentUser,
  displayRole,
  permissionsRoleTab,
  setPermissionsRoleTab,
  permissionCapabilities,
  permissionsByRole,
  rbacRoles,
}) {
  return (
    <section
      className="panel permissions-panel"
      aria-label="Role permissions matrix"
    >
      <div className="permissions-header">
        <h3>Role Permissions Matrix</h3>
        <span className="member-pill">
          Current Role: {displayRole(currentUser.role)}
        </span>
      </div>
      <p className="snapshot-footnote">
        Switch tabs to compare Admin, Accountant, and Viewer permissions.
        Enabled capabilities are marked with Allow and restricted capabilities
        are marked with Restricted.
      </p>
      <div
        className="permissions-tab-row"
        role="tablist"
        aria-label="Role permission tabs"
      >
        {rbacRoles.map((role) => (
          <button
            key={role}
            type="button"
            role="tab"
            aria-selected={permissionsRoleTab === role}
            className={permissionsRoleTab === role ? "active" : ""}
            onClick={() => setPermissionsRoleTab(role)}
          >
            {displayRole(role)}
          </button>
        ))}
      </div>
      <div className="permissions-grid" role="table" aria-label="Permissions">
        {permissionCapabilities.map((capability) => (
          <div className="permissions-row" role="row" key={capability}>
            <span className="permissions-capability" role="cell">
              {capability}
            </span>
            <StatusBadge
              label={
                permissionsByRole[permissionsRoleTab][capability]
                  ? "Allow"
                  : "Restricted"
              }
              variant={
                permissionsByRole[permissionsRoleTab][capability]
                  ? "ok"
                  : "danger"
              }
            />
          </div>
        ))}
      </div>
    </section>
  );
}
