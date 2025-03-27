from typing import Any, Literal

from pydantic import BaseModel


class Tool:
    """
    A tool is a function that can be called by an LLM with a set of parameters.
    """

    name: str
    """
    The name of the tool.
    """
    description: str | None
    """
    An optional description of the tool.
    """
    parameters: dict[str, Any]
    """
    A dictionary of parameters (json_schema) that the tool requires.
    """

    def __init__(self, name: str, description: str | None, parameters: dict[str, Any]):
        """
        Initialize a new tool.
        """
        self.name = name
        self.description = description
        self.parameters = parameters

    async def __call__(self, args: dict[str, Any]) -> Any:
        """
        Call the tool with the given arguments (should match the provided schema).

        The return result can be:
        - Pydantic model, which will be serialized to JSON and passed back to the model as text.
        - string, which will be passed back to the model as text.
        - ToolResponse, which allows for more structured content to be passed back to the model.
        - Anything else will be serialized using `json.dumps` and passed back to the model as text.
        """
        raise NotImplementedError()


class ToolResponseTextContent(BaseModel):
    """
    Content when the tool responds with text.
    """

    type: Literal["text"] = "text"
    data: str
    """
    The text content.
    """


class ToolResponseImageContent(BaseModel):
    """
    Content when the tool responds with an image.
    """

    type: Literal["image"] = "image"
    data: str
    """
    The base64 encoded image data.
    """
    mime_type: str
    """
    The mime type of the image.
    """


class ToolResponse(BaseModel):
    """
    A special responce type from a tool that allows passing back more structured
    content to the Agent, such as images or multiple contents at once.
    """

    content: list[ToolResponseTextContent | ToolResponseImageContent] = []
