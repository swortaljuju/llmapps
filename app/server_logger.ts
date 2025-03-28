import winston from 'winston';
import 'winston-daily-rotate-file';

const serverLogger = winston.createLogger({
    level: process.env.LOG_LEVEL ,
    format: winston.format.json(),
    defaultMeta: {service: 'user-service'},
    transports: [
        new (winston.transports.DailyRotateFile)({
            dirname: process.env.LOG_DIR,
            filename: 'nextjs-%DATE%.log',
            zippedArchive: true,
            maxSize: '20m',
            maxFiles: '14d',
        }),
    ],
});

// If we're not in production then log to the `console` with the format:
// `${info.level}: ${info.message} JSON.stringify({ ...rest }) `
if (process.env.NODE_ENV !== 'production') {
    serverLogger.add(new winston.transports.Console({
        format: winston.format.simple(),
    }));
}

export default serverLogger;
