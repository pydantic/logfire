---
title: "Solo builder: just me and my app"
description: "The fastest path from zero to seeing your own app in Logfire: install Logfire, turn on tracing for the library you already use, and watch your app's activity arrive live."
---

# Solo builder: just me and my app

It's just you and your app, and you want to see what it's doing without wading through a platform first. This is the shortest path: install, add one line for the library you already use, and watch your app show up live. That's it. You can come back for the rest later.

## Your path

1. **[Send your first trace to Logfire](../index.md)**: about five minutes. You install Logfire, sign in through your browser (no secret key to copy and paste), and run a small program. A **trace** is the record of what your code did on one run (the steps it took and how long each one took) and you'll see one appear on screen.

2. **Turn on tracing for what you already use**: pick the one that matches your app and add its single line of setup:
    - Building with an LLM (the AI that generates text)? [OpenAI](../integrations/llms/openai.md), [Anthropic](../integrations/llms/anthropic.md), or an [agent framework](../integrations/llms/pydanticai.md).
    - Running a web app? [FastAPI](../integrations/web-frameworks/fastapi.md), [Flask](../integrations/web-frameworks/flask.md), or [Django](../integrations/web-frameworks/django.md).
    - Something else? Browse [all integrations](../integrations/index.md). There's probably a one-liner for it.

3. **[Watch it arrive live](../guides/web-ui/live.md)**: use your app as you normally would and watch the activity stream into the Live view. Click any trace to open it up and see each step nested inside.

That's the whole loop: instrument, use your app, look. When you want more (measuring quality, dashboards, alerts, controlling cost), head back to [Choose your path](choose-your-path.md) and pick the role that fits what you're doing next.
