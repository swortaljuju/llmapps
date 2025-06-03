'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { BiMenu, BiX } from 'react-icons/bi';
import { MdExpandMore, MdExpandLess } from 'react-icons/md';
import { apps } from './constants';

export interface SideSectionItem {
    label: string;
    id: string;
    selected: boolean;
    onClick: (id: string) => boolean;
}

export interface SideSection {
    title: string;
    items: SideSectionItem[];
}

interface AppsLayoutProps {
    mainChat: React.ReactNode;
    customAction: SideSection;
    chatList: SideSection;
}

export function AppsLayout({
    mainChat,
    customAction,
    chatList
}: AppsLayoutProps) {
    const [isNavOpen, setIsNavOpen] = useState(true);
    const [expandedSections, setExpandedSections] = useState({
        apps: false,
        chatList: false,
    });

    const toggleSection = (section: 'apps' | 'chatList') => {
        setExpandedSections(prev => ({
            ...prev,
            [section]: !prev[section]
        }));
    };

    const initializeCustomActionHighlights = () => {
        return customAction.items.reduce((acc, item) => ({
            ...acc,
            [item.id]: false || item.selected
        }), {});
    };
    const [customActionHighlights, setCustomActionHighlights] = useState<Record<string, boolean>>(
        initializeCustomActionHighlights()
    );
    useEffect(() => {
        setCustomActionHighlights(initializeCustomActionHighlights());
    }, [customAction]);

    const initializeChatHighlights = () => {
        return chatList.items.reduce((acc, item) => ({
            ...acc,
            [item.id]: false || item.selected
        }), {});
    };
    const [chatHighlights, setChatHighlights] = useState<Record<string, boolean>>(
        chatList.items.reduce((acc, item) => ({
            ...acc,
            [item.id]: false || item.selected
        }), {})
    );
    useEffect(() => {
        setChatHighlights(initializeChatHighlights());
    }, [chatList]);

    const resetHighlights = () => {
        setCustomActionHighlights(
            Object.keys(customActionHighlights).reduce((acc, key) => ({
                ...acc,
                [key]: false
            }), {})
        );
        setChatHighlights(
            Object.keys(chatHighlights).reduce((acc, key) => ({
                ...acc,
                [key]: false
            }), {})
        );
    };

    const onChatListItemClick = (chatListItem: SideSectionItem) => {
        resetHighlights();
        setChatHighlights(prev => ({
            ...prev,
            [chatListItem.id]: true
        }));
        chatListItem.onClick(chatListItem.id);
    }
    const onCustomActionItemClick = (customActionItem: SideSectionItem) => {
        resetHighlights();
        setCustomActionHighlights(prev => ({
            ...prev,
            [customActionItem.id]: true
        }));
        customActionItem.onClick(customActionItem.id);
    }
    return (
        <div className="h-screen flex flex-col">
            {/* Header */}
            <header className="h-14 border-b flex items-center px-4 bg-white">
                <button
                    onClick={() => setIsNavOpen(!isNavOpen)}
                    className="p-2 hover:bg-gray-100 rounded-md"
                >
                    {isNavOpen ? <BiX size={24} /> : <BiMenu size={24} />}
                </button>
            </header>

            <div className="flex-1 flex overflow-hidden">
                {/* Navigation Sidebar */}
                <nav className={`w-64 border-r bg-gray-50 flex-shrink-0 flex flex-col transition-all duration-300 ease-in-out ${isNavOpen ? 'translate-x-0' : '-translate-x-64'}
        `}>
                    {/* Apps Section */}
                    <div className="border-b">
                        <button
                            onClick={() => toggleSection('apps')}
                            className="w-full p-2 flex items-center justify-between hover:bg-gray-100"
                        >
                            <span className="font-small">Apps</span>
                            {expandedSections.apps ? <MdExpandLess /> : <MdExpandMore />}
                        </button>
                        {expandedSections.apps && (
                            <div className="px-2 pb-1">
                                {apps.
                                    filter(app => app.launched)
                                    .map(app => (
                                        <Link
                                            key={app.route}
                                            href={app.route}
                                            className="block px-4 py-1 rounded-md hover:bg-gray-100"
                                        >
                                            {app.name}
                                        </Link>
                                    ))}
                            </div>
                        )}
                    </div>

                    {/* Custom Actions - Flattened List */}
                    {customAction.items.map(customActionItem => (
                        <button
                            key={customActionItem.id}
                            onClick={() => onCustomActionItemClick(customActionItem)}
                            className={`w-full p-2 flex items-center justify-between hover:bg-gray-100 ${customActionHighlights[customActionItem.id] ? 'bg-blue-100' : ''
                                }`}
                        >
                            <span className="font-small">{customActionItem.label}</span>
                        </button>
                    ))}

                    <div className="border-b">
                        <button
                            onClick={() => toggleSection('chatList')}
                            className="w-full p-2 flex items-center justify-between hover:bg-gray-100"
                        >
                            <span className="font-small">{chatList.title}</span>
                            {expandedSections.chatList ? <MdExpandLess /> : <MdExpandMore />}
                        </button>
                        {expandedSections.chatList && (
                            <div className="px-2 pb-1">
                                {chatList.items
                                    .map(chatListItem => (
                                        <button
                                            key={chatListItem.id}
                                            onClick={() => onChatListItemClick(chatListItem)}
                                            className={`w-full p-2 flex items-center justify-between hover:bg-gray-100 ${chatHighlights[chatListItem.id] ? 'bg-blue-100' : ''
                                                }`}
                                        >
                                            <span className="font-small">{chatListItem.label}</span>
                                        </button>
                                    ))}
                            </div>
                        )}
                    </div>
                </nav>

                {/* Main Content */}
                <main className="flex-1 overflow-auto bg-white">
                    {mainChat}
                </main>
            </div>
        </div>
    );
}