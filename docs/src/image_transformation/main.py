import json
from pathlib import Path
from typing import Annotated, Literal

import openai
from annotated_types import Ge, Le
from PIL import Image, ImageEnhance
from pydantic import BaseModel

import logfire


class ScaleImage(BaseModel):
    width: int
    height: int


class CropImage(BaseModel):
    width: int
    height: int
    x: int
    y: int


class ImageTransform(BaseModel):
    resize: CropImage | ScaleImage | None = None
    make_grayscale: bool | None = None
    remove_transparency: bool | None = None
    make_transparent: bool | None = None
    transparency_threshold: Annotated[int, Ge(0), Le(255)] = 200
    brightness_adjustment_percentage: Annotated[float, Ge(0), Le(100)] | None = None
    contrast_adjustment_percentage: Annotated[float, Ge(0), Le(100)] | None = None
    save_as: Literal['png', 'jpg', 'bmp'] = None


functions = [
    {
        'name': 'resize_image',
        'description': 'Defines transformations to an image',
        'parameters': ImageTransform.model_json_schema(),
    }
]

setup = """
Help the use by defining how an image should be transformed based on the user's input.
"""


@logfire.instrument('transform_image {image_path=} {user_prompt=!r}')  # (1)!
def transform_image(image_path: Path, user_prompt: str) -> None:
    with logfire.span('loading image'):  # (2)!
        img = Image.open(image_path)
        width, height = img.size
        logfire.info('image size is {width}x{height}', width=width, height=height)  # (3)!
    try:
        messages = [
            {'role': 'system', 'content': setup},
            {'role': 'system', 'content': f'image current size is {width}x{height}'},
            {'role': 'user', 'content': user_prompt},
        ]

        model: ImageTransform | None = None
        with logfire.span('calling OpenAI'):
            response = openai.ChatCompletion.create(
                model='gpt-4',
                messages=messages,
                functions=functions,
            )
            tokens_used = response['usage']['prompt_tokens']
            logfire.info(
                'got response {tokens_used=}', tokens_used=tokens_used, user_prompt=user_prompt, response=response
            )

            response_choice = response['choices'][0]
            finish_reason = response_choice['finish_reason']
            if finish_reason == 'stop':
                msg = response_choice['message']['content']
                logfire.warn('OpenAI refused to resize the image: {msg}', msg=msg)
            else:
                assert finish_reason == 'function_call'
                message = response_choice['message']
                arguments_json: str = message['function_call']['arguments']
                # model_validate_json currently doesn't instrument
                model = ImageTransform.model_validate(json.loads(arguments_json))

        if model is not None:
            with logfire.span('transforming image'):
                match model.resize:
                    case ScaleImage(width=width, height=height):
                        img = img.resize((width, height))
                    case CropImage(width=width, height=height, x=x, y=y):
                        box = (x, y, x + width, y + height)
                        img = img.crop(box)

                if model.make_grayscale:
                    img = img.convert('L')

                if model.remove_transparency:
                    img = img.convert('RGB')

                if model.make_transparent:
                    img = img.convert('RGBA')

                    data = list(img.getdata())

                    for index, item in enumerate(data):
                        if item[0] in range(model.transparency_threshold, 256):
                            data[index] = (255, 255, 255, 0)

                    img.putdata(data)

                if (b := model.brightness_adjustment_percentage) is not None:
                    img = ImageEnhance.Brightness(img).enhance(1 + b / 100)
                if (c := model.contrast_adjustment_percentage) is not None:
                    img = ImageEnhance.Contrast(img).enhance(1 + c / 100)

            new_path = image_path.with_stem(f'{image_path.stem}-transformed')
            if (save_as := model.save_as) is not None:
                new_path = new_path.with_suffix(f'.{save_as}')
            img.save(new_path)
    finally:
        img.close()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('image_path', type=Path)
    # example prompts:
    # * make the image square by cropping it and increase the brightness by 10%
    # * crop the image to be square, centered
    # * crop the image to be square, left offset 0
    parser.add_argument('user_prompt', type=str)

    args = parser.parse_args()
    transform_image(args.image_path, args.user_prompt)
