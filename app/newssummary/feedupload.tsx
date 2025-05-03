'use client';

import { useState } from 'react';
import { uploadRssFeeds } from './store';
import { MainUiMode } from './common';

interface FeedUploadProps {
    setMainUiState: React.Dispatch<React.SetStateAction<MainUiMode>>;
}

export default function FeedUpload({ setMainUiState }: FeedUploadProps) {
    const [file, setFile] = useState<File | null>(null);
    const [isUploading, setIsUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const selectedFile = e.target.files?.[0];
        if (selectedFile) {
            if (!selectedFile.name.endsWith('.opml')) {
                setError('Please select a valid .opml file');
                setFile(null);
                return;
            }
            setFile(selectedFile);
            setError(null);
        }
    };

    const handleUpload = async () => {
        if (!file) {
            setError('Please select an OPML file first');
            return;
        }

        try {
            setIsUploading(true);
            await uploadRssFeeds(file, false);
            setMainUiState(MainUiMode.Chat);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to upload OPML file');
        } finally {
            setIsUploading(false);
        }
    };

    const handleUseDefault = async () => {
        try {
            setIsUploading(true);
            await uploadRssFeeds(null, true);
            setMainUiState(MainUiMode.Chat);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to use default OPML');
        } finally {
            setIsUploading(false);
        }
    };

    return (
        <div className="flex flex-col items-center justify-center p-8 max-w-md mx-auto">
            <h1 className="text-2xl font-bold mb-6">Upload RSS Feeds</h1>

            <div className="w-full bg-white p-6 rounded-lg shadow-md">
                <p className="mb-4 text-gray-700">
                    Please upload an OPML file with your RSS feed subscriptions, or use our default feeds.
                </p>

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

                {error && (
                    <div className="mb-4 p-3 bg-red-100 text-red-700 rounded-md">
                        {error}
                    </div>
                )}

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
        </div>
    );
}