from typing import List

from fastapi import FastAPI
from pydantic import BaseModel

import logfire  # (1)!

app = FastAPI()


class TodoItem(BaseModel):
    title: str
    description: str | None = None
    completed: bool = False


todos: List[TodoItem] = []  # (2)!


@app.post('/todos')
async def create_todo_item(item: TodoItem):
    todos.append(item)
    logfire.info('Todo item created: {item=}', item=item)
    return item


@app.get('/todos', response_model=List[TodoItem])
async def read_todo_items():
    logfire.info('Reading all todo items')
    return todos


@app.get('/todos/{item_id}', response_model=TodoItem)
async def read_todo_item(item_id: int):
    item = todos[item_id]
    logfire.info('Reading todo item with {item_id=}', item_id=item_id)
    return item


@app.put('/todos/{item_id}')
async def update_todo_item(item_id: int, item: TodoItem):
    todos[item_id] = item
    logfire.info('Todo item updated: {item=}', item=item)
    return item


@app.delete('/todos/{item_id}')
async def delete_todo_item(item_id: int):
    todos.pop(item_id)
    logfire.info('Todo item deleted with {item_id=}', item_id=item_id)
    return {'message': 'Todo item deleted'}
