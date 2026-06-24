# Add `ctx.ext`

Area: Middleware
Change type: Architecture

## Problem

Middleware often needs to make application-specific data available to function handlers. Common examples include database clients, current user or service-account data, tenant context, feature flags, tracing handles, and request-scoped service objects.

Without a dedicated extension namespace, Python middleware has to rely on ad hoc dynamic attributes:

```python
setattr(ctx, "db", db)
db = getattr(ctx, "db")
```

That works at runtime, but it is clunky, implicit, hard to document, and easy to collide with SDK-owned context fields.

Adding arbitrary fields directly to `ctx` is not a good fix. `ctx` has SDK-owned fields such as `event`, `events`, `step`, `logger`, run IDs, and attempt metadata. If user-defined middleware writes to the same namespace, application fields can collide with current or future SDK fields.

Typing also pushes against adding arbitrary fields directly to `ctx`. The SDK should keep precise types for known context fields, but user extensions need an "accept anything" surface where unknown attribute access resolves to `Any`. Putting that behavior on `ctx` itself would make the entire context object more permissive than the SDK-owned fields should be.

Python cannot reliably infer context extensions from middleware, and the first two `Context[...]` generic arguments are already used for trigger event typing and invocation input typing. Adding a third required generic argument would make the common typed-event path more verbose.

## Solution

Add `ctx.ext` as the dedicated namespace for middleware-provided application extensions. `ctx.ext` is an SDK-owned mutable namespace object.

The namespace supports attribute access:

```python
ctx.ext.db
```

Statically, `ctx.ext` is untyped by default. Arbitrary attribute access should resolve to `Any`; users who want stronger checking can cast `ctx.ext` to a `Protocol` or other application-owned type.

Middleware can add values by mutating `ctx.ext` directly. Later middleware sees earlier middleware changes and silently replaces conflicting keys according to middleware ordering.

`ctx.ext` is intentionally broad:

- It can hold dependency-injection objects.
- It can hold current user, service-account, or tenant context.
- It can hold observability or request-scoped application state.
- It is not inspected by the SDK.

The default value should be an empty namespace-like object. Middleware can add values during `transform_function_input`.

```python
class Ext(typing.Protocol):
    db: Database
    principal: Principal


class AppMiddleware(inngest.Middleware):
    def transform_function_input(
        self,
        arg: inngest.TransformFunctionInputArgs,
    ) -> inngest.TransformFunctionInputArgs:
        arg.ctx.ext.db = self.db
        arg.ctx.ext.principal = get_principal(arg.ctx.event)
        return arg


async def handler(
    ctx: inngest.Context[UserCreated, UserCreatedData],
) -> None:
    ext = typing.cast(Ext, ctx.ext)
    user = await ext.db.get_user(ctx.event.data.user_id)
```

Untyped handlers can read the same direct keys without a cast:

```python
arg.ctx.ext.db = self.db
return arg
```

```python
ctx.ext.db
```

Dynamic names use normal Python attribute helpers:

```python
setattr(arg.ctx.ext, key, value)
value = getattr(ctx.ext, key)
```

## Out of scope

Future releases may add a third `Context[...]` generic for statically typing `ctx.ext`.

Future releases may add logging for extension key conflicts or configuration for the replacement strategy. Conflicts are silently replaced according to middleware ordering in this change.

## Blocked by

[`foundation/rewrite_middleware.md`](./rewrite_middleware.md) must land first or in the same v0.6 middleware release. This spec depends on the new public `Middleware` API, `TransformFunctionInputArgs`, and `transform_function_input` ordering defined there.

Do not implement this against the old `MiddlewareSync` and `transform_input` hook contract. Supporting that older contract would require compatibility behavior that is outside the scope of this spec.

## Open questions

- Should `ExtensionNamespace` subclass `types.SimpleNamespace` or use another small SDK-owned namespace type?

## Implementation

Add `ext: ExtensionNamespace` or an equivalent SDK-owned type to async and sync context objects. The type should be intentionally dynamic:

```python
class ExtensionNamespace:
    def __getattr__(self, name: str) -> Any: ...
    def __setattr__(self, name: str, value: Any) -> None: ...
```

The default `ctx.ext` value should be an empty SDK-owned namespace object that supports attribute access:

```python
ctx.ext.db
```

Reading a missing extension attribute should behave like normal Python attribute access and raise `AttributeError`. Do not raise SDK-specific errors from `ExtensionNamespace.__getattr__`. This keeps `hasattr(ctx.ext, "db")` and `getattr(ctx.ext, "db", default)` working as Python users expect.

`ExtensionNamespace` should support normal Python introspection. Prefer an SDK-owned class with a normal instance `__dict__` so `vars(ctx.ext)` returns the stored extension fields. `repr(ctx.ext)` should be concise and useful for debugging, showing field names without requiring verbose or sensitive value representations, for example `ExtensionNamespace(db=..., principal=...)`.

Middleware should add values by mutating `ctx.ext` in `transform_function_input` and returning the transform argument:

```python
arg.ctx.ext.db = db
return arg
```

Dynamic names use `setattr` and `getattr`:

```python
setattr(arg.ctx.ext, key, value)
value = getattr(arg.ctx.ext, key)
return arg
```

`ctx.ext` itself is SDK-owned and must not be replaceable by middleware or user code. Function handlers always observe `ctx.ext` as an `ExtensionNamespace`.

Implement `ctx.ext` as a read-only context property or an equivalent guarded field. Middleware may freely set, replace, and delete attributes on the namespace object, but assigning a new namespace object to `ctx.ext` should fail. This preserves middleware composition: one middleware cannot accidentally discard extension fields added by earlier middleware.

Multiple middleware should compose naturally:

```python
# Middleware A
arg.ctx.ext.db = db
return arg

# Middleware B
arg.ctx.ext.flags = flags
return arg

# Handler
ctx.ext.db
ctx.ext.flags
```

Most middleware should add the fields handlers naturally want to read:

```python
arg.ctx.ext.db = db
arg.ctx.ext.principal = principal
return arg
```

Middleware can still store a grouped object under one key when namespacing is intentional:

```python
arg.ctx.ext.my_package = MyPackageExt(db=db, principal=principal)
return arg
```

Do not add extension helper methods to `Context` itself. Context methods for middleware mechanics would be visible to ordinary function handlers and would be confusing outside middleware.

`ctx.ext` attributes are `Any` by default. Python users who want static typing should cast individual extension values or write a small helper:

```python
def get_ext(ctx: inngest.Context[Any, Any]) -> Ext:
    return typing.cast(Ext, ctx.ext)
```

Do not use `ctx.ext` for SDK-owned fields such as `event`, `events`, `step`, `logger`, run IDs, or attempt metadata. Those remain explicit context fields and should be transformed through dedicated middleware argument helpers where supported.

## Testing

Add async and sync runtime tests that prove:

- Middleware can set `arg.ctx.ext.db = db`.
- Later middleware can read fields set by earlier middleware.
- Later middleware can replace an existing extension attribute, such as `arg.ctx.ext.db = other_db`.
- Assigning a new object to `arg.ctx.ext` fails.
- Function handlers still observe the original `ExtensionNamespace`.

Add static type coverage that proves:

- `ctx.ext.anything` resolves to `Any` by default.
- Casting `ctx.ext` to a user-defined `Protocol` or helper return type enables typed extension access.
- `ctx.ext = object()` is a type error.
