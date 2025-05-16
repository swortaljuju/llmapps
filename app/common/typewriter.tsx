import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';

interface TypewriterProps {
    text: string;
    showEffect: boolean; // Whether to show typewriter effect
    speed?: number;  // Speed in milliseconds between words
    onComplete?: () => void;
}

export function TypewriterText({
    text,
    showEffect = false,  // Default to false if not provided
    speed = 150,  // Default speed: 150ms per word
    onComplete,
} : TypewriterProps )  {
    const [displayedText, setDisplayedText] = useState(showEffect ? '' : text);
    const [currentWordIndex, setCurrentWordIndex] = useState(0);
    useEffect(() => {
        if (!showEffect) {
            return;
        }
        // Reset state when text changes
        setDisplayedText('');
        setCurrentWordIndex(0);
    }, [text]);

    useEffect(() => {
        if (!showEffect) {
            return;
        }
        // Split text into words
        const words = text.split(' ');

        // If we've completed all words, call onComplete
        if (currentWordIndex >= words.length) {
            onComplete && onComplete();
            return;
        }

        // Set timeout to add the next word
        const timer = setTimeout(() => {
            const newWord = words[currentWordIndex];
            const newText = displayedText + (currentWordIndex > 0 ? ' ' : '') + newWord;
            setDisplayedText(newText);
            setCurrentWordIndex(currentWordIndex + 1);
        }, speed);

        // Cleanup timeout on component unmount or when effect re-runs
        return () => clearTimeout(timer);
    }, [currentWordIndex, displayedText, text, speed, onComplete, showEffect]);    
    
    
    return (
        <ReactMarkdown>{displayedText}</ReactMarkdown>
    );
};

export default TypewriterText;