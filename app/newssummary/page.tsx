// News summary app
'use client';
import { AppsLayout, ChatList, ChatListItem } from "../common/appslayout";
import { useState } from 'react';

export default function NewsSummary() {
    const [mainUiMode, setMainUiMode] = useState<MainUiMode>(MainUiMode.Chat);
    const [chatId, setChatId] = useState<number>(1);
    const onChatListItemClick = (chatId: number) => { 
        setChatId(chatId); 
        setMainUiMode(MainUiMode.Chat); }
    const chatList: ChatList = {
        title: 'Chat List',
        items: [
            {
                label: 'Chat 1',
                chatId: 1,
                onClick: onChatListItemClick
            },
            {
                label: 'Chat 2',
                chatId: 2,
                onClick: onChatListItemClick 
            },
            {
                label: 'Chat 3',
                chatId: 3,
                onClick: onChatListItemClick
            }
        ]
    }

    const mainChat = <NewsSummaryMainUi mainUiMode={mainUiMode} chatId={chatId}></NewsSummaryMainUi>;

    return (
        <AppsLayout
            mainChat={mainChat}
            editPreference={() => { setMainUiMode(MainUiMode.EditPreference) }}
            chatList={chatList}
        ></AppsLayout>
    );
}

enum MainUiMode {
    EditPreference = 'EditPreference',
    Chat = 'Chat',
}

interface NewsSummaryMainUiProps {
    mainUiMode: MainUiMode;
    chatId: number;
}

function NewsSummaryMainUi({
    mainUiMode,
    chatId
}: NewsSummaryMainUiProps) {
    const renderPage = () => {
        switch (mainUiMode) {
            case MainUiMode.EditPreference:
                return <div> Edit Preference</div>;
            case MainUiMode.Chat:
                return <div> chat {chatId}</div>;
        }
    };

    return (
        <div>
            {renderPage()}
        </div>
    );
}