"""
EXPERIMENTAL: The images a sandbox can start from, passed as `image` when
creating one. Each helper only names a published image; the create call
validates it. Building and uploading images happens through the REST API.

```py
from inngest.experimental.sandbox import image

sandbox = await client.sandboxes.create(
    name="job", vcpu=1, memory_mb=1024, image=image.custom("my-image:v1")
)
```
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class SandboxImage:
    """
    EXPERIMENTAL: An image for a sandbox to start from, made by
    image.inngest() or image.custom().
    """

    # The catalog reference sent as the create request's image.
    ref: str


def inngest(name: str) -> SandboxImage:
    """
    An image Inngest maintains, such as image.inngest("base"). Omit image to
    use the default base image.
    """

    return SandboxImage(f"inngest/{name}")


def custom(ref: str) -> SandboxImage:
    """
    An image published to your workspace: "my-image", "my-image:v1", or
    "my-image@sha256:<hex>". A name without a tag uses latest.
    """

    return SandboxImage(ref)
