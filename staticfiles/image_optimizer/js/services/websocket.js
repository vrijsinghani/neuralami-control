import { BaseWebSocketService } from '/static/common/js/services/websocket.js';

class ImageOptimizationWebSocket extends BaseWebSocketService {
    constructor(optimizationId) {
        super({
            endpoint: `/ws/image-optimizer/${optimizationId}/`
        });
        this.optimizationId = optimizationId;
    }

    handleMessage(data) {
        switch (data.type) {
            case 'optimization_update':
                this.emit('optimizationUpdate', data);
                break;
            case 'job_update':
                this.emit('jobUpdate', data);
                break;
            case 'error':
                this.emit('error', data);
                break;
            default:
                console.log('Unknown message type:', data.type);
        }
    }
}

export { ImageOptimizationWebSocket }; 