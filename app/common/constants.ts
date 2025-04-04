import { BiNews } from 'react-icons/bi';
import { BsGraphUp, BsBook } from 'react-icons/bs';
import { MdOutlineRestaurant } from 'react-icons/md';
import { AiOutlineShopping } from 'react-icons/ai';

export const apps = [
    {
        name: "News Summary",
        description: "Weekly news summary",
        icon: BiNews,
        launched: true,
        route: "/newssummary"
    },
    {
        name: "Stock Summary (Coming Soon)",
        description: "Weekly stock summary",
        icon: BsGraphUp,
        launched: false,
        route: "/stock"
    },
    {
        name: "Recipe Recommendation (Coming Soon)",
        description: "Recommend weekly recipe",
        icon: MdOutlineRestaurant,
        launched: false,
        route: "/menurecipe"
    },
    {
        name: "Shopping Guide (Coming Soon)",
        description: "Detailed production comparison and shopping suggestion",
        icon: AiOutlineShopping,
        launched: false,
        route: "/shoppingguide"
    },
    {
        name: "Knowledge Assistant (Coming Soon)",
        description: "Generate questions to review the note of any knowledge from a book or an open course or a podcast and further expand some ideas from the book",
        icon: BsBook,
        launched: false,
        route: "/booknotes"
    }
];