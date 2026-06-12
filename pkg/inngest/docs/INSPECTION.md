# Inspection

How the SDK responds to GET requests with app metadata. This is typically used for:

- Checking if there's really an Inngest SDK behind a URL.
- Our "health check" feature, where we show warnings/errors to users for misconfigurations.

## Overview

The GET handler on `CommHandler` returns an inspection response. This is used by the Dev Server for auto-discovery and by the Inngest dashboard for diagnostics. In cloud mode, the request must be signed. In dev mode, signature validation is skipped.

Models live in `_internal/server_lib/inspection.py`.

## Unauthenticated Response

Returned in dev mode when the request has no valid signature. Exposes only non-sensitive metadata. Notably, this must not include signing key hashes. Even though they are hashes and not raw keys, the hashed signing key can be a Bearer token to authenticate requests to the Inngest API.

## Authenticated Response

Returned when the request has a valid signature. Includes everything in the unauthenticated response plus sensitive details.

## Server Kind Mismatch

Cloud-mode GET requests must be signed before the handler inspects server kind. Unsigned requests, including Dev Server auto-discovery requests against a production SDK, return the generic 401 response.

If a GET request reaches the handler and its server kind does not match the SDK mode, the handler returns 403 with an empty body. This is a DX concern, since apps were mistakenly syncing with Inngest Cloud when the Dev Server sent a PUT request.
