import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';

const rootElement = document.getElementById('root');

if (!rootElement) {
  throw new Error('Failed to find root element');
}

try {
  console.log('Creating root');
  const root = createRoot(rootElement);
  console.log('Root created:', root);
  
  console.log('Rendering app');
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
  console.log('App rendered');
} catch (error) {
  console.error('Error rendering app:', error);
}
