from abc import ABC, abstractmethod
from typing import Any, Callable, Optional, Type
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic import BaseModel as PydanticBaseModel
import logging

logger = logging.getLogger(__name__)

class ToolUsageError(Exception):
    """Exception raised when a tool is used incorrectly."""
    pass

class BaseTool(BaseModel, ABC):
    class _ArgsSchemaPlaceholder(PydanticBaseModel):
        pass

    model_config = ConfigDict()

    name: str
    """The unique name of the tool that clearly communicates its purpose."""
    description: str
    """Used to tell the model how/when/why to use the tool."""
    args_schema: Type[PydanticBaseModel] = Field(default_factory=_ArgsSchemaPlaceholder)
    """The schema for the arguments that the tool accepts."""
    description_updated: bool = False
    """Flag to check if the description has been updated."""
    cache_function: Optional[Callable] = lambda _args, _result: True
    """Function that will be used to determine if the tool should be cached."""
    result_as_answer: bool = False
    """Flag to check if the tool should be the final agent answer."""

    @field_validator("args_schema", mode="before")
    def _default_args_schema(
        cls, v: Type[PydanticBaseModel]
    ) -> Type[PydanticBaseModel]:
        if not isinstance(v, cls._ArgsSchemaPlaceholder):
            return v

        return type(
            f"{cls.__name__}Schema",
            (PydanticBaseModel,),
            {
                "__annotations__": {
                    k: v for k, v in cls._run.__annotations__.items() if k != "return"
                },
            },
        )

    def model_post_init(self, __context: Any) -> None:
        self._generate_description()
        super().model_post_init(__context)

    def run(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        return self._run(*args, **kwargs)

    @abstractmethod
    def _run(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Here goes the actual implementation of the tool."""

    def _set_args_schema(self):
        if self.args_schema is None:
            class_name = f"{self.__class__.__name__}Schema"
            self.args_schema = type(
                class_name,
                (PydanticBaseModel,),
                {
                    "__annotations__": {
                        k: v
                        for k, v in self._run.__annotations__.items()
                        if k != "return"
                    },
                },
            )

    def _generate_description(self):
        args = []
        args_description = []
        for arg, attribute in self.args_schema.schema()["properties"].items():
            if "type" in attribute:
                args.append(f"{arg}: '{attribute['type']}'")
            if "description" in attribute:
                args_description.append(f"{arg}: '{attribute['description']}'")

        description = self.description.replace("\n", " ")
        self.description = f"{self.name}({', '.join(args)}) - {description} {', '.join(args_description)}"

    def _run(self, *args, **kwargs):
        try:
            logger.info(f"Starting tool execution: {self.__class__.__name__}")
            result = self.run(*args, **kwargs)
            logger.info(f"Tool execution completed: {self.__class__.__name__}")
            # Log the result type and structure without sensitive data
            result_preview = str(result)[:250] + "..." if len(str(result)) > 250 else str(result)
            logger.debug(f"Tool result type: {type(result)}, preview: {result_preview}")
            return result
        except Exception as e:
            logger.error(f"Tool execution failed: {self.__class__.__name__}, Error: {str(e)}", exc_info=True)
            raise

class Tool(BaseTool):
    """A tool that wraps a callable function."""
    
    func: Callable
    """The function that will be executed when the tool is called."""

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the wrapped function with the provided arguments."""
        return self.func(*args, **kwargs)

def tool(*args):
    """
    Decorator to create a tool from a function.
    """
    def _make_with_name(tool_name: str) -> Callable:
        def _make_tool(f: Callable) -> BaseTool:
            if f.__doc__ is None:
                raise ValueError("Function must have a docstring")
            if f.__annotations__ is None:
                raise ValueError("Function must have type annotations")

            class_name = "".join(tool_name.split()).title()
            args_schema = type(
                class_name,
                (PydanticBaseModel,),
                {
                    "__annotations__": {
                        k: v for k, v in f.__annotations__.items() if k != "return"
                    },
                },
            )

            return Tool(
                name=tool_name,
                description=f.__doc__,
                func=f,
                args_schema=args_schema,
            )

        return _make_tool

    if len(args) == 1 and callable(args[0]):
        return _make_with_name(args[0].__name__)(args[0])
    if len(args) == 1 and isinstance(args[0], str):
        return _make_with_name(args[0])
    raise ValueError("Invalid arguments") 