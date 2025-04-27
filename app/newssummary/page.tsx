// News summary app
'use client';
import { AppsLayout, SideSection } from "../common/appslayout";
import { useState, useEffect } from 'react';
import { InitializeResponse, initialize } from './store';
import { EditPreference, NewsPreferenceChat} from "./preference";
import { MainUiMode } from "./common";

export default function NewsSummary() {
    // State for API data
    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [apiError, setApiError] = useState<string | null>(null);
    const [initData, setInitData] = useState<InitializeResponse | null>(null);

    const [mainUiMode, setMainUiMode] = useState<MainUiMode>(MainUiMode.Chat);
    const [chatId, setChatId] = useState<string>('1');
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
            } catch (error) {
                console.error('Error initializing news summary:', error);
                setApiError(error instanceof Error ? error.message : 'Unknown error');
            } finally {
                setIsLoading(false);
            }
        };

        fetchInitialData();
    }, []); // Empty dependency array means this runs once on component mount

    const onChatListItemClick = (id: string) => {
        setChatId(id);
        setMainUiMode(MainUiMode.Chat);
    }
    const onPreferenceClick = () => {
        if (mainUiMode !== MainUiMode.CreatePreference && mainUiMode !== MainUiMode.EditPreference) {
            setMainUiMode(MainUiMode.EditPreference);
        }
    }
    const onUploadRssClick = () => {
        setMainUiMode(MainUiMode.UploadRss);
    }
    const chatList: SideSection = {
        title: 'Chat List',
        items: [
            {
                label: 'Chat 1',
                id: '1',
                onClick: onChatListItemClick,
                selected: false
            },
            {
                label: 'Chat 2',
                id: '2',
                onClick: onChatListItemClick,
                selected: false
            },
            {
                label: 'Chat 3',
                id: '3',
                onClick: onChatListItemClick,
                selected: false
            }
        ]
    }

    const customAction: SideSection = {
        title: 'Preference and RSS Upload',
        items: [
            {
                label: 'Preference',
                id: 'Preference',
                onClick: onPreferenceClick,
                selected: mainUiMode === MainUiMode.EditPreference || mainUiMode === MainUiMode.CreatePreference
            },
            {
                label: 'Upload RSS',
                id: MainUiMode.UploadRss,
                onClick: onUploadRssClick,
                selected: mainUiMode === MainUiMode.UploadRss
            }
        ]
    }

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
}

function NewsSummaryMainUi({
    mainUiMode,
    initData,
    setMainUiState
}: NewsSummaryMainUiProps) {

    switch (mainUiMode) {
        case MainUiMode.CreatePreference:
            return <NewsPreferenceChat preferenceConversationHistory={initData!.preference_conversation_history} setMainUiState={setMainUiState}></NewsPreferenceChat>;
        case MainUiMode.EditPreference:
            return <EditPreference/> ;
        case MainUiMode.UploadRss:
            return <div> Upload RSS</div>;
        case MainUiMode.Chat:
            return <div> chat </div>;
    }
}