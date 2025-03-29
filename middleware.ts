import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export default async function middleware(request: NextRequest) {
    // TODO: Use JWT to verify if session data is valid and not expired.
    const valid = !!request.cookies.get('session_id')?.value;
    const path = request.nextUrl.pathname
    const isRoot = path === '/'
    if (valid && isRoot) {
        logInDev('User with valid session in root page. redirecting to newssummary');
        return NextResponse.redirect(new URL('/newssummary', request.url))
    } else if (!valid && !isRoot) {
        logInDev('User with invalid session not in root page. redirecting to root');
        return NextResponse.redirect(new URL('/', request.url))
    }
    logInDev('no redirect needed');

    return NextResponse.next()
}

function logInDev(message: string) {
    if (process.env.NODE_ENV === 'development') {
        console.log(message);
    }
}

export const config = {
    matcher: ['/', '/newssummary'], // Adjust to your protected routes
}
