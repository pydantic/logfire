
As a Logfire user, you can be part of multiple organizations, and each organization can have multiple projects.

There are two types of organizations:

* **Personal organizations**: this is the default organization created when you sign up. You are the owner of this organization,
  but can invite other people.
* **Normal organizations**: these can be created separately from the personal one.

Both organization types are functionally equivalent and you can invite others to all of them.

Multiple projects can be created in organizations, and they can be either _public_ (within the organization) or _private_ (see [roles](#roles) below).
Depending on the user's organization role, they may have implicit access to the organization projects.

## Which organization type should I use?

While you _can_ use your personal org for production use-cases (e.g. if you
are working alone or in a small team), you may wish to switch your personal org to a normal org if you are working
at a larger company and want to create a more "official" Logfire org for that company. This also means you don't have
to share your personal org's projects (which you may wish to keep private) with any colleagues.

**See the [step-by-step guide to converting your personal account to an organization](../../how-to-guides/convert-to-organization.md) for screenshots and detailed instructions.**

## Roles

Logfire provides a fixed set of _organization_ and _project_ roles, that can be managed in the organization settings. Roles contain a set of permissions,
and are assigned to team members either at the organization or project level.

### Organization roles

Every user in your organization has an organization role assigned. They contain **organization** permissions (e.g. `create_project`),
as well as **project** permissions (e.g. `read_dashboard`), which apply to projects the user have access to (unless they have an explicit
project role on some projects).

Three organization roles are available:

<!-- Note: Using https://github.com/fralau/mkdocs-macros-plugin would have helped in moving the SVGs out of the table, but we already make use of the `{{ }}` syntax for custom replacements.. -->

| Role                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | Description                                                                           | Project access              | Editable |
|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|-----------------------------|----------|
| <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-crown-icon lucide-crown"><path d="M11.562 3.266a.5.5 0 0 1 .876 0L15.39 8.87a1 1 0 0 0 1.516.294L21.183 5.5a.5.5 0 0 1 .798.519l-2.834 10.246a1 1 0 0 1-.956.734H5.81a1 1 0 0 1-.957-.734L2.02 6.02a.5.5 0 0 1 .798-.519l4.276 3.664a1 1 0 0 0 1.516-.294z"/><path d="M5 21h14"/></svg> **Admin** | Gives all permissions. This is the role assigned to you when creating an organization | Public and private projects | ❌        |
| <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-user-icon lucide-user"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>**Member**                                                                                                                                                                        | Has a specific set of organization and project permissions, which can be changed.     | Public projects             | ✅        |
| <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-eye-icon lucide-eye"><path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/></svg> **Guest**                                                                                                             | Assigned to users when they are invited directly to a project of the organization.    | None                        | ❌        |


### Project roles

When a user is part of an organization, they have access to the projects of that organization according to the project access policy described in the organization roles table.

However, users can also be invited directly to a project, in which case a project role is being assigned to them (and they are added to the organization as guests). Of course,
it is possible to assign a specific project role to an existing organization user, in which case the project permissions from their organization role will *not* apply.

Three project roles are available:

| Role                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | Description                                                     | Editable |
|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------|----------|
| <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-crown-icon lucide-crown"><path d="M11.562 3.266a.5.5 0 0 1 .876 0L15.39 8.87a1 1 0 0 0 1.516.294L21.183 5.5a.5.5 0 0 1 .798.519l-2.834 10.246a1 1 0 0 1-.956.734H5.81a1 1 0 0 1-.957-.734L2.02 6.02a.5.5 0 0 1 .798-.519l4.276 3.664a1 1 0 0 0 1.516-.294z"/><path d="M5 21h14"/></svg> **Admin** | Gives all permissions.                                          | ❌        |
| <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-pen-icon lucide-pen"><path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/></svg> **Write**                                                                                                                 | Has a specific set of *edit* permissions, which can be changed. | ✅        |
| <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-book-open-icon lucide-book-open"><path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/></svg> **Read**                                                                                | Has only *read* permissions.                                    | ❌        |

### Custom roles and externally managed teams

Organizations using the [entreprise plan](../../enterprise.md) have the ability to create custom roles (on top of the existing ones), as well
as using external identity and access management providers such as [Microsoft Entra ID](https://www.microsoft.com/en-us/security/business/identity-access/microsoft-entra-id).
