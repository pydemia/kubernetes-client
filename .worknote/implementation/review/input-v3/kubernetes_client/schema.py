
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    model_validator,
)


__all__ = [
    "ResourceSpec",
]


MEMField = Field(
    2, title="Memory size",
    ge=0.1, le=128, multiple_of=0.1,
)

CPUField = Field(
    1, title="CPU size",
    ge=0.1, le=64, multiple_of=0.1,
)

GPUField = Field(
    0, title="GPU count",
    ge=0, le=8, multiple_of=1,
    alias="nvidia.com/gpu",
)

REPLICAField = Field(
    1, title="replica",
    ge=0, le=10_000, multiple_of=1,
)

CONCURRENCYField = Field(
    100, title="concurrency",
    ge=1, le=10_000, multiple_of=1,
)

NAMEField = Field(
    "", title="k8s namespace",
    max_length=200,
)


class Spec(BaseModel):
    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True)

    cpu: Optional[float] = CPUField
    memory: Optional[float] = MEMField
    gpu: Optional[int] = GPUField

    @field_serializer("cpu")
    def format_cpu(self, value: Optional[float]) -> Optional[str]:
        return format(value, "g") if value is not None else None

    @field_serializer("memory")
    def format_memory(self, value: Optional[float]) -> Optional[str]:
        return f"{value:g}Gi" if value is not None else None

    @field_serializer("gpu")
    def format_gpu(self, value: Optional[int]) -> Optional[str]:
        return str(value) if value is not None else None


class ResourceSpec(BaseModel):
    requests: Optional[Spec] = None
    limits: Optional[Spec] = None

    @model_validator(mode="after")
    def validate_minmax(self) -> "ResourceSpec":
        if self.requests is None or self.limits is None:
            return self

        updates = {}
        for field in ("cpu", "memory", "gpu"):
            request = getattr(self.requests, field)
            limit = getattr(self.limits, field)
            if request is not None and limit is not None and limit < request:
                updates[field] = request
        if updates:
            self.limits = self.limits.model_copy(update=updates)
        return self
