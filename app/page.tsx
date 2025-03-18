'use client';

import { BiNews } from 'react-icons/bi';
import { BsGraphUp, BsBook } from 'react-icons/bs';
import { MdOutlineRestaurant } from 'react-icons/md';
import { AiOutlineShopping } from 'react-icons/ai';


export default function Home() {
  const apps = [
    {
      name: "News Summary",
      description: "Weekly news summary",
      icon: BiNews
    },
    {
      name: "Stock Summary",
      description: "Weekly stock summary",
      icon: BsGraphUp
    },
    {
      name: "Recipe Recommendation",
      description: "Recommend weekly recipe",
      icon: MdOutlineRestaurant
    },
    {
      name: "Shopping Guide",
      description: "Detailed production comparison and shopping suggestion",
      icon: AiOutlineShopping
    },
    {
      name: "Book Note",
      description: "Generate questions to review the note of a book and further expand some ideas from the book",
      icon: BsBook
    }
  ];
  return (
    <div className="min-h-screen p-8 bg-gray-100">
      <h1 className="text-4xl font-bold text-center mb-8">LLM App Portfolio</h1>
      <div className="max-w-2xl mx-auto mb-8 bg-blue-50 border border-blue-200 rounded-lg p-4 text-blue-700 text-center">
        Sign in to unlock personalized recommendations and save your preferences
      </div>
      <div className="flex justify-center gap-4 mb-12">
        <button className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors duration-300">
          Sign Up
        </button>
        <button className="px-6 py-2 border border-blue-600 text-blue-600 rounded-lg hover:bg-blue-50 transition-colors duration-300">
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