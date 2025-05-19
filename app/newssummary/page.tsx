// News summary app
'use client';

import { AppsLayout, SideSection, SideSectionItem } from "../common/appslayout";
import { useState, useEffect } from 'react';
import { InitializeResponse, initialize } from './store';
import { EditPreference, NewsPreferenceChat } from "./preference";
import { MainUiMode } from "./common";
import FeedUpload from './feedupload';

const EMPTY_SUMMARY_CHAT_ID = 'empty-summary';
const PREFERENCE_ID = 'preference';

export default function NewsSummary() {
    // State for API data
    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [apiError, setApiError] = useState<string | null>(null);
    const [initData, setInitData] = useState<InitializeResponse | null>(null);

    const [mainUiMode, setMainUiMode] = useState<MainUiMode>(MainUiMode.Chat);
    const [chatId, setChatId] = useState<string>('');
    const onChatListItemClick = (id: string) => {
        setChatId(id);
        setMainUiMode(MainUiMode.Chat);
        return true;
    }

    const initializeChatListItems = (initData: InitializeResponse) => {
        // Assuming initData has a property 'chat_threads' which is an array of chat thread objects
        if (initData.news_summary_periods && initData.news_summary_periods.length > 0) {
            return initData.news_summary_periods.map(newsSummaryPeriod => ({
                label: `Summary from ${new Date(newsSummaryPeriod.start_date_timestamp * 1000).toLocaleDateString()} to ${new Date(newsSummaryPeriod.end_date_timestamp * 1000).toLocaleDateString()}`,
                id: newsSummaryPeriod.id + '',
                onClick: onChatListItemClick, // Placeholder for click handler
                selected: chatId === newsSummaryPeriod.id + ''
            }));
        } else {
            return [
                {
                    label: 'Next Summary Coming',
                    id: EMPTY_SUMMARY_CHAT_ID,
                    onClick: onChatListItemClick,
                    selected: chatId === EMPTY_SUMMARY_CHAT_ID
                }
            ]
        }

    };
    const [chatList, setChatList] = useState<SideSection>({
        title: 'Chat List',
        items: []
    });

    const onPreferenceClick = () => {
        if (initData?.mode === 'collect_rss_feeds') {
            return false;
        }
        if (initData?.mode === 'show_summary') {
            setMainUiMode(MainUiMode.EditPreference);
        } else {
            setMainUiMode(MainUiMode.CreatePreference);
        }
        return true;
    }
    const onUploadRssClick = () => {
        setMainUiMode(MainUiMode.UploadRss);
        return true;
    }
    const createCustomActionItem = () => {
        return [
            {
                label: 'Upload RSS',
                id: MainUiMode.UploadRss,
                onClick: onUploadRssClick,
                selected: mainUiMode === MainUiMode.UploadRss
            },
            {
                label: 'Preference',
                id: PREFERENCE_ID,
                onClick: onPreferenceClick,
                selected: mainUiMode === MainUiMode.EditPreference || mainUiMode === MainUiMode.CreatePreference
            }
        ]
    };
    const [customAction, setCustomAction] = useState<SideSection>({
        title: 'Preference and RSS Upload',
        items: createCustomActionItem()
    });
    // Fetch initialization data
    useEffect(() => {
        const fetchInitialData = async () => {
            setIsLoading(true);
            setApiError(null);

            try {
                const data: InitializeResponse = await initialize();
                setInitData(data);
                // Set the UI mode based on the API response
                if (data.mode === 'collect_news_preference') {
                    setMainUiMode(MainUiMode.CreatePreference);
                } else if (data.mode === 'collect_rss_feeds') {
                    setMainUiMode(MainUiMode.UploadRss);
                } else {
                    setMainUiMode(MainUiMode.Chat);
                }

                const chatListItems = initializeChatListItems(data);
                if (chatId === '') {
                    setChatId(chatListItems[0].id);
                    chatListItems[0].selected = true; // Set the first item as selected
                }
                setChatList((prev) => {
                    // Update the chatList with the new items
                    return {
                        ...prev,
                        items: chatListItems
                    };
                });
                
            } catch (error) {
                console.error('Error initializing news summary:', error);
                setApiError(error instanceof Error ? error.message : 'Unknown error');
            } finally {
                setIsLoading(false);
            }
        };
        fetchInitialData();
    }, []); // Empty dependency array means this runs once on component mount

    const fromFeedUploadToCreatePreference = async () => {
        const data: InitializeResponse = await initialize();
        // generate initial preference survey
        setInitData(data);
        setMainUiMode(MainUiMode.CreatePreference);
    }
    // Update chatList selection when mainUiMode or chatId changes
    useEffect(() => {
        setChatList(prev => ({
            ...prev,
            items: prev.items.map(item => ({
                ...item,
                selected: item.id === chatId && mainUiMode === MainUiMode.Chat
            }))
        }));
        // Update the 'selected' property of each item in the chatList
        setCustomAction(prev => ({
            ...prev,
            items: createCustomActionItem()
        }));
    }, [mainUiMode, chatId]);

    let mainChat: React.ReactNode = null;
    // Loading state
    if (isLoading) {
        mainChat = <div className="flex items-center justify-center h-screen">Loading...</div>;
    } else if (apiError) {
        mainChat = (
            <div className="flex flex-col items-center justify-center h-screen">
                <h2 className="text-xl font-bold text-red-600 mb-4">Error</h2>
                <p>{apiError}</p>
                <button
                    className="mt-4 px-4 py-2 bg-blue-600 text-white rounded"
                    onClick={() => window.location.reload()}
                >
                    Retry
                </button>
            </div>
        );
    } else {
        mainChat = (
            <NewsSummaryMainUi
                mainUiMode={mainUiMode}
                initData={initData}
                setMainUiState={setMainUiMode}
                fromFeedUploadToCreatePreference={fromFeedUploadToCreatePreference}
                selectedSummaryId={chatId}
            />
        );
    }

    return (
        <AppsLayout
            mainChat={mainChat}
            customAction={customAction}
            chatList={chatList}
        ></AppsLayout>
    );
}


interface NewsSummaryMainUiProps {
    mainUiMode: MainUiMode;
    initData: InitializeResponse | null;
    setMainUiState: React.Dispatch<React.SetStateAction<MainUiMode>>;
    fromFeedUploadToCreatePreference: () => void;
    selectedSummaryId: string;
}

function NewsSummaryMainUi({
    mainUiMode,
    initData,
    setMainUiState,
    fromFeedUploadToCreatePreference,
    selectedSummaryId,
}: NewsSummaryMainUiProps) {

    switch (mainUiMode) {
        case MainUiMode.CreatePreference:
            return <NewsPreferenceChat preferenceConversationHistory={initData!.preference_conversation_history} setMainUiState={setMainUiState}></NewsPreferenceChat>;
        case MainUiMode.EditPreference:
            return <EditPreference />;
        case MainUiMode.UploadRss:
            return <FeedUpload fromFeedUploadToCreatePreference={fromFeedUploadToCreatePreference} initMode={initData?.mode}/>;
        case MainUiMode.Chat:
            if (selectedSummaryId === EMPTY_SUMMARY_CHAT_ID) {
                return <div className="flex items-center justify-center h-screen">No summary available yet. Please wait for the next summary.</div>;
            }
            return <div> chat </div>;
    }
}
