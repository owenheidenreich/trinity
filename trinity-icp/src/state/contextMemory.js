/**
 * Context Memory and Summarization
 * Handles conversation compression for long chats
 */
import State from './store.js';
import UI from '../ui/index.js';

export const ContextMemory = {
    /**
     * Compress conversation history into a summary
     * Triggered every 15 messages to reduce context window size
     */
    async compressContext() {
        console.log('🗜️ Compressing conversation history...');
        
        const state = State.get();
        
        // Calculate range to summarize
        const startIdx = state.lastSummaryAt;
        const endIdx = state.chatHistory.length - 6;  // Keep last 6 messages full
        
        if (endIdx - startIdx < 10) {
            console.log('⏭️ Skipping compression - not enough new messages');
            return;
        }
        
        // Extract messages to compress
        const messagesToSummarize = state.chatHistory.slice(startIdx, endIdx);
        
        // Build summarization prompt
        const conversationText = messagesToSummarize
            .map(msg => `${msg.role === 'user' ? 'User' : 'Assistant'}: ${msg.content}`)
            .join('\n');
        
        const summaryPrompt = `Please analyze this conversation excerpt and extract ONLY the key facts, data points, and context that should be remembered. Be concise but preserve important details like:
- Specific numbers, dates, or values mentioned
- User preferences or requirements stated
- Technical specifications or constraints
- Names of files, functions, or variables discussed
- Decisions made or conclusions reached

Conversation excerpt:
${conversationText}

Provide a bullet-point summary of key facts to remember:`;
        
        try {
            UI.showSummarizationIndicator();
            
            // Import API from app.js (will be extracted to api/client.js in next step)
            const { API } = await import('../app.js');
            
            // Request summary from LLM (no context - standalone request)
            const summaryResponse = await API.generate(summaryPrompt, 0.7, true);
            
            // Update state
            const currentSummary = State.conversationSummary;
            const newSummary = currentSummary 
                ? currentSummary + '\n\n' + summaryResponse
                : summaryResponse;
            
            State.setConversationSummary(newSummary, state.chatHistory.length);
            
            console.log('✅ Context compressed successfully');
            console.log(`📊 Summary covers messages ${startIdx}-${endIdx}`);
            console.log('📝 Summary:', newSummary.substring(0, 100) + '...');
            
        } catch (error) {
            console.error('❌ Failed to compress context:', error);
            // Non-critical - continue without summary
        }
    }
};

export default ContextMemory;
