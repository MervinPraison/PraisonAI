# PraisonAI Platform — Comprehensive UI Integration Report

> **Purpose**: This document provides everything a UI provider needs to build a frontend layer on top of the PraisonAI Platform backend. It covers every API endpoint, data model, UI component requirement, and analysis against similar tools in the space.

---

## Table of Contents

1. [Platform Overview](#1-platform-overview)
2. [Tech Stack & Architecture](#2-tech-stack--architecture)
3. [API Base & Conventions](#3-api-base--conventions)
4. [Feature 1: Authentication & User Management](#4-feature-1-authentication--user-management)
5. [Feature 2: Workspace & Multi-tenancy](#5-feature-2-workspace--multi-tenancy)
6. [Feature 3: RBAC / Member Management](#6-feature-3-rbac--member-management)
7. [Feature 4: Project Management](#7-feature-4-project-management)
8. [Feature 5: Issue Tracking & Workflow](#8-feature-5-issue-tracking--workflow)
9. [Feature 6: Agent Registry & Management](#9-feature-6-agent-registry--management)
10. [Feature 7: Labels & Tagging](#10-feature-7-labels--tagging)
11. [Feature 8: Issue Dependencies](#11-feature-8-issue-dependencies)
12. [Feature 9: Comments & Threading](#12-feature-9-comments--threading)
13. [Feature 10: Activity Logs & Audit Trail](#13-feature-10-activity-logs--audit-trail)
14. [Feature 11: Client SDK](#14-feature-11-client-sdk)
15. [Feature 12: Database & Schema](#15-feature-12-database--schema)
16. [Comparison Matrix](#16-comparison-matrix)
17. [Recommended UI Views & Components](#17-recommended-ui-views--components)
18. [WebSocket / Real-time Considerations](#18-websocket--real-time-considerations)
19. [Gaps & Recommendations for UI Layer](#19-gaps--recommendations-for-ui-layer)
20. [Appendix: Full API Endpoint Reference](#20-appendix-full-api-endpoint-reference)

---

## 1. Platform Overview

PraisonAI Platform is a **multi-tenant project management and issue tracking backend** designed for **human + AI agent teams**. It sits on top of the `praisonaiagents` Core SDK and provides:

- JWT-based authentication
- Workspace-scoped multi-tenancy
- Role-based access control (owner/admin/member)
- Project and issue management with full lifecycle
- AI agents as first-class participants (can create issues, comment, be assigned)
- Labels, dependencies, threaded comments, activity logs
- Async Python Client SDK for programmatic access

**Key differentiator**: Unlike pure human PM tools, this platform treats **agents as equal participants** — they have profiles, can be assignees, authors, and creators alongside human users.

---

## 2. Tech Stack & Architecture

| Layer | Technology |
|-------|-----------|
| **API Framework** | FastAPI (Python, async) |
| **ORM** | SQLAlchemy 2.0 (async) |
| **Database** | SQLite (default) / PostgreSQL (production) |
| **Auth** | PyJWT + passlib[bcrypt] |
| **Validation** | Pydantic v2 |
| **HTTP Client** | httpx (async) |
| **Migrations** | Alembic |
| **Python** | 3.10+ |

### Architecture Diagram

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│    UI Layer      │────>│  FastAPI Backend  │────>│   SQLAlchemy     │
│  (Any framework) │<────│  /api/v1/*        │<────│   async ORM      │
└──────────────────┘     └────────┬─────────┘     └────────┬─────────┘
                                  │                         │
                         ┌────────┴─────────┐     ┌────────┴─────────┐
                         │  Service Layer   │     │  SQLite / PG     │
                         │  (business logic)│     │  Database        │
                         └──────────────────┘     └──────────────────┘
```

### Key Files

| File | Purpose |
|------|---------|
| `__init__.py` | Package exports: `PlatformClient`, `create_app`, `__version__` |
| `__main__.py` | CLI entry point: `python -m praisonai_platform` (uvicorn server) |
| `api/app.py` | FastAPI app factory, router registration, health check |
| `api/deps.py` | Dependency injection (DB session, current user, RBAC enforcement) |
| `api/schemas.py` | All Pydantic request/response models |
| `api/routes/*.py` | Route handlers per domain |
| `services/*.py` | Business logic services |
| `services/workspace_context.py` | `PlatformWorkspaceContext` — provides workspace context & agent config to agents |
| `db/models.py` | SQLAlchemy ORM models |
| `db/base.py` | Engine, session factory, table init |
| `client/platform_client.py` | Async HTTP client SDK with connection pooling |
| `exceptions.py` | Custom exceptions: `NotFoundError`, `DuplicateError`, `AuthenticationError`, `AuthorizationError`, `ValidationError` |

---

## 3. API Base & Conventions

| Convention | Value |
|-----------|-------|
| **Base URL** | `/api/v1` |
| **Auth** | `Authorization: Bearer <JWT>` header |
| **Content-Type** | `application/json` |
| **ID format** | UUIDv4 strings (36 chars) |
| **Timestamps** | ISO 8601 with timezone (UTC) |
| **Pagination** | `?limit=50&offset=0` (default 50, max 200) |
| **Error format** | `{"detail": "message"}` with appropriate HTTP status |
| **Health check** | `GET /api/v1/health` → `{"status": "ok"}` |

### Authentication Flow

```
1. POST /api/v1/auth/register  → {token, user}
2. POST /api/v1/auth/login     → {token, user}
3. All subsequent requests:  Authorization: Bearer <token>
4. GET /api/v1/auth/me         → current user info
```

---

## 4. Feature 1: Authentication & User Management

### API Endpoints

| Method | Path | Request Body | Response | Description |
|--------|------|-------------|----------|-------------|
| `POST` | `/auth/register` | `{email, password, name?}` | `{token, user}` | Register new user |
| `POST` | `/auth/login` | `{email, password}` | `{token, user}` | Login, get JWT |
| `GET` | `/auth/me` | — | `UserResponse` | Get current user profile |

### Data Models

**UserResponse**:
```json
{
  "id": "uuid",
  "name": "string",
  "email": "string",
  "avatar_url": "string | null",
  "created_at": "datetime"
}
```

### UI Components Needed

| Component | Description |
|-----------|-------------|
| **Login Page** | Email + password form, submit → `POST /auth/login` |
| **Register Page** | Email + password + optional name, submit → `POST /auth/register` |
| **Auth Context/Provider** | Store JWT in localStorage/cookie, attach to all API calls |
| **User Avatar** | Display `avatar_url` or fallback to initials |
| **Profile Dropdown** | Show current user name/email from `GET /auth/me` |

### Industry Comparison

| Aspect | PraisonAI | Tool A | Tool B |
|--------|-----------|---------|-----------|
| **Auth method** | JWT (email+password) | Email code + Google OAuth | better-auth sessions, trusted loopback mode |
| **Token storage** | Client-managed JWT | Session-based | Session-based |
| **Social login** | ❌ Not yet | ✅ Google OAuth | ❌ |
| **Email verification** | ❌ Not yet | ✅ Email codes | ❌ |
| **Agent auth** | ✅ AuthIdentity(type="agent") | ✅ Agent tokens via daemon | ✅ Heartbeat-based |

### Gaps & Recommendations

1. **Add OAuth support** — Tool A offers Google OAuth; consider adding OAuth2 provider support
2. **Add email verification** — Tool A uses email codes for verification
3. **Add password reset flow** — Neither endpoint exists yet
4. **Consider session-based auth option** — Tool B uses session-based auth for simpler UX
5. **Fail-fast JWT secret** — Already implemented: production rejects default `"dev-secret-change-me"`

---

## 5. Feature 2: Workspace & Multi-tenancy

### API Endpoints

| Method | Path | Request Body | Response | Description |
|--------|------|-------------|----------|-------------|
| `POST` | `/workspaces/` | `{name, slug?, description?}` | `WorkspaceResponse` | Create workspace |
| `GET` | `/workspaces/` | `?limit=50&offset=0` | `[WorkspaceResponse]` | List user's workspaces |
| `GET` | `/workspaces/{id}` | — | `WorkspaceResponse` | Get workspace detail |
| `PATCH` | `/workspaces/{id}` | `{name?, description?, settings?}` | `WorkspaceResponse` | Update workspace |
| `DELETE` | `/workspaces/{id}` | — | `204` | Delete workspace |

### Data Models

**WorkspaceResponse**:
```json
{
  "id": "uuid",
  "name": "string",
  "slug": "string (unique)",
  "description": "string | null",
  "settings": {},
  "created_at": "datetime"
}
```

**Internal fields** (not exposed in API but present in DB):
- `issue_prefix` (default: `"ISS"`) — prefix for human-readable issue IDs
- `issue_counter` — auto-incrementing counter for issue numbering

### UI Components Needed

| Component | Description |
|-----------|-------------|
| **Workspace Switcher** | Dropdown/sidebar to switch between workspaces |
| **Workspace Settings Page** | Edit name, description, settings JSON, slug |
| **Create Workspace Modal** | Name + optional slug (auto-generated from name) |
| **Workspace Sidebar** | Navigation showing projects, issues, agents, settings |

### Industry Comparison

| Aspect | PraisonAI | Tool A | Tool B |
|--------|-----------|---------|-----------|
| **Multi-tenancy** | ✅ Workspace-scoped | ✅ Multi-workspace | ✅ Multi-company |
| **Isolation** | Workspace-level DB scoping | Workspace-level | Complete company-level |
| **Slug** | ✅ Unique slug per workspace | ✅ Slug-based routing | N/A (company name) |
| **Settings** | ✅ JSON settings blob | ✅ Per-workspace settings | ✅ Per-company config |
| **Auto-create on signup** | ❌ Must create manually | ✅ Auto-created | ✅ Via onboard CLI |

### Gaps & Recommendations

1. **Auto-create workspace on first login** — Tool A does this automatically
2. **Workspace invitation flow** — Need invite-by-email endpoint
3. **Workspace branding** — Consider adding logo/icon field

---

## 6. Feature 3: RBAC / Member Management

### API Endpoints

| Method | Path | Request Body | Response | Description |
|--------|------|-------------|----------|-------------|
| `POST` | `/workspaces/{ws_id}/members/` | `{user_id, role?}` | `MemberResponse` | Add member |
| `GET` | `/workspaces/{ws_id}/members/` | — | `[MemberResponse]` | List members |
| `PATCH` | `/workspaces/{ws_id}/members/{id}` | `{role}` | `MemberResponse` | Update role |
| `DELETE` | `/workspaces/{ws_id}/members/{id}` | — | `204` | Remove member |

### Role Hierarchy

```
owner > admin > member
```

| Role | Permissions |
|------|------------|
| **owner** | Full control, can delete workspace, manage all members |
| **admin** | Manage members (except owner), manage all resources |
| **member** | Create/edit issues, comments, view projects |

### Data Models

**MemberResponse**:
```json
{
  "id": "uuid",
  "workspace_id": "uuid",
  "user_id": "uuid",
  "role": "owner | admin | member",
  "created_at": "datetime"
}
```

### UI Components Needed

| Component | Description |
|-----------|-------------|
| **Members Page** | Table of workspace members with role badges |
| **Invite Member Modal** | Search/add user by ID, assign role |
| **Role Selector** | Dropdown: owner/admin/member |
| **Remove Member Confirm** | Confirmation dialog before removal |
| **Member Avatars** | Show in issue assignees, comments, activity |

### Industry Comparison

| Aspect | PraisonAI | Tool A | Tool B |
|--------|-----------|---------|-----------|
| **Roles** | owner/admin/member | owner/admin/member | Hierarchical org chart |
| **Principal types** | User only (agent via separate model) | User + Agent members | User + Agent (same entity) |
| **Invite flow** | By user_id | By email invitation | CLI onboard |
| **RBAC enforcement** | ✅ Route-level via `require_workspace_member` dependency | Middleware + service | Governance layer |

### Gaps & Recommendations

1. **Add invite-by-email** — Current flow requires knowing user_id
2. ~~**Add permission checking middleware**~~ — ✅ **Resolved**: All workspace-scoped routes now enforce membership via `require_workspace_member` dependency in `api/deps.py`. Non-members receive `403 Forbidden` (no information leakage about resource existence).
3. **Consider Tool B's org chart model** — Hierarchical reporting lines for agents

---

## 7. Feature 4: Project Management

### API Endpoints

| Method | Path | Request Body | Response | Description |
|--------|------|-------------|----------|-------------|
| `POST` | `/workspaces/{ws_id}/projects/` | `{title, description?, icon?, lead_type?, lead_id?}` | `ProjectResponse` | Create project |
| `GET` | `/workspaces/{ws_id}/projects/` | `?limit=50&offset=0` | `[ProjectResponse]` | List projects |
| `GET` | `/workspaces/{ws_id}/projects/{id}` | — | `ProjectResponse` | Get project |
| `PATCH` | `/workspaces/{ws_id}/projects/{id}` | `{title?, description?, status?, lead_type?, lead_id?}` | `ProjectResponse` | Update project |
| `DELETE` | `/workspaces/{ws_id}/projects/{id}` | — | `204` | Delete project |
| `GET` | `/workspaces/{ws_id}/projects/{id}/stats` | — | Stats object | Project statistics |

### Project Statuses

```
planned → in_progress → paused → completed → cancelled
```

### Data Models

**ProjectResponse**:
```json
{
  "id": "uuid",
  "workspace_id": "uuid",
  "title": "string",
  "description": "string | null",
  "icon": "string | null",
  "status": "planned | in_progress | paused | completed | cancelled",
  "lead_type": "member | agent | null",
  "lead_id": "uuid | null",
  "created_at": "datetime"
}
```

### UI Components Needed

| Component | Description |
|-----------|-------------|
| **Projects List** | Card or table view with status badges, lead avatar |
| **Project Detail Page** | Header + description + issue list + stats |
| **Create Project Modal** | Title, description, icon picker, lead selector |
| **Project Status Dropdown** | Cycle through: planned → in_progress → completed etc. |
| **Lead Selector** | Combined member + agent picker (both can be leads) |
| **Project Stats Dashboard** | Issue counts by status, completion percentage |

### Industry Comparison

| Aspect | PraisonAI | Tool A | Tool B |
|--------|-----------|---------|-----------|
| **Project concept** | ✅ Workspace-scoped projects | ✅ Projects with boards | ✅ Goals (not projects) |
| **Lead assignment** | ✅ Member or agent as lead | ✅ Project lead | ✅ Agent as department head |
| **Status workflow** | 5 statuses | Similar | Goal-based milestones |
| **Statistics** | ✅ Stats endpoint | ✅ Dashboard analytics | ✅ Cost analytics |

### Gaps & Recommendations

1. **Add project templates** — Pre-configured project structures
2. **Add project archiving** — Soft delete vs hard delete
3. **Consider goal-based structure** like Tool B for agent alignment

---

## 8. Feature 5: Issue Tracking & Workflow

### API Endpoints

| Method | Path | Request Body | Response | Description |
|--------|------|-------------|----------|-------------|
| `POST` | `/workspaces/{ws_id}/issues/` | `IssueCreate` | `IssueResponse` | Create issue |
| `GET` | `/workspaces/{ws_id}/issues/` | `?status=&project_id=&assignee_id=&limit=50&offset=0` | `[IssueResponse]` | List issues (filterable) |
| `GET` | `/workspaces/{ws_id}/issues/{id}` | — | `IssueResponse` | Get issue |
| `PATCH` | `/workspaces/{ws_id}/issues/{id}` | `IssueUpdate` | `IssueResponse` | Update issue |
| `DELETE` | `/workspaces/{ws_id}/issues/{id}` | — | `204` | Delete issue |

### Issue Statuses

```
backlog → todo → in_progress → in_review → done
                                          → blocked
                                          → cancelled
```

### Priority Levels

```
urgent > high > medium > low > none
```

### Data Models

**IssueCreate**:
```json
{
  "title": "string",
  "description": "string | null",
  "project_id": "uuid | null",
  "status": "backlog (default)",
  "priority": "none (default)",
  "assignee_type": "member | agent | null",
  "assignee_id": "uuid | null",
  "parent_issue_id": "uuid | null",
  "acceptance_criteria": ["string"]
}
```

**IssueResponse**:
```json
{
  "id": "uuid",
  "workspace_id": "uuid",
  "project_id": "uuid | null",
  "title": "string",
  "description": "string | null",
  "status": "string",
  "priority": "string",
  "assignee_type": "member | agent | null",
  "assignee_id": "uuid | null",
  "creator_type": "member | agent",
  "creator_id": "uuid",
  "number": 42,
  "identifier": "ISS-42",
  "parent_issue_id": "uuid | null",
  "created_at": "datetime"
}
```

### Key Features

- **Human-readable IDs**: Auto-generated `ISS-42` format using workspace `issue_prefix` + `issue_counter`
- **Sub-issues**: `parent_issue_id` enables hierarchical issue trees
- **Dual assignees**: Both members and agents can be assigned
- **Dual creators**: Issues can be created by humans or agents
- **Acceptance criteria**: JSON array stored per issue
- **Position**: Float field for drag-and-drop ordering
- **Due date**: Optional datetime field
- **Context refs**: JSON array for external references

### UI Components Needed

| Component | Description |
|-----------|-------------|
| **Issue Board (Kanban)** | Columns by status, drag-and-drop between columns |
| **Issue List View** | Filterable table: status, priority, assignee, project |
| **Issue Detail Panel** | Side panel or full page with all fields |
| **Issue Create Modal** | Title, description (rich text), project, assignee, priority |
| **Status Badge** | Color-coded: backlog(gray), todo(blue), in_progress(yellow), done(green), blocked(red) |
| **Priority Badge** | Icon+color: urgent(red), high(orange), medium(yellow), low(blue), none(gray) |
| **Assignee Picker** | Combined list of members + agents with avatar/icon differentiation |
| **Sub-issue Tree** | Nested list showing parent → child hierarchy |
| **Issue Identifier** | Display `ISS-42` prominently (like Linear's `LIN-123`) |
| **Acceptance Criteria** | Checklist component with add/remove/check items |
| **Due Date Picker** | Calendar date/time selector |

### Industry Comparison

| Aspect | PraisonAI | Tool A | Tool B |
|--------|-----------|---------|-----------|
| **Issue model** | Full (status, priority, assignee, labels, deps) | Full (Linear-like) | Tasks (simpler, goal-aligned) |
| **Human-readable IDs** | ✅ `ISS-42` | ✅ `MUL-123` style | ❌ UUIDs only |
| **Agent as assignee** | ✅ | ✅ (first-class) | ✅ (heartbeat-based) |
| **Agent as creator** | ✅ | ✅ (autonomous participation) | ✅ |
| **Sub-issues** | ✅ parent_issue_id | ✅ Sub-tasks | ❌ |
| **Task lifecycle** | Status-based | enqueue→claim→start→complete/fail | Heartbeat + governance |
| **Board view** | API supports it (status grouping) | ✅ Kanban board | ✅ Task board |
| **Acceptance criteria** | ✅ JSON array | ✅ | ❌ |
| **Due dates** | ✅ | ✅ | ❌ (deadline via goals) |
| **Position/ordering** | ✅ Float position | ✅ Drag-and-drop | ❌ |
| **WebSocket streaming** | ❌ Not yet | ✅ Real-time via WS | ✅ |

### Gaps & Recommendations

1. **Add WebSocket for real-time updates** — Tool A has WS-powered live updates; critical for board UX
2. **Add bulk operations** — Move multiple issues, bulk status change
3. **Add search/full-text** — Neither search endpoint nor full-text search exists
4. **Add filters by date range** — Only status/project/assignee filters exist
5. **Consider task lifecycle model** — Tool A's enqueue→claim→start→complete is more agent-friendly

---

## 9. Feature 6: Agent Registry & Management

### API Endpoints

| Method | Path | Request Body | Response | Description |
|--------|------|-------------|----------|-------------|
| `POST` | `/workspaces/{ws_id}/agents/` | `AgentCreate` | `AgentResponse` | Register agent |
| `GET` | `/workspaces/{ws_id}/agents/` | `?status=&limit=50&offset=0` | `[AgentResponse]` | List agents |
| `GET` | `/workspaces/{ws_id}/agents/{id}` | — | `AgentResponse` | Get agent |
| `PATCH` | `/workspaces/{ws_id}/agents/{id}` | `AgentUpdate` | `AgentResponse` | Update agent |
| `DELETE` | `/workspaces/{ws_id}/agents/{id}` | — | `204` | Delete agent |

### Agent Statuses

```
idle | working | blocked | error | offline
```

### Runtime Modes

```
local | cloud
```

### Data Models

**AgentCreate**:
```json
{
  "name": "string",
  "runtime_mode": "local | cloud",
  "runtime_config": {},
  "instructions": "string | null",
  "max_concurrent_tasks": 1
}
```

**AgentResponse**:
```json
{
  "id": "uuid",
  "workspace_id": "uuid",
  "name": "string",
  "avatar_url": "string | null",
  "runtime_mode": "local | cloud",
  "instructions": "string | null",
  "status": "idle | working | blocked | error | offline",
  "max_concurrent_tasks": 1,
  "owner_id": "uuid | null",
  "created_at": "datetime"
}
```

### UI Components Needed

| Component | Description |
|-----------|-------------|
| **Agent List** | Grid/table with status indicators (green=idle, yellow=working, red=error, gray=offline) |
| **Agent Profile Card** | Avatar, name, status, runtime mode, current task |
| **Create Agent Modal** | Name, runtime mode, instructions textarea, max tasks |
| **Agent Settings** | Edit instructions, runtime config JSON editor |
| **Agent Status Indicator** | Real-time dot: green/yellow/red/gray |
| **Agent in Assignee Picker** | Combined with members, visually distinguished (robot icon) |

### Industry Comparison

| Aspect | PraisonAI | Tool A | Tool B |
|--------|-----------|---------|-----------|
| **Agent model** | Workspace-scoped, instructions, runtime config | Workspace-scoped, CLI-based providers | Company-scoped, org chart position |
| **Runtime modes** | local/cloud | Local daemon + cloud | Heartbeat-based |
| **Status tracking** | 5 statuses | Real-time via daemon | Heartbeat alive/dead |
| **Instructions** | ✅ Free-text instructions | ✅ Per-agent config | ✅ Job description |
| **Max concurrent** | ✅ Configurable | ✅ | Budget-based limiting |
| **Provider support** | Runtime config JSON | Claude/Codex/OpenClaw/OpenCode | Any agent with heartbeat |
| **Skills** | ❌ Not yet | ✅ Reusable skills system | ✅ Skills manager |
| **Cost tracking** | ❌ Not yet | ❌ | ✅ Per-agent budgets |

### Gaps & Recommendations

1. **Add skills/capabilities system** — Both Tool A and Tool B have reusable skills
2. **Add cost tracking per agent** — Tool B's per-agent budgets are compelling
3. **Add agent heartbeat/health checks** — Detect offline agents proactively
4. **Add runtime provider field** — Store which CLI (claude/codex/etc.) the agent uses

---

## 10. Feature 7: Labels & Tagging

### API Endpoints

| Method | Path | Request Body | Response | Description |
|--------|------|-------------|----------|-------------|
| `POST` | `/workspaces/{ws_id}/labels` | `{name, color?}` | `LabelResponse` | Create label |
| `GET` | `/workspaces/{ws_id}/labels` | — | `[LabelResponse]` | List labels |
| `PATCH` | `/workspaces/{ws_id}/labels/{id}` | `{name?, color?}` | `LabelResponse` | Update label |
| `DELETE` | `/workspaces/{ws_id}/labels/{id}` | — | `204` | Delete label |
| `POST` | `/workspaces/{ws_id}/issues/{issue_id}/labels/{label_id}` | — | `204` | Add label to issue |
| `DELETE` | `/workspaces/{ws_id}/issues/{issue_id}/labels/{label_id}` | — | `204` | Remove label from issue |
| `GET` | `/workspaces/{ws_id}/issues/{issue_id}/labels` | — | `[LabelResponse]` | List issue's labels |

### Data Models

**LabelResponse**:
```json
{
  "id": "uuid",
  "workspace_id": "uuid",
  "name": "string",
  "color": "#6B7280 (default)"
}
```

### UI Components Needed

| Component | Description |
|-----------|-------------|
| **Label Manager** | Settings page to CRUD workspace labels |
| **Label Chip** | Colored pill with label name (like GitHub labels) |
| **Label Picker** | Multi-select dropdown on issue detail to add/remove labels |
| **Label Filter** | Filter issues by label on board/list view |
| **Color Picker** | Hex color selector for label creation/editing |

### Industry Comparison

| Aspect | PraisonAI | Tool A | Tool B |
|--------|-----------|---------|-----------|
| **Labels** | ✅ Workspace-scoped, color | ✅ Full label system | ❌ No label system |
| **Many-to-many** | ✅ issue_to_label link table | ✅ | N/A |
| **Label groups** | ❌ | ✅ Label groups | N/A |

### Gaps & Recommendations

1. **Add label groups** — Tool A groups labels (e.g., "Priority", "Type", "Team")
2. **Add label description field** — Help users understand label purpose
3. **Add filter-by-label on issue list** — API filter endpoint needed

---

## 11. Feature 8: Issue Dependencies

### API Endpoints

| Method | Path | Request Body | Response | Description |
|--------|------|-------------|----------|-------------|
| `POST` | `/workspaces/{ws_id}/issues/{issue_id}/dependencies/` | `{depends_on_issue_id, type?}` | `DependencyResponse` | Create dependency |
| `GET` | `/workspaces/{ws_id}/issues/{issue_id}/dependencies/` | — | `[DependencyResponse]` | List dependencies |
| `DELETE` | `/workspaces/{ws_id}/issues/{issue_id}/dependencies/{dep_id}` | — | `204` | Delete dependency |

### Dependency Types

```
blocks | blocked_by | related
```

### Data Models

**DependencyResponse**:
```json
{
  "id": "uuid",
  "issue_id": "uuid",
  "depends_on_issue_id": "uuid",
  "type": "blocks | blocked_by | related"
}
```

### UI Components Needed

| Component | Description |
|-----------|-------------|
| **Dependency Section** | On issue detail: list of blocking/blocked-by/related issues |
| **Add Dependency Modal** | Search issues + select type (blocks/blocked_by/related) |
| **Dependency Graph** | Visual graph showing issue dependency chains |
| **Blocked Indicator** | Badge/icon on issue cards when blocked by another issue |

### Industry Comparison

| Aspect | PraisonAI | Tool A | Tool B |
|--------|-----------|---------|-----------|
| **Dependencies** | ✅ blocks/blocked_by/related | ✅ Full dependency model | ❌ No dependencies |
| **Cycle detection** | ❌ Not yet | ✅ | N/A |
| **Visualization** | ❌ API only | ✅ Board view integration | N/A |

### Gaps & Recommendations

1. **Add cycle detection** — Prevent circular dependency chains
2. **Add reverse dependency lookup** — "What depends on this issue?"
3. **Auto-block status** — When a blocking issue is not done, auto-set blocked issue status

---

## 12. Feature 9: Comments & Threading

### API Endpoints

| Method | Path | Request Body | Response | Description |
|--------|------|-------------|----------|-------------|
| `POST` | `/workspaces/{ws_id}/issues/{issue_id}/comments/` | `{content, parent_id?}` | `CommentResponse` | Add comment |
| `GET` | `/workspaces/{ws_id}/issues/{issue_id}/comments/` | — | `[CommentResponse]` | List comments |

### Comment Types

```
comment | status_change | progress_update | system
```

### Data Models

**CommentResponse**:
```json
{
  "id": "uuid",
  "issue_id": "uuid",
  "author_type": "member | agent",
  "author_id": "uuid",
  "parent_id": "uuid | null",
  "content": "string",
  "type": "comment | status_change | progress_update | system",
  "created_at": "datetime"
}
```

### UI Components Needed

| Component | Description |
|-----------|-------------|
| **Comment Thread** | Chronological list with nested replies (parent_id) |
| **Comment Input** | Rich text input with submit button |
| **Reply Button** | Per-comment, sets parent_id for threaded reply |
| **Author Badge** | Member avatar vs Agent robot icon |
| **System Comments** | Styled differently (gray, italic) for status_change/system types |
| **Activity Timeline** | Interleave comments + status changes + system events |

### Industry Comparison

| Aspect | PraisonAI | Tool A | Tool B |
|--------|-----------|---------|-----------|
| **Threading** | ✅ parent_id for replies | ✅ Threaded comments | ✅ Task threads |
| **Agent comments** | ✅ author_type=agent | ✅ Agents comment autonomously | ✅ |
| **Comment types** | ✅ 4 types | ✅ Similar | Activity-based |
| **Rich text** | Plain text (content field) | ✅ Markdown/rich text | ✅ Markdown |
| **Mentions** | ❌ | ✅ @mentions | ✅ @mentions trigger heartbeat |
| **Reactions** | ❌ | ✅ Emoji reactions | ❌ |

### Gaps & Recommendations

1. **Add @mentions support** — Parse `@user` and `@agent` in content; trigger notifications
2. **Add rich text/markdown support** — Store as markdown, render in UI
3. **Add comment editing** — No PATCH endpoint for comments yet
4. **Add comment deletion** — No DELETE endpoint for comments yet
5. **Add reactions** — Tool A has emoji reactions
6. **Add file attachments** — Common need across PM tools

---

## 13. Feature 10: Activity Logs & Audit Trail

### API Endpoints

| Method | Path | Request Body | Response | Description |
|--------|------|-------------|----------|-------------|
| `GET` | `/workspaces/{ws_id}/activity` | `?limit=50&offset=0` | `[ActivityLogResponse]` | Workspace activity |
| `GET` | `/workspaces/{ws_id}/issues/{issue_id}/activity` | `?limit=50&offset=0` | `[ActivityLogResponse]` | Issue activity |

### Data Models

**ActivityLogResponse**:
```json
{
  "id": "uuid",
  "workspace_id": "uuid",
  "issue_id": "uuid | null",
  "actor_type": "member | agent | system | null",
  "actor_id": "uuid | null",
  "action": "string (e.g., 'issue.created', 'issue.updated')",
  "details": {},
  "created_at": "datetime"
}
```

### Currently Logged Actions

- `issue.created` — When an issue is created
- `issue.updated` — When an issue is updated (details contain changed fields)

### UI Components Needed

| Component | Description |
|-----------|-------------|
| **Activity Feed** | Chronological stream of all workspace events |
| **Issue Activity Timeline** | Per-issue history of all changes |
| **Activity Item** | Actor avatar + action description + timestamp |
| **Activity Filters** | Filter by actor, action type, date range |
| **Real-time Feed** | Live-updating activity (needs WebSocket) |

### Industry Comparison

| Aspect | PraisonAI | Tool A | Tool B |
|--------|-----------|---------|-----------|
| **Activity logging** | ✅ Issue create/update | ✅ Unified timeline (human+agent) | ✅ Full tracing + audit |
| **Actor types** | member/agent/system | member/agent | agent (all agents) |
| **Granularity** | Action + details JSON | Fine-grained events | Tool-call level tracing |
| **Real-time** | ❌ Polling only | ✅ WebSocket | ✅ WebSocket |
| **Cost tracking** | ❌ | ❌ | ✅ Per-action cost |

### Gaps & Recommendations

1. **Expand logged actions** — Log member changes, label changes, dependency changes, comments
2. **Add WebSocket for live feed** — Both Tool A and Tool B have real-time feeds
3. **Add cost tracking in activity** — Tool B tracks per-action costs
4. **Add activity filtering API** — Filter by actor_type, action, date range

---

## 14. Feature 11: Client SDK

### Overview

The `PlatformClient` is an async Python HTTP client at `client/platform_client.py` that wraps all API endpoints. It uses **connection pooling** via `httpx.AsyncClient` for efficient HTTP connections.

### Key Features

- **Connection pooling** — Single `httpx.AsyncClient` lifecycle via async context manager
- **Async context manager** — `async with PlatformClient(...) as client:`
- **Auto token management** — `register()` and `login()` automatically set the JWT token
- **Full CRUD coverage** — All 40+ API endpoints have corresponding SDK methods
- **Custom exceptions** — `NotFoundError`, `DuplicateError`, `AuthenticationError`, `AuthorizationError`, `ValidationError`

### Available Methods

| Category | Methods |
|----------|---------|
| **Auth** | `register()`, `login()`, `get_me()` |
| **Workspaces** | `create_workspace()`, `list_workspaces()`, `get_workspace()`, `update_workspace()`, `delete_workspace()` |
| **Members** | `add_member()`, `list_members()`, `update_member()`, `remove_member()` |
| **Projects** | `create_project()`, `list_projects()`, `get_project()`, `update_project()`, `delete_project()`, `get_project_stats()` |
| **Issues** | `create_issue()`, `list_issues()`, `get_issue()`, `update_issue()`, `delete_issue()` |
| **Comments** | `add_comment()`, `list_comments()` |
| **Agents** | `create_agent()`, `list_agents()`, `get_agent()`, `update_agent()`, `delete_agent()` |
| **Labels** | `create_label()`, `list_labels()`, `update_label()`, `delete_label()`, `add_label_to_issue()`, `remove_label_from_issue()`, `list_issue_labels()` |
| **Dependencies** | `create_dependency()`, `list_dependencies()`, `delete_dependency()` |
| **Activity** | `list_workspace_activity()`, `list_issue_activity()` |

### Usage Pattern

```python
from praisonai_platform import PlatformClient

# Recommended: async context manager for connection pooling
async with PlatformClient(base_url="http://localhost:8000") as client:
    await client.register("user@example.com", "password")  # auto-sets token
    
    workspaces = await client.list_workspaces()
    ws_id = workspaces[0]["id"]
    
    issues = await client.list_issues(ws_id)
    activity = await client.list_workspace_activity(ws_id, limit=20)
```

### Running the Server

```bash
# CLI entry point
python -m praisonai_platform --host 0.0.0.0 --port 8000 --reload
```

### UI Provider Relevance

A UI provider can either:
1. **Call the REST API directly** from their frontend (recommended for web UIs)
2. **Use the Python SDK** for server-side rendering or backend-for-frontend patterns
3. **Build a TypeScript/JS SDK** mirroring the Python client (recommended for React/Next.js UIs)

### Test Coverage

The Client SDK has **17 integration tests** covering all methods end-to-end, including RBAC enforcement:
- Auth (register, login, get_me)
- Workspace CRUD
- Member operations
- Project CRUD + stats
- Issue CRUD + pagination + sub-issues
- Comments, Agents, Labels, Dependencies, Activity
- Connection pooling (context manager, standalone mode)
- RBAC enforcement (non-member gets 403, member can access)

---

## 15. Feature 12: Database & Schema

### Entity-Relationship Summary

```
User ──1:N──> Member ──N:1──> Workspace
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
                 Project       Agent        IssueLabel
                    │                          │
                    ▼                          ▼
                  Issue ──────────────> IssueLabelLink
                    │
          ┌────────┼────────┐
          ▼        ▼        ▼
       Comment  IssueDep  ActivityLog
       (threaded) (blocks/  (audit)
                  related)
```

### All Tables

| Table | Primary Key | Key Fields |
|-------|-------------|-----------|
| `user` | `id` (uuid) | name, email, password_hash, avatar_url |
| `workspace` | `id` (uuid) | name, slug (unique), settings (JSON), issue_prefix, issue_counter |
| `member` | `id` (uuid) | workspace_id, user_id, role; unique(workspace_id, user_id) |
| `agent` | `id` (uuid) | workspace_id, name, runtime_mode, runtime_config (JSON), instructions, status, max_concurrent_tasks, owner_id |
| `project` | `id` (uuid) | workspace_id, title, status, lead_type, lead_id |
| `issue` | `id` (uuid) | workspace_id, project_id, title, status, priority, assignee_type/id, creator_type/id, number, identifier, parent_issue_id, acceptance_criteria (JSON), context_refs (JSON), position, due_date |
| `issue_label` | `id` (uuid) | workspace_id, name, color |
| `issue_to_label` | composite(issue_id, label_id) | Many-to-many link |
| `issue_dependency` | `id` (uuid) | issue_id, depends_on_issue_id, type |
| `comment` | `id` (uuid) | issue_id, author_type/id, parent_id, content, type |
| `activity_log` | `id` (uuid) | workspace_id, issue_id, actor_type/id, action, details (JSON) |

### Indexes

- `idx_project_workspace` — project.workspace_id
- `idx_issue_workspace` — issue.workspace_id
- `idx_issue_status` — issue(workspace_id, status)
- `idx_issue_assignee` — issue(assignee_type, assignee_id)
- `idx_issue_project` — issue.project_id
- `idx_issue_parent` — issue.parent_issue_id
- `idx_comment_issue` — comment.issue_id
- `idx_activity_log_issue` — activity_log.issue_id

---

## 16. Comparison Matrix

| Feature | PraisonAI Platform | Tool A | Tool B |
|---------|-------------------|---------|-----------|
| **Tech stack** | Python/FastAPI/SQLAlchemy | Go backend + Next.js frontend | Node.js + React |
| **Database** | SQLite/PostgreSQL | PostgreSQL + pgvector | Embedded PostgreSQL |
| **Auth** | JWT (email+password) | Email codes + Google OAuth | better-auth sessions |
| **Multi-tenancy** | Workspace-scoped | Multi-workspace | Multi-company |
| **RBAC** | ✅ owner/admin/member (route-level enforcement) | owner/admin/member | Org chart hierarchy |
| **Projects** | ✅ Full CRUD + stats | ✅ With boards | Goals (not projects) |
| **Issues** | ✅ Full lifecycle + sub-issues | ✅ Linear-like board | Tasks (goal-aligned) |
| **Human-readable IDs** | ✅ ISS-42 | ✅ | ❌ |
| **Agents as teammates** | ✅ | ✅ (core feature) | ✅ (core feature) |
| **Agent runtime** | local/cloud config | Daemon + CLI detection | Heartbeat-based |
| **Skills system** | ❌ | ✅ Reusable skills | ✅ Skills manager |
| **Labels** | ✅ | ✅ With groups | ❌ |
| **Dependencies** | ✅ blocks/blocked_by/related | ✅ | ❌ |
| **Comments** | ✅ Threaded | ✅ Threaded + mentions | ✅ |
| **Activity logs** | ✅ Basic | ✅ Unified timeline | ✅ Full tracing |
| **WebSocket** | ❌ | ✅ Real-time | ✅ |
| **Cost tracking** | ❌ | ❌ | ✅ Per-agent budgets |
| **Governance** | ❌ | ❌ | ✅ Approval workflows |
| **Search** | ❌ | ✅ | ❌ |
| **CLI** | ✅ `python -m praisonai_platform` | ✅ Full CLI | ✅ npx CLI |
| **Client SDK** | ✅ Python async (connection pooling, 40+ methods) | CLI-based | Node.js |
| **Self-hosted** | ✅ | ✅ | ✅ |

---

## 17. Recommended UI Views & Components

### Core Views (Must-Have for MVP)

| # | View | Description | Key API Calls |
|---|------|-------------|---------------|
| 1 | **Login / Register** | Auth forms | `POST /auth/login`, `POST /auth/register` |
| 2 | **Workspace Selector** | List + switch workspaces | `GET /workspaces/` |
| 3 | **Issue Board (Kanban)** | Columns by status, drag-and-drop | `GET /issues/?status=...` per column |
| 4 | **Issue List** | Filterable table view | `GET /issues/?...filters` |
| 5 | **Issue Detail** | Full issue view + comments + activity | `GET /issues/{id}`, `GET /comments/`, `GET /activity` |
| 6 | **Project List** | All projects with stats | `GET /projects/`, `GET /projects/{id}/stats` |
| 7 | **Agent Dashboard** | Agent status grid | `GET /agents/` |
| 8 | **Settings** | Workspace, members, labels | Various settings endpoints |

### Advanced Views (Phase 2)

| # | View | Description |
|---|------|-------------|
| 9 | **Dependency Graph** | Visual graph of issue dependencies |
| 10 | **Activity Feed** | Real-time workspace activity stream |
| 11 | **Project Detail** | Issues within project + burndown |
| 12 | **Agent Profile** | Detailed agent view with task history |
| 13 | **Member Management** | Invite, role management |
| 14 | **Search** | Global search across issues, projects |

### Component Library Requirements

| Category | Components |
|----------|-----------|
| **Layout** | Sidebar, TopBar, WorkspaceSwitcher, BreadcrumbNav |
| **Auth** | LoginForm, RegisterForm, AuthProvider/Context |
| **Data Display** | IssueCard, ProjectCard, AgentCard, MemberRow, LabelChip, StatusBadge, PriorityBadge |
| **Input** | AssigneePicker (members+agents), LabelPicker, StatusDropdown, PriorityDropdown, DatePicker, RichTextEditor |
| **Board** | KanbanBoard, KanbanColumn, DraggableCard |
| **Detail** | IssueDetailPanel, CommentThread, CommentInput, ActivityTimeline, DependencyList |
| **Charts** | ProjectStats, BurndownChart, AgentStatusChart |

---

## 18. WebSocket / Real-time Considerations

### Current State

The platform currently has **no WebSocket support**. All data is fetched via REST API with polling.

### Recommended Implementation

Both Tool A and Tool B use WebSockets for real-time updates. For the UI to feel modern, WebSocket support should be added for:

| Event | Description | Trigger |
|-------|-------------|---------|
| `issue.created` | New issue appeared | `POST /issues/` |
| `issue.updated` | Issue status/assignee/priority changed | `PATCH /issues/{id}` |
| `issue.deleted` | Issue removed | `DELETE /issues/{id}` |
| `comment.created` | New comment on issue | `POST /comments/` |
| `agent.status_changed` | Agent went online/offline/working | Agent heartbeat |
| `activity.new` | New activity log entry | Any mutation |

### Suggested WebSocket Protocol

```
WS /api/v1/ws?token=<JWT>&workspace_id=<ws_id>

→ Server sends: {"event": "issue.updated", "data": {...}}
→ Client sends: {"subscribe": "issue:ISS-42"}  // optional granular subscription
```

### Interim Solution

Until WebSocket is implemented, UI can use **polling with exponential backoff**:
- Active tab: poll every 5s
- Background tab: poll every 30s
- Use `If-Modified-Since` or ETags for efficiency

---

## 19. Gaps & Recommendations for UI Layer

### Recently Resolved

| # | Gap | Resolution |
|---|-----|-----------|
| ✅ | **RBAC enforcement in routes** | All workspace-scoped routes now use `require_workspace_member` dependency. Non-members get `403 Forbidden`. Role hierarchy: owner > admin > member. |
| ✅ | **Client SDK connection pooling** | `PlatformClient` now uses single `httpx.AsyncClient` via async context manager. |
| ✅ | **CLI entry point** | `python -m praisonai_platform` runs uvicorn with `--host`, `--port`, `--reload` options. |
| ✅ | **Custom exceptions** | `exceptions.py` provides `NotFoundError`, `DuplicateError`, `AuthenticationError`, `AuthorizationError`, `ValidationError`. |
| ✅ | **Package exports** | `from praisonai_platform import PlatformClient, create_app` works directly. |
| ✅ | **WorkspaceContextProtocol** | `PlatformWorkspaceContext` provides workspace/agent config to agents. |
| ✅ | **Client SDK missing methods** | Activity, delete operations, workspace update/delete, project get/update/delete, get_me — all implemented. |
| ✅ | **/me endpoint bug** | `GET /auth/me` now queries DB for full user info (was returning `created_at=None`). |

### Priority 1 (Critical for MVP)

| # | Gap | Impact | Effort |
|---|-----|--------|--------|
| 1 | **WebSocket support** | No real-time updates without it | Medium |
| 2 | **Search endpoint** | Can't search issues/projects | Low |
| 3 | **Comment edit/delete** | Basic comment management missing | Low |
| 4 | **Filter issues by label** | Labels exist but can't filter by them | Low |

### Priority 2 (Important for Parity)

| # | Gap | Impact | Effort |
|---|-----|--------|--------|
| 6 | **OAuth/social login** | Tool A has Google OAuth | Medium |
| 7 | **@mentions in comments** | Both Tool A and Tool B have this | Medium |
| 8 | **Skills/capabilities system** | Both Tool A and Tool B have reusable skills | High |
| 9 | **Cost tracking per agent** | Tool B's key differentiator | Medium |
| 10 | **Agent heartbeat/health** | Detect offline agents proactively | Medium |

### Priority 3 (Nice-to-Have)

| # | Gap | Impact | Effort |
|---|-----|--------|--------|
| 11 | **Email verification** | Security improvement | Low |
| 12 | **Password reset** | Essential auth flow | Low |
| 13 | **Invite by email** | Better onboarding than by user_id | Medium |
| 14 | **Dependency cycle detection** | Prevent circular deps | Low |
| 15 | **Governance/approval workflows** | Tool B's key feature | High |
| 16 | **File attachments** | Common PM feature | Medium |
| 17 | **Rich text/markdown** | Better content authoring | Low (UI-only) |
| 18 | **Activity log expansion** | Log all mutations, not just issues | Medium |
| 19 | **Bulk operations** | Multi-select + bulk status change | Medium |
| 20 | **Project templates** | Quick-start project structures | Low |

---

## 20. Appendix: Full API Endpoint Reference

### Auth Routes (`/api/v1/auth`)

```
POST   /register          → {token, user}
POST   /login             → {token, user}
GET    /me                → UserResponse
```

### Workspace Routes (`/api/v1/workspaces`)

```
POST   /                  → WorkspaceResponse
GET    /                  → [WorkspaceResponse]    ?limit=50&offset=0
GET    /{id}              → WorkspaceResponse
PATCH  /{id}              → WorkspaceResponse
DELETE /{id}              → 204
```

### Member Routes (`/api/v1/workspaces/{ws_id}/members`)

```
POST   /                  → MemberResponse
GET    /                  → [MemberResponse]
PATCH  /{id}              → MemberResponse
DELETE /{id}              → 204
```

### Project Routes (`/api/v1/workspaces/{ws_id}/projects`)

```
POST   /                  → ProjectResponse
GET    /                  → [ProjectResponse]      ?limit=50&offset=0
GET    /{id}              → ProjectResponse
PATCH  /{id}              → ProjectResponse
DELETE /{id}              → 204
GET    /{id}/stats        → StatsObject
```

### Issue Routes (`/api/v1/workspaces/{ws_id}/issues`)

```
POST   /                  → IssueResponse
GET    /                  → [IssueResponse]        ?status=&project_id=&assignee_id=&limit=50&offset=0
GET    /{id}              → IssueResponse
PATCH  /{id}              → IssueResponse
DELETE /{id}              → 204
```

### Comment Routes (`/api/v1/workspaces/{ws_id}/issues/{issue_id}/comments`)

```
POST   /                  → CommentResponse
GET    /                  → [CommentResponse]
```

### Agent Routes (`/api/v1/workspaces/{ws_id}/agents`)

```
POST   /                  → AgentResponse
GET    /                  → [AgentResponse]        ?status=&limit=50&offset=0
GET    /{id}              → AgentResponse
PATCH  /{id}              → AgentResponse
DELETE /{id}              → 204
```

### Label Routes (`/api/v1/workspaces/{ws_id}`)

```
POST   /labels            → LabelResponse
GET    /labels            → [LabelResponse]
PATCH  /labels/{id}       → LabelResponse
DELETE /labels/{id}       → 204
POST   /issues/{iid}/labels/{lid}    → 204  (add label to issue)
DELETE /issues/{iid}/labels/{lid}    → 204  (remove label from issue)
GET    /issues/{iid}/labels          → [LabelResponse]
```

### Dependency Routes (`/api/v1/workspaces/{ws_id}/issues/{issue_id}/dependencies`)

```
POST   /                  → DependencyResponse
GET    /                  → [DependencyResponse]
DELETE /{dep_id}          → 204
```

### Activity Routes (`/api/v1/workspaces/{ws_id}`)

```
GET    /activity                      → [ActivityLogResponse]  ?limit=50&offset=0
GET    /issues/{issue_id}/activity    → [ActivityLogResponse]  ?limit=50&offset=0
```

---

## Summary

The PraisonAI Platform provides a **solid, production-ready backend** with 40+ API endpoints covering authentication, multi-tenancy, project management, issue tracking, agent management, labels, dependencies, comments, and activity logging.

**Key strengths**:
- Clean REST API design with consistent conventions
- Human-readable issue IDs (like Linear)
- Sub-issues and dependencies (not in Tool B)
- Labels system (not in Tool B)
- Dual principal support (member + agent) throughout
- **Route-level RBAC enforcement** via `require_workspace_member` dependency — non-members get `403 Forbidden`
- **Full Python Client SDK** with connection pooling, 40+ methods, async context manager
- **CLI entry point** — `python -m praisonai_platform` for easy server startup
- **Custom exceptions** for structured error handling
- **WorkspaceContextProtocol** — agents can retrieve workspace config and instructions
- **113 passing tests** (0 failures) — comprehensive coverage including RBAC enforcement

**Key gaps to close**:
- WebSocket for real-time (both Tool A and Tool B have this)
- Skills/capabilities system (both Tool A and Tool B have this)
- Cost tracking (Tool B)
- Search functionality
- OAuth/social login (Tool A)

A UI provider can immediately build a functional frontend using the existing REST API. The recommended tech stack for the UI would be **Next.js + React + TailwindCSS + shadcn/ui** to match modern standards (Tool A uses Next.js, Tool B uses React).
