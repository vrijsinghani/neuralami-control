    async def send_initial_state(self):
        """Send initial state to the client"""
        research = await self.get_research()
        if not research:
            await self.send_error("Research not found")
            return
        
        # Send current state
        await self.send_json({
            'type': 'initial_state',
            'research': {
                'id': research.id,
                'status': research.status,
                'progress': self._calculate_progress(research),
                'query': research.query,
                'created_at': research.created_at.isoformat(),
                'error': research.error
            }
        })
        
        # Send HTML for steps
        if research.reasoning_steps:
