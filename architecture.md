# MedCover Planner app


## Business Context and Goals

### Overall Idea
- a web application for planning medical cover for Events
- developed by and to be primarily used by the Czech Red Cross organization
- the app shall replace the current Google Sheets app that is used for the same purpose and is reaching its limits
- the app shall meet all the current requirements and allow seamless transition


### Assumptions and Constraints

**Assumptions**
- The primary user base is Czech Red Cross members; UI language is Czech
- The application replaces an existing Google Sheets solution — a seamless transition is expected
- User adoption depends on ease of use; not all users are IT-proficient
- Events are coordinated by a small group of admins/coordinators; the majority of users are members or viewers

**Constraints**
- The project is maintained by a volunteer team; the project lead is the primary maintainer
- Technology choices must favour simplicity and long-term maintainability over feature richness
- Infrastructure costs should be kept low (volunteer/non-profit context)

## Functional Requirements
- Users administration:
    - app roles (authorization) - admin, coordinator, member, viewer
    - credentials (unified model covering both medical qualifications and additional certifications — see AD07):
        - medical qualifications: Doctor, Nurse (SZP), First Aider (zdravotník), Trainee (zelenáč)
        - additional certifications: Driver, PSP training, KI training, humanitarian unit training, etc.
        - credentials shall support a hierarchy tree, allowing a holder of a higher-ranked credential to fill spots requiring a lower-ranked one (e.g. Doctor can fill a First Aider spot; KI-trained can fill a PSP spot)
        - credentials and their hierarchy shall be manageable (create, edit, delete) through the application by users with appropriate permissions
    - member equipment — the user profile shall display organisation-owned items currently issued to the member (long-term dislocation, e.g. uniform, personal medikit). Managed via the equipment inventory model (see Equipment section).
    - phone number, email
    - reporting/overview section:
        - **per-user**: planned hours, actual worked hours, nearest upcoming Event, last attended Event, full Event history
        - **per Master Event**: total planned and worked hours, number of Events (completed / cancelled / open), total patients treated, medical materials used, attendance summary
        - **date-range report**: all Events within a configurable date range (e.g. a calendar year), aggregated across all MEs — this replaces any need for a "yearly" ME hierarchy
    - new User Registration shall be invite-only: an admin generates a unique registration link which is sent to the prospective user; only the holder of the link can register (see AD03)
    - a newly registered account shall require admin activation before the user can log in
    - users shall be able to reset their own password via a self-service email link ("forgot password" flow)
    - users shall be able to set a preferred calendar view (month, week, day, or list); this preference is stored per user and applied when they open the calendar on desktop; on mobile, list view is the default regardless of stored preference
- Master Event (ME):
    - the system shall allow grouping of related Events under an overarching Master Event entity
    - a default "General" Master Event shall exist; all Events are assigned to a ME (General by default)
    - admins/coordinators shall be able to create and edit custom Master Events
    - admins shall be able to archive Master Events to hide them from the default view; archived MEs remain accessible for historical reporting
    - the built-in "General" Master Event cannot be archived
    - the ME view shall provide an aggregated overview of all its Events: assignment status, worked hours, count of Completed / open / cancelled Events
- Event
    - Each Event shall have
        - lifecycle statuses
            - **Draft** — created but not yet visible to members
            - **Published** — visible to members but assignments not yet open
            - **Assignments Open** — members can register for spots
            - **Assignments Closed** — no new assignments; Event is staffed or closed by coordinator/RP
            - **Completed** — Event has taken place; debriefing phase begins
            - **Cancelled** — Event will not take place; archived (hidden from normal views but not deleted)
        - lifecycle transitions
            - Draft → Published: manual (coordinator/admin)
            - Published → Assignments Open: **automatic** at the configured assignment-opening date/time; can also be manually triggered or overridden by coordinator/admin
            - Assignments Open → Assignments Closed: **automatic** when all spots are filled; can also be manually closed by coordinator/admin or the RP
            - Assignments Closed → Assignments Open: manual re-open by coordinator/admin or RP (e.g. a person drops out and spots need to be re-opened)
            - Assignments Closed → Completed: **automatic** after the Event end date/time passes
            - Any non-Completed state → Cancelled: manual (coordinator/admin only)
            - Cancelled → Draft: manual restore (coordinator/admin) — allows reuse as a basis for a new Event
            - Completed Events cannot be cancelled
        - cancellation and archiving
            - a Cancelled Event is **archived** (hidden from default views) but not deleted
            - archived Events can be restored to Draft, or used as the basis for a new Event
            - admins can permanently delete archived Events
        - staffing statuses (derived, not manually set)
            - Not staffed
            - Partially staffed
            - Fully staffed
            - Overstaffed
    - Event management - Create, modify, cancel Events
    - Event templates
        - some Events are very similar, so the system shall provide Event templates to simplify creation of new Events (e.g. a simple Event requiring 1 First Aider and 1 Trainee; a larger Event requiring 2 First Aiders, 2 Trainees and an ambulance)
        - a template may include a reminder schedule (list of "X days/hours before start" reminder triggers) which is applied automatically when an Event is created from it
        - Event templates shall be manageable (create, edit, delete) by **admins and coordinators only**
    - parametrize Events
        - start date,
        - start time,
        - end date,
        - end time,
        - number of Patrols (hlídky zdravotníků) - 1 as a default, but can be more
        - required personnel (how many of each qualification or training kind are needed; multiple qualifications can be required for one spot - e.g. 1 First Aider who is also a Driver, 2 Trainees)
        - when a person assigned to an Event is eligible for multiple spots, the specific spot they will cover must be selected at assignment time
        - required equipment (ambulance, tent, PR material, etc.),
        - optional parameter for setting maximum personnel of each qualification or training
        - paid or unpaid Event
        - date/time of Assignments opening ("immediately" being the default) - some Events can be active but not open for Assignment
        - contact person, Event address
    - The Responsible Person mechanism:
        - Each Event shall have a Responsible Person (RP) assigned before the Event start date/time.
        - Typically the first First Aider who registers to an Event becomes the RP.
        - The RP can be assigned or changed by the coordinator/admin
        - Once the RP is assigned, he/she is responsible for managing the other personnel on that Event.
        - On Events that belong to a custom ME (for example large music festivals), when a new Event is created the ME coordinator is automatically pre-filled as the RP; the coordinator can later reassign the RP slot to another eligible member
        - The RP shall be notified about changes in the Event, for example users switching spots, or coordinator/admin changing some parameters of the Event
    - If someone removes his/her's Assignment from an Event, all users who fulfill the spot requirements will be notified about the new Assignment possibility/need. No approval from the RP is required to free a spot.
    - If the Event is nearing its start and still has unfilled spots, all eligible users shall receive escalating reminder emails; the reminder schedule is configurable per Event by a coordinator/admin (default: 1 reminder, 1 day before start). When an Event is created from a template, the template's reminder schedule is applied.
    - The users registered to an Event shall be able to release their Assignment at any time; no approval from the RP or anyone else is required (see AD06)
- Post-event Debriefing
    - after an Event reaches the Completed status, the system shall trigger a debriefing process for all assigned members
    - each member shall receive a personalised email link leading directly to their debriefing form
    - the debriefing form shall allow reporting:
        - actual worked hours (may differ from the planned Event duration — e.g. Event ended early, or the person only attended part of the Event)
        - number of patients treated
        - medical materials used
        - general feedback / notes
    - partial attendance shall be supported: a member may report they were present for only part of the Event duration
- Equipment
    - manage **equipment types** (e.g. AED, medikit, large medikit, training dummy, uniform, personal LED light, etc.); types are classified as either *personal* or *shared*
    - manage **equipment inventory** — individual physical items, each belonging to an equipment type:
        - **Personal equipment** (uniforms, personal lights, etc.) — items issued long-term to a specific member; remain with that member until explicitly returned (e.g. member leaves the organisation or item is destroyed); members can self-report their own personal equipment
        - **Shared equipment** (AEDs, medikits, training dummies, etc.) — items from a communal pool; assigned to Events for the duration of the event and then returned to inventory
    - **Event equipment planning**: when creating or editing an Event, a coordinator can specify how many items of each shared equipment type are required (e.g. "2× AED, 1× large medikit")
    - **Event equipment assignment**: before or during an Event, specific shared EquipmentItems from inventory are assigned to the Event (e.g. AED-1 and AED-red are assigned to Event #42); this records which physical items were used at each Event
- Display Events in a table or calendar with the following properties:
    - **Views**: month, week, day (calendar), and list/table view
    - **Interactive**: clicking a day slot in the calendar opens the Event creation form pre-filled with that date (Coordinators / Admins only)
    - **Colour coding**: Events are coloured by lifecycle phase (e.g. Draft, Published, Assignments Open, etc.); if the logged-in user is not eligible to join the Event — even if spots exist — the Event is shown in grey
    - **Default view**: shows all non-archived Events that are in a Published or later phase; filtering options (by ME, date range, etc.) are deferred to post-MVP
- Email notifications — **email only for MVP** (in-app notifications are on the wish list)
- Notifications should be customisable to prevent unnecessary spamming (configurable per Event and at the user level)
- Audit capability
    - all create, edit, delete and status-change actions on every entity shall be recorded (users, events, master events, assignments, equipment, credentials, roles, debriefing records, system configuration)
    - each audit entry records: timestamp, actor (user account), action type, entity type, entity ID, and a summary of what changed (before/after values where applicable)
    - audit log is immutable — entries cannot be edited or deleted
    - the UI shall expose:
        - **per-entity timeline** — a chronological history of changes for a single entity (e.g. all changes to Event #42)
        - **global activity feed** — a filterable feed of all changes across the system, filterable by entity type, user, and date range
    - audit log access is restricted to admins (see RBAC table)

### Notification Triggers

| Trigger | Recipients | Timing |
|---|---|---|
| Spot released on an Event | RP (immediately) + all eligible users (immediately) | On event |
| User joins an Event (spot filled) | RP (immediately) | On event |
| Coordinator/admin changes Event parameters | RP (immediately) | On event |
| Unfilled spots as Event approaches | All eligible users | Configurable reminder schedule per Event (default: 1 day before start); inherited from template if applicable |
| Event Completed — debriefing | Each assigned member (personalised link) | On transition to Completed |
| User-set personal reminder | The individual user | At the user-configured time |
| Manual reminder by admin/coordinator/RP | Selected roles on a specific Event | On demand |
| Admin system digest | All admins | Adaptive: once/day normally; more frequent if many changes occur in a short window |
| Account pending activation | All admins | On user registration (immediately) |
| Registration invite | Invited email address | On admin action |
| Account activated | Newly activated user | On admin action |
| Password reset | Requesting user | On demand |


## Non-Functional Requirements
- The app must be user friendly and very easy to use - not all users are very skilled at IT
- There should be tooltips helping users use the app
- The app must be available 24/7
- The app must be accessible via Internet (public-facing)
- The app must have user authentication
- The app UI must be in Czech language
- The app UI must be optimized for both PC and mobile phone screens - most users will access the app using their mobile phones
- all changes must be logged and allow auditing - who changed what and when
- The infrastructure used by the app should allow backup/restore of the app. Daily backups with 60 days retention, 1day RPO, 12 hours RTO


## Architectural Decisions
- AD01 User Roles Customization
    - Problem statement - Should the user roles be hardcoded or customizable?
    - Decision - Hardcoded pre-defined roles, adding custom roles may be added to the app later
    - Justification - app roles are sets of permissions (see AD02) 
      they are relatively stable and allow good testing. Custom roles may be added to the app later but at this point, for simplicity, only pre-defined roles will be used.


- AD02 Application Object Permissions
    - Problem statement - It is not known exactly how the user roles will look like in the final app. The app should allow granular permission assignment to roles to provide flexibility.
    - Options
        - Minimalistic approach - define only create/edit/view permissions per app module
        - Maximum flexibility - design the app in a way that each meaningful component/object/action will have a permission associated with it
    - Decision - Maximum flexibility
    - Justification
        - All objects in the application (such as Equipment, Event, Master Event, User) shall have permission objects assigned to it. This will allow granular permissions assignment to user roles. However, there will be only pre-defined RBAC roles (admin, coordinator, member, viewer) at this time. Custom roles may be implemented in the future, so the object based permission model should be prepared for this.
        - Admins and Coordinators should be able to edit all Events and change people assignment to Events. This should be useful if a person can't change their own reservation, an admin or coordinator can do it for them.
        - Example permissions:  
            user.view  
            user.edit  
            Event.create  
            Event.edit  
            Event.cancel  
            Event.publish  
            Event.assign  
            Event.set_responsible_person  
            equipment_type.view  
            equipment_type.edit  
            equipment_type.create  
            audit.view  
            notification.send  
            master_Event.view  
            master_Event.edit  
            master_Event.create  
            master_Event.archive

- AD03 User Registration Access Control
    - Problem statement - Should new user self-registration be open to anyone, or should access be restricted?
    - Options
        - Open registration - anyone can register; account is activated after admin approval
        - Invite-only registration - new users can only register via a unique link generated by an admin
    - Decision - **Invite-only registration**
    - Justification - Prevents unsolicited registrations and bot attempts. Only people explicitly invited by an admin can create an account. Admin approval remains part of the flow (the invite link leads to a registration form; the resulting account is activated by admin).


- AD04 Technology Stack
    - Problem statement - Which technology stack should be used to implement the application?
    - Options
        - Python Flask + relational database + lightweight JavaScript frontend
        - Python Django + relational database + lightweight JavaScript frontend
        - Other frameworks / languages
    - Decision - **Python Flask + PostgreSQL + server-rendered HTML (Jinja2) + vanilla JS/jQuery**
    - Justification
        - Flask is lightweight and familiar to the project lead; keeps the codebase simple and easy for volunteers to contribute to
        - PostgreSQL provides robustness and production-grade reliability without significant operational overhead
        - Jinja2 server-rendered templates eliminate the need for a separate frontend build pipeline or SPA framework
        - Vanilla JS / jQuery is sufficient for the required interactivity (form enhancements, dynamic notifications); calendar views are handled by FullCalendar (see AD08)
        - This stack is well-supported on all considered hosting platforms (VPS, PythonAnywhere, Render, etc.)
    - Implications
        - REST API: can be added later using Flask blueprints without major architectural changes (auth mechanism TBD when REST API is scoped)
        - ORM: SQLAlchemy (standard Flask ORM for PostgreSQL)


- AD05 Authentication Mechanism
    - Problem statement - How should users authenticate to the application?
    - Options
        - Username + password (local accounts only)
        - Local accounts + social login (e.g. Google OAuth)
        - Single Sign-On via external identity provider (e.g. LDAP, Azure AD)
    - Decision - Username + password with email address as the login identifier
    - Justification - Simplest option to implement and maintain. No dependency on third-party identity providers. Social login or SSO may be revisited in the future if demand arises.
    - Notes
        - Users log in with their email address and a password
        - A self-service "forgot password" flow (password reset via email link) shall be provided
        - Password reset and initial account activation emails require the email/notification service to be operational


- AD06 Assignment Handover Mechanism
    - Problem statement - When a member can no longer attend an Event, how should the spot be handed over to someone else?
    - Options
        - **Explicit transfer** — the member selects a specific replacement; the replacement must confirm before the original member is removed. Requires both parties to act.
        - **Simple spot release** — the member frees the spot without selecting a replacement; the system notifies all eligible users; any eligible user can then self-assign. No bilateral coordination required.
    - Decision - **Simple spot release**
    - Justification - Operationally simpler and avoids requiring the replacement's approval. No coordination delay. The system handles notification to all eligible users automatically.


- AD07 Qualification and Training Hierarchy Model
    - Problem statement - Should medical Qualifications (Doctor, Nurse, First Aider, Trainee) and additional Trainings (Driver, PSP, KI, humanitarian unit, etc.) be modelled as separate entities, or as a single unified hierarchy?
    - Options
        - **Separate entities** — Qualifications carry a medical hierarchy; Trainings are independent certifications with no hierarchy between them or with Qualifications.
        - **Unified hierarchy tree** — a single entity type with a parent–child hierarchy covering both Qualifications and Trainings (e.g. KI-trained can fill a PSP-trained spot; Doctor can fill a First Aider spot).
    - Decision - **Unified hierarchy tree**
    - Justification - A unified tree naturally models cross-category substitution (e.g. a KI-trained volunteer filling a PSP spot, a Doctor filling a First Aider spot) without requiring special-case logic. Eliminates duplication in spot requirements. Slightly more complex to model initially but more flexible long-term.
    - Notes
        - The entity will be called **Credential** (or **Qualification**) to cover both medical levels and additional certifications
        - A Credential may have zero or more parent Credentials whose holders can fill spots requiring it
        - Examples: Doctor > Nurse > First Aider > Trainee; KI-training > PSP-training

- AD08 Calendar UI Component
    - Problem statement - The application requires a full event calendar with month, week, day, and list views, interactive day-click to create events, and per-event colour coding. Should this be built from scratch or fulfilled by a third-party library?
    - Options
        - **Build from scratch** (vanilla JS / jQuery) — write all calendar grid logic, view switching, and touch handling manually.
        - **FullCalendar** (open-source, MIT licence) — a widely-used JS calendar library delivered via CDN; no build pipeline required.
    - Decision - **FullCalendar**
    - Justification
        - All required views (month, week, day, list) are built-in; no custom grid logic needed.
        - Interactive day-click (`dateClick` / `select` callbacks) and per-event colour coding are first-class features.
        - Touch-aware out of the box; swipe-to-navigate works on phones.
        - MIT-licensed, actively maintained, extensive documentation — volunteer contributors can find tutorials and examples easily.
        - Delivered via CDN — no build pipeline or npm dependency management required, consistent with the project's simplicity goal.
        - Building equivalent functionality from scratch would take weeks and be harder to maintain long-term.
    - Notes
        - **Mobile default view**: on small screens (phones) the list view shall be the primary default; month/week/day remain accessible but secondary. On desktop the user's preferred view is stored as a personal setting (user preference in the database).
        - Only the free open-source distribution is used; the paid "Scheduler" add-on (drag-and-drop resource scheduling) is not required.
        - FullCalendar fetches events from a lightweight JSON endpoint served by the Flask backend.

- AD09 Deployment Platform and Containerisation Strategy
    - Problem statement - Where should the application be hosted, and how should it be packaged for deployment? The choice must balance simplicity, cost (non-profit context), portability, and reproducibility.
    - Options
        - **Platform-specific deployment** (e.g. PythonAnywhere, Heroku buildpacks) — simple setup but tightly coupled to the platform; migration is painful.
        - **Container-first deployment** (Docker) — application packaged as a container image; deployable to any container-capable platform with no code changes.
    - Decision - **Container-first (Docker) deployment on Render.com for MVP; targeting a hyperscaler with NGO credits long-term**
    - Justification
        - A `Dockerfile` decouples the application from the hosting platform — migrating from Render to Azure or Google Cloud requires no application changes.
        - Docker Compose provides a consistent local development environment for all contributors, reducing "works on my machine" issues.
        - Render.com supports Docker natively (push to GitHub → auto-deploy), has a free tier covering MVP needs, and includes managed PostgreSQL.
        - Czech Red Cross qualifies as an NGO for cloud credit programmes (Azure for Nonprofits ~$3,500/year; Google Cloud for Nonprofits ~$10,000/year); applying after MVP launch unlocks production-grade infrastructure at zero cost.
        - Container-first is the industry standard and familiar to most developers, making it easier for future volunteers to contribute.
    - Notes
        - **MVP target**: Render.com free tier (Flask container + managed PostgreSQL 256 MB). Free tier apps sleep after 15 minutes of inactivity — acceptable given the usage pattern (event-driven, not 24/7).
        - **Long-term target**: Azure Container Apps or Google Cloud Run using NGO credits; same `Dockerfile` applies.
        - **Local development**: Docker Compose with Flask app + PostgreSQL containers; `.env` file for secrets (not committed).
        - **CI/CD**: GitHub Actions builds and pushes the image; Render or the target platform pulls and deploys automatically.
        - The Deployment Model section should be updated once the NGO credit application is approved and a hyperscaler is chosen.


MedCover is a standard three-tier web application:

- **Frontend** — a browser-based web client accessed over the public Internet. Optimised for both desktop and mobile screens.
- **Backend** — a server-side application exposing a web UI (and optionally a REST API). It implements all business logic, enforces RBAC, and manages application state.
- **Data store** — a relational database holding all persistent application data (users, events, equipment, audit log, etc.).
- **Email / notification service** — an outbound mail integration for sending notifications, reminders and digests to users.

All user interactions flow through the backend; the data store and mail service are internal dependencies not directly exposed to users. The infrastructure administrator (P02) accesses the server directly for operational tasks (deployment, backup, maintenance).

## System Context
The System Context describes how MedCover fits into the broader landscape of users, services and external systems around it.

```mermaid
flowchart TD
    A[MedCover Solution]
    B(P01 - User) -->|HTTPS - web UI| A
    C(S01 - Other Apps) -->|HTTPS - REST API - future| A
    D(P02 - Admin) -->|SSH - ops & maintenance| A
    A -->|SMTP / email API| E(S02 - Email Service)
```

| Entity ID | Entity Type | Entity Name | Description | Trust Level |
|---|---|---|---|---|
| P01 | Person | User | Czech Red Cross members accessing the app via a web browser over the public Internet | Authenticated; access controlled by RBAC |
| S01 | System | Other Apps | **Future** — third-party systems integrating via the REST API (e.g. reporting tools) | Authenticated via API token; read-only scope initially |
| P02 | Person | Infrastructure Admin | Person responsible for deployment, backups, OS/app updates and server maintenance | Trusted; accesses the server directly via SSH — outside the app's own auth |
| S02 | System | Email Service | External SMTP relay or email API (e.g. SendGrid, Mailgun, AWS SES) used for all outbound notifications | Outbound only; credentials stored as server-side secrets |

**Trust boundaries:**
- All P01 traffic crosses the public Internet and must be served over HTTPS
- S02 credentials (SMTP/API keys) must never be exposed to P01 users
- P02 SSH access must be restricted to authorised IP addresses or key-based authentication
- S01 API tokens must be scoped to minimum required permissions and revocable


## Component Model

### Logical Components

```mermaid
flowchart TD
    FE[Frontend\nWeb Client]
    BE[Backend\nApplication]
    DB[(Relational\nDatabase)]
    MAIL[Email / Notification\nService]

    FE -->|HTTP/HTTPS| BE
    BE -->|SQL| DB
    BE -->|SMTP / API| MAIL
```

| Component | Responsibility |
|---|---|
| **Frontend Web Client** | Server-rendered HTML pages (Jinja2 templates) with vanilla JS/jQuery for interactivity. Served directly by the Flask application. Optimised for desktop and mobile. |
| **Backend Application** | Python Flask application. Implements all business logic, RBAC, event lifecycle, assignment management, credential matching, notification triggers, audit logging, scheduled tasks. Serves the web UI via Jinja2 templates and will expose a REST API (future). Uses SQLAlchemy as the ORM. |
| **Relational Database** | PostgreSQL. Persistent storage for all domain data: users, roles, credentials, master events, events, event spots, assignments, equipment, audit log, notification settings, debriefing records. |
| **Email / Notification Service** | Outbound email delivery: invite links, account activation, password reset, event notifications/reminders, admin digests, debriefing links. May be an external SMTP relay or third-party email API. |


## Runtime / Interaction View

### Event Lifecycle State Machine

```mermaid
flowchart LR
    S(( )) --> Draft --> Published --> AO[Assignments Open] --> AC[Assignments Closed] --> Completed --> E(( ))
    AC -->|re-open| AO
    Draft & Published & AO & AC -->|cancel| Cancelled
    Cancelled -->|restore| Draft
```

**Notes:**
- Cancelled Events are **archived** (hidden from default views, not deleted). Admins can permanently delete archived Events.
- A Completed or Cancelled Event can serve as the basis for creating a new Event (copy/template flow).
- Staffing status (Not staffed / Partially staffed / Fully staffed / Overstaffed) is a **derived** status updated whenever assignments change; it is not a separate lifecycle state.

### Automatic Transitions (Background Processing)
The following transitions require a scheduled background job or task:
- **Published → Assignments Open**: triggered at the configured `assignments_open_at` datetime
- **Assignments Closed → Completed**: triggered after the Event `end_datetime`
- **Urgent fill notification**: reminder emails sent to eligible users at each offset in the Event's reminder schedule

The following happen in real time as a side effect of a user action:
- **RP pre-fill on Event creation**: when an Event is created inside a custom ME, the ME coordinator is automatically set as the initial RP; the coordinator or admin can later change this
- **RP auto-assignment (General ME)**: when the first user holding a First Aider (or higher) credential registers for an Event that has no RP yet, they are automatically set as the RP
- **Assignments auto-close**: when the last unfilled spot is taken, lifecycle transitions to Assignments Closed
- **Staffing status update**: recalculated whenever an Assignment is added or removed

### Spot Selection at Assignment Time
An Event requires 1 Doctor, 1 Driver/First Aider and 1 First Aider. A user who holds both Doctor and Driver credentials must explicitly choose which spot they are filling when registering. The system shall present only the spots the user is eligible for and require a selection before confirming the assignment.

### User Registration Flow
```mermaid
sequenceDiagram
    actor Admin
    actor User
    participant App
    participant Email

    Admin->>App: generate invite link (enters email)
    App->>Email: send invite email with unique token link
    Email->>User: receives invite link
    User->>App: opens link, fills registration form
    App->>App: create inactive account
    App->>Admin: notify admin of pending activation
    Admin->>App: review and activate account
    App->>Email: send account activated email
    Email->>User: receives confirmation, can now log in
```

### Event Assignment Flow
```mermaid
sequenceDiagram
    actor Member
    participant App
    participant Email
    actor RP

    Member->>App: browse events (table or calendar)
    Member->>App: select Event, view open spots
    App->>App: filter spots eligible for Member's credentials
    Member->>App: choose spot (select credential if multiple eligible)
    App->>App: record Assignment, update staffing status
    App->>Email: notify RP of new assignment
    Email->>RP: "Member X has joined your Event"
    opt all spots filled
        App->>App: auto-close assignments
        App->>Email: notify RP assignments are closed
    end
```

### Spot Release Flow
```mermaid
sequenceDiagram
    actor Member
    participant App
    participant Email
    actor RP
    actor EligibleUsers

    Member->>App: release Assignment
    App->>App: remove Assignment, update staffing status
    App->>Email: notify RP of released spot
    App->>Email: notify all eligible users of open spot
    Email->>RP: "A spot on your Event has been freed"
    Email->>EligibleUsers: "A spot is available on Event X"
```

### Post-Event Debriefing Flow
```mermaid
sequenceDiagram
    participant Scheduler
    participant App
    participant Email
    actor Member

    Scheduler->>App: Event end_datetime passes
    App->>App: transition Event to Completed
    loop for each assigned Member
        App->>Email: send personalised debriefing link
        Email->>Member: receives debriefing email
    end
    Member->>App: opens link, fills debriefing form
    Member->>App: submit (actual hours, patients, materials, notes)
    App->>App: store DebriefingRecord
```



## Data View

### Core Domain Model

```mermaid
erDiagram
    UserAccount }o--o{ Role : "assigned to"
    Role }o--o{ Permission : "has"
    UserAccount }o--o{ Credential : "holds"
    Credential }o--o{ Credential : "parent of (hierarchy)"

    MasterEvent ||--o{ Event : "contains"
    Event ||--o{ EventSpot : "has"
    EventSpot }o--o{ Credential : "requires"
    EventSpot ||--o| Assignment : "filled by"
    Assignment }o--|| UserAccount : "assigned to"

    EventTemplate ||--o{ EventSpotTemplate : "defines"
    EventSpotTemplate }o--o{ Credential : "requires"

    EquipmentItem }o--|| EquipmentType : "is of"
    EquipmentItem }o--o| UserAccount : "issued to (personal)"
    EquipmentItem ||--o{ EventEquipmentAssignment : "assigned via"
    EventEquipmentAssignment }o--|| Event : "at"

    EventEquipmentRequirement }o--|| Event : "for"
    EventEquipmentRequirement }o--|| EquipmentType : "requires type"

    DebriefingRecord }o--|| Event : "for"
    DebriefingRecord }o--|| UserAccount : "submitted by"

    RegistrationInvite }o--|| UserAccount : "created by (admin)"
    AuditLogEntry }o--|| UserAccount : "performed by"
```

### Key Entities and Their Data

| Entity | Key attributes | Notes |
|---|---|---|
| **UserAccount** | email, password hash, name, phone, active flag, preferred_calendar_view | Email = login identifier; accounts inactive until admin-activated |
| **Role** | name, description | Pre-defined: Admin, Coordinator, Member, Viewer |
| **Permission** | code (e.g. `event.create`) | Object-level permissions assigned to roles |
| **Credential** | name, description, parent credentials | Unified model for medical qualifications and training certifications |
| **MasterEvent** | name, description, coordinator, archived flag | Default "General" ME always exists and cannot be archived |
| **Event** | name, start/end datetime, lifecycle status, staffing status, assignments_open_at, paid flag, contact, address | Belongs to a MasterEvent |
| **EventSpot** | required credentials (list), assignment | One spot = one person |
| **Assignment** | user, spot, selected credential | Records which credential the user is covering for this spot |
| **EventTemplate** | name, description, spot templates | Pre-populates Event creation form |
| **EventSpotTemplate** | event template, required credentials (list) | Defines one spot position within an EventTemplate |
| **EquipmentType** | name, description, category (personal / shared) | Defines a category of equipment (e.g. AED, medikit, uniform) |
| **EquipmentItem** | name, type, home location | For *personal* items: issued_to (UserAccount); for *shared* items: assignable to Events via EventEquipmentAssignment |
| **EventEquipmentRequirement** | event, equipment type, quantity required | Coordinator specifies how many of each shared type are needed for an Event |
| **EventEquipmentAssignment** | event, equipment item | Records which specific shared items were actually brought to an Event |
| **DebriefingRecord** | event, user, actual hours, patients treated, materials used, notes | Submitted after Event completion; one record per assigned user |
| **RegistrationInvite** | token, email, created by, expires at, used flag | Invite-only registration; single-use link |
| **AuditLogEntry** | timestamp, actor (user), action, entity type, entity id, change detail | Immutable; records all significant changes |

### Data Store
- Single **relational database**: **PostgreSQL** (see AD04)
- All domain data is stored in one database; no separate read replicas or caches planned for MVP
- Audit log is append-only and stored in the same database

### Retention and Privacy
- Personal data (name, email, phone) is subject to GDPR as the organisation operates in the Czech Republic
- Audit log entries are retained indefinitely (required for accountability)
- Event and debriefing data: retained indefinitely for statistical purposes
- Equipment records: retained while items exist in inventory
- Backup retention: 60 days (as stated in Non-Functional Requirements)


## Integration Model

### Outbound Email
- The backend sends all email via an **external SMTP relay** (e.g. SendGrid, Mailgun, AWS SES, or the organisation's own SMTP server)
- Communication: SMTP (port 587/465) or provider HTTP API
- Use cases: user invite links, account activation, password reset, event notifications/reminders, admin digest emails, post-event debriefing links
- Failure handling: email delivery failures shall be logged; critical flows (invite, password reset) should surface errors to the admin/user where possible

### REST API (External Integration)
- The backend shall expose a **REST API** to allow future integration with other systems (S01)
- Protocol: HTTPS, JSON payloads
- Authentication: token-based (e.g. API key or OAuth2 bearer token) — mechanism TBD
- Scope for initial release: read-only access to events and assignments; write access may be added later
- The REST API is **optional / not required** for the initial MVP


## Deployment Model

### Environments

| Environment | Purpose | Notes |
|---|---|---|
| **Development** | Local developer machines; rapid iteration and testing | Docker Compose (Flask + PostgreSQL containers); `.env` for secrets |
| **Staging** | Pre-production validation; testing changes before release | Same Docker image as production; deployed on Render (free tier) |
| **Production** | Live system serving real users | Render.com free tier (MVP); hyperscaler with NGO credits long-term — see AD09 |

### Hosting Platform
- **MVP**: Render.com — native Docker support, free tier (Flask container + managed PostgreSQL 256 MB), auto-deploy from GitHub. See AD09.
- **Long-term**: Azure Container Apps or Google Cloud Run using NGO non-profit credits (Czech Red Cross qualifies). Same `Dockerfile` used — no application changes required to migrate.
- **CI/CD**: GitHub Actions builds the Docker image on push to `main`; platform pulls and deploys automatically.

### HA / DR Topology
- No high-availability redundancy planned for MVP (single-server deployment acceptable given the non-critical nature and low cost constraint)
- Recovery targets (from Non-Functional Requirements): RPO 1 day, RTO 12 hours

### Backup and Restore
- Daily automated database backups, 60-day retention
- Backup storage shall be on a separate system from the production server
- Restore procedure shall be documented and tested

### Monitoring, Logging and Alerting
- **Application logs**: errors, warnings, and significant events logged to file or a centralised log store
- **Uptime monitoring**: external uptime check (e.g. UptimeRobot or equivalent) to detect service unavailability
- **Alerts**: email notification to admins on application errors or service downtime
- Advanced observability (metrics, tracing, dashboards) is out of scope for MVP

### Patching and Maintenance
- Application and OS updates applied by the infrastructure administrator (P02)
- No automated rolling updates; maintenance windows acceptable given the user base and usage patterns



### Role Based Access Control (RBAC)
The application will be built using the RBAC concept where User Accounts will be assigned to one or more Roles.  
A Role will be assigned to Permissions. (A Role is a set of permissions)  
For example an User Account assigned to the Admin role will have all the permissions of this role, allowing the User to administer the whole application. Multiple User Accounts can be assigned to a Role, one User Account can be assigned to multiple Roles.

**Responsible Person (RP)** is not a separate Role but a contextual responsibility assigned to a specific user for a specific Event. The RP gains a small set of additional permissions scoped to their Event (see table note below).

### Permissions

| Permission | Admin | Coordinator | Member | Viewer |
|---|:---:|:---:|:---:|:---:|
| **Users** | | | | |
| user.view | ✓ | ✓ | ✓ | ✓ |
| user.edit_own | ✓ | ✓ | ✓ | ✓ |
| user.edit_any | ✓ | — | — | — |
| user.activate / deactivate | ✓ | — | — | — |
| user.assign_role | ✓ | — | — | — |
| user.assign_credential | ✓ | — | — | — |
| invite.create | ✓ | — | — | — |
| **Credentials** | | | | |
| credential.view | ✓ | ✓ | ✓ | ✓ |
| credential.create / edit / delete | ✓ | — | — | — |
| **Master Events** | | | | |
| master_event.view | ✓ | ✓ | ✓ | ✓ |
| master_event.create / edit | ✓ | ✓ | — | — |
| master_event.archive / unarchive | ✓ | — | — | — |
| **Events** | | | | |
| event.view (Published and later) | ✓ | ✓ | ✓ | ✓ |
| event.view (Draft) | ✓ | ✓ | — | — |
| event.create / edit | ✓ | ✓ | — | — |
| event.publish | ✓ | ✓ | — | — |
| event.assignments.open / close | ✓ | ✓ | RP* | — |
| event.cancel / restore | ✓ | ✓ | — | — |
| event.delete (archived, permanent) | ✓ | — | — | — |
| event.assign_own (join / leave) | ✓ | ✓ | ✓ | — |
| event.assign_other | ✓ | ✓ | — | — |
| event.set_responsible_person | ✓ | ✓ | — | — |
| event.notification.send (manual) | ✓ | ✓ | RP* | — |
| **Event Templates** | | | | |
| event_template.view | ✓ | ✓ | ✓ | ✓ |
| event_template.create / edit / delete | ✓ | ✓ | — | — |
| **Equipment** | | | | |
| equipment.view | ✓ | ✓ | ✓ | ✓ |
| equipment_type.create / edit / delete | ✓ | — | — | — |
| equipment_item.create / edit / delete | ✓ | — | — | — |
| equipment_item.issue_personal (assign/unassign personal item to a member) | ✓ | — | — | — |
| equipment_item.report_own (member self-reports status of their own issued personal items) | ✓ | ✓ | ✓ | — |
| event.equipment.plan (set required equipment types + quantities on an Event) | ✓ | ✓ | — | — |
| event.equipment.assign (record which specific shared items were brought to an Event) | ✓ | ✓ | — | — |
| **Debriefing** | | | | |
| debriefing.submit_own | ✓ | ✓ | ✓ | — |
| debriefing.view_own | ✓ | ✓ | ✓ | — |
| debriefing.view_all | ✓ | ✓ | — | — |
| **Reports** | | | | |
| report.view | ✓ | ✓ | ✓ | ✓ (limited) |
| **Audit** | | | | |
| audit.view | ✓ | — | — | — |

*\*RP (Responsible Person)* — a Member who is the RP of an Event gains `event.assignments.open`, `event.assignments.close`, and `event.notification.send` scoped to that specific Event only.


### Application Components / Classes

#### User Account
- description: represents a person with access to the application
- properties
    - email address - serves as the login identifier; can be changed by admin only
    - password hash - used for authentication; can be changed by the user or admin
    - name and surname - including title
    - phone number
    - roles - list of assigned Roles; assigned by admin only
    - credentials - list of assigned Credentials
    - active flag - inactive until admin-activated after registration
    - preferred_calendar_view — preferred calendar view for desktop (month / week / day / list); list view is always used on mobile regardless of this setting
- methods
    - assign / unassign role
    - assign / unassign credential
    - list upcoming events
    - get statistics (hours worked, events attended, etc.)

#### Role
- description: a grouping of assigned permissions
- properties
    - role name
    - role description
    - permissions
- methods
    - list permissions
    - assign permission
    - unassign permission
    - list users
    - etc.

#### Credential
- description: A unified entity representing both medical qualifications (Doctor, Nurse, First Aider, Trainee) and additional certifications (Driver, PSP training, KI training, etc.). Credentials form a directed hierarchy tree: a holder of a higher-ranked Credential can fill any spot that requires a lower-ranked one in its ancestry (see AD07).
- properties
    - name
    - description — conditions for obtaining it and/or what it entitles the holder to do
    - parent credentials — list of Credentials whose holders can substitute this one (e.g. Doctor can fill a First Aider spot → Doctor is a parent of First Aider)
- methods
    - list holders
    - list subordinate credentials (credentials this one can substitute for)
    - etc.

#### Master Event
- description: An overarching entity that groups related Events (dozory). Exists to support large or multi-day happenings (e.g. music festivals, sports tournaments) that span multiple locations or time slots. A built-in "General" Master Event is always present and acts as the default container for all standalone Events. Yearly and other time-period statistics are obtained via date-range filtering, not through ME hierarchy.
- properties
    - name
    - description
    - coordinator (user responsible for the ME)
    - archived flag — when set, the ME is hidden from default views but remains available for historical reporting; the built-in "General" ME cannot be archived
    - events - list of Events belonging to this ME
- methods
    - list events
    - get staffing overview (assignment status, worked hours, counts of Completed / open / cancelled events)
    - when an Event is created within this ME, the ME coordinator is automatically pre-filled as the RP of that Event; the coordinator (or admin) can later reassign the RP slot to another eligible member

#### Event Spot
- description: a position in an Event that can be filled by exactly one person. The person must hold all required Credentials (or higher-ranked equivalents per the Credential hierarchy).
- properties
    - event ID - the Event this spot belongs to
    - required credentials - list of required Credentials
    - assignment - the Assignment filling this spot (null if unfilled)
- methods
    - check eligibility (given a user, returns whether they can fill this spot)
    - assign user
    - release assignment

#### Event
- description: AKA "Zdravotní dozor" - a calendar event with a start, end and other properties that allow medical cover planning for a happening such as a music festival, sports or cultural happening where medical cover is requested.
- properties
    - parent ME - a Master Event this Event belongs to. By default, it should be the Default ME, unless a different ME is specified
    - name - name of the event, not unique
    - ID - unique, to be used to reference the Event
    - lifecycle status
        - Draft
        - Published
        - Assignments Open
        - Assignments Closed
        - Completed
        - Cancelled
    - staffing status
        - Not staffed
        - Partially staffed
        - Fully staffed
        - Overstaffed
    - spots - list of Event Spots
    - number of Patrols - an abstract unit used to calculate required staffing levels; does not model on-site organization. One Patrol typically maps to one First Aider and one Trainee. For more complex on-site requirements, multiple Events or a Master Event should be used instead.
    - start datetime
    - end datetime
    - assignments_open_at - datetime when Assignments Open is triggered automatically; null = open immediately on Publish
    - reminder_schedule — list of offsets before Event start (e.g. [1 day]) at which unfilled-spot reminder emails are sent to eligible users; inherited from template, editable by coordinator/admin
    - responsible person - assigned User Account (RP)
    - required equipment - list of `EventEquipmentRequirement` entries (equipment type + quantity needed)
    - paid flag - whether the Event is a paid engagement
    - contact person - name and contact details for the Event organiser
    - address - location of the Event
- permissions
    - event.create
    - event.edit
    - event.view
    - event.assign_own
    - event.assign_other
    - event.cancel
    - event.restore
    - event.delete
    - event.notification.send
    - event.set_responsible_person
    - event.publish
    - event.assignments.open
    - event.assignments.close

#### Event Template
- description: A reusable set of Event parameters (spots, required qualifications/trainings, required equipment, paid/unpaid flag, etc.) that pre-populates the Event creation form to reduce repetitive data entry. All pre-filled values remain fully editable before the Event is saved.
- properties
    - template name
    - description
    - default spots (list of Event Spot templates with Credential requirements)
    - default required equipment
    - paid / unpaid flag
    - reminder schedule — list of offsets before Event start (e.g. [7 days, 1 day]) at which unfilled-spot reminder emails are sent
    - any other Event parameters that may be pre-set
- methods
    - create Event from template
    - etc.

#### Assignment
- description: records that a specific user is filling a specific Event Spot, and which Credential they are covering for that spot.
- properties
    - event spot ID
    - user account ID
    - credential used - the specific Credential the user is fulfilling for this spot (selected at assignment time)
    - assigned at - timestamp

#### DebriefingRecord
- description: post-event report submitted by an assigned member after an Event is Completed.
- properties
    - event ID
    - user account ID
    - actual hours worked - may differ from the planned Event duration (partial attendance supported)
    - patients treated
    - materials used - free-text description of medical materials consumed (bandages, gloves, etc.); structured equipment assignment is tracked separately via EventEquipmentAssignment
    - notes / feedback
    - submitted at - timestamp

#### EquipmentType
- description: a category of physical equipment (e.g. AED, medikit, large medikit, training dummy, uniform, personal LED light).
- properties
    - name
    - description
    - category — `personal` (long-term issued to a member) or `shared` (pool of items assignable to Events)

#### EquipmentItem
- description: a specific physical item belonging to an EquipmentType.
- properties
    - name (e.g. AED-1, AED-red, uniform-42)
    - equipment type
    - home location — where the item belongs when not in use
    - **For personal items**: `issued_to` — UserAccount the item is currently assigned to (long-term); null if in storage
    - **For shared items**: assignable to Events via EventEquipmentAssignment; home location is the default storage point

#### EventEquipmentRequirement
- description: specifies how many items of a given shared EquipmentType are needed for an Event (the plan).
- properties
    - event ID
    - equipment type
    - quantity required

#### EventEquipmentAssignment
- description: records that a specific shared EquipmentItem was actually brought to and used at an Event (the actuals).
- properties
    - event ID
    - equipment item


## Ideas for future
- Feature to manage not only medical cover but also medical training Events with its specific requirements
- In-app notifications (notification bell / inbox in the UI) — email only for MVP
- Create a new Event from a Cancelled or Completed Event (copy/reuse as a starting point)
- Custom user roles (currently only pre-defined roles per AD01)
- REST API write access for third-party integrations
- Advanced reporting / statistics dashboard beyond per-user and per-ME summaries
