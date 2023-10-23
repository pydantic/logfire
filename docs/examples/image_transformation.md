This project is a simple example of how to use the `logfire` package to transform images.

??? note "See source code! 🔎"
    ```py
    --8<-- "src/packages/logfire/docs/src/image_transformation/main.py"
    ```

    1. You can use the [`logfire.instrument`][logfire.Logfire.instrument] decorator to
        instrument a function as a span.
    2. Use the [`logfire.span`][logfire.Logfire.span] context manager to instrument a
        block of code as a span.
    3. Use the [`logfire.info`][logfire.Logfire.info] method to log information.

## Installation

To install the dependencies, you can copy the following dependencies to a `requirements.txt` file:

```txt
--8<-- "src/packages/logfire/docs/src/image_transformation/requirements.txt"
```

Then run the following command:

```bash
pip install -r requirements.txt
```

## Usage

If you want to run this example, you can do so by running the following command:

```bash
python main.py <image_path> <user_prompt>
```

For example, if you want to transform the image `image.jpg`, and want to convert the image to grayscale, you can run the following command:

```bash
python main.py image.jpg "Convert to grayscale"
```
