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
 * Running the exported flight software (fsw_scheduler.c, generated):
 *
 *   fsw_init();                 parameters, SelfInit, constants, connections
 *   (write the inputs that were written at Reset)
 *   fsw_reset(0);               Reset of every module, in order
 *   each step at time t:        write the inputs, then fsw_step(t), then read the outputs
 *
 * This is the order Basilisk runs the same modules in: InitializeSimulation()
 * (SelfInit, then Reset) and one task step per call.
 */

#ifndef FSW_SCHEDULER_H
#define FSW_SCHEDULER_H

#include <stdint.h>

/*! @brief The step of the one rate group, in nanoseconds. */
extern const uint64_t fsw_rate_ns;

/*! @brief Sets every parameter, calls each module's SelfInit, writes the constants and connects the messages. */
void fsw_init(void);

/*!
 * @brief Calls each module's Reset, in execution order.
 * @param timeNs the simulation time of the reset
 */
void fsw_reset(uint64_t timeNs);

/*!
 * @brief Runs every rate group due at this time, in execution order.
 * @param timeNs the simulation time of the step
 */
void fsw_step(uint64_t timeNs);

#endif
