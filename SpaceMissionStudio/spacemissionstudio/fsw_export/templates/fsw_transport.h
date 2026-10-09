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
 * The byte stream the SIL contract runs over (SIL_CONTRACT.md). The protocol
 * (fsw_sil.c) only sends and receives bytes through these three functions, so
 * a serial line or a UDP link replaces fsw_transport_socket.c without touching
 * it: fill in an FswTransport with your own functions.
 */

#ifndef FSW_TRANSPORT_H
#define FSW_TRANSPORT_H

#include <stddef.h>

/*! @brief A connected, reliable, ordered byte stream. */
typedef struct FswTransport {
    /*! Sends all `size` bytes; returns 0, or -1 when the link failed. */
    int (*send)(struct FswTransport *transport, const void *data, size_t size);
    /*! Receives exactly `size` bytes, waiting as long as it takes; returns 0, or -1 when the link closed or failed. */
    int (*receive)(struct FswTransport *transport, void *data, size_t size);
    /*! Closes the link. */
    void (*close)(struct FswTransport *transport);
    /*! The implementation's own state (fsw_transport_socket.c: the socket). */
    long long handle;
} FswTransport;

/*!
 * @brief Connects to the simulation's address.
 * @param transport the transport to fill in
 * @param address "unix:<path>" (Linux, macOS) or "tcp:127.0.0.1:<port>" (every platform)
 * @param error a buffer for the reason when it fails
 * @param errorSize the buffer's size
 * @return 0 when connected, -1 with the reason in error
 */
int fsw_transport_connect(FswTransport *transport, const char *address, char *error, size_t errorSize);

#endif
