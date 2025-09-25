# Fast API realtime example

This example is a Fast API application with a minimal webapp using the [`@inngest/realtime`](https://github.com/inngest/inngest-js/tree/main/packages/realtime) package.

## Client

Install the dependencies using npm and build the client side application (see `/client/main.ts`):

```
npm install
npm run build
```

## Server

Start the API server using this command:

```
make dev
```

## Dev server

Run the [Inngest Dev Server](https://www.inngest.com/docs/dev-server) passing the URL to the serve endpoint in the Fast API server:

```
npx inngest-cli@latest dev -u http://localhost:8000/api/inngest
```
