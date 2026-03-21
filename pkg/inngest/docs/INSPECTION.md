# Inspection

How the SDK responds to GET requests with app metadata. This is typically used for:

- Checking if there's really an Inngest SDK behind a URL.
- Our "health check" feature, where we show warnings/errors to users for misconfigurations.

## Overview

The GET handler on `CommHandler` returns an inspection response. This is used by the Dev Server for auto-discovery and by the Inngest dashboard for diagnostics. The response shape depends on whether the request is signed.

Models live in `_internal/server_lib/inspection.py`.

## Unauthenticated Response

Returned when the request has no valid signature. Exposes only non-sensitive metadata. Notably, this must not include signing key hashes. Even though they are hashes and not raw keys, the hashed signing key can be a Bearer token to authenticate requests to the Inngest API.

## Authenticated Response

Returned when the request has a valid signature. Includes everything in the unauthenticated response plus sensitive details.

## Server Kind Mismatch

If the request comes from a Dev Server but the SDK is in production mode (or vice versa), the GET handler returns 403 with an empty body. This is a DX concern, since apps were mistakenly syncing with Inngest Cloud when the Dev Server sent a PUT request.
