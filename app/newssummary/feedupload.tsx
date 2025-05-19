'use client';

import { useEffect, useState } from 'react';
import { RssFeed, uploadRssFeeds, getSubscribedRssFeeds, deleteRssFeed, subscribeRssFeed,  NewsSummaryMode} from './store';
import { MainUiMode } from './common';

interface FeedUploadProps {
    fromFeedUploadToCreatePreference: () => void;
    initMode?: NewsSummaryMode;
}

export default function FeedUpload({ fromFeedUploadToCreatePreference, initMode }: FeedUploadProps) {
    const [file, setFile] = useState<File | null>(null);
    const [isUploading, setIsUploading] = useState(false);
    // Error for feed subscription file upload
    const [feedsUploadError, setFeedsUploadError] = useState<string | null>(null);
    // Error for single rss feed addition
    const [feedAddError, setFeedAddError] = useState<string | null>(null);
    // Error for deleting a feed
    const [feedDeletionError, setFeedDeletionError] = useState<string | null>(null);
    const [feedFetchError, setFeedFetchError] = useState<string | null>(null);
    const [subscribedFeeds, setSubscribedFeeds] = useState<RssFeed[]>([]);
    const [singleFeedAdditionFormData, setSingleFeedAdditionFormData] = useState<RssFeed>({
        title: '',
        feed_url: ''});

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setFeedsUploadError(null);
        const selectedFile = e.target.files?.[0];
        if (selectedFile) {
            if (!selectedFile.name.endsWith('.opml')) {
                setFeedsUploadError('Please select a valid .opml file');
                setFile(null);
                return;
            }
            setFile(selectedFile);
            setFeedsUploadError(null);
        }
    };
    const moveForwardIfInitialUploadComplete = () => {
        if (initMode === 'collect_rss_feeds') {
            fromFeedUploadToCreatePreference();
        }
    };
    const handleUpload = async () => {
        setFeedsUploadError(null);
        if (!file) {
            setFeedsUploadError('Please select an OPML file first');
            return;
        }

        try {
            setIsUploading(true);
            await uploadRssFeeds(file, false);
            moveForwardIfInitialUploadComplete();
        } catch (err) {
            setFeedsUploadError(err instanceof Error ? err.message : 'Failed to upload OPML file');
        } finally {
            setIsUploading(false);
        }
    };

    const handleUseDefault = async () => {
        setFeedsUploadError(null);
        try {
            setIsUploading(true);
            await uploadRssFeeds(null, true);
            moveForwardIfInitialUploadComplete();
        } catch (err) {
            setFeedsUploadError(err instanceof Error ? err.message : 'Failed to use default OPML');
        } finally {
            setIsUploading(false);
        }
    };

    const handleDeleteFeed = async (feedId: number) => {
        setFeedDeletionError(null);
        try {
            setIsUploading(true);
            await deleteRssFeed(feedId);
            setSubscribedFeeds((prevFeeds) => prevFeeds.filter((feed) => feed.id !== feedId));
        } catch (err) {
            setFeedDeletionError(err instanceof Error ? err.message : 'Failed to delete feed');
        } finally {
            setIsUploading(false);
        }
    };

    const handleSingleFeedAdditionFormSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFeedAddError(null);
        try {
            setIsUploading(true);
            const feed_id = await subscribeRssFeed(singleFeedAdditionFormData);
            singleFeedAdditionFormData.id = feed_id;
            setSubscribedFeeds((prevFeeds) => [...prevFeeds, singleFeedAdditionFormData]);
            setSingleFeedAdditionFormData({ title: '', feed_url: '' });
        } catch (err) {
            setFeedAddError(err instanceof Error ? err.message : 'Failed to subscribe to feed');
        } finally {
            setIsUploading(false);
        }
    };

    useEffect(() => {
        const fetchSubscribedFeeds = async () => {
            setFeedFetchError(null);
            try {
                const feeds = await getSubscribedRssFeeds();
                setSubscribedFeeds(feeds);
            } catch (err) {
                setFeedFetchError(err instanceof Error ? err.message : 'Failed to fetch subscribed feeds');
            }
        };
        fetchSubscribedFeeds();
    }, []);
    return (
        <div className="flex flex-col items-center justify-center p-8 w-full mx-auto">
            <div className='flex flex-row'>
                <div className="flex flex-col items-center justify-center p-8 max-w-md mx-auto">
                    <h1 className="text-2xl font-bold mb-6">Upload RSS Feeds</h1>
                    {feedsUploadError && (
                            <div className="mb-4 p-3 bg-red-100 text-red-700 rounded-md">
                                {feedsUploadError}
                            </div>
                        )}
                        <div className="mb-6">
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                Upload OPML File
                            </label>
                            <div className="flex items-center justify-center w-full">
                                <label className="flex flex-col w-full h-32 border-2 border-dashed border-gray-300 rounded-md hover:bg-gray-50 cursor-pointer">
                                    <div className="flex flex-col items-center justify-center pt-7">
                                        <svg xmlns="http://www.w3.org/2000/svg" className="w-8 h-8 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                                        </svg>
                                        <p className="pt-1 text-sm tracking-wider text-gray-400">
                                            {file ? file.name : 'Select a file'}
                                        </p>
                                    </div>
                                    <input
                                        type="file"
                                        className="opacity-0"
                                        accept=".opml,application/xml"
                                        onChange={handleFileChange}
                                        disabled={isUploading}
                                    />
                                </label>
                            </div>
                        </div>

                        <div className="flex flex-col sm:flex-row gap-4">
                            <button
                                onClick={handleUpload}
                                disabled={!file || isUploading}
                                className={`flex-1 py-2 px-4 rounded-md ${!file || isUploading
                                        ? 'bg-blue-300 cursor-not-allowed'
                                        : 'bg-blue-600 hover:bg-blue-700'
                                    } text-white font-medium`}
                            >
                                {isUploading ? 'Uploading...' : 'Upload File'}
                            </button>

                            <button
                                onClick={handleUseDefault}
                                disabled={isUploading}
                                className={`flex-1 py-2 px-4 border border-gray-300 rounded-md ${isUploading
                                        ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                                        : 'bg-white hover:bg-gray-50 text-gray-700'
                                    } font-medium`}
                            >
                                {isUploading ? 'Processing...' : 'Use Default Feeds'}
                            </button>
                        </div>
                    </div>     
                <div className="flex flex-col items-center justify-center p-8 max-w-md mx-auto">
                    <div className="w-full bg-white p-6 rounded-lg shadow-md mt-6">
                        <h2 className="text-lg font-medium text-gray-800 mb-4">Add RSS Feed Manually</h2>
                        {feedAddError && (
                            <div className="mb-4 p-3 bg-red-100 text-red-700 rounded-md">
                                {feedAddError}
                            </div>
                        )}
                        <form onSubmit={handleSingleFeedAdditionFormSubmit} className="space-y-4">
                            <div>
                                <label htmlFor="title" className="block text-sm font-medium text-gray-700 mb-1">
                                    Feed Title
                                </label>
                                <input
                                    type="text"
                                    id="title"
                                    value={singleFeedAdditionFormData.title}
                                    onChange={(e) => setSingleFeedAdditionFormData({...singleFeedAdditionFormData, title: e.target.value})}
                                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                                    required
                                />
                            </div>
                            <div>
                                <label htmlFor="url" className="block text-sm font-medium text-gray-700 mb-1">
                                    Feed URL
                                </label>
                                <input
                                    type="url"
                                    id="url"
                                    value={singleFeedAdditionFormData.feed_url}
                                    onChange={(e) => setSingleFeedAdditionFormData({...singleFeedAdditionFormData, feed_url: e.target.value})}
                                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                                    placeholder="https://example.com/rss"
                                    required
                                />
                            </div>
                            <button
                                type="submit"
                                disabled={isUploading || !singleFeedAdditionFormData.title || !singleFeedAdditionFormData.feed_url}
                                className={`w-full py-2 px-4 rounded-md ${
                                    isUploading || !singleFeedAdditionFormData.title || !singleFeedAdditionFormData.feed_url
                                        ? 'bg-blue-300 cursor-not-allowed'
                                        : 'bg-blue-600 hover:bg-blue-700'
                                } text-white font-medium`}
                            >
                                {isUploading ? 'Adding...' : 'Add Feed'}
                            </button>
                        </form>
                    </div>
                </div>  
            </div> 
            <div className="w-full bg-white p-6 rounded-lg shadow-md mt-6">
                <h2 className="text-lg font-medium text-gray-800 mb-4">Subscribed Feeds</h2>
                {feedDeletionError && (
                            <div className="mb-4 p-3 bg-red-100 text-red-700 rounded-md">
                                {feedDeletionError}
                            </div>
                        )}
                {feedFetchError && (
                            <div className="mb-4 p-3 bg-red-100 text-red-700 rounded-md">
                                {feedFetchError}
                            </div>
                        )}
                {subscribedFeeds.length === 0 ? (
                    <p className="text-gray-500">No subscribed feeds.</p>
                ) : (
                    <ul className="space-y-4">
                        {subscribedFeeds.map((feed) => (
                            <li key={feed.id} className="flex justify-between items-center">
                                    <a 
                                        href={feed.feed_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-blue-600 hover:underline block py-2 px-1 w-full"
                                    >
                                        {feed.title}
                                    </a>
                                <button
                                    onClick={() => handleDeleteFeed(feed.id!)}
                                    className="text-red-600 hover:text-red-700 ml-4"
                                >
                                    Delete
                                </button>
                            </li>
                        ))}
                    </ul>
                )}
            </div>
        </div>
    );
}