**Logfire** has many [built-in integrations], focusing on the most popular packages.

However, if you are a maintainer of a package and would like to create an integration for **Logfire**, you can also do it! :smile:

We've created a shim package called `logfire-api`, which can be used to integrate your package with **Logfire**.

The idea of `logfire-api` is that it doesn't have any dependencies. It's a very small package that matches the API of **Logfire**.
We created it so that you can create an integration for **Logfire** without having to install **Logfire** itself.

If `logfire` is installed, then `logfire-api` will use it. If not, it will use a **no-op implementation**.

Here's how you can use `logfire-api`:

```python
import logfire_api as logfire

logfire.info("Hello, Logfire!")
```

All the **Logfire** API methods are available in `logfire-api`.

[built-in integrations]: ../../integrations/index.md#opentelemetry-integrations
