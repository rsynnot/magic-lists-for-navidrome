/**
 * Analytics Module
 * Handles tracking and analytics functionality
 */

// Global state for analytics
let aiModelInfo = null;

// Export functions
export {
    getAIModelInfo,
    trackLibrarySize
};

// AI model information cache
async function getAIModelInfo() {
    if (aiModelInfo) {
        return aiModelInfo;
    }

    try {
        const response = await fetch('/api/ai-model-info');
        if (response.ok) {
            aiModelInfo = await response.json();
            return aiModelInfo;
        }
    } catch (error) {
        console.error('Error fetching AI model info:', error);
    }

    // Fallback
    return {
        provider: 'unknown',
        model: 'unknown',
        has_api_key: false
    };
}

// Post-launch library size tracking
async function trackLibrarySize() {
    try {
        const response = await fetch('/api/track-library-size', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (response.ok) {
            const data = await response.json();

            if (data.tracked && typeof window.rybbit !== 'undefined') {
                // Track library size event with Rybbit
                window.rybbit.event('Library Size Tracked', {
                    songCount: data.song_count,
                    userId: data.user_id
                });
                console.log('📊 Library size tracked for analytics');
            }
        }
    } catch (error) {
        console.error('❌ Error tracking library size:', error);
    }
}