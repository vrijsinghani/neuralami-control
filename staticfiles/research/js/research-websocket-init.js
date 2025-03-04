import { ResearchWebSocketService } from './research-websocket.js';

console.log('Initializing research WebSocket...');
const researchId = window.RESEARCH_ID;

if (researchId) {
    const wsService = new ResearchWebSocketService(researchId);
    window.researchWsService = wsService;
    console.log('WebSocket service initialized');
} else {
    console.error('Error: RESEARCH_ID is not defined.');
} 