'use client';

import { useEffect, useState } from 'react';
import {
    getNewsSummary,
    likeDislikeNewsSummary,
    expandSummary,
    NewsChunkingExperiment,
    NewsPreferenceApplicationExperiment,
    NewsSummaryItem,
    NewsSummaryOptions,
    NewsSummaryPeriod,
    NewsSummaryLikeDislikeRequest,
    NewsSummaryLikeDislikeAction,
} from './store';
import ReactMarkdown from 'react-markdown';

interface SummaryContentProps {
    latestSummary: NewsSummaryItem[] | undefined;
    defaultOptions: NewsSummaryOptions | undefined;
    startDateList: string[] | undefined;
}

function getCurrentWeekStartDateStr(): string {
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, '0'); // Months are 0-based, so add 1
    const dayOfWeek = today.getDay();
    today.setDate(today.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1)); // Set to the previous Monday
    const day = String(today.getDate()).padStart(2, '0');

    return `${year}-${month}-${day}`;
}

function getTodayStr(): string {
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, '0'); // Months are 0-based, so add 1
    const day = String(today.getDate()).padStart(2, '0');

    return `${year}-${month}-${day}`;
}

interface UiNewsSummaryItem extends NewsSummaryItem {
    expandSummaryCalled: boolean;
    expandedContentShown: boolean;
    isLoading: boolean;
}

interface UiNewsSummaryItemPerCategory {
    category: string;
    items: UiNewsSummaryItem[];
}

function createUiNewsSummaryItemPerCategory(newsSummaryItemList: NewsSummaryItem[]): UiNewsSummaryItemPerCategory[] {
    const uiItemsByCategory: { [category: string]: UiNewsSummaryItem[] } = {};

    newsSummaryItemList.forEach(item => {
        const uiItem: UiNewsSummaryItem = createUiNewsSummaryItem(item);
        if (!uiItemsByCategory[item.category]) {
            uiItemsByCategory[item.category] = [];
        }
        uiItemsByCategory[item.category].push(uiItem);
    });

    // Convert the object to an array of UiNewsSummaryItemPerCategory
    const uiItemsPerCategoryArray: UiNewsSummaryItemPerCategory[] = Object.entries(uiItemsByCategory).map(([category, items]) => ({
        category: category,
        items: items,
    }));

    // Sort the array based on the display_order of the first item in each category
    uiItemsPerCategoryArray.sort((a, b) => {
        return a.items[0].display_order - b.items[0].display_order;
    });
    uiItemsPerCategoryArray.forEach(category => {
        category.items.sort((a, b) => a.display_order - b.display_order);
    });
    return uiItemsPerCategoryArray;
}

function createUiNewsSummaryItem(newsSummaryItem: NewsSummaryItem): UiNewsSummaryItem {
    return {
        ...newsSummaryItem,
        expandSummaryCalled: false,
        expandedContentShown: false,
        isLoading: false,
    };
}

const CURRENT_WEEK_LABEL = "Current Week";
const TODAY_LABEL = 'Today';
const CURRENT_WEEK_STR = getCurrentWeekStartDateStr();
const TODAY_STR = getTodayStr();


export default function SummaryContent({ latestSummary, defaultOptions, startDateList }: SummaryContentProps) {
    const [summaryItems, setSummaryItems] = useState<UiNewsSummaryItemPerCategory[]>(latestSummary ? createUiNewsSummaryItemPerCategory(latestSummary) : []);
    const [isSummaryEntryLoading, setIsSummaryEntryLoading] = useState<boolean>(false);
    const [selectedOptions, setSelectedOptions] = useState<NewsSummaryOptions>(defaultOptions || {
        news_chunking_experiment: NewsChunkingExperiment.AGGREGATE_DAILY,
        news_preference_application_experiment: NewsPreferenceApplicationExperiment.APPLY_PREFERENCE,
        period_type: NewsSummaryPeriod.WEEKLY,
    });

    const [isOptionsVisible, setIsOptionsVisible] = useState(true);

    const filterAvailableStartDate = () => {
        if (startDateList) {
            const tempStartDateList = startDateList.filter(date => {
                if (selectedOptions.period_type === NewsSummaryPeriod.DAILY) {
                    return date !== TODAY_STR; // Remove 'Today' if it exists
                } else if (selectedOptions.period_type === NewsSummaryPeriod.WEEKLY) {
                    var date_components = date.split('-');
                    const dateObj = new Date();
                    dateObj.setFullYear(parseInt(date_components[0]), parseInt(date_components[1]) - 1, parseInt(date_components[2]));
                    const dayOfWeek = dateObj.getDay();
                    return dayOfWeek === 1 && date !== CURRENT_WEEK_STR; // Keep only Mondays and remove 'Current Week'
                }
                return false;
            }); // Remove 'Today' if it exists
            if (selectedOptions.period_type === NewsSummaryPeriod.WEEKLY) {
                return [CURRENT_WEEK_LABEL, ...tempStartDateList];
            } else if (selectedOptions.period_type === NewsSummaryPeriod.DAILY) {
                return [TODAY_LABEL, ...tempStartDateList];
            } else {
                return [];
            }
        }
        if (selectedOptions.period_type === NewsSummaryPeriod.WEEKLY) {
            return [CURRENT_WEEK_LABEL];
        } else if (selectedOptions.period_type === NewsSummaryPeriod.DAILY) {
            return [TODAY_LABEL];
        } else {
            return [];
        }
    };

    const [availableStartDateList, setAvailableStartDateList] = useState<string[]>(() => filterAvailableStartDate());
    const [periodStartDate, setPeriodStartDate] = useState<string>(availableStartDateList[0]);

    const [summaryLoadingError, setSummaryLoadingError] = useState<string | null>(null);
    useEffect(() => {
        setSummaryItems(latestSummary ? createUiNewsSummaryItemPerCategory(latestSummary) : []);
        setPeriodStartDate(availableStartDateList[0]);
    }, [latestSummary]);

    useEffect(() => {
        setAvailableStartDateList(filterAvailableStartDate());
        if (selectedOptions.period_type === NewsSummaryPeriod.WEEKLY) {
            setPeriodStartDate(CURRENT_WEEK_LABEL);
        }
        else if (selectedOptions.period_type === NewsSummaryPeriod.DAILY) {
            setPeriodStartDate(TODAY_LABEL);
        }
    }, [selectedOptions.period_type]);

    const handleOptionChange = (optionType: keyof NewsSummaryOptions, value: any) => {
        setSelectedOptions(prev => ({ ...prev, [optionType]: value }));

    };

    const getPeriodStartDateStr = () => {
        if (periodStartDate === CURRENT_WEEK_LABEL) {
            return CURRENT_WEEK_STR;
        } else if (periodStartDate === TODAY_LABEL) {
            return TODAY_STR;
        }
        return periodStartDate;
    };
    const handleGetNewsSummary = async () => {
        if (!selectedOptions) {
            console.error("Options not initialized");
            return;
        }
        const getNewsSummaryRequest = {
            news_summary_start_date_and_option_selector: {
                start_date: getPeriodStartDateStr(),
                option: selectedOptions,
            }
        };

        try {
            setIsSummaryEntryLoading(true);
            const newSummary = await getNewsSummary(getNewsSummaryRequest);
            setSummaryItems(newSummary ? createUiNewsSummaryItemPerCategory(newSummary) : []);
        } catch (error: any) {
            setSummaryLoadingError(error.message);
            console.error("Failed to get news summary:", error.message);
        } finally {
            setIsSummaryEntryLoading(false);
        }
    };

    const handleLikeDislike = async (action: NewsSummaryLikeDislikeAction) => {
        if (!selectedOptions) {
            console.error("Options not initialized");
            return;
        }


        const newsSummaryLikeDislikeRequest: NewsSummaryLikeDislikeRequest = {
            news_summary_start_date_and_option_selector: {
                start_date: getPeriodStartDateStr(),
                option: selectedOptions,
            },
            action: action,
        };

        try {
            await likeDislikeNewsSummary(newsSummaryLikeDislikeRequest);
            console.log(`Successfully ${action}d news summary`);
        } catch (error: any) {
            console.error(`Failed to ${action} news summary:`, error.message);
        }
    };

    const callExpandSummaryApi = async (selectedItem: UiNewsSummaryItem) => {
        setSummaryItems(prev =>
            {
                return prev.map(category => ({
                    ...category,
                    items: category.items.map(item =>
                        item.id === selectedItem.id ? { ...item,  isLoading: true  } : item
                    )
                }));
            }
        );

        try {
            const expandedItem = await expandSummary(selectedItem.id);
            setSummaryItems(prev => {
                return prev.map(category => ({
                    ...category,
                    items: category.items.map(item =>
                        item.id === selectedItem.id ? { ...item, ...expandedItem, expandedContentShown: true, expandSummaryCalled: true, isLoading: false } : item
                    )
                }));
            });
        } catch (error: any) {
            console.error("Failed to expand summary:", error.message);
            throw error;
        } finally {
            setSummaryItems(prev =>
                {
                    return prev.map(category => ({
                        ...category,
                        items: category.items.map(item =>
                            item.id === selectedItem.id ? { ...item,  isLoading: false  } : item
                        )
                    }));
                }
            );
        }
    };

    const onSummaryItemClicked = (selectedItem: UiNewsSummaryItem) => {
        if (selectedItem.expandedContentShown) {
            // If already expanded, collapse it
            setSummaryItems(prev =>
                {
                    return prev.map(category => ({
                        ...category,
                        items: category.items.map(item =>
                            item.id === selectedItem.id ? { ...item,  expandedContentShown: false  } : item
                        )
                    }));
                }
            );
        } else {
            if (selectedItem.expandSummaryCalled) {
                setSummaryItems(prev =>
                    {
                        return prev.map(category => ({
                            ...category,
                            items: category.items.map(item =>
                                item.id === selectedItem.id ? { ...item,  expandedContentShown: true  } : item
                            )
                        }));
                    }
                );
            } else {
                callExpandSummaryApi(selectedItem)
            }
        }

    };

    return (
        <div className="flex flex-col h-full">
            {/* Upper Panel: News Summary Entry List */}
            <div className="flex-1 overflow-y-auto p-4">
                {isSummaryEntryLoading ? (
                    <div className="justify-center text-center">
                        <p className="text-lg font-semibold mb-4">Generating news summaries... It may take several minutes....</p>
                        <div className="animate-spin rounded-full h-32 w-32 border-t-2 border-b-2 border-blue-500 mx-auto"></div>

                    </div>
                ) : summaryLoadingError ? (
                    <p className="text-red-500">Error: {summaryLoadingError}</p>
                ) : summaryItems.length === 0 ? (
                    <p>No news summaries available.</p>
                ) : (
                    summaryItems.map(category => (
                        <div key={category.category} className="mb-8">
                            <h2 className="text-xl font-bold mb-2">{category.category}</h2>
                            {category.items.map(item => (
                                <div key={item.id} className="mb-4 p-4 border rounded-md">
                                    <div onClick={() => onSummaryItemClicked(item)}>
                                        <h3
                                            className="text-lg font-semibold cursor-pointer"
                                            title='Click to expand/collapse summary'
                                            
                                        >
                                            {item.title}
                                            {item.isLoading ? ' ⏳' : item.expandedContentShown ? ' ▲' : ' ▼'}

                                        </h3>
                                        {item.content && <ReactMarkdown>{item.content}</ReactMarkdown>}

                                    </div>
                                    {item.reference_urls && (
                                        <div className="mt-2">
                                            {item.reference_urls.map((url, index) => (
                                                <a
                                                    key={index}
                                                    href={url}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="text-blue-500 hover:underline mr-2"
                                                >
                                                    Ref {index + 1}
                                                </a>
                                            ))}
                                        </div>
                                    )}
                                    {item.isLoading ? (
                                        <div className="flex justify-center items-center">
                                            <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-blue-500"></div>
                                        </div>
                                    ) : (
                                        <div className={`mt-2 overflow-hidden transition-all duration-500 ease-in-out ${item.expandedContentShown ? 'max-h-96' : 'max-h-0'}`}>
                                            {item.expanded_content && <ReactMarkdown>{item.expanded_content}</ReactMarkdown>}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    ))
                )}
            </div>


            {/* Bottom Panel: Options and Buttons */}
            <div className="p-4 border-t">
                <button
                    onClick={() => setIsOptionsVisible(!isOptionsVisible)}
                    className="bg-gray-500 hover:bg-gray-700 text-white font-bold py-2 px-4 rounded mb-4"
                >
                    {isOptionsVisible ? 'Hide Options' : 'Show Options'}
                </button>
                {isOptionsVisible && (
                    <div className="flex flex-wrap gap-10">
                        {/* Option Pickers */}
                        <div className="mb-4">
                            <label className="block text-lg font-bold text-gray-700">Summarization Strategy</label>
                            <select
                                className="mt-1 block w-full rounded-md border-gray-300 text-lg shadow-sm bg-white h-12 text-center focus:border-indigo-500 focus:ring-indigo-500"
                                value={selectedOptions?.news_chunking_experiment}
                                onChange={e => handleOptionChange('news_chunking_experiment', e.target.value)}
                            >
                                <option value={NewsChunkingExperiment.AGGREGATE_DAILY}>Aggregate Daily</option>
                                <option value={NewsChunkingExperiment.EMBEDDING_CLUSTERING}>Cluster by Content</option>
                            </select>
                        </div>

                        <div className="mb-4">
                            <label className="block text-lg font-bold text-gray-700">Apply Preference</label>
                            <select
                                className="mt-1 block w-full rounded-md border-gray-300 text-lg shadow-sm bg-white h-12 text-center focus:border-indigo-500 focus:ring-indigo-500"
                                value={selectedOptions?.news_preference_application_experiment}
                                onChange={e => handleOptionChange('news_preference_application_experiment', e.target.value)}
                            >
                                <option value={NewsPreferenceApplicationExperiment.APPLY_PREFERENCE}>Use Preference</option>
                                <option value={NewsPreferenceApplicationExperiment.NO_PREFERENCE}>No Preference</option>
                            </select>
                        </div>

                        <div className="mb-4">
                            <label className="block text-lg font-bold text-gray-700" title="The period during which news are summarized">Period Type</label>
                            <select
                                className="mt-1 block w-full rounded-md border-gray-300 text-lg shadow-sm bg-white h-12 text-center focus:border-indigo-500 focus:ring-indigo-500"
                                value={selectedOptions?.period_type}
                                onChange={e => handleOptionChange('period_type', e.target.value)}
                            >
                                <option value={NewsSummaryPeriod.DAILY}>Daily</option>
                                <option value={NewsSummaryPeriod.WEEKLY}>Weekly</option>
                            </select>
                        </div>

                        <div className="mb-4">
                            <label className="block text-lg font-bold text-gray-700">Period start date</label>
                            <select
                                className="mt-1 block w-full rounded-md border-gray-300 text-lg shadow-sm bg-white h-12 text-center focus:border-indigo-500 focus:ring-indigo-500"
                                value={periodStartDate}
                                onChange={e => setPeriodStartDate(e.target.value)}
                            >
                                {availableStartDateList.map(date => (
                                    <option key={date} value={date}>{date}</option>
                                ))}
                            </select>
                        </div>
                    </div>
                )}
                {/* Buttons */}
                <div className="flex gap-4 mt-4">
                    <button
                        onClick={handleGetNewsSummary}
                        title="Get news summary based on selected options"
                        className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded mr-20"
                    >
                        Submit
                    </button>
                    <div>
                        <button
                            onClick={() => handleLikeDislike(NewsSummaryLikeDislikeAction.LIKE)}
                            className="bg-green-500 hover:bg-green-700 text-white font-bold py-2 px-4 rounded mr-2"
                            title="Like the news summary given the selected options"
                            disabled={summaryItems.length === 0}
                        >
                            Like
                        </button>
                        <button
                            onClick={() => handleLikeDislike(NewsSummaryLikeDislikeAction.DISLIKE)}
                            className="bg-red-500 hover:bg-red-700 text-white font-bold py-2 px-4 rounded"
                            title="Dislike the news summary given the selected options"
                            disabled={summaryItems.length === 0}
                        >
                            Dislike
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}