# Mirascope

[Mirascope](https://github.com/Mirascope/mirascope) is an intuitive approach to building AI-powered applications using LLMs. Their library is the first third party integration with Logfire to make observability and monitoring for LLMs easy and seamless.

You can enable it using the `@with_logire` decorator, which will work with all of the [model providers that they support](https://docs.mirascope.io/latest/concepts/supported_llm_providers/) (e.g. OpenAI, Anthropic, Groq, and more).

```py hl_lines="1 2 5 8"
import logfire
from mirascope.logfire import with_logfire
from mirascope.anthropic import AnthropicCall

logfire.configure()


@with_logfire
class BookRecommender(AnthropicCall):
    prompt_template = "Please recommend some {genre} books"

    genre: str


recommender = BookRecommender(genre="fantasy")
response = recommender.call()  # this will automatically get logged with logfire
print(response.content)
#> Here are some recommendations for great fantasy book series: ...
```

This will give you:

* A span around the `AnthropicCall.call()` that captures items like the prompt template, templating properties and fields, and input/output attributes.
* Human-readable display of the conversation with the agent
* Details of the response, including the number of tokens used

<figure markdown="span">
  ![Logfire Mirascope Anthropic call](../../images/logfire-screenshot-mirascope-anthropic-call.png){ width="500" }
  <figcaption>Mirascope Anthropic Call span and Anthropic span and conversation</figcaption>
</figure>

Since Mirascope is build on top of [Pydantic][pydantic], you can use the [Pydantic plugin][pydantic-plugin] to track additional logs and metrics about model validation, which you can enable using the [`pydantic_plugin`][logfire.configure(pydantic_plugin)] configuration.

This can be particularly useful when [extracting structured information](https://docs.mirascope.io/latest/concepts/extracting_structured_information_using_llms/) using LLMs:

```py hl_lines="3 4 8 17"
from typing import Literal, Type

import logfire
from mirascope.logfire import with_logfire
from mirascope.openai import OpenAIExtractor
from pydantic import BaseModel

logfire.configure(pydantic_plugin=logfire.PydanticPlugin(record="all"))


class TaskDetails(BaseModel):
    description: str
    due_date: str
    priority: Literal["low", "normal", "high"]


@with_logfire
class TaskExtractor(OpenAIExtractor[TaskDetails]):
    extract_schema: Type[TaskDetails] = TaskDetails
    prompt_template = """
    Extract the task details from the following task:
    {task}
    """

    task: str


task = "Submit quarterly report by next Friday. Task is high priority."
task_details = TaskExtractor(
    task=task
).extract()  # this will be logged automatically with logfire
assert isinstance(task_details, TaskDetails)
print(task_details)
#> description='Submit quarterly report' due_date='next Friday' priority='high'
```

For more information on Mirascope and what you can do with it, check out their [documentation](https://docs.mirascope.io)

[pydantic]: https://docs.pydantic.dev/latest/
[pydantic-plugin]: https://docs.pydantic.dev/latest/concepts/plugins/
