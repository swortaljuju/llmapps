'use client';

import { useState } from 'react';
import { apps } from './common/constants';
import { BiLoaderAlt } from 'react-icons/bi';
import { useRouter } from "next/navigation";
import {getBackendApiUrl} from "./common/utils"

enum PageState {
  AppsSummary = 'AppsSummary',
  SignIn = 'SignIn',
  SignUp = 'SignUp'
}

export default function Home() {
  const [currentPage, setCurrentPage] = useState<PageState>(PageState.AppsSummary);

  const renderPage = () => {
    switch (currentPage) {
      case PageState.SignIn:
        return <SignInForm onStateChange={setCurrentPage} />;
      case PageState.SignUp:
        return <SignUpForm onStateChange={setCurrentPage} />;
      default:
        return <AppsSummary onStateChange={setCurrentPage} />;
    }
  };

  return (
    <div>
      {renderPage()}
    </div>
  );
}

function AppsSummary({ onStateChange }: { onStateChange: (state: PageState) => void }) {

  return (
    <div className="min-h-screen p-8 bg-gray-100">
      <h1 className="text-4xl font-bold text-center mb-8">LLM App Portfolio</h1>
      <div className="max-w-2xl mx-auto mb-8 bg-blue-50 border border-blue-200 rounded-lg p-4 text-blue-700 text-center">
        Sign in to unlock personalized recommendations and save your preferences
      </div>
      <div className="flex justify-center gap-4 mb-12">
        <button
          onClick={() => onStateChange(PageState.SignUp)}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors duration-300">
          Sign Up
        </button>
        <button onClick={() => onStateChange(PageState.SignIn)}
          className="px-6 py-2 border border-blue-600 text-blue-600 rounded-lg hover:bg-blue-50 transition-colors duration-300">
          Sign In
        </button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-7xl mx-auto mb-12">
        {apps.map((app, index) => (
          <div
            key={index}
            className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-all duration-300 group relative h-[120px] overflow-hidden"
          >
            <app.icon className="absolute right-4 bottom-4 text-gray-100 text-6xl" />
            <div className="relative z-10">
              <h2 className="text-xl font-semibold mb-2 text-gray-800 group-hover:opacity-0 transition-opacity duration-300">
                {app.name}
              </h2>
              <p className="text-gray-600 opacity-0 group-hover:opacity-100 transition-opacity duration-300 absolute top-0 left-0">
                {app.description}
              </p>
            </div>
          </div>
        ))}
      </div>

    </div>
  );
}

function SignInForm({ onStateChange }: { onStateChange: (state: PageState) => void }) {
  const [formData, setFormData] = useState({
    name: '',
    password: ''
  });
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    try {
      const response = await fetch( getBackendApiUrl('/users/signin'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData)
      });

      if (!response.ok) {
        const errorData = await response.json();
        setError(errorData.detail || 'An error occurred. Please try again.');
        return;
      }

      router.push('/newssummary');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100">
      <div className="bg-white p-8 rounded-lg shadow-md w-96">
        <h1 className="text-2xl font-bold text-center mb-6">Sign In</h1>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label className="block text-gray-700 text-sm font-bold mb-2">
              User name
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
              disabled={isLoading}
              className="w-full p-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              required
              minLength={3}
              maxLength={20}
            />
          </div>

          <div className="mb-6">
            <label className="block text-gray-700 text-sm font-bold mb-2">
              Password
            </label>
            <input
              type="password"
              value={formData.password}
              onChange={(e) => setFormData(prev => ({ ...prev, password: e.target.value }))}
              disabled={isLoading}
              className="w-full p-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              required
              minLength={4}
              maxLength={20}
            />
          </div>

          <div className="flex gap-4">
            <button
              type="button"
              onClick={() => onStateChange(PageState.AppsSummary)}
              disabled={isLoading}
              className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded hover:bg-gray-50 disabled:bg-gray-100 disabled:text-gray-400"
            >
              Close
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-blue-400 flex items-center justify-center"
            >
              {isLoading ? (
                <BiLoaderAlt className="animate-spin text-xl" />
              ) : (
                'Sign In'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function SignUpForm({ onStateChange }: { onStateChange: (state: PageState) => void }) {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    password: '',
    invitation_code: ''
  });
  const [isLoading, setIsLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    const response = await fetch(getBackendApiUrl('/users/signup'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(formData)
    });

    if (response.ok) {
      setIsSuccess(true);
    } else {
      const errorData = await response.json();
      setError(errorData.detail || 'An error occurred. Please try again.');
    }
    setIsLoading(false);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100">
      <div className="bg-white p-8 rounded-lg shadow-md w-96">
        <h1 className="text-2xl font-bold text-center mb-6">Sign Up</h1>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded">
            {error}
          </div>
        )}

        {isSuccess && (
          <div className="mb-4 p-3 bg-green-50 border border-green-200 text-green-700 rounded">
            An email has been sent to your email address. Please check your inbox to verify your account.
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label className="block text-gray-700 text-sm font-bold mb-2">
              User name
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
              disabled={isLoading || isSuccess}
              className="w-full p-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              required
              minLength={3}
              maxLength={20}
            />
          </div>
          <div className="mb-4">
            <label className="block text-gray-700 text-sm font-bold mb-2">
              Email
            </label>
            <input
              type="text"
              value={formData.email}
              onChange={(e) => setFormData(prev => ({ ...prev, email: e.target.value }))}
              disabled={isLoading || isSuccess}
              className="w-full p-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              required
            />
          </div>
          <div className="mb-4">
            <label className="block text-gray-700 text-sm font-bold mb-2">
              Password
            </label>
            <input
              type="text"
              value={formData.password}
              onChange={(e) => setFormData(prev => ({ ...prev, password: e.target.value }))}
              disabled={isLoading || isSuccess}
              className="w-full p-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              required
            />
          </div>

          <div className="mb-6">
            <label className="block text-gray-700 text-sm font-bold mb-2">
              Invitation Code
            </label>
            <input
              type="text"
              value={formData.invitation_code}
              onChange={(e) => setFormData(prev => ({ ...prev, invitation_code: e.target.value }))}
              disabled={isLoading || isSuccess}
              className="w-full p-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              required
              minLength={4}
              maxLength={50}
            />
          </div>

          <div className="flex gap-4">
            <button
              type="button"
              onClick={() => onStateChange(PageState.AppsSummary)}
              disabled={isLoading}
              className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded hover:bg-gray-50 disabled:bg-gray-100 disabled:text-gray-400"
            >
              Close
            </button>
            <button
              type="submit"
              disabled={isLoading || isSuccess}
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-blue-400 flex items-center justify-center"
            >
              {isLoading ? (
                <BiLoaderAlt className="animate-spin text-xl" />
              ) : (
                'Sign Up'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}