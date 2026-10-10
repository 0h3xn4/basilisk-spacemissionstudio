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
 * The flight-software side of the SIL contract, version 1 (SIL_CONTRACT.md):
 * HELLO with the ports, then RESET and one STEP per simulation step, each
 * answered, until BYE. It drives whatever implements fsw_scheduler.h and
 * fsw_ports.h: the exported Basilisk modules, or your own code through the
 * adapter (adapter/, ADAPTER_GUIDE.md).
 */

#ifndef FSW_SIL_H
#define FSW_SIL_H

#include <stddef.h>
#include <stdint.h>

#include "fsw_transport.h"

/*! @brief The contract version this harness speaks. */
#define FSW_SIL_CONTRACT_VERSION 1u
/*! @brief The environment variable the simulation passes its session token in. */
#define FSW_SIL_TOKEN_ENV "SMS_SIL_TOKEN"

/*! @brief Return values of fsw_sil_serve(). */
enum {
    FSW_SIL_DONE = 0,          /*!< the simulation ended the run with BYE */
    FSW_SIL_REFUSED = 3,       /*!< the simulation sent ERROR (e.g. the ports do not match) */
    FSW_SIL_LINK_FAILED = 4,   /*!< the link closed or failed */
    FSW_SIL_PROTOCOL_ERROR = 5 /*!< a frame broke the contract; ERROR was sent */
};

/*!
 * @brief Serves one session: sends HELLO, then answers every frame until BYE, ERROR or a failure.
 * @param transport a connected transport
 * @param token the 32-character session token the simulation gave this process
 * @param error a buffer for the reason when it does not end with BYE
 * @param errorSize the buffer's size
 * @return one of the FSW_SIL_ values
 */
int fsw_sil_serve(FswTransport *transport, const char *token, char *error, size_t errorSize);

/*!
 * @brief Sends an ERROR frame with this message on the session being served, if any. For a flight
 * software error handler (fsw_log.h's fsw_set_error_handler) so the simulation sees why it stopped.
 * @param message the reason
 */
void fsw_sil_report_error(const char *message);

#endif
