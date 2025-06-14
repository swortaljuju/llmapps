'use client';

import { useState, useRef, useEffect } from 'react';
import { ChatMessage, ChatAuthorType, NewsResearchAnswerQuestionRequest, newsResearchAnswerQuestion, getNewsResearchChatHistory} from './store';
import { TypewriterText } from '../common/typewriter';


export function NewsResearchChat() {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [error, setError] = useState<string>('');
    const [userInput, setUserInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        // Fetch initial chat history
        const fetchChatHistory = async () => {
            try {
                setIsLoading(true);
                const chatHistory = await getNewsResearchChatHistory();
                setMessages(chatHistory);
            } catch (error) {
                console.error('Error fetching chat history:', error);
                setError('Failed to load chat history. Please try again.');
            } finally { 
                setIsLoading(false);
            }
        };

        fetchChatHistory();
    }, []);

    // Scroll to bottom when messages change
    useEffect(() => {
        scrollToBottom();
        inputRef.current?.focus();
    }, [messages]);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!userInput.trim() || isLoading) {
            return;
        }
        let parentMessageId;
        let threadId;
        if (messages.length > 0) {
            parentMessageId = messages[messages.length - 1].message_id!;
            threadId = messages[0].thread_id;
        }
        // Add user message to chat
        const userMessage: ChatMessage = {
            thread_id: threadId,
            parent_message_id: parentMessageId,
            content: userInput,
            author: 'user' as ChatAuthorType,
            isInitData: false
        };

        setMessages(prev => [...prev, userMessage]);
        setUserInput('');
        setIsLoading(true);
        setError('');

        try {
            // Prepare request payload
            const request: NewsResearchAnswerQuestionRequest = {
                parent_message_id: parentMessageId,
                thread_id: threadId,
                question: userInput
            };

            // Call API
            const response = await newsResearchAnswerQuestion(request);
            setMessages(prev => {
                prev[prev.length - 1].message_id = response.question.message_id;
                prev[prev.length - 1].thread_id = response.question.thread_id;
                return [...prev, {
                    thread_id: response.answer.thread_id,
                    message_id: response.answer.message_id,
                    parent_message_id: response.answer.parent_message_id,
                    content: response.answer.content,
                    author: 'ai' as ChatAuthorType,
                    isInitData: false
                } as ChatMessage];
            });

        } catch (error) {
            console.error('Error submitting question:', error);
            // Remove the last user message when error occurs
            setMessages(prev => prev.slice(0, -1));
            setError('Failed to submit answer. Please try again.');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="flex flex-col h-full">
            {/* Error alert */}
            {error && (
                <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-4 mx-4 mt-4">
                    <span className="block sm:inline">{error}</span>
                    <span
                        className="absolute top-0 bottom-0 right-0 px-4 py-3"
                        onClick={() => setError('')}
                    >
                        <span className="text-red-500 font-bold cursor-pointer">×</span>
                    </span>
                </div>
            )}

            {/* Chat messages */}
            <div className="flex-grow overflow-auto p-4 space-y-4">
                {/* Display conversation history */}
                {messages.map((message, index) => (
                    <div
                        key={message.message_id || index}
                        className={`p-4 rounded-lg max-w-3xl ${message.author === 'user'
                            ? 'bg-blue-100 ml-auto' // Right align user messages
                            : 'bg-gray-100 mr-auto' // Left align AI messages
                            }`}
                    >
                        <TypewriterText text={message.content} showEffect={!message.isInitData && message.author == 'ai' && index == messages.length - 1} />
                    </div>
                ))}
                {isLoading && (
                    <div className="flex justify-center items-center">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
                    </div>
                )}
                {/* Invisible element for scrolling */}
                <div ref={messagesEndRef} />
            </div>

            {/* Input area */}
            <div className="border-t p-4 bg-white">
                <form onSubmit={handleSubmit} className="flex space-x-2">
                    <input
                        ref={inputRef}
                        type="text"
                        value={userInput}
                        onChange={(e) => setUserInput(e.target.value)}
                        disabled={isLoading}
                        className="flex-grow border rounded-md px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        placeholder="Ask a question about recent news... For example: 'What are the latest developments in AI?'"
                    />
                    <button
                        type="submit"
                        disabled={!userInput.trim() || isLoading}
                        className={`px-4 py-2 rounded-md ${!userInput.trim() || isLoading
                            ? 'bg-gray-300 cursor-not-allowed'
                            : 'bg-blue-500 hover:bg-blue-600 text-white'
                            }`}
                    >
                        {isLoading ? 'Sending...' : 'Send'}
                    </button>
                </form>
            </div>
        </div>
    );
}