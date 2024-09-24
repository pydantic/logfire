The following diagram shows the structure of an organization in **Logfire**:

```mermaid
classDiagram
  Organization <-- OrganizationMember
  User <-- OrganizationMember
  User <-- ProjectMember
  Organization <-- Project
  Project <-- ProjectMember

  class Organization {
    UUID id
    string name
  }

  class User {
    UUID id
    string name
  }

  class OrganizationMember {
    UUID user_id
    UUID organization_id
    string role ['admin', 'member', 'guest']
  }

  class Project {
    UUID id
    UUID organization_id
    string name
  }

  class ProjectMember {
    UUID user_id
    UUID project_id
    string role ['admin', 'member']
  }
```

As a **user**, you can be a member of multiple **organizations**. On each **organization**, you can either be:

- [X] An **admin**: who can manage the organization and its projects.
- [X] A **member**: who can only view the organization and the projects that are shared with them.
- [X] A **guest**: who can only view the projects that are shared with them.

An **admin** can invite other users to join the organization.
When a user accepts the invitation, they become a **member** of the organization.

Each **organization** can have multiple **projects**. On each **project**, you can either be:

- [X] An **admin**: who can manage the project.
- [X] A **member**: who can only view the project.

If a user is invited to join a project, they become a **member** of the project, but they are a **guest** in the organization.
