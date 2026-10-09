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
 * The flight software's boundary: its input, output and telemetry ports,
 * each with its payload type, size and layout hash, and the functions that
 * move payloads across it. fsw_ports.c is generated for each export.
 */

#ifndef FSW_PORTS_H
#define FSW_PORTS_H

#include <stddef.h>
#include <stdint.h>

/*!
 * @brief An output container's current payload. Some modules initialise an output only when
 * something subscribes to it (cssWlsEst's cssWLSFiltResOutMsg), leaving its pointer NULL; then the
 * container's own copy is the payload, as the simulation recorded it.
 */
#define FSW_OUTPUT_PAYLOAD(container) \
    ((container).payloadPointer != NULL ? (const void *)(container).payloadPointer \
                                        : (const void *)&(container).payload)

/*! @brief The kind of one run of scalar values in a payload. */
typedef enum {
    FSW_LEAF_F64,
    FSW_LEAF_F32,
    FSW_LEAF_I8,
    FSW_LEAF_U8,
    FSW_LEAF_I16,
    FSW_LEAF_U16,
    FSW_LEAF_I32,
    FSW_LEAF_U32,
    FSW_LEAF_I64,
    FSW_LEAF_U64
} FswLeafKind;

/*! @brief A run of `count` scalars of one kind at a byte offset; padding is never part of a leaf. */
typedef struct {
    uint32_t offset;
    uint32_t count;
    FswLeafKind kind;
    const char *name;
} FswLeaf;

/*! @brief One message crossing the boundary. */
typedef struct {
    const char *name;
    const char *messageType;
    uint32_t size;
    const char *layoutHash;
    const FswLeaf *leaves;
    uint32_t leafCount;
    /*! Writes an input port's payload (inputs only, NULL otherwise). */
    void (*write)(const void *payload, uint64_t timeNs);
    /*! Copies the current payload out (outputs and telemetry); returns 1 when it has been written, else 0. */
    int (*read)(void *payload);
} FswPort;

extern const FswPort fsw_input_ports[];
extern const size_t fsw_input_port_count;
extern const FswPort fsw_output_ports[];
extern const size_t fsw_output_port_count;
extern const FswPort fsw_telemetry_ports[];
extern const size_t fsw_telemetry_port_count;

/*! @brief The configuration hash of the scenario this export was made from (64 hex digits). */
extern const char fsw_config_digest[];
/*! @brief The spacecraft the flight software belongs to. */
extern const char fsw_spacecraft_name[];

/*!
 * @brief Compares two payloads leaf by leaf.
 * @param port the port whose payload type both are
 * @param actual the payload to check
 * @param expected the reference payload
 * @param rtol relative tolerance on floating-point values
 * @param atol absolute tolerance on floating-point values
 * @param maxAbsError set to the largest absolute difference found (may be NULL)
 * @return 1 when every value is within tolerance (integers: equal), else 0
 */
int fsw_payloads_match(const FswPort *port, const void *actual, const void *expected, double rtol, double atol,
                       double *maxAbsError);

#endif
