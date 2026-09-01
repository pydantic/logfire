---
title: "Session Replays"
description: "Replay a user's browser session alongside navigation, network, console, and Logfire trace data."
---
# Session Replays

Use <OpenInLogfire path="frontend/session-replays" variant="inline" label="Session Replays" /> to reproduce what a user saw, then connect the recording to browser errors, failed requests, and the matching Logfire spans.

A session replay records changes to the page's document structure and user interactions. Logfire reconstructs those events in a player. It does not store a video stream.

!!! note "Experimental"

    Open **Settings → Early access**, choose **Show experimental features**, and enable **Frontend observability**. The same setting enables the Frontend and Session Replays pages.

## Record sessions

1. Create a frontend application under **Project settings → Frontend applications** and add its generated browser setup to your application.
2. Install the optional `@pydantic/logfire-session-replay` package.
3. Follow the [Session Replay setup](https://pydantic.dev/docs/logfire/instrument/typescript/packages/browser/#session-replay) to load the recorder and configure the replay endpoint.
4. Deploy the change, open the application, and interact with more than one page or control.

Replay data is sent to and stored in your Logfire project. The recorder masks rendered text and input values by default, leaves console capture off, and removes query strings and fragments from captured URLs. Those defaults do not redact document attributes, CSS-generated content, resource URLs, or custom-event payloads. Review the [privacy controls](https://pydantic.dev/docs/logfire/instrument/typescript/packages/browser/#session-replay) before recording pages that contain sensitive data.

## Find a useful recording

The list shows the entry page, user identity when available, last page, activity counts, duration, and start time. Use the time range, duration, error-only, and text filters to narrow the list. The search matches users, pages, and session identifiers.

Open a recording to inspect:

- **Playback**, including idle-period skipping and activity markers.
- **Activity**, such as navigation, clicks, and input activity.
- **Network**, including failed and incomplete requests.
- **Console**, when the application explicitly enables console capture.
- **Session and browser context**, including URLs, environment, application version, country, language, and platform when those values were retained.
- **Browser telemetry**, with a link to every span from the same browser session in Live view.

The event rows are synchronized with playback. Select an activity, network request, or console entry to seek to that point in the recording.

## Verify a recording

After using the instrumented application, open **Frontend → Session Replays** and include the session's start time in the selected range. You should see the entry page and activity counts. Open the row and confirm that playback and the activity list advance together.

## Fix missing or incomplete recordings

| Symptom | What to check |
|---------|---------------|
| **No replays yet** | Confirm the optional replay package loads, the replay endpoint accepts the frontend application token, and the browser did not block the request. |
| A recording stops early | Some replay chunks failed to upload or download. Check browser network failures and retry from the replay page. |
| The recording is playable but browser telemetry is empty | Confirm browser spans and replay chunks share the same application setup and browser session. Also check the project's retention and sampling configuration. |
| Text is missing from playback | Text and input masking is on by default. Change masking only after reviewing what the page may expose. |
