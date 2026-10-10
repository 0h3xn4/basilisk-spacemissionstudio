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
 * Trace files: a recorded sequence of payloads for a list of ports.
 *
 * Little-endian, as the machine that wrote it:
 *   char     magic[8]      "SMSFTRC1"
 *   uint32   kind          1 = inputs, 2 = outputs and telemetry
 *   uint32   portCount
 *   uint32   recordCount
 *   per port: uint32 size, char layoutHash[16]
 *   per record: uint64 timeNs, uint8 written[portCount], then each port's payload
 * An input trace's first record is the state at Reset (time 0); the rest are steps.
 */

#ifndef FSW_TRACE_H
#define FSW_TRACE_H

#include <stdint.h>
#include <stdio.h>

#include "fsw_ports.h"

#define FSW_TRACE_INPUTS 1u
#define FSW_TRACE_OUTPUTS 2u

/*! @brief An open trace file. */
typedef struct {
    FILE *file;
    uint32_t kind;
    uint32_t portCount;
    uint32_t recordCount;
} FswTrace;

/*!
 * @brief Opens a trace and checks it against the compiled ports.
 * @param trace the trace to fill in
 * @param path the file to read
 * @param kind FSW_TRACE_INPUTS or FSW_TRACE_OUTPUTS
 * @param ports the ports it must match, in order
 * @param portCount how many
 * @param error a buffer for the reason when it does not match
 * @param errorSize the buffer's size
 * @return 0 on success, -1 with the reason in error
 */
int fsw_trace_open(FswTrace *trace, const char *path, uint32_t kind, const FswPort *const *ports,
                   uint32_t portCount, char *error, size_t errorSize);

/*!
 * @brief Reads the next record.
 * @param trace the open trace
 * @param timeNs set to the record's time
 * @param written one flag per port
 * @param payloads one buffer per port, each at least that port's size
 * @param ports the trace's ports
 * @return 1 when a record was read, 0 at the end, -1 on a short read
 */
int fsw_trace_read(FswTrace *trace, uint64_t *timeNs, uint8_t *written, void *const *payloads,
                   const FswPort *const *ports);

/*!
 * @brief Creates a trace file and writes its header.
 * @param trace the trace to fill in
 * @param path the file to create
 * @param kind FSW_TRACE_INPUTS or FSW_TRACE_OUTPUTS
 * @param ports the ports, in order
 * @param portCount how many
 * @param recordCount how many records will be written
 * @return 0 on success, -1 when the file cannot be written
 */
int fsw_trace_create(FswTrace *trace, const char *path, uint32_t kind, const FswPort *const *ports,
                     uint32_t portCount, uint32_t recordCount);

/*!
 * @brief Appends one record.
 * @param trace the trace being written
 * @param timeNs the record's time
 * @param written one flag per port
 * @param payloads one payload per port
 * @param ports the trace's ports
 * @return 0 on success, -1 on a write error
 */
int fsw_trace_write(FswTrace *trace, uint64_t timeNs, const uint8_t *written, const void *const *payloads,
                    const FswPort *const *ports);

/*!
 * @brief Closes the file.
 * @param trace the trace
 */
void fsw_trace_close(FswTrace *trace);

#endif
