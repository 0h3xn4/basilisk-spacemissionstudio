/*
 ISC License

 Copyright (c) 2026, Autonomous Vehicle Systems Lab, University of Colorado at Boulder

 Permission to use, copy, modify, and/or distribute this software for any
 purpose with or without fee is hereby granted, provided that the above
 copyright notice and this permission notice appear in all copies.

 THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
 ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
 OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
*/

/*
 * The C side of Basilisk's logging API (architecture/utilities/bskLogging.h),
 * for flight software built without Basilisk. Basilisk implements these
 * functions in C++ (bskLogging.cpp); the modules only ever call them through
 * this C interface, with their configuration's bskLogger pointer, which
 * Basilisk leaves NULL. A NULL logger logs at the default level.
 *
 * Errors stop the flight software, as in Basilisk, where they throw a
 * BasiliskError: _bskError(), and _bskLog() at level BSK_ERROR, print the
 * message, call the handler set with fsw_set_error_handler() (the SIL
 * harness reports the error to the simulation there), then exit with status
 * 70. _bskLogNoThrow() returns -1 at level BSK_ERROR instead, and does
 * nothing for a NULL logger, as Basilisk's does.
 */

#include <stdio.h>
#include <stdlib.h>

#include "architecture/utilities/bskLogging.h"
#include "fsw_log.h"

struct BSKLogger {
    logLevel_t level;
};

logLevel_t LogLevel = BSK_INFORMATION;
static struct BSKLogger defaultLogger = {BSK_INFORMATION};
static FswErrorHandler errorHandler = NULL;

static const char *levelName(logLevel_t level)
{
    switch (level) {
    case BSK_DEBUG: return "DEBUG";
    case BSK_INFORMATION: return "INFORMATION";
    case BSK_WARNING: return "WARNING";
    case BSK_ERROR: return "ERROR";
    default: return "SILENT";
    }
}

void fsw_set_error_handler(FswErrorHandler handler)
{
    errorHandler = handler;
}

void fsw_set_log_level(logLevel_t level)
{
    defaultLogger.level = level;
    LogLevel = level;
}

void printDefaultLogLevel(void)
{
    printf("Default logging level: %s\n", levelName(LogLevel));
}

BSKLogger *_BSKLogger(void)
{
    return &defaultLogger;
}

void _BSKLogger_d(BSKLogger *logger)
{
    (void)logger;
}

void _printLogLevel(BSKLogger *logger)
{
    printf("Current logging level: %s\n", levelName((logger ? logger : &defaultLogger)->level));
}

void _setLogLevel(BSKLogger *logger, logLevel_t level)
{
    (logger ? logger : &defaultLogger)->level = level;
}

void _bskLog(BSKLogger *logger, logLevel_t level, const char *info)
{
    if (level == BSK_ERROR) {
        _bskError(logger, info);
    }
    if (level >= (logger ? logger : &defaultLogger)->level) {
        fprintf(stderr, "BSK_%s: %s\n", levelName(level), info);
    }
}

int _bskLogNoThrow(BSKLogger *logger, logLevel_t level, const char *info)
{
    if (logger == NULL) {
        return 0;
    }
    if (level == BSK_ERROR) {
        return -1;
    }
    _bskLog(logger, level, info);
    return 0;
}

void _bskError(BSKLogger *logger, const char *info)
{
    (void)logger;
    fprintf(stderr, "BSK_ERROR: %s\n", info != NULL ? info : "");
    fflush(stderr);
    if (errorHandler != NULL) {
        errorHandler(info != NULL ? info : "");
    }
    exit(70);
}
