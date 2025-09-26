import './style.css';

import { subscribe } from '@inngest/realtime';

console.log('Inngest Realtime Demo starting...');

const runFunctionButton = document.querySelector('#run-function-button');
const realtimeMessages = document.querySelector('#realtime-messages');

function addMessage(message: string) {
  const messageElement = document.createElement('div');
  messageElement.textContent = message;
  messageElement.classList.add('message');
  realtimeMessages?.appendChild(messageElement);
}

runFunctionButton?.addEventListener('click', () => {
  console.log('Running function...');
  fetch('/api/trigger_function').then(() => {
    console.log('Function triggered');
  });
});

const token = await fetch('/api/get_subscription_token').then((res) =>
  res.json()
);
if (!token) {
  throw new Error('No token found');
}

const stream = await subscribe(token);

// @ts-ignore
for await (const chunk of stream) {
  addMessage(chunk.data.message);
}
