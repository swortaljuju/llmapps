const express = require("express");
const next = require("next");
const { createProxyMiddleware } = require("http-proxy-middleware");

const dev = process.env.NODE_ENV !== "production";
const app = next({ dev });
const handle = app.getRequestHandler();

app.prepare().then(() => {
    const server = express();
    const userSessionMiddleware = function(req, res, next) {
        // Mimic the Next.js request object structure
        const url = new URL(req.url, `http://${req.headers.host}`);
        const pathname = url.pathname;
        const isRoot = pathname === '/';

        // Use req and res to interact with the request
        fetch(`http://localhost:8000/api/py/users/has_valid_session`, {
            method: 'GET',
            headers: {
            'Cookie': req.headers.cookie || '',
            }
        })
        .then(response => response.json())
        .then(responseJson => {
            const valid = responseJson.valid;

            if (valid && isRoot) {
                console.log('User with valid session in root page. redirecting to newssummary');
                res.redirect('/newssummary');
            } else if (!valid && !isRoot) {
                console.log('User with invalid session not in root page. redirecting to root');
                res.redirect('/');
            } else {
                next();
            }
        })
        .catch(err => {
            console.error("Error during session validation:", err);
            res.status(500).send("Internal Server Error");
        });
    };
    // Proxy API requests to FastAPI
    server.use(
        "/api/py",
        userSessionMiddleware,
        createProxyMiddleware({
            target: "http://localhost:8000/api/py", // FastAPI server
            changeOrigin: true,
            // 20 minutes timeout for long api requests containing llm calls
            timeout: 1200000,
            proxyTimeout: 1200000,
        })
    );

    // Let Next.js handle everything else
    server.all('/{*any}', [userSessionMiddleware], (req, res) => {
        return handle(req, res);
    });

    server.listen(3000, () => {
        console.log("> Ready on http://localhost:3000");
    });
});