import { getBackendApiUrl } from "../common/utils"

export interface NewsSummaryItem {
    title: string
    content: string
    reference_urls: string[]
    clicked: boolean
}

export interface NewsSummaryList {
    summary: NewsSummaryItem[]
}

export interface NewsSummaryPeriod {
    start_date_timestamp: number;  // Timestamp in seconds
    end_date_timestamp: number;    // Timestamp in seconds
    id: number;
}

export interface InitializeResponse {
    mode: NewsSummaryMode;
    latest_summary?: NewsSummaryList;
    news_summary_periods: NewsSummaryPeriod[];
    preference_conversation_history: ChatMessage[];
}

export interface ChatMessage {
    thread_id: string;
    message_id?: string;
    parent_message_id?: string;
    content: string;
    author: ChatAuthorType;
}

// You'll need to define ChatAuthorType as well, for example:
export type ChatAuthorType = 'user' | 'ai'; // Adjust based on your actual types

export type NewsSummaryMode = 'collect_news_preference' | 'collect_rss_feeds' | 'show_summary';

export async function initialize(): Promise<InitializeResponse> {
    const response = await fetch(getBackendApiUrl('/news_summary/initialize'), {
        method: 'GET',
        credentials: 'include', // Important for sending cookies
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to initialize news summary');
    }

    return await response.json();
}

export interface PreferenceSurveyRequest {
    parent_message_id: string | null;
    answer: string;
}

export interface PreferenceSurveyResponse {
    parent_message_id: string;
    next_question?: string;
    next_question_message_id?: string;
    preference_summary?: string;
}

export async function submitPreferenceSurvey(PreferenceSurveyRequest: PreferenceSurveyRequest): Promise<PreferenceSurveyResponse> {
    const response = await fetch(getBackendApiUrl('/news_summary/preference_survey'), {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(PreferenceSurveyRequest),
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to submit preference survey');
    }

    return await response.json();
}

export async function getPreference(): Promise<string> {
    const response = await fetch(getBackendApiUrl('/news_summary/get_preference'), {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include',
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to get preference');
    }
    let responseJson = await response.json();
    return responseJson.preference_summary;
}

export interface SavePreferenceRequest {
    preference_summary: string;
}

export async function savePreference(savePreferenceRequest: SavePreferenceRequest): Promise<void> {
    const response = await fetch(getBackendApiUrl('/news_summary/save_preference'), {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(savePreferenceRequest),
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to save preference');
    }
}

export interface RssFeed {
    id?: number;
    title: string;
    url: string;
}

export async function uploadRssFeeds(file: File | null, useDefault: boolean): Promise<void> {
    const formData = new FormData();
    
    if (file) {
        formData.append('opml_file', file);
    }
    formData.append('use_default', useDefault.toString());
    
    const response = await fetch(getBackendApiUrl('/news_summary/upload_rss_feeds'), {
        method: 'POST',
        credentials: 'include',
        body: formData,
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to upload RSS feeds');
    }

    return await response.json();
}

export async function getSubscribedRssFeeds(): Promise<RssFeed[]> {
    const response = await fetch(getBackendApiUrl('/news_summary/get_subscribed_rss_feeds'), {
        method: 'GET',
        credentials: 'include',
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to get RSS feeds');
    }

    return await response.json();
}

export async function deleteRssFeed(feedId: number): Promise<void> {
    const response = await fetch(getBackendApiUrl(`/news_summary/delete_rss_feed/${feedId}`), {
        method: 'GET',
        credentials: 'include',
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to delete RSS feed');
    }
}

export async function subscribeRssFeed(rss_feed: RssFeed): Promise<void> {
    const response = await fetch(getBackendApiUrl('/news_summary/subscribe_rss_feed'), {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(rss_feed),
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to subscribe RSS feed');
    }
}