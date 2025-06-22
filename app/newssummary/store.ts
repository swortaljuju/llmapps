import { init } from "next/dist/compiled/webpack/webpack";
import { getBackendApiUrl } from "../common/utils"

export interface NewsSummaryItem {
    id: number;
    category: string;
    title: string;
    content: string;
    expanded_content?: string;
    reference_urls: string[];
    display_order: number;
    clicked: boolean;
}

export interface NewsSummaryOptions {
    news_chunking_experiment: NewsChunkingExperiment;
    news_preference_application_experiment: NewsPreferenceApplicationExperiment;
    period_type: NewsSummaryPeriod;
}
export interface InitializeResponse {
    mode: NewsSummaryMode;
    latest_summary: NewsSummaryItem[];
    default_news_summary_options: NewsSummaryOptions;
    available_period_start_date_str: string[];
    preference_conversation_history: ChatMessage[];
}

export interface ChatMessage {
    thread_id?: string;
    message_id?: string;
    parent_message_id?: string;
    content: string;
    author: ChatAuthorType;
    isInitData: boolean;
}

// You'll need to define ChatAuthorType as well, for example:
export type ChatAuthorType = 'user' | 'ai'; // Adjust based on your actual types

export type NewsSummaryMode = 'collect_rss_feeds' | 'collect_news_preference' | 'show_summary';

export enum NewsChunkingExperiment {
    AGGREGATE_DAILY = "AGGREGATE_DAILY",
    EMBEDDING_CLUSTERING = "EMBEDDING_CLUSTERING"
}

export enum NewsPreferenceApplicationExperiment {
    APPLY_PREFERENCE = "APPLY_PREFERENCE",
    NO_PREFERENCE = "NO_PREFERENCE"
}

export enum NewsSummaryPeriod {
    DAILY = "daily",
    WEEKLY = "weekly",
}

export async function initialize(): Promise<InitializeResponse> {
    const response = await fetch(getBackendApiUrl('/news_summary/initialize'), {
        method: 'GET',
        credentials: 'include', // Important for sending cookies
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to initialize news summary');
    }

    const initializeResponse =  await response.json();

    if (initializeResponse.preference_conversation_history) {
        initializeResponse.preference_conversation_history = initializeResponse.preference_conversation_history.map((msg: any) => ({
            ...msg,
            isInitData: true,
        })) as ChatMessage[];
    }
    return initializeResponse;
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
    feed_url: string;
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

export async function subscribeRssFeed(rss_feed: RssFeed): Promise<number> {
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
    const responseJson = await response.json();
    return responseJson.feed_id;
}

export interface NewsSummaryStartDateAndOptionSelector {
    start_date: string;
    option: NewsSummaryOptions;
}

export interface GetNewsSummaryRequest {
    news_summary_start_date_and_option_selector: NewsSummaryStartDateAndOptionSelector;
}

export async function getNewsSummary(request: GetNewsSummaryRequest): Promise<NewsSummaryItem[]> {
    const response = await fetch(getBackendApiUrl('/news_summary/get_news_summary'), {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(request),
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to get news summary');
    }

    return await response.json();
}

export enum NewsSummaryLikeDislikeAction {
    LIKE = 'like',
    DISLIKE = 'dislike'
}
export interface NewsSummaryLikeDislikeRequest {
    news_summary_start_date_and_option_selector: NewsSummaryStartDateAndOptionSelector;
    action: NewsSummaryLikeDislikeAction;
}

export async function likeDislikeNewsSummary(request: NewsSummaryLikeDislikeRequest): Promise<void> {
    const response = await fetch(getBackendApiUrl('/news_summary/like_dislike_news_summary'), {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(request),
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to like/dislike news summary');
    }
}

export async function expandSummary(summaryId: number): Promise<NewsSummaryItem> {
    const response = await fetch(getBackendApiUrl(`/news_summary/expand_summary?summary_id=${summaryId}`), {
        method: 'GET',
        credentials: 'include',
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to expand summary');
    }

    return await response.json();
}

export interface NewsResearchAnswerQuestionRequest {
    parent_message_id?: string | null;
    thread_id?: string | null;
    question: string;
}

export interface  NewsResearchAnswerQuestionResponse{
    question: ChatMessage;
    answer: ChatMessage;
}

export async function newsResearchAnswerQuestion(request: NewsResearchAnswerQuestionRequest): Promise<NewsResearchAnswerQuestionResponse> {
    const response = await fetch(getBackendApiUrl('/news_summary/news_research_answer_question'), {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(request),
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to submit question');
    }

    return await response.json();
}

export async function getNewsResearchChatHistory(): Promise<ChatMessage[]> {
    const response = await fetch(getBackendApiUrl('/news_summary/get_news_research_chat_history'), {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include',
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to load news research chat history');
    }
    const chatHistory =  await response.json();

    return chatHistory.map((msg: any) => ({
        ...msg,
        isInitData: true,
    })) as ChatMessage[];
}