import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export async function middleware(request: NextRequest) {
    const sessionId = request.cookies.get('session_id')?.value;
    let valid = false;
    if (sessionId) {
        const res = await fetch(`${process.env.DOMAIN}/users/hasValidSession/${sessionId}`, {
            method: 'GET'
        });

        valid = (await res.json()).valid
    }
    const path = request.nextUrl.pathname
    const isRoot = path === '/'
    if (valid && isRoot) {
        return NextResponse.redirect(new URL('/newssummary', process.env.DOMAIN))
    } else if (!valid && !isRoot) {
        return NextResponse.redirect(new URL('/', process.env.DOMAIN))
    }

    return NextResponse.next()
}

export const config = {
    matcher: ['/:path*'], // Adjust to your protected routes
}
