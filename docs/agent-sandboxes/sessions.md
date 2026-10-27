---
title: "Persist, resume, snapshot, and fork Agent Sandbox sessions"
description: "Pause and resume sandbox sessions, take snapshots as checkpoints, fork a session into branches, and use ephemeral sessions."
---

# Persist, resume, and fork sessions

!!! info "Experimental"
    Agent Sandboxes is available to selected Logfire organizations. See [access and availability](index.md).

Pick up an agent's sandbox where it left off, from a new connection or a different process.
Python client sessions are **persistent** by default: Logfire saves each session's state under a session ID, and you can
start a new session from that state later.
You can also take a **snapshot** (a saved copy of a session's state at one moment) and start several sessions from it,
which forks the session into independent branches.

This page assumes you have [run code from Python](python.md) already.
The [Workbench](workbench.md#continue-after-a-reload) also saves Python state and offers browser controls to continue or load it.
Use [Snapshots](snapshots.md) to find saved state and manage its storage in the web UI.

## What is saved

A session's saved state is the memory of its Python interpreter: the global variables, functions, and classes that
earlier `feed_run()` calls defined.
A restored session also keeps the script name, resource limits, and type-checking settings it was created with.
The options you pass to `checkout()` for the restoring session don't override them.

A session runs in an interpreter, not a virtual machine, so there are no processes, open network connections, or root
filesystem to save.

These are not saved:

- Anything on your side of the connection.
  Host functions, `print_callback`, and mounted host directories are passed again with each call.
- Files in mounted host directories.
  They stay on your machine.
- Files in hosted [volumes](volumes.md).
  These files persist separately. A restored snapshot sees their current contents.
- Objects that belong to your application.
  A `ClassInstance` passed into the sandbox comes back as a stand-in after a restore, and calling its methods fails.

## When a session is saved

The server saves a session's state, which Monty calls **parking** the session, in these cases:

- **The session is idle for 60 seconds.** The server releases the sandbox and keeps your connection open.
  Your next call loads the state into a new sandbox under the same session ID, so your code sees no difference apart
  from a short delay on that call.
  This is the equivalent of an automatic pause and resume after an idle timeout.
  A parked session doesn't hold a sandbox, so you can keep more sessions open than there are sandboxes running.
- **Your application closes the connection**, or stops answering keepalive pings for about 10 seconds.
  The state is saved under the session ID, and you can [resume it](#resume-a-session-from-a-new-connection) later.
- **The server is being redeployed.** With `auto_resume=True` (the default), the client reconnects, loads the session on
  another server, and repeats the call that was interrupted.
  If that fails, the call raises `MontyShutdown`.
- **The connection reaches its 1-hour limit while idle.** The client resumes the session on a new connection on its next
  call.

Saved sessions and snapshots are kept for 7 days after they're saved, then deleted.
They count toward your organization's snapshot storage quota.

!!! warning "Session state is stored by Logfire"
    The values your sandbox code creates, including anything computed from
    inputs or host function results, are stored on Logfire's servers for up to 7 days.
    Use an [ephemeral session](#opt-out-of-storage-with-ephemeral-sessions) if state must not be stored.

## Resume a session from a new connection

Read `session.session_id` while the session is open.
It is a 16-byte universally unique identifier (UUID).
Store it wherever your application keeps the agent's conversation state, such as a database row.

To resume, check out a new session and pass the ID to `load_session()`:

```python skip-run="true" skip-reason="external-connection"
import asyncio
import uuid

import logfire

logfire.configure()


async def first_turn() -> str:
    async with logfire.agent_sandboxes() as pool:
        async with pool.checkout() as session:
            await session.feed_run('total = 40')
            return str(uuid.UUID(bytes=session.session_id))


async def later_turn(session_id: str) -> None:
    async with logfire.agent_sandboxes() as pool:
        async with pool.checkout() as session:
            await session.load_session(uuid.UUID(session_id).bytes)
            print(await session.feed_run('total + 2'))  # 42


async def main():
    session_id = await first_turn()
    await later_turn(session_id)


asyncio.run(main())
```

The resumed session gets a **new** session ID.
`load_session()` copies the saved state into the new session and never reattaches to the old one, so the record you
loaded is unchanged.
To resume again later, store `session.session_id` from the new session.

Loading a session ID gives you the state as of that session's last save.
That is the state when the connection closed, unless the server stopped without saving, for example after a crash.
If you need a guaranteed restore point, take a snapshot.

The server saves the session as the connection closes, which takes a moment.
`load_session()` raises `MontyRuntimeError: unknown session` if you call it before the save completes.

## Take a snapshot as a checkpoint

`session.dump()` saves the session's current state and returns a snapshot ID.
The session carries on under its own session ID.

A snapshot never changes after it's taken.
Use snapshots as checkpoints, for example before the agent runs code that may leave the session's state broken, or
before each step of a multi-step task.
To roll back, load the snapshot in a new session:

```python skip-run="true" skip-reason="external-connection"
import asyncio

import logfire

logfire.configure()


async def main():
    async with logfire.agent_sandboxes() as pool:
        async with pool.checkout() as session:
            await session.feed_run('items = [1, 2, 3]')
            checkpoint = await session.dump()
            await session.feed_run('items.clear()')

        async with pool.checkout() as restored:
            await restored.load_session(checkpoint)
            print(await restored.feed_run('items'))  # [1, 2, 3]


asyncio.run(main())
```

`dump()` also works while code is paused waiting on a host function, if you drive execution with `feed_start()`.
Restore that kind of snapshot with `load_snapshot()` instead of `load_session()`.

## Fork a session into branches

Each `load_session()` call starts a new, independent session, so loading one snapshot ID in several sessions forks it
into branches from the same starting point.
Changes in one branch are not visible in the others.

```python skip-run="true" skip-reason="external-connection"
import asyncio

import logfire

logfire.configure()


async def main():
    async with logfire.agent_sandboxes() as pool:
        async with pool.checkout() as session:
            await session.feed_run('items = [1]')
            base = await session.dump()

        async def branch(value: str) -> str:
            async with pool.checkout() as fork:
                await fork.load_session(base)
                await fork.feed_run(f'items.append({value!r})')
                return await fork.feed_run('repr(items)')

        print(await asyncio.gather(branch('a'), branch('b')))  # ["[1, 'a']", "[1, 'b']"]


asyncio.run(main())
```

Forking lets an agent try several approaches from the same state and keep the best one.
It also lets you run an expensive setup once and start many tasks from it.
A branch can be snapshotted and forked again.

## Opt out of storage with ephemeral sessions

Pass `ephemeral=True` to `checkout()` to prevent saved interpreter state:

```python skip-run="true" skip-reason="external-connection"
import asyncio

import logfire

logfire.configure()


async def main():
    async with logfire.agent_sandboxes() as pool:
        async with pool.checkout(ephemeral=True) as session:
            await session.feed_run('secret = 42')


asyncio.run(main())
```

An ephemeral session has no session ID (`session.session_id` is `None`).
`dump()` raises `MontyRuntimeError: this session is ephemeral, so it cannot be dumped`.
The server discards the interpreter state when the connection closes or the server is redeployed.
Ephemeral sessions still send code and data to Logfire for execution. They can also produce recorded telemetry.
See [tracing controls](limits.md#control-client-tracing).

## Saved state is not durable execution

Agent Sandboxes save and restore **state**.
They don't record or replay your application's code.
Durable execution and workflow engines keep a history of each step and re-run your code after a failure, skipping the
steps that already finished.
Agent Sandboxes don't do that: if your application crashes, nothing continues on its own.
When your application restarts, it can load the saved session ID or a snapshot and continue from that state.

Restoring a session also doesn't undo the effects of host function calls.
If sandbox code called a host function that sent an email, restoring a snapshot taken before that call doesn't unsend
it.

## Terms used for these features

Other sandbox and agent platforms use different names for the same ideas.
This is how they apply to Agent Sandboxes:

- **Persistence, persistent sessions**: the default.
  Every session is saved unless it's ephemeral.
- **Pause and resume, suspend, hibernate, auto-pause, idle timeout**: parking.
  A session is parked after 60 seconds idle and resumes on the next call, with its memory state intact and the same
  session ID.
  After a disconnect, resuming with `load_session()` gives a new session ID.
- **Snapshot, checkpoint, memory snapshot**: `dump()`.
  The snapshot holds interpreter memory: variables, functions, and classes.
  There is no filesystem snapshot, because a session has no filesystem of its own.
- **Restore, roll back**: `load_session()` with a snapshot ID.
  The snapshot and the session it came from are never overwritten.
- **Fork, branch, clone**: calling `load_session()` with the same ID in several sessions.
- **Ephemeral, non-persistent**: `checkout(ephemeral=True)`.
- **Retention, expiration, time to live (TTL)**: 7 days from when the state was saved.
- **Live migration, failover**: `auto_resume`, which moves a session to another server during a redeploy.

## Troubleshooting

- **`MontyRuntimeError: unknown session` from `load_session()`**: the ID isn't a saved session or snapshot in this
  project.
  Check that:
    - the API key belongs to the same project that created the session;
    - the session or snapshot was saved less than 7 days ago;
    - the original session's connection has finished closing.
      Retry after a short delay.
- **`MontyRuntimeError` from `dump()` on an ephemeral session**: ephemeral sessions can't be saved.
  Check out the session without `ephemeral=True`.
- **`MontyShutdown` raised during a call**: the server was redeployed and resuming the session on another server failed.
  Load `session.session_id` in a new session to continue from the last saved state.

## Next steps

- [Run code from Python](python.md): pool options, host functions, and tracing.
- [Agent Sandboxes overview](index.md): when to use sandboxes, and when not to.
