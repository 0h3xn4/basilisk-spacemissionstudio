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

/* Logging and error hooks of the exported flight software (fsw_log.c). */

#ifndef FSW_LOG_H
#define FSW_LOG_H

#include "architecture/utilities/bskLogging.h"

/*! @brief Called by _bskError() before the process exits; must not rely on returning. */
typedef void (*FswErrorHandler)(const char *message);

/*!
 * @brief Sets the function _bskError() calls before exiting.
 * @param handler the handler, or NULL for none
 */
void fsw_set_error_handler(FswErrorHandler handler);

/*!
 * @brief Sets the level below which _bskLog() stays silent.
 * @param level the lowest level that is printed
 */
void fsw_set_log_level(logLevel_t level);

#endif
