# Fast API realtime example

This example is a Fast API application with a minimal webapp demonstrating [realtime functionality](https://www.inngest.com/docs/features/realtime) in Inngest.

## Setup

### Server

Start the API server using this command:

```
make dev
```

### Client

The client side of the application, uses the [`@inngest/realtime`](https://github.com/inngest/inngest-js/tree/main/packages/realtime) npm package. First, copy the `.env.example` file into your own `.env` file to configure your client build. Next, you'll need to install the dependencies using npm then build the client side application (see `/client/main.ts`).

```
cp .env.example .env
npm install
npm run build
```

### Dev server

Run the [Inngest Dev Server](https://www.inngest.com/docs/dev-server) passing the URL to the serve endpoint in the Fast API server:

```
npx inngest-cli@latest dev -u http://localhost:8000/api/inngest
```

### Test it

Open up [http://localhost:8000/](http://localhost:8000/) in your browser and click the button to run the function and get a realtime update. Open the Dev Server at [http://localhost:8288/](http://localhost:8288/) to view your running functions.
