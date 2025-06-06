// News summary app
'use client';

import { AppsLayout, SideSection, SideSectionItem } from "../common/appslayout";
import { useState, useEffect } from 'react';
import { InitializeResponse, initialize } from './store';
import { EditPreference, NewsPreferenceChat } from "./preference";
import { MainUiMode } from "./common";
import FeedUpload from './feedupload';
import SummaryContent from './summarycontent';

const PREFERENCE_ID = 'preference';

export default function NewsSummary() {
    // State for API data
    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [apiError, setApiError] = useState<string | null>(null);
    const [initData, setInitData] = useState<InitializeResponse | null>(null);

    const [mainUiMode, setMainUiMode] = useState<MainUiMode>(MainUiMode.Summary);
    const refreshInitData = async () => {
        setIsLoading(true);
        setApiError(null);

        try {
            const data: InitializeResponse = await initialize();
            setInitData(data);
        } catch (error) {
            console.error('Error initializing news summary:', error);
            setApiError(error instanceof Error ? error.message : 'Unknown error');
        } finally {
            setIsLoading(false);
        }
    };
    const onPreferenceClick = async () => {
        if (initData?.mode === 'collect_rss_feeds') {
            return false;
        }
        await refreshInitData();
        if (initData?.mode === 'show_summary') {
            setMainUiMode(MainUiMode.EditPreference);
        } else {
            setMainUiMode(MainUiMode.CreatePreference);
        }
        return true;
    }
    const onUploadRssClick = async () => {
        await refreshInitData();
        setMainUiMode(MainUiMode.UploadRss);
        return true;
    }
    const onSummaryClick = async () => {
        if (initData?.mode !== 'show_summary') {
            return false;
        }
        setMainUiMode(MainUiMode.Summary);
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
            },
            {
                label: 'News Summary',
                id: MainUiMode.Summary,
                onClick: onSummaryClick,
                selected: mainUiMode === MainUiMode.Summary
            }
        ]
    };
    const [customAction, setCustomAction] = useState<SideSection>({
        title: 'Custom Actions',
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
                    setMainUiMode(MainUiMode.Summary);
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

    const fromFeedUploadToCreatePreference = async () => {
        const data: InitializeResponse = await initialize();
        // generate initial preference survey
        setInitData(data);
        setMainUiMode(MainUiMode.CreatePreference);
    }

    const fromCreatePreferenceToNewsSummary = async () => {
        const data: InitializeResponse = await initialize();
        // generate initial preference survey
        setInitData(data);
        setMainUiMode(MainUiMode.Summary);
    }

    useEffect(() => {
        // Update the 'selected' property of each item in the chatList
        setCustomAction(prev => ({
            ...prev,
            items: createCustomActionItem()
        }));
    }, [mainUiMode]);

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
                fromCreatePreferenceToNewsSummary={fromCreatePreferenceToNewsSummary}
            />
        );
    }
    const chatList = {
        title: 'News Research',
        items: []
    } as SideSection;
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
    fromCreatePreferenceToNewsSummary: () => void;
}

function NewsSummaryMainUi({
    mainUiMode,
    initData,
    setMainUiState,
    fromFeedUploadToCreatePreference,
    fromCreatePreferenceToNewsSummary,
}: NewsSummaryMainUiProps) {

    switch (mainUiMode) {
        case MainUiMode.CreatePreference:
            return <NewsPreferenceChat preferenceConversationHistory={initData!.preference_conversation_history} fromCreatePreferenceToNewsSummary={fromCreatePreferenceToNewsSummary}></NewsPreferenceChat>;
        case MainUiMode.EditPreference:
            return <EditPreference />;
        case MainUiMode.UploadRss:
            return <FeedUpload fromFeedUploadToCreatePreference={fromFeedUploadToCreatePreference} initMode={initData?.mode}/>;
        case MainUiMode.Summary:
            return <SummaryContent latestSummary={initData?.latest_summary} defaultOptions={initData?.default_news_summary_options} startDateList={initData?.available_period_start_date_str}/>;
        case MainUiMode.NewsResearch:
            return <div className="flex items-center justify-center h-screen">News Research</div>;
    }
}
