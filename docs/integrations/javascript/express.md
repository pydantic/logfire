---
integration: logfire
---

# Express

Instrumenting an Express application with Logfire is straightforward. You can use the `logfire` package to set up logging and monitoring for your Express routes.

```ts title="app.ts"
import express, type { Express } from 'express';

const PORT: number = parseInt(process.env.PORT || '8080');
const app: Express = express();

function getRandomNumber(min: number, max: number) {
  return Math.floor(Math.random() * (max - min + 1) + min);
}

app.get('/rolldice', (req, res) => {
  res.send(getRandomNumber(1, 6).toString());
});

app.listen(PORT, () => {
  console.log(`Listening for requests on http://localhost:${PORT}`);
});
```

To get started, install the `logfire` and `dotenv` NPM packages. This will allow you to keep your Logfire write token in a `.env` file:

```sh
npm install logfire dotenv
```

Add your token to the `.env` file:

```sh title=".env"
LOGFIRE_TOKEN=your-write-token
```

Then, create an `instrumentation.ts` file to set up the instrumentation. The
`logfire` package includes a `configure` function that simplifies the setup:

```ts title="instrumentation.ts"
import * as logfire from "logfire";
import "dotenv/config";

logfire.configure();
```

The `logfire.configure` call should happen before importing the actual Express module, so your NPM start script should look like this in `package.json`. Note that we use `npx ts-node` to run the TypeScript code directly:

```json title="package.json"
"scripts": {
  "start": "npx ts-node --require ./instrumentation.ts app.ts"
A complete working example can be found in [examples/express](https://github.com/pydantic/logfire-js/tree/main/examples/express).
```

A working example can be found in the [examples/express](https://github.com/pydantic/logfire-js/tree/main/examples/express) directory of the `pydantic/logfire-js` repository.
