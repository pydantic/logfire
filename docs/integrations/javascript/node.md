---
integration: logfire
---

# Node.js

Using Logfire in your Node.js script is straightforward. You need to [get a write token](https://logfire.pydantic.dev/docs/how-to-guides/create-write-tokens/), install the package, configure it, and use the provided API.

Let's create an empty project:

```sh
mkdir test-logfire-js
cd test-logfire-js
npm init -y es6 # This creates a package.json with `type: module` for ES6 support
npm install logfire
```

Then, create the following `hello.js` script in the directory:

```js
import * as logfire from "logfire";

logfire.configure({
  token: "your-write-token",
  serviceName: "example-node-script",
  serviceVersion: "1.0.0",
});

logfire.info("Hello from Node.js", {
  "attribute-key": "attribute-value",
}, {
  tags: ["example", "example2"],
});
```

Run the script with `node hello.js`, and you should see the log entry appear in
the live view of your Logfire project.

A working example can be found in the [examples/node](https://github.com/pydantic/logfire-js/tree/main/examples/node) directory of the logfire-js repository.
