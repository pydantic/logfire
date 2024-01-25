Here you'll find an example of how to use `logfire` with [FastAPI][fastapi].

??? note "See source code! 🔎"
    ```py
    --8<-- "src/packages/logfire/docs/src/app/main.py"
    ```

    1. Importing `logfire` is the only thing needed to use it!
    2. We are using a list to store the items, but this could be a database.

[fastapi]: https://fastapi.tiangolo.com/

## Installation

To install the dependencies, you can copy the following dependencies to a `requirements.txt` file:

```txt
--8<-- "src/packages/logfire/docs/src/app/requirements.txt"
```

Then run the following command:

```bash
pip install -r requirements.txt
```

## Usage

If you want to run this example, you can do so by running the following command:

```bash
uvicorn app:app --reload
```
