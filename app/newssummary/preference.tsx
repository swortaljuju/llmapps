'use client';

import { useState, useRef, useEffect } from 'react';
import { ChatMessage, ChatAuthorType, PreferenceSurveyRequest, submitPreferenceSurvey, getPreference, savePreference } from './store';
import { TypewriterText } from '../common/typewriter';

interface NewsPreferenceChatProps {
    preferenceConversationHistory: ChatMessage[];
    fromCreatePreferenceToNewsSummary: () => void;
}

export function NewsPreferenceChat({
    preferenceConversationHistory,
    fromCreatePreferenceToNewsSummary
}: NewsPreferenceChatProps) {
    const [messages, setMessages] = useState<ChatMessage[]>(preferenceConversationHistory);
    console.log('Initial messages:', messages);
    const [error, setError] = useState<string>('');
    const [userInput, setUserInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

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
        let parentMessageId: string = messages[messages.length - 1].message_id!;
        // Add user message to chat
        const userMessage: ChatMessage = {
            thread_id: messages[0].thread_id,
            parent_message_id: parentMessageId,
            content: userInput,
            author: 'user' as ChatAuthorType,
            isInitData: true
        };

        setMessages(prev => [...prev, userMessage]);
        setUserInput('');
        setIsLoading(true);

        try {
            // Prepare request payload
            const preferenceSurveyRequest: PreferenceSurveyRequest = {
                parent_message_id: parentMessageId,
                answer: userInput
            };

            // Call API
            const response = await submitPreferenceSurvey(preferenceSurveyRequest);
            if (response.preference_summary) {
                fromCreatePreferenceToNewsSummary();
            } else {
                setMessages(prev => {
                    prev[prev.length - 1].message_id = response.parent_message_id;
                    return [...prev, {
                        thread_id: messages[0].thread_id,
                        message_id: response.next_question_message_id,
                        parent_message_id: response.parent_message_id,
                        content: response.next_question,
                        author: 'ai' as ChatAuthorType,
                        isInitData: true
                    } as ChatMessage];
                });
            }

        } catch (error) {
            console.error('Error submitting preference:', error);
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

export function EditPreference() {
    const [preference, setPreference] = useState<string>('');
    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [isSaving, setIsSaving] = useState<boolean>(false);
    const [error, setError] = useState<string>('');
    const [successMessage, setSuccessMessage] = useState<string>('');

    useEffect(() => {
        async function fetchPreference() {
            try {
                setIsLoading(true);
                const preference_summary = await getPreference();
                setPreference(preference_summary);
                setError('');
            } catch (err) {
                console.error('Failed to fetch preferences:', err);
                setError('Failed to load your preferences. Please try again later.');
            } finally {
                setIsLoading(false);
            }
        }

        fetchPreference();
    }, []);

    // Add effect to clear error message after 10 seconds
    useEffect(() => {
        let timeoutId: NodeJS.Timeout;

        if (error) {
            timeoutId = setTimeout(() => {
                setError('');
            }, 10000); // 10 seconds
        }

        return () => {
            if (timeoutId) clearTimeout(timeoutId);
        };
    }, [error]);

    // Add effect to clear success message after 10 seconds
    useEffect(() => {
        let timeoutId: NodeJS.Timeout;

        if (successMessage) {
            timeoutId = setTimeout(() => {
                setSuccessMessage('');
            }, 10000); // 10 seconds
        }

        return () => {
            if (timeoutId) clearTimeout(timeoutId);
        };
    }, [successMessage]);

    const handleSave = async () => {
        try {
            setIsSaving(true);
            setSuccessMessage('');
            setError('');

            await savePreference({ preference_summary: preference });
            setSuccessMessage('Preferences saved successfully!');
        } catch (err) {
            console.error('Failed to save preferences:', err);
            setError('Failed to save your preferences. Please try again later.');
        } finally {
            setIsSaving(false);
        }
    };

    if (isLoading) {
        return (
            <div className="flex justify-center items-center p-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
            </div>
        );
    }

    return (
        <div className="p-4 max-w-2xl mx-auto">
            <h2 className="text-xl font-semibold mb-4">Edit Your News Preferences And Instructions for AI to Show the News Summary</h2>

            {error && (
                <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4 transition-opacity duration-300 ease-in-out">
                    <span>{error}</span>
                </div>
            )}

            {successMessage && (
                <div className="bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded mb-4 transition-opacity duration-300 ease-in-out">
                    <span>{successMessage}</span>
                </div>
            )}

            <div className="mb-4">
                <textarea
                    id="preference"
                    rows={6}
                    disabled={isSaving}
                    value={preference}
                    onChange={(e) => setPreference(e.target.value)}
                    className="w-full p-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="Enter your news preferences here..."
                />
            </div>

            <button
                onClick={handleSave}
                disabled={isSaving}
                className={`px-4 py-2 rounded-md ${isSaving ? 'bg-gray-300 cursor-not-allowed' : 'bg-blue-500 hover:bg-blue-600 text-white'
                    }`}
            >
                {isSaving ? 'Saving...' : 'Save Preferences'}
            </button>
        </div>
    );
}